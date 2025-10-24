"""
Singleton management for Coin Quant R11

Process management with PID file locking and singleton enforcement.
Prevents multiple instances of the same service from running.
"""

import os
import time
from pathlib import Path
from typing import Optional
from .paths import get_data_dir
from .io import atomic_writer, atomic_reader


class SingletonError(Exception):
    """Singleton-related error"""
    pass


class SingletonGuard:
    """Singleton process guard with PID file management"""
    
    def __init__(self, service_name: str, data_dir: Optional[Path] = None):
        self.service_name = service_name
        self.data_dir = data_dir or get_data_dir()
        self.pid_file = self.data_dir / f"{service_name}.pid"
        self.pid = os.getpid()
    
    def acquire(self) -> bool:
        """
        Acquire singleton lock.
        
        Returns:
            True if acquired, False if already running
        """
        try:
            # Check if PID file exists
            if self.pid_file.exists():
                existing_pid = self._read_pid()
                if existing_pid and self._is_process_running(existing_pid):
                    return False
            
            # Write PID file
            return self._write_pid()
            
        except Exception as e:
            raise SingletonError(f"Failed to acquire singleton lock: {e}")
    
    def release(self) -> bool:
        """
        Release singleton lock.
        
        Returns:
            True if released successfully
        """
        try:
            if self.pid_file.exists():
                self.pid_file.unlink()
            return True
        except Exception as e:
            raise SingletonError(f"Failed to release singleton lock: {e}")
    
    def is_running(self) -> bool:
        """
        Check if singleton is running.
        
        Returns:
            True if running, False otherwise
        """
        if not self.pid_file.exists():
            return False
        
        existing_pid = self._read_pid()
        if not existing_pid:
            return False
        
        return self._is_process_running(existing_pid)
    
    def get_running_pid(self) -> Optional[int]:
        """
        Get PID of running singleton.
        
        Returns:
            PID if running, None otherwise
        """
        if not self.pid_file.exists():
            return None
        
        existing_pid = self._read_pid()
        if not existing_pid:
            return None
        
        if self._is_process_running(existing_pid):
            return existing_pid
        
        return None
    
    def _read_pid(self) -> Optional[int]:
        """Read PID from file"""
        try:
            content = atomic_reader.read_text(self.pid_file)
            if content:
                return int(content.strip())
        except (ValueError, TypeError):
            pass
        return None
    
    def _write_pid(self) -> bool:
        """Write PID to file"""
        try:
            return atomic_writer.write_text(self.pid_file, str(self.pid))
        except Exception:
            return False
    
    def _is_process_running(self, pid: int) -> bool:
        """Check if process is running"""
        try:
            # On Windows, use tasklist command
            if os.name == 'nt':
                import subprocess
                result = subprocess.run(
                    ['tasklist', '/FI', f'PID eq {pid}'],
                    capture_output=True,
                    text=True
                )
                return str(pid) in result.stdout
            else:
                # On Unix-like systems, use kill with signal 0
                os.kill(pid, 0)
                return True
        except (OSError, subprocess.SubprocessError):
            return False


class PIDLock:
    """PID file lock for process management"""
    
    def __init__(self, service_name: str, data_dir: Optional[Path] = None):
        self.service_name = service_name
        self.data_dir = data_dir or get_data_dir()
        self.pid_file = self.data_dir / f"{service_name}.pid"
        self.pid = os.getpid()
        self._locked = False
    
    def __enter__(self):
        """Context manager entry"""
        self.acquire()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.release()
    
    def acquire(self) -> bool:
        """
        Acquire PID lock.
        
        Returns:
            True if acquired, False if already locked
        """
        if self._locked:
            return True
        
        try:
            # Check if PID file exists and process is running
            if self.pid_file.exists():
                existing_pid = self._read_pid()
                if existing_pid and self._is_process_running(existing_pid):
                    return False
            
            # Write PID file
            if self._write_pid():
                self._locked = True
                return True
            
            return False
            
        except Exception as e:
            raise SingletonError(f"Failed to acquire PID lock: {e}")
    
    def release(self) -> bool:
        """
        Release PID lock.
        
        Returns:
            True if released successfully
        """
        if not self._locked:
            return True
        
        try:
            if self.pid_file.exists():
                self.pid_file.unlink()
            self._locked = False
            return True
        except Exception as e:
            raise SingletonError(f"Failed to release PID lock: {e}")
    
    def _read_pid(self) -> Optional[int]:
        """Read PID from file"""
        try:
            content = atomic_reader.read_text(self.pid_file)
            if content:
                return int(content.strip())
        except (ValueError, TypeError):
            pass
        return None
    
    def _write_pid(self) -> bool:
        """Write PID to file"""
        try:
            return atomic_writer.write_text(self.pid_file, str(self.pid))
        except Exception:
            return False
    
    def _is_process_running(self, pid: int) -> bool:
        """Check if process is running"""
        try:
            # On Windows, use tasklist command
            if os.name == 'nt':
                import subprocess
                result = subprocess.run(
                    ['tasklist', '/FI', f'PID eq {pid}'],
                    capture_output=True,
                    text=True
                )
                return str(pid) in result.stdout
            else:
                # On Unix-like systems, use kill with signal 0
                os.kill(pid, 0)
                return True
        except (OSError, subprocess.SubprocessError):
            return False


def create_singleton_guard(service_name: str) -> SingletonGuard:
    """
    Create singleton guard for a service.
    
    Args:
        service_name: Name of the service
        
    Returns:
        SingletonGuard instance
    """
    return SingletonGuard(service_name)


def create_pid_lock(service_name: str) -> PIDLock:
    """
    Create PID lock for a service.
    
    Args:
        service_name: Name of the service
        
    Returns:
        PIDLock instance
    """
    return PIDLock(service_name)
