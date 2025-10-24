"""
Single-writer lock for dispatcher status and other shared files.
Ensures only one process can write to prevent conflicts.
"""

import logging
import os
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class WriterLock:
    """Process-wide writer lock using PID file"""
    
    def __init__(self, lock_name: str, lock_dir: Path = None):
        """
        Initialize writer lock.
        
        Args:
            lock_name: Name of the lock (e.g., "dispatcher_status")
            lock_dir: Directory for lock files (default: shared_data/runtime/locks)
        """
        self.lock_name = lock_name
        
        if lock_dir is None:
            lock_dir = Path("shared_data/runtime/locks")
        
        self.lock_dir = Path(lock_dir)
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        
        self.lock_file = self.lock_dir / f"{lock_name}.lock"
        self.is_primary = False
        self.pid = os.getpid()
    
    def acquire(self, timeout_sec: float = 5.0) -> bool:
        """
        Try to acquire the lock (non-blocking with timeout).
        
        Args:
            timeout_sec: Timeout in seconds (default: 5.0)
        
        Returns:
            True if acquired, False if lock is held by another process
        """
        start_time = time.time()
        
        while True:
            # Check if lock exists
            if self.lock_file.exists():
                try:
                    # Read existing PID
                    with open(self.lock_file, 'r') as f:
                        content = f.read().strip()
                        if not content:
                            # Empty lock file, consider it stale
                            logger.warning(f"Empty lock file {self.lock_file}, removing")
                            self.lock_file.unlink()
                            continue
                        
                        existing_pid = int(content)
                    
                    # Check if process is still running
                    if self._is_process_running(existing_pid):
                        # Lock is held by another running process
                        if time.time() - start_time > timeout_sec:
                            logger.info(f"Lock {self.lock_name} held by PID {existing_pid}, we are SECONDARY")
                            self.is_primary = False
                            return False
                        
                        # Wait a bit and retry
                        time.sleep(0.1)
                        continue
                    else:
                        # Stale lock from dead process, remove it
                        logger.warning(f"Stale lock from dead PID {existing_pid}, removing")
                        try:
                            self.lock_file.unlink()
                        except Exception as e:
                            logger.error(f"Failed to remove stale lock: {e}")
                            return False
                
                except Exception as e:
                    logger.error(f"Error reading lock file: {e}")
                    if time.time() - start_time > timeout_sec:
                        return False
                    time.sleep(0.1)
                    continue
            
            # Try to create lock file
            try:
                # Use 'x' mode to fail if file exists (atomic check-and-create)
                with open(self.lock_file, 'x') as f:
                    f.write(str(self.pid))
                    f.flush()
                    os.fsync(f.fileno())
                
                logger.info(f"Acquired lock {self.lock_name} as PRIMARY (PID {self.pid})")
                self.is_primary = True
                return True
                
            except FileExistsError:
                # Race condition: another process created the lock
                if time.time() - start_time > timeout_sec:
                    logger.info(f"Failed to acquire lock {self.lock_name}, we are SECONDARY")
                    self.is_primary = False
                    return False
                
                time.sleep(0.1)
                continue
                
            except Exception as e:
                logger.error(f"Failed to create lock file: {e}")
                return False
    
    def release(self):
        """Release the lock"""
        if not self.is_primary:
            return
        
        try:
            if self.lock_file.exists():
                # Verify it's our lock
                with open(self.lock_file, 'r') as f:
                    content = f.read().strip()
                    if content and int(content) == self.pid:
                        self.lock_file.unlink()
                        logger.info(f"Released lock {self.lock_name} (PID {self.pid})")
                    else:
                        logger.warning(f"Lock file PID mismatch, not removing")
        except Exception as e:
            logger.error(f"Error releasing lock: {e}")
        
        self.is_primary = False
    
    def _is_process_running(self, pid: int) -> bool:
        """Check if a process with given PID is running"""
        try:
            # Send signal 0 to check if process exists (works on Unix)
            # On Windows, we'll use a different approach
            import sys
            if sys.platform == 'win32':
                # Windows: use tasklist or psutil if available
                try:
                    import psutil
                    return psutil.pid_exists(pid)
                except ImportError:
                    # Fallback: assume process is running if we can't check
                    # This is conservative but safe
                    logger.warning(f"psutil not available, assuming PID {pid} is running")
                    return True
            else:
                # Unix: send signal 0
                os.kill(pid, 0)
                return True
        except (ProcessLookupError, PermissionError):
            return False
        except Exception as e:
            logger.error(f"Error checking process {pid}: {e}")
            # Conservative: assume running
            return True
    
    def __enter__(self):
        """Context manager entry"""
        self.acquire()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.release()
        return False


# Global lock instances
_locks = {}


def get_writer_lock(lock_name: str) -> WriterLock:
    """
    Get or create a writer lock instance.
    
    Args:
        lock_name: Name of the lock
    
    Returns:
        WriterLock instance
    """
    if lock_name not in _locks:
        _locks[lock_name] = WriterLock(lock_name)
    return _locks[lock_name]


__all__ = ["WriterLock", "get_writer_lock"]

