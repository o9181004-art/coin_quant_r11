"""
Write telemetry for monitoring file write performance and failures.
"""

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class WriteTelemetry:
    """Telemetry data for file writes"""
    write_ok: int = 0
    write_fail: int = 0
    total_retries: int = 0
    total_latency_ms: float = 0.0
    last_error_code: Optional[int] = None
    last_error_message: str = ""
    last_error_time: float = 0.0
    
    # Recent write history (for rate calculations)
    recent_writes: Deque[tuple] = field(default_factory=lambda: deque(maxlen=100))
    
    def record_success(self, retries: int, latency_ms: float):
        """Record successful write"""
        self.write_ok += 1
        self.total_retries += retries
        self.total_latency_ms += latency_ms
        self.recent_writes.append((time.time(), True, retries, latency_ms))
    
    def record_failure(self, retries: int, latency_ms: float, error_code: Optional[int] = None, error_message: str = ""):
        """Record failed write"""
        self.write_fail += 1
        self.total_retries += retries
        self.total_latency_ms += latency_ms
        self.last_error_code = error_code
        self.last_error_message = error_message
        self.last_error_time = time.time()
        self.recent_writes.append((time.time(), False, retries, latency_ms))
    
    def get_recent_retry_count(self, window_sec: float = 60.0) -> int:
        """Get number of retries in recent time window"""
        cutoff = time.time() - window_sec
        return sum(retries for ts, ok, retries, _ in self.recent_writes if ts > cutoff)
    
    def get_avg_latency_ms(self) -> float:
        """Get average write latency in milliseconds"""
        total = self.write_ok + self.write_fail
        return self.total_latency_ms / total if total > 0 else 0.0
    
    def should_show_warning(self) -> bool:
        """Check if we should show warning badge (≥3 retries in last minute)"""
        return self.get_recent_retry_count(60.0) >= 3
    
    def get_summary(self) -> Dict:
        """Get telemetry summary"""
        total = self.write_ok + self.write_fail
        success_rate = (self.write_ok / total * 100) if total > 0 else 0.0
        
        return {
            "total_writes": total,
            "success_rate_pct": round(success_rate, 1),
            "total_retries": self.total_retries,
            "avg_latency_ms": round(self.get_avg_latency_ms(), 1),
            "recent_retries_60s": self.get_recent_retry_count(60.0),
            "should_warn": self.should_show_warning(),
            "last_error": {
                "code": self.last_error_code,
                "message": self.last_error_message,
                "time": self.last_error_time
            } if self.last_error_code else None
        }


# Global telemetry instances per file
_telemetry_registry: Dict[str, WriteTelemetry] = {}


def get_telemetry(file_path: str) -> WriteTelemetry:
    """
    Get or create telemetry instance for a file.
    
    Args:
        file_path: Path to the file being monitored
    
    Returns:
        WriteTelemetry instance
    """
    if file_path not in _telemetry_registry:
        _telemetry_registry[file_path] = WriteTelemetry()
    return _telemetry_registry[file_path]


def record_write_result(file_path: str, result):
    """
    Record write result to telemetry.
    
    Args:
        file_path: Path to the file
        result: WriteResult object
    """
    telemetry = get_telemetry(file_path)
    
    if result.ok:
        telemetry.record_success(result.retries, result.latency_ms)
        if result.retries > 0:
            logger.info(
                f"Write succeeded after {result.retries} retries: {file_path} "
                f"({result.latency_ms:.1f}ms)"
            )
    else:
        telemetry.record_failure(
            result.retries,
            result.latency_ms,
            result.last_errno,
            result.error_message
        )
        logger.error(
            f"Write failed after {result.retries} retries: {file_path} "
            f"(errno: {result.last_errno}, msg: {result.error_message})"
        )


def get_all_telemetry() -> Dict[str, Dict]:
    """Get telemetry summary for all monitored files"""
    return {
        path: telemetry.get_summary()
        for path, telemetry in _telemetry_registry.items()
    }


__all__ = [
    "WriteTelemetry",
    "get_telemetry",
    "record_write_result",
    "get_all_telemetry"
]

