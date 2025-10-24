#!/usr/bin/env python3
"""
Service ACK Schema - Acknowledgement fields for service lifecycle
Provides deterministic health state based on timestamps and heartbeats
"""

import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Literal, Optional

from shared.io.jsonio import read_json_nobom, write_json_atomic_nobom


@dataclass
class ServiceACK:
    """Service acknowledgement state"""
    service: Literal["feeder", "trader", "ares"]
    
    # Lifecycle ACKs
    launch_request_ts: Optional[float] = None  # When start was requested
    ready_ts: Optional[float] = None  # When service became ready
    ready_reason: Optional[str] = None  # Why service is ready
    
    stop_request_ts: Optional[float] = None  # When stop was requested
    stopped_ack_ts: Optional[float] = None  # When service confirmed stop
    
    # Runtime heartbeats
    last_loop_ts: Optional[float] = None  # Last main loop iteration
    last_order_attempt_ts: Optional[float] = None  # Last order attempt (Trader only)
    last_signal_ts: Optional[float] = None  # Last signal generation (ARES only)
    
    # Error tracking
    last_error_code: Optional[str] = None
    last_error_detail: Optional[str] = None
    last_error_ts: Optional[float] = None
    
    # Process info
    pid: Optional[int] = None
    started_at: Optional[float] = None
    uptime_seconds: float = 0
    
    # Health status
    health_status: Literal["green", "yellow", "red", "unknown"] = "unknown"
    
    def is_ready(self) -> bool:
        """Check if service is ready (ready_ts > launch_request_ts)"""
        if self.ready_ts is None or self.launch_request_ts is None:
            return False
        return self.ready_ts > self.launch_request_ts
    
    def is_stopped(self) -> bool:
        """Check if service is stopped (stopped_ack_ts > stop_request_ts)"""
        if self.stopped_ack_ts is None or self.stop_request_ts is None:
            return False
        return self.stopped_ack_ts > stop_request_ts
    
    def heartbeat_age(self) -> float:
        """Get heartbeat age in seconds"""
        if self.last_loop_ts is None:
            return float('inf')
        return time.time() - self.last_loop_ts
    
    def get_health_state(self) -> Literal["green", "yellow", "red"]:
        """Compute health state based on heartbeat age"""
        age = self.heartbeat_age()
        
        if age <= 60:
            return "green"
        elif age <= 120:
            return "yellow"
        else:
            return "red"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)
    
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "ServiceACK":
        """Create from dictionary"""
        return ServiceACK(**data)


class ServiceACKManager:
    """Manager for service ACK states"""
    
    def __init__(self):
        self.repo_root = Path(__file__).parent.parent
        self.ack_file = self.repo_root / "shared_data" / "runtime" / "service_acks.json"
        self.ack_file.parent.mkdir(parents=True, exist_ok=True)
        
        self._load_acks()
    
    def _load_acks(self):
        """Load ACKs from disk"""
        try:
            data = read_json_nobom(self.ack_file, {"services": {}})
            self.acks: Dict[str, ServiceACK] = {
                svc: ServiceACK.from_dict(ack_data)
                for svc, ack_data in data.get("services", {}).items()
            }
        except Exception as e:
            print(f"Error loading service ACKs: {e}")
            self.acks = {}
    
    def _save_acks(self):
        """Save ACKs to disk"""
        try:
            data = {
                "services": {
                    svc: ack.to_dict()
                    for svc, ack in self.acks.items()
                },
                "last_updated": time.time()
            }
            write_json_atomic_nobom(self.ack_file, data)
        except Exception as e:
            print(f"Error saving service ACKs: {e}")
    
    def get_ack(self, service: str) -> ServiceACK:
        """Get or create ACK for service"""
        if service not in self.acks:
            self.acks[service] = ServiceACK(service=service)
        return self.acks[service]
    
    def set_launch_requested(self, service: str):
        """Mark service launch requested"""
        ack = self.get_ack(service)
        ack.launch_request_ts = time.time()
        self._save_acks()
    
    def set_ready(self, service: str, pid: int, reason: str = "startup_complete"):
        """Mark service ready"""
        ack = self.get_ack(service)
        ack.ready_ts = time.time()
        ack.ready_reason = reason
        ack.pid = pid
        ack.started_at = ack.ready_ts
        self._save_acks()
    
    def set_stop_requested(self, service: str):
        """Mark service stop requested"""
        ack = self.get_ack(service)
        ack.stop_request_ts = time.time()
        self._save_acks()
    
    def set_stopped(self, service: str):
        """Mark service stopped"""
        ack = self.get_ack(service)
        ack.stopped_ack_ts = time.time()
        ack.pid = None
        self._save_acks()
    
    def update_heartbeat(self, service: str, loop_ts: Optional[float] = None):
        """Update service heartbeat"""
        ack = self.get_ack(service)
        if loop_ts:
            ack.last_loop_ts = loop_ts
        else:
            ack.last_loop_ts = time.time()
        
        if ack.started_at:
            ack.uptime_seconds = time.time() - ack.started_at
        
        ack.health_status = ack.get_health_state()
        self._save_acks()
    
    def set_error(self, service: str, error_code: str, error_detail: str):
        """Record service error"""
        ack = self.get_ack(service)
        ack.last_error_code = error_code
        ack.last_error_detail = error_detail
        ack.last_error_ts = time.time()
        self._save_acks()
    
    def get_all_acks(self) -> Dict[str, ServiceACK]:
        """Get all service ACKs"""
        return self.acks.copy()


# Global singleton
_ack_manager: Optional[ServiceACKManager] = None


def get_ack_manager() -> ServiceACKManager:
    """Get global ACK manager singleton"""
    global _ack_manager
    if _ack_manager is None:
        _ack_manager = ServiceACKManager()
    return _ack_manager

