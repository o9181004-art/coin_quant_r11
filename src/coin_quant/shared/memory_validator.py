#!/usr/bin/env python3
"""
Memory Layer Validation System for Coin Quant R11

Implements integrity checks, quarantine management, and debug bundle export.
Provides deterministic replay and state reconstruction capabilities.
"""

import json
import time
import logging
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union
from dataclasses import dataclass
from enum import Enum

from coin_quant.shared.io import AtomicWriter, AtomicReader
from coin_quant.shared.paths import get_data_dir
from coin_quant.shared.time import utc_now_seconds

logger = logging.getLogger(__name__)


class IntegrityStatus(Enum):
    """Memory integrity status"""
    VALID = "valid"
    DEGRADED = "degraded"
    CORRUPTED = "corrupted"
    QUARANTINED = "quarantined"


@dataclass
class IntegrityReport:
    """Memory integrity report"""
    status: IntegrityStatus
    timestamp: float
    errors: List[str]
    warnings: List[str]
    merkle_root: Optional[str]
    chain_length: int
    last_valid_snapshot: Optional[str]
    quarantine_active: bool
    remediation_steps: List[str]


class MemoryValidator:
    """Memory layer integrity validator"""
    
    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or get_data_dir() / "memory"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.writer = AtomicWriter()
        self.reader = AtomicReader()
        
        # File paths
        self.event_chain_file = self.data_dir / "event_chain.ndjson"
        self.snapshot_store_file = self.data_dir / "snapshot_store.json"
        self.hash_chain_file = self.data_dir / "hash_chain.json"
        self.integrity_file = self.data_dir / "integrity.json"
        
        logger.info(f"MemoryValidator initialized: {self.data_dir}")
    
    def validate_integrity(self) -> Dict[str, Any]:
        """Perform comprehensive integrity validation"""
        errors = []
        warnings = []
        remediation_steps = []
        
        # Check file existence
        if not self.event_chain_file.exists():
            errors.append("Event chain file missing")
            remediation_steps.append("Restart services to recreate event chain")
        
        if not self.snapshot_store_file.exists():
            errors.append("Snapshot store file missing")
            remediation_steps.append("Restart services to recreate snapshot store")
        
        if not self.hash_chain_file.exists():
            errors.append("Hash chain file missing")
            remediation_steps.append("Restart services to recreate hash chain")
        
        if errors:
            report = {
                "status": IntegrityStatus.CORRUPTED.value,
                "timestamp": utc_now_seconds(),
                "errors": errors,
                "warnings": warnings,
                "merkle_root": None,
                "chain_length": 0,
                "last_valid_snapshot": None,
                "quarantine_active": True,
                "remediation_steps": remediation_steps
            }
            self._save_integrity_report_dict(report)
            return report
        
        # Validate hash chain
        hash_chain_valid, hash_errors = self._validate_hash_chain()
        if not hash_chain_valid:
            errors.extend(hash_errors)
            remediation_steps.append("Perform replay from last valid snapshot")
        
        # Validate event chain
        event_chain_valid, event_errors = self._validate_event_chain()
        if not event_chain_valid:
            errors.extend(event_errors)
            remediation_steps.append("Reconstruct event chain from snapshots")
        
        # Validate snapshot store
        snapshot_valid, snapshot_errors = self._validate_snapshot_store()
        if not snapshot_valid:
            errors.extend(snapshot_errors)
            remediation_steps.append("Recreate snapshot store from events")
        
        # Determine overall status
        if errors:
            status = IntegrityStatus.CORRUPTED.value
        elif warnings:
            status = IntegrityStatus.DEGRADED.value
        else:
            status = IntegrityStatus.VALID.value
        
        # Get chain metrics
        merkle_root = self._get_latest_merkle_root()
        chain_length = self._get_chain_length()
        last_valid_snapshot = self._get_last_valid_snapshot()
        
        report = {
            "status": status,
            "timestamp": utc_now_seconds(),
            "errors": errors,
            "warnings": warnings,
            "merkle_root": merkle_root,
            "chain_length": chain_length,
            "last_valid_snapshot": last_valid_snapshot,
            "quarantine_active": status in [IntegrityStatus.CORRUPTED.value, IntegrityStatus.QUARANTINED.value],
            "remediation_steps": remediation_steps
        }
        
        # Save integrity report
        self._save_integrity_report_dict(report)
        
        return report
    
    def _validate_hash_chain(self) -> Tuple[bool, List[str]]:
        """Validate hash chain integrity"""
        errors = []
        
        try:
            chain_data = self.reader.read_json(self.hash_chain_file)
            if not chain_data or "chain" not in chain_data:
                errors.append("Hash chain data missing or malformed")
                return False, errors
            
            chain = chain_data["chain"]
            if not isinstance(chain, list):
                errors.append("Hash chain is not a list")
                return False, errors
            
            # Validate each block
            for i, block in enumerate(chain):
                if not self._validate_block(block, i):
                    errors.append(f"Block {i} validation failed")
            
            # Validate chain continuity
            for i in range(1, len(chain)):
                current_block = chain[i]
                previous_block = chain[i-1]
                
                if current_block.get("previous_hash") != previous_block.get("hash"):
                    errors.append(f"Chain continuity broken at block {i}")
            
            return len(errors) == 0, errors
            
        except Exception as e:
            errors.append(f"Hash chain validation error: {str(e)}")
            return False, errors
    
    def _validate_block(self, block: Dict[str, Any], index: int) -> bool:
        """Validate individual block"""
        required_fields = ["index", "timestamp", "data", "previous_hash", "hash"]
        
        for field in required_fields:
            if field not in block:
                logger.error(f"Block {index} missing field: {field}")
                return False
        
        # Validate hash
        expected_hash = self._calculate_block_hash(
            block["index"],
            block["timestamp"],
            block["data"],
            block["previous_hash"]
        )
        
        if block["hash"] != expected_hash:
            logger.error(f"Block {index} hash mismatch")
            return False
        
        return True
    
    def _validate_event_chain(self) -> Tuple[bool, List[str]]:
        """Validate event chain integrity"""
        errors = []
        
        try:
            if not self.event_chain_file.exists():
                errors.append("Event chain file does not exist")
                return False, errors
            
            # Read events line by line
            events = []
            with open(self.event_chain_file, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        event = json.loads(line)
                        events.append(event)
                    except json.JSONDecodeError as e:
                        errors.append(f"Event chain line {line_num} JSON error: {str(e)}")
            
            # Validate event structure
            for i, event in enumerate(events):
                if not self._validate_event(event, i):
                    errors.append(f"Event {i} validation failed")
            
            return len(errors) == 0, errors
            
        except Exception as e:
            errors.append(f"Event chain validation error: {str(e)}")
            return False, errors
    
    def _validate_event(self, event: Dict[str, Any], index: int) -> bool:
        """Validate individual event"""
        required_fields = ["event_id", "timestamp", "event_type", "source", "data"]
        
        for field in required_fields:
            if field not in event:
                logger.error(f"Event {index} missing field: {field}")
                return False
        
        # Validate timestamp
        if not isinstance(event["timestamp"], (int, float)):
            logger.error(f"Event {index} invalid timestamp")
            return False
        
        return True
    
    def _validate_snapshot_store(self) -> Tuple[bool, List[str]]:
        """Validate snapshot store integrity"""
        errors = []
        
        try:
            snapshots = self.reader.read_json(self.snapshot_store_file)
            if not snapshots:
                errors.append("Snapshot store is empty")
                return False, errors
            
            if not isinstance(snapshots, dict):
                errors.append("Snapshot store is not a dictionary")
                return False, errors
            
            # Validate each snapshot
            for snapshot_id, snapshot_data in snapshots.items():
                if not self._validate_snapshot(snapshot_data, snapshot_id):
                    errors.append(f"Snapshot {snapshot_id} validation failed")
            
            return len(errors) == 0, errors
            
        except Exception as e:
            errors.append(f"Snapshot store validation error: {str(e)}")
            return False, errors
    
    def _validate_snapshot(self, snapshot: Dict[str, Any], snapshot_id: str) -> bool:
        """Validate individual snapshot"""
        required_fields = ["timestamp", "data"]
        
        for field in required_fields:
            if field not in snapshot:
                logger.error(f"Snapshot {snapshot_id} missing field: {field}")
                return False
        
        return True
    
    def _calculate_block_hash(self, index: int, timestamp: float, data: Any, previous_hash: str) -> str:
        """Calculate block hash"""
        block_string = json.dumps({
            "index": index,
            "timestamp": timestamp,
            "data": data,
            "previous_hash": previous_hash
        }, sort_keys=True).encode('utf-8')
        return hashlib.sha256(block_string).hexdigest()
    
    def _get_latest_merkle_root(self) -> Optional[str]:
        """Get latest Merkle root from hash chain"""
        try:
            chain_data = self.reader.read_json(self.hash_chain_file)
            if chain_data and "merkle_root" in chain_data:
                return chain_data["merkle_root"]
        except Exception:
            pass
        return None
    
    def _get_chain_length(self) -> int:
        """Get hash chain length"""
        try:
            chain_data = self.reader.read_json(self.hash_chain_file)
            if chain_data and "chain" in chain_data:
                return len(chain_data["chain"])
        except Exception:
            pass
        return 0
    
    def _get_last_valid_snapshot(self) -> Optional[str]:
        """Get last valid snapshot ID"""
        try:
            snapshots = self.reader.read_json(self.snapshot_store_file)
            if snapshots and isinstance(snapshots, dict):
                # Find snapshot with latest timestamp
                latest_id = max(snapshots.keys(), 
                              key=lambda k: snapshots[k].get("timestamp", 0))
                return latest_id
        except Exception:
            pass
        return None
    
    def _save_integrity_report(self, report: IntegrityReport) -> None:
        """Save integrity report"""
        report_data = {
            "status": report.status.value,
            "timestamp": report.timestamp,
            "errors": report.errors,
            "warnings": report.warnings,
            "merkle_root": report.merkle_root,
            "chain_length": report.chain_length,
            "last_valid_snapshot": report.last_valid_snapshot,
            "quarantine_active": report.quarantine_active,
            "remediation_steps": report.remediation_steps
        }
        
        self.writer.write_json(self.integrity_file, report_data)
    
    def _save_integrity_report_dict(self, report: Dict[str, Any]) -> None:
        """Save integrity report from dictionary"""
        self.writer.write_json(self.integrity_file, report)
    
    def quarantine_symbol(self, symbol: str, reason: str) -> bool:
        """Quarantine a symbol due to integrity issues"""
        quarantine_file = self.data_dir / "quarantine.json"
        
        try:
            quarantine_data = self.reader.read_json(quarantine_file, default={})
            quarantine_data[symbol] = {
                "timestamp": utc_now_seconds(),
                "reason": reason,
                "status": "quarantined"
            }
            
            success = self.writer.write_json(quarantine_file, quarantine_data)
            if success:
                logger.warning(f"Symbol {symbol} quarantined: {reason}")
            return success
            
        except Exception as e:
            logger.error(f"Failed to quarantine symbol {symbol}: {str(e)}")
            return False
    
    def release_quarantine(self, symbol: str) -> bool:
        """Release symbol from quarantine"""
        quarantine_file = self.data_dir / "quarantine.json"
        
        try:
            quarantine_data = self.reader.read_json(quarantine_file, default={})
            if symbol in quarantine_data:
                del quarantine_data[symbol]
                success = self.writer.write_json(quarantine_file, quarantine_data)
                if success:
                    logger.info(f"Symbol {symbol} released from quarantine")
                return success
            return True
            
        except Exception as e:
            logger.error(f"Failed to release quarantine for symbol {symbol}: {str(e)}")
            return False
    
    def get_quarantined_symbols(self) -> List[str]:
        """Get list of quarantined symbols"""
        quarantine_file = self.data_dir / "quarantine.json"
        
        try:
            quarantine_data = self.reader.read_json(quarantine_file, default={})
            return list(quarantine_data.keys())
        except Exception:
            return []
    
    def export_debug_bundle(self, output_dir: Optional[Path] = None) -> Path:
        """Export debug bundle for troubleshooting"""
        if not output_dir:
            output_dir = get_data_dir() / "debug_bundles" / f"bundle_{int(time.time())}"
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Export integrity report
        integrity_report = self.validate_integrity()
        self.writer.write_json(output_dir / "integrity_report.json", integrity_report)
        
        # Export recent events (last 100)
        try:
            events = []
            if self.event_chain_file.exists():
                with open(self.event_chain_file, 'r') as f:
                    lines = f.readlines()
                    for line in lines[-100:]:  # Last 100 events
                        line = line.strip()
                        if line:
                            try:
                                events.append(json.loads(line))
                            except json.JSONDecodeError:
                                continue
            
            self.writer.write_json(output_dir / "recent_events.json", events)
        except Exception as e:
            logger.error(f"Failed to export recent events: {str(e)}")
        
        # Export snapshots
        try:
            snapshots = self.reader.read_json(self.snapshot_store_file, default={})
            self.writer.write_json(output_dir / "snapshots.json", snapshots)
        except Exception as e:
            logger.error(f"Failed to export snapshots: {str(e)}")
        
        # Export hash chain
        try:
            hash_chain = self.reader.read_json(self.hash_chain_file, default={})
            self.writer.write_json(output_dir / "hash_chain.json", hash_chain)
        except Exception as e:
            logger.error(f"Failed to export hash chain: {str(e)}")
        
        # Export quarantine status
        try:
            quarantine_data = self.reader.read_json(self.data_dir / "quarantine.json", default={})
            self.writer.write_json(output_dir / "quarantine.json", quarantine_data)
        except Exception as e:
            logger.error(f"Failed to export quarantine data: {str(e)}")
        
        logger.info(f"Debug bundle exported to: {output_dir}")
        return output_dir
    
    def replay_from_snapshot(self, snapshot_id: Optional[str] = None) -> Dict[str, Any]:
        """Replay events from snapshot or beginning"""
        try:
            if snapshot_id:
                # Replay from specific snapshot
                snapshots = self.reader.read_json(self.snapshot_store_file, default={})
                if snapshot_id not in snapshots:
                    raise ValueError(f"Snapshot {snapshot_id} not found")
                
                base_state = snapshots[snapshot_id]["data"]
                logger.info(f"Replaying from snapshot {snapshot_id}")
            else:
                # Replay from beginning
                base_state = {}
                logger.info("Replaying from beginning")
            
            # Apply events after snapshot
            events = []
            if self.event_chain_file.exists():
                with open(self.event_chain_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                event = json.loads(line)
                                events.append(event)
                            except json.JSONDecodeError:
                                continue
            
            # Apply events to state
            current_state = base_state.copy()
            for event in events:
                current_state = self._apply_event_to_state(current_state, event)
            
            logger.info(f"Replay completed: {len(events)} events applied")
            return current_state
            
        except Exception as e:
            logger.error(f"Replay failed: {str(e)}")
            raise
    
    def _apply_event_to_state(self, state: Dict[str, Any], event: Dict[str, Any]) -> Dict[str, Any]:
        """Apply event to state (simplified implementation)"""
        # This is a simplified implementation
        # In a real system, this would be more sophisticated
        event_type = event.get("event_type", "")
        
        if event_type == "order_executed":
            # Update positions
            symbol = event.get("data", {}).get("symbol", "")
            if symbol:
                if "positions" not in state:
                    state["positions"] = {}
                state["positions"][symbol] = event.get("data", {})
        
        elif event_type == "signal_generated":
            # Update signals
            symbol = event.get("data", {}).get("symbol", "")
            if symbol:
                if "signals" not in state:
                    state["signals"] = {}
                state["signals"][symbol] = event.get("data", {})
        
        return state


# Global memory validator instance
memory_validator = MemoryValidator()


def get_memory_validator() -> MemoryValidator:
    """Get global memory validator instance"""
    return memory_validator
