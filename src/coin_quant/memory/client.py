"""
Memory Layer - Memory Client

Single façade for all memory layer operations.
"""

import time
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from .event_chain import EventChain
from .snapshot_store import SnapshotStore
from .hash_chain import HashChain
from .types import MemoryStatus, EventRecord, SnapshotRecord, ChainVerificationResult, DebugBundle
from coin_quant.shared.time import utc_now_seconds


class MemoryClient:
    """Single façade for all memory layer operations"""
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.event_chain = EventChain(data_dir)
        self.snapshot_store = SnapshotStore(data_dir)
        self.hash_chain = HashChain(data_dir)
    
    def append_event(self, event_type: str, data: Dict[str, Any], 
                    source: str = "unknown") -> bool:
        """
        Append event to chain.
        
        Args:
            event_type: Type of event
            data: Event data
            source: Source of event
            
        Returns:
            True if appended successfully, False otherwise
        """
        return self.event_chain.append_event(event_type, data, source)
    
    def get_events(self, event_type: Optional[str] = None, 
                  since: Optional[float] = None) -> List[Dict[str, Any]]:
        """
        Get events from chain.
        
        Args:
            event_type: Filter by event type
            since: Filter events since timestamp
            
        Returns:
            List of events
        """
        return self.event_chain.get_events(event_type, since)
    
    def get_latest_event(self, event_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get latest event.
        
        Args:
            event_type: Filter by event type
            
        Returns:
            Latest event or None
        """
        return self.event_chain.get_latest_event(event_type)
    
    def create_snapshot(self, data: Dict[str, Any], 
                       snapshot_type: str = "full") -> bool:
        """
        Create snapshot.
        
        Args:
            data: Snapshot data
            snapshot_type: Type of snapshot
            
        Returns:
            True if created successfully, False otherwise
        """
        return self.snapshot_store.create_snapshot(data, snapshot_type)
    
    def get_snapshot(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        """
        Get snapshot by ID.
        
        Args:
            snapshot_id: Snapshot ID
            
        Returns:
            Snapshot data or None
        """
        return self.snapshot_store.get_snapshot(snapshot_id)
    
    def get_latest_snapshot(self, snapshot_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get latest snapshot.
        
        Args:
            snapshot_type: Filter by snapshot type
            
        Returns:
            Latest snapshot or None
        """
        return self.snapshot_store.get_latest_snapshot(snapshot_type)
    
    def get_deltas(self, since: Optional[float] = None) -> List[Dict[str, Any]]:
        """
        Get deltas since timestamp.
        
        Args:
            since: Filter deltas since timestamp
            
        Returns:
            List of deltas
        """
        return self.snapshot_store.get_deltas(since)
    
    def add_block(self, data: List[Dict[str, Any]], 
                  block_type: str = "data") -> bool:
        """
        Add block to hash chain.
        
        Args:
            data: Block data
            block_type: Type of block
            
        Returns:
            True if added successfully, False otherwise
        """
        return self.hash_chain.add_block(data, block_type)
    
    def verify_chain(self) -> Tuple[bool, List[str]]:
        """
        Verify hash chain integrity.
        
        Returns:
            Tuple of (is_valid, error_messages)
        """
        return self.hash_chain.verify_chain()
    
    def get_proof(self, data_item: Dict[str, Any], 
                  block_index: int) -> Optional[Dict[str, Any]]:
        """
        Get Merkle proof for data item.
        
        Args:
            data_item: Data item to prove
            block_index: Block index
            
        Returns:
            Merkle proof or None
        """
        return self.hash_chain.get_proof(data_item, block_index)
    
    def get_memory_status(self) -> MemoryStatus:
        """
        Get memory layer status as typed record.
        
        Returns:
            MemoryStatus record
        """
        try:
            events = self.get_events()
            snapshots = []
            
            # Count snapshots
            for snapshot_file in self.snapshot_store.snapshots_dir.glob("*.json"):
                try:
                    snapshot = self.snapshot_store.get_snapshot(snapshot_file.stem)
                    if snapshot:
                        snapshots.append(snapshot)
                except Exception:
                    continue
            
            # Verify chain
            chain_valid, error_messages = self.verify_chain()
            
            return MemoryStatus(
                status="GREEN" if chain_valid else "RED",
                timestamp=utc_now_seconds(),
                events_count=len(events),
                snapshots_count=len(snapshots),
                chain_valid=chain_valid,
                error_messages=error_messages
            )
            
        except Exception as e:
            return MemoryStatus(
                status="RED",
                timestamp=utc_now_seconds(),
                events_count=0,
                snapshots_count=0,
                chain_valid=False,
                error_messages=[f"Failed to get memory status: {e}"]
            )
    
    def export_debug_bundle(self) -> DebugBundle:
        """
        Export debug bundle with all data as typed record.
        
        Returns:
            DebugBundle record
        """
        try:
            events = self.get_events()
            snapshots = []
            
            # Add snapshots
            for snapshot_file in self.snapshot_store.snapshots_dir.glob("*.json"):
                try:
                    snapshot = self.snapshot_store.get_snapshot(snapshot_file.stem)
                    if snapshot:
                        snapshots.append(snapshot)
                except Exception:
                    continue
            
            # Verify chain
            chain_valid, error_messages = self.verify_chain()
            
            return DebugBundle(
                timestamp=utc_now_seconds(),
                data_dir=str(self.data_dir),
                events=events,
                snapshots=snapshots,
                deltas=self.get_deltas(),
                chain_verification=ChainVerificationResult(
                    is_valid=chain_valid,
                    error_messages=error_messages,
                    blocks_verified=len(snapshots),
                    last_valid_block=len(snapshots) - 1 if snapshots else None
                )
            )
            
        except Exception as e:
            return DebugBundle(
                timestamp=utc_now_seconds(),
                data_dir=str(self.data_dir),
                events=[],
                snapshots=[],
                deltas=[],
                chain_verification=ChainVerificationResult(
                    is_valid=False,
                    error_messages=[f"Failed to export debug bundle: {e}"],
                    blocks_verified=0,
                    last_valid_block=None
                ),
                error=f"Failed to export debug bundle: {e}"
            )
