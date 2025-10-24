"""
Typed records for Memory Layer operations
"""

from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path


@dataclass
class MemoryStatus:
    """Memory layer status record"""
    status: str
    timestamp: float
    events_count: int
    snapshots_count: int
    chain_valid: bool
    error_messages: List[str]


@dataclass
class EventRecord:
    """Event record with typed attributes"""
    event_type: str
    data: Dict[str, Any]
    source: str
    timestamp: float
    event_id: str


@dataclass
class SnapshotRecord:
    """Snapshot record with typed attributes"""
    snapshot_id: str
    data: Dict[str, Any]
    snapshot_type: str
    timestamp: float
    size_bytes: int


@dataclass
class ChainVerificationResult:
    """Hash chain verification result"""
    is_valid: bool
    error_messages: List[str]
    blocks_verified: int
    last_valid_block: Optional[int]


@dataclass
class DebugBundle:
    """Debug bundle with typed attributes"""
    timestamp: float
    data_dir: str
    events: List[EventRecord]
    snapshots: List[SnapshotRecord]
    deltas: List[Dict[str, Any]]
    chain_verification: ChainVerificationResult
    error: Optional[str] = None


def create_memory_status(status: str, timestamp: float, events_count: int = 0,
                        snapshots_count: int = 0, chain_valid: bool = True,
                        error_messages: Optional[List[str]] = None) -> MemoryStatus:
    """Create a MemoryStatus record"""
    return MemoryStatus(
        status=status,
        timestamp=timestamp,
        events_count=events_count,
        snapshots_count=snapshots_count,
        chain_valid=chain_valid,
        error_messages=error_messages or []
    )


def create_event_record(event_type: str, data: Dict[str, Any], source: str,
                       timestamp: float, event_id: str) -> EventRecord:
    """Create an EventRecord"""
    return EventRecord(
        event_type=event_type,
        data=data,
        source=source,
        timestamp=timestamp,
        event_id=event_id
    )


def create_snapshot_record(snapshot_id: str, data: Dict[str, Any],
                         snapshot_type: str, timestamp: float,
                         size_bytes: int = 0) -> SnapshotRecord:
    """Create a SnapshotRecord"""
    return SnapshotRecord(
        snapshot_id=snapshot_id,
        data=data,
        snapshot_type=snapshot_type,
        timestamp=timestamp,
        size_bytes=size_bytes
    )


def create_chain_verification_result(is_valid: bool, error_messages: List[str],
                                   blocks_verified: int = 0,
                                   last_valid_block: Optional[int] = None) -> ChainVerificationResult:
    """Create a ChainVerificationResult"""
    return ChainVerificationResult(
        is_valid=is_valid,
        error_messages=error_messages,
        blocks_verified=blocks_verified,
        last_valid_block=last_valid_block
    )
