"""
Memory Telemetry for Coin Quant Services
Provides RSS/VMS monitoring and leak detection
"""

import json
import logging
import os
import time
import tracemalloc
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil


@dataclass
class MemorySnapshot:
    """Memory usage snapshot"""
    ts: float
    service: str
    rss_mb: float
    vms_mb: float
    top_allocs: List[Dict[str, Any]]
    gc_counts: Optional[Dict[str, int]] = None


class MemoryTelemetry:
    """Memory monitoring and telemetry for services"""
    
    def __init__(self, service_name: str, log_dir: str = "logs/metrics"):
        self.service_name = service_name
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Configuration from environment
        self.enabled = os.getenv("MEM_TRACE", "false").lower() == "true"
        self.interval = int(os.getenv("MEM_INTERVAL_SEC", "60"))
        self.max_allocs = int(os.getenv("MEM_MAX_ALLOCS", "10"))
        
        # Setup logging
        self.logger = logging.getLogger(f"memory.{service_name}")
        self.log_file = self.log_dir / f"memory_{service_name}.ndjson"
        
        # State
        self.last_log_time = 0
        self.start_time = time.time()
        self.process = psutil.Process()
        
        # Initialize tracemalloc if enabled
        if self.enabled:
            tracemalloc.start()
            self.logger.info(f"Memory tracing enabled for {service_name}")
        
        # Log initial state
        self._log_memory_snapshot("startup")
    
    def get_rss_mb(self) -> float:
        """Get current RSS memory usage in MB"""
        try:
            return self.process.memory_info().rss / 1024 / 1024
        except Exception:
            return 0.0
    
    def get_vms_mb(self) -> float:
        """Get current VMS memory usage in MB"""
        try:
            return self.process.memory_info().vms / 1024 / 1024
        except Exception:
            return 0.0
    
    def get_top_allocations(self) -> List[Dict[str, Any]]:
        """Get top memory allocations if tracemalloc is enabled"""
        if not self.enabled or not tracemalloc.is_tracing():
            return []
        
        try:
            snapshot = tracemalloc.take_snapshot()
            top_stats = snapshot.statistics('lineno')
            
            allocs = []
            for stat in top_stats[:self.max_allocs]:
                allocs.append({
                    "filename": stat.traceback.format()[0] if stat.traceback.format() else "unknown",
                    "size_mb": stat.size / 1024 / 1024,
                    "count": stat.count
                })
            
            return allocs
        except Exception as e:
            self.logger.warning(f"Failed to get allocations: {e}")
            return []
    
    def _log_memory_snapshot(self, event: str = "periodic"):
        """Log memory snapshot to file"""
        try:
            snapshot = MemorySnapshot(
                ts=time.time(),
                service=self.service_name,
                rss_mb=self.get_rss_mb(),
                vms_mb=self.get_vms_mb(),
                top_allocs=self.get_top_allocations()
            )
            
            # Write to NDJSON file
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(snapshot), ensure_ascii=False) + "\n")
            
            # Log to console if significant change
            if event == "startup" or event == "shutdown":
                self.logger.info(f"Memory {event}: RSS={snapshot.rss_mb:.1f}MB, VMS={snapshot.vms_mb:.1f}MB")
            
        except Exception as e:
            self.logger.error(f"Failed to log memory snapshot: {e}")
    
    def periodic_log(self):
        """Periodic memory logging (call from main loop)"""
        current_time = time.time()
        if current_time - self.last_log_time >= self.interval:
            self._log_memory_snapshot("periodic")
            self.last_log_time = current_time
    
    def shutdown(self):
        """Shutdown telemetry"""
        self._log_memory_snapshot("shutdown")
        if self.enabled and tracemalloc.is_tracing():
            tracemalloc.stop()
        self.logger.info(f"Memory telemetry shutdown for {self.service_name}")


def get_memory_config() -> Dict[str, Any]:
    """Get memory configuration from environment"""
    return {
        "low_mem": os.getenv("LOW_MEM", "true").lower() == "true",
        "symbol_limit": int(os.getenv("SYMBOL_LIMIT", "20")),
        "history_bars_max": int(os.getenv("HISTORY_BARS_MAX", "720")),
        "tick_buffer_max": int(os.getenv("TICK_BUFFER_MAX", "200")),
        "ws_queue_max": int(os.getenv("WS_QUEUE_MAX", "2000")),
        "ares_dtype": os.getenv("ARES_DTYPE", "float32"),
        "ares_copy_on_write": os.getenv("ARES_COPY_ON_WRITE", "true").lower() == "true",
        "cache_max_entries": int(os.getenv("CACHE_MAX_ENTRIES", "64")),
        "cache_ttl_sec": int(os.getenv("CACHE_TTL_SEC", "120")),
        "record_ws": os.getenv("RECORD_WS", "false").lower() == "true",
        "ui_heavy_charts": os.getenv("UI_HEAVY_CHARTS", "false").lower() == "true",
        "mem_trace": os.getenv("MEM_TRACE", "false").lower() == "true",
        "mem_interval_sec": int(os.getenv("MEM_INTERVAL_SEC", "60")),
    }


def memory_leak_test(service_func, duration_minutes: int = 10, max_growth_percent: float = 10.0) -> bool:
    """Run memory leak test for a service function"""
    import gc
    
    telemetry = MemoryTelemetry("leak_test")
    
    start_rss = telemetry.get_rss_mb()
    start_time = time.time()
    
    # Run service for specified duration
    end_time = start_time + (duration_minutes * 60)
    
    while time.time() < end_time:
        try:
            service_func()
            telemetry.periodic_log()
            time.sleep(1)
        except KeyboardInterrupt:
            break
    
    end_rss = telemetry.get_rss_mb()
    growth_percent = ((end_rss - start_rss) / start_rss) * 100
    
    telemetry.shutdown()
    
    success = growth_percent <= max_growth_percent
    print(f"Memory leak test: {growth_percent:.1f}% growth ({start_rss:.1f}MB -> {end_rss:.1f}MB)")
    print(f"Test {'PASSED' if success else 'FAILED'}")
    
    return success


# Global telemetry instance for easy access
_telemetry: Optional[MemoryTelemetry] = None


def init_telemetry(service_name: str) -> MemoryTelemetry:
    """Initialize global telemetry instance"""
    global _telemetry
    _telemetry = MemoryTelemetry(service_name)
    return _telemetry


def get_telemetry() -> Optional[MemoryTelemetry]:
    """Get global telemetry instance"""
    return _telemetry


def log_memory(event: str = "check"):
    """Quick memory logging"""
    if _telemetry:
        _telemetry._log_memory_snapshot(event)
