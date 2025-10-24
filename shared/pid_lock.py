"""
Phase 1: PID Lock Discipline
Ensures only one instance of each service runs at a time
"""

import os
import sys
from pathlib import Path
from typing import Optional

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


class PIDLock:
    """PID lock manager for single-instance enforcement"""
    
    def __init__(self, service_name: str, pid_dir: Optional[Path] = None):
        """
        Initialize PID lock
        
        Args:
            service_name: Name of the service (e.g., "feeder", "trader")
            pid_dir: Directory for PID files (default: shared_data/pids)
        """
        self.service_name = service_name
        self.pid_dir = pid_dir or Path("shared_data/pids")
        self.pid_dir.mkdir(parents=True, exist_ok=True)
        self.pid_file = self.pid_dir / f"{service_name}.pid"
    
    def is_process_running(self, pid: int) -> bool:
        """
        Check if process with given PID is running
        
        Args:
            pid: Process ID to check
        
        Returns:
            True if process is running, False otherwise
        """
        if PSUTIL_AVAILABLE:
            try:
                proc = psutil.Process(pid)
                return proc.is_running()
            except psutil.NoSuchProcess:
                return False
        else:
            # Fallback: try to send signal 0 (no-op)
            try:
                os.kill(pid, 0)
                return True
            except OSError:
                return False
    
    def acquire(self) -> bool:
        """
        Acquire PID lock for this service
        
        Returns:
            True if lock acquired, False if already locked
        """
        # Check for existing lock
        if self.pid_file.exists():
            try:
                with open(self.pid_file, "r") as f:
                    existing_pid = int(f.read().strip())
                
                # Check if process is still running
                if self.is_process_running(existing_pid):
                    print(f"❌ ERROR: {self.service_name} already running (PID: {existing_pid})")
                    print(f"PID file: {self.pid_file}")
                    print(f"To override, stop the existing process or delete: {self.pid_file}")
                    return False
                else:
                    print(f"⚠️ Stale PID lock found (PID: {existing_pid}), removing...")
                    self.pid_file.unlink()
            except (ValueError, IOError) as e:
                print(f"⚠️ Invalid PID file, removing: {e}")
                try:
                    self.pid_file.unlink()
                except OSError:
                    pass
        
        # Write current PID
        try:
            with open(self.pid_file, "w") as f:
                f.write(str(os.getpid()))
            return True
        except IOError as e:
            print(f"❌ ERROR: Failed to write PID file: {e}")
            return False
    
    def release(self):
        """Release PID lock"""
        try:
            if self.pid_file.exists():
                self.pid_file.unlink()
        except OSError:
            pass
    
    def __enter__(self):
        """Context manager entry"""
        if not self.acquire():
            sys.exit(1)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.release()


def check_single_instance(service_name: str) -> bool:
    """
    Quick check if service is already running
    
    Args:
        service_name: Name of the service
    
    Returns:
        True if service is NOT running (safe to start), False if already running
    """
    lock = PIDLock(service_name)
    pid_file = lock.pid_file
    
    if not pid_file.exists():
        return True
    
    try:
        with open(pid_file, "r") as f:
            existing_pid = int(f.read().strip())
        return not lock.is_process_running(existing_pid)
    except (ValueError, IOError):
        return True

