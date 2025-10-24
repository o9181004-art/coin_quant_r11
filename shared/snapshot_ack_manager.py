#!/usr/bin/env python3
"""
Snapshot ACK Manager
Implements read/write handshake with ACK timestamps
Writers must atomic-write with updated_ts
Readers must publish last_read_ts to confirm consumption
"""

import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Optional

from .atomic_io import atomic_write
from .path_registry import get_absolute_path


@dataclass
class SnapshotAck:
    """Snapshot acknowledgment"""
    reader_service: str
    snapshot_type: str  # 'positions', 'account', 'databus'
    last_read_ts: float
    snapshot_ts: float
    read_at: float
    acknowledged: bool


class SnapshotAckManager:
    """
    Manages snapshot read/write handshakes
    Ensures readers confirm they consumed latest snapshots
    """
    
    def __init__(self):
        self.logger = logging.getLogger('SnapshotACK')
        self.acks_path = get_absolute_path('shared_data') / 'snapshot_acks.json'
        self.acks_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.acks: Dict[str, SnapshotAck] = {}
        self._load_acks()
    
    def _load_acks(self):
        """Load ACKs from file"""
        if self.acks_path.exists():
            try:
                with open(self.acks_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                for key, ack_data in data.items():
                    self.acks[key] = SnapshotAck(**ack_data)
            except Exception as e:
                self.logger.error(f"Failed to load ACKs: {e}")
    
    def _save_acks(self):
        """Save ACKs to file"""
        try:
            data = {
                key: asdict(ack) for key, ack in self.acks.items()
            }
            atomic_write(self.acks_path, json.dumps(data, indent=2))
        except Exception as e:
            self.logger.error(f"Failed to save ACKs: {e}")
    
    def publish_read_ack(
        self, 
        reader_service: str, 
        snapshot_type: str,
        snapshot_ts: float
    ):
        """
        Publish that a service has read a snapshot
        
        Args:
            reader_service: Name of the service (e.g., 'trader')
            snapshot_type: Type of snapshot (e.g., 'positions')
            snapshot_ts: Timestamp from the snapshot that was read
        """
        key = f"{reader_service}.{snapshot_type}"
        
        ack = SnapshotAck(
            reader_service=reader_service,
            snapshot_type=snapshot_type,
            last_read_ts=time.time(),
            snapshot_ts=snapshot_ts,
            read_at=time.time(),
            acknowledged=True
        )
        
        self.acks[key] = ack
        self._save_acks()
        
        self.logger.info(
            f"ACK: {reader_service} read {snapshot_type} snapshot (ts={snapshot_ts:.2f})"
        )
    
    def get_read_ack(
        self, 
        reader_service: str, 
        snapshot_type: str
    ) -> Optional[SnapshotAck]:
        """Get ACK for a specific service and snapshot type"""
        key = f"{reader_service}.{snapshot_type}"
        return self.acks.get(key)
    
    def is_snapshot_consumed(
        self, 
        reader_service: str, 
        snapshot_type: str,
        snapshot_ts: float,
        max_age_seconds: float = 60.0
    ) -> bool:
        """
        Check if a snapshot has been consumed by a service
        
        Args:
            reader_service: Name of the service
            snapshot_type: Type of snapshot
            snapshot_ts: Timestamp of the snapshot to check
            max_age_seconds: Maximum age for ACK to be considered valid
        
        Returns:
            True if snapshot was consumed within max_age_seconds
        """
        ack = self.get_read_ack(reader_service, snapshot_type)
        
        if not ack or not ack.acknowledged:
            return False
        
        # Check if ACK is for this snapshot or newer
        if ack.snapshot_ts < snapshot_ts:
            return False
        
        # Check if ACK is not too old
        age = time.time() - ack.read_at
        if age > max_age_seconds:
            return False
        
        return True
    
    def get_all_acks(self) -> Dict[str, SnapshotAck]:
        """Get all ACKs"""
        return self.acks.copy()
    
    def get_ack_summary(self) -> Dict[str, Dict]:
        """Get summary of all ACKs for UI display"""
        summary = {}
        
        for key, ack in self.acks.items():
            age = time.time() - ack.read_at
            status = "ok" if age < 60 else "stale"
            
            summary[key] = {
                "reader": ack.reader_service,
                "type": ack.snapshot_type,
                "snapshot_ts": ack.snapshot_ts,
                "read_at": ack.read_at,
                "age_seconds": age,
                "status": status,
                "acknowledged": ack.acknowledged
            }
        
        return summary


# Global instance
_ack_manager = SnapshotAckManager()


def publish_read_ack(reader_service: str, snapshot_type: str, snapshot_ts: float):
    """Publish a read ACK"""
    _ack_manager.publish_read_ack(reader_service, snapshot_type, snapshot_ts)


def get_read_ack(reader_service: str, snapshot_type: str) -> Optional[SnapshotAck]:
    """Get a read ACK"""
    return _ack_manager.get_read_ack(reader_service, snapshot_type)


def is_snapshot_consumed(
    reader_service: str, 
    snapshot_type: str,
    snapshot_ts: float,
    max_age_seconds: float = 60.0
) -> bool:
    """Check if snapshot was consumed"""
    return _ack_manager.is_snapshot_consumed(
        reader_service, snapshot_type, snapshot_ts, max_age_seconds
    )


def get_ack_summary() -> Dict[str, Dict]:
    """Get ACK summary"""
    return _ack_manager.get_ack_summary()

