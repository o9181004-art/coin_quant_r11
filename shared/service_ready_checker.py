"""
Deterministic service ready checker.
Replaces blind timeouts with multi-probe health checks.
"""

import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ReadyCheckResult:
    """Result of service ready check"""
    ok: bool
    code: str  # READY, PID_NOT_FOUND, HEARTBEAT_STALE, DATABUS_MISSING, etc.
    detail: str
    probe_results: dict
    boot_log_path: Optional[str] = None
    last_boot_lines: str = ""


class ServiceReadyChecker:
    """Multi-probe service ready checker"""
    
    def __init__(self, service_name: str, max_wait_sec: float = 15.0, probe_interval_sec: float = 0.5):
        self.service_name = service_name
        self.max_wait_sec = max_wait_sec
        self.probe_interval_sec = probe_interval_sec
        
        # Paths
        self.pid_file = Path(f"shared_data/pids/{service_name}.pid")
        self.heartbeat_file = Path(f"shared_data/heartbeats/{service_name}.json")
        self.boot_log = Path(f"logs/ops/{service_name}_boot.log")
    
    def wait_until_ready(self) -> ReadyCheckResult:
        """
        Wait for service to be ready with deterministic checks.
        
        Probes:
        A. PID exists and process is alive
        B. Heartbeat file exists and updated within ≤ 3s
        C. DataBus snapshot produced (for Feeder)
        
        Returns:
            ReadyCheckResult with ok=True if ready, ok=False with error details if not
        """
        logger.info(f"Checking if {self.service_name} is ready (max {self.max_wait_sec}s)...")
        
        start_time = time.time()
        probe_results = {}
        
        while (time.time() - start_time) < self.max_wait_sec:
            # Probe A: PID check
            pid_ok, pid_detail = self._probe_pid()
            probe_results['pid'] = {'ok': pid_ok, 'detail': pid_detail}
            
            if not pid_ok:
                # No PID yet, wait and retry
                time.sleep(self.probe_interval_sec)
                continue
            
            # Probe B: Heartbeat check
            hb_ok, hb_detail = self._probe_heartbeat()
            probe_results['heartbeat'] = {'ok': hb_ok, 'detail': hb_detail}
            
            # Probe C: DataBus check (for Feeder only)
            if self.service_name == "feeder":
                db_ok, db_detail = self._probe_databus()
                probe_results['databus'] = {'ok': db_ok, 'detail': db_detail}
            else:
                db_ok = True  # Not required for other services
            
            # All required probes passed?
            if pid_ok and hb_ok and db_ok:
                elapsed = time.time() - start_time
                logger.info(f"✅ {self.service_name} is READY ({elapsed:.1f}s)")
                return ReadyCheckResult(
                    ok=True,
                    code="READY",
                    detail=f"Service ready in {elapsed:.1f}s",
                    probe_results=probe_results
                )
            
            # Not ready yet, wait and retry
            time.sleep(self.probe_interval_sec)
        
        # Timeout - determine failure reason
        elapsed = time.time() - start_time
        logger.error(f"❌ {self.service_name} NOT READY after {elapsed:.1f}s")
        
        # Determine specific failure code
        if not probe_results.get('pid', {}).get('ok'):
            code = "PID_NOT_FOUND"
            detail = probe_results['pid']['detail']
        elif not probe_results.get('heartbeat', {}).get('ok'):
            code = "HEARTBEAT_STALE"
            detail = probe_results['heartbeat']['detail']
        elif self.service_name == "feeder" and not probe_results.get('databus', {}).get('ok'):
            code = "DATABUS_MISSING"
            detail = probe_results['databus']['detail']
        else:
            code = "TIMEOUT"
            detail = f"Service did not become ready within {self.max_wait_sec}s"
        
        # Capture last boot log lines
        last_boot_lines = self._read_last_boot_lines(50)
        
        return ReadyCheckResult(
            ok=False,
            code=code,
            detail=detail,
            probe_results=probe_results,
            boot_log_path=str(self.boot_log) if self.boot_log.exists() else None,
            last_boot_lines=last_boot_lines
        )
    
    def _probe_pid(self) -> tuple[bool, str]:
        """Probe A: Check if PID file exists and process is alive"""
        if not self.pid_file.exists():
            return False, "PID file does not exist"
        
        try:
            with open(self.pid_file, 'r') as f:
                pid = int(f.read().strip())
            
            # Check if process exists
            if self._is_process_alive(pid):
                return True, f"Process {pid} is alive"
            else:
                return False, f"Process {pid} is not running"
                
        except Exception as e:
            return False, f"Error reading PID file: {e}"
    
    def _probe_heartbeat(self) -> tuple[bool, str]:
        """Probe B: Check if heartbeat file exists and is recent (≤ 3s)"""
        if not self.heartbeat_file.exists():
            return False, "Heartbeat file does not exist"
        
        try:
            import json
            with open(self.heartbeat_file, 'r') as f:
                hb_data = json.load(f)
            
            timestamp = hb_data.get('timestamp', 0)
            age = time.time() - timestamp
            
            if age <= 3.0:
                return True, f"Heartbeat fresh ({age:.1f}s old)"
            else:
                return False, f"Heartbeat stale ({age:.1f}s old, threshold: 3s)"
                
        except Exception as e:
            return False, f"Error reading heartbeat: {e}"
    
    def _probe_databus(self) -> tuple[bool, str]:
        """Probe C: Check if DataBus snapshot exists (Feeder only)"""
        databus_path = Path("shared_data/databus_snapshot.json")
        
        if not databus_path.exists():
            return False, "DataBus snapshot does not exist"
        
        try:
            # Check if file was recently modified (within 10s)
            mtime = databus_path.stat().st_mtime
            age = time.time() - mtime
            
            if age <= 10.0:
                return True, f"DataBus snapshot recent ({age:.1f}s old)"
            else:
                return False, f"DataBus snapshot stale ({age:.1f}s old)"
                
        except Exception as e:
            return False, f"Error checking DataBus: {e}"
    
    def _is_process_alive(self, pid: int) -> bool:
        """Check if process with given PID is alive"""
        try:
            import sys
            if sys.platform == 'win32':
                # Windows
                try:
                    import psutil
                    return psutil.pid_exists(pid)
                except ImportError:
                    # Fallback: try to open process handle
                    import ctypes
                    kernel32 = ctypes.windll.kernel32
                    PROCESS_QUERY_INFORMATION = 0x0400
                    handle = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid)
                    if handle:
                        kernel32.CloseHandle(handle)
                        return True
                    return False
            else:
                # Unix
                os.kill(pid, 0)
                return True
        except (ProcessLookupError, PermissionError, Exception):
            return False
    
    def _read_last_boot_lines(self, n: int = 50) -> str:
        """Read last N lines from boot log"""
        if not self.boot_log.exists():
            return ""
        
        try:
            with open(self.boot_log, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                return ''.join(lines[-n:])
        except Exception as e:
            return f"Error reading boot log: {e}"


__all__ = ["ServiceReadyChecker", "ReadyCheckResult"]

