#!/usr/bin/env python3
"""
Enhanced PID/Lock Handling
========================================
Eliminates zombie PID/lock false-positives with validation.

Features:
- PID existence & liveness check
- Process path validation (venv match)
- Hostname validation
- Lock TTL check (≤2 minutes)
- Auto-purge stale locks
- FORCE_START override
"""

import json
import os
import platform
import socket
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

import psutil


class EnhancedPIDLock:
    """Enhanced PID lock with validation"""
    
    # Exit codes
    EXIT_STALE_PURGED = 10  # Stale lock auto-purged, started OK
    EXIT_ACTIVE_PROCESS = 11  # Active process detected, start aborted
    EXIT_LOCK_PERMISSION = 12  # Lock permission issue
    
    def __init__(self, service_name: str, lock_dir: str = "runtime"):
        self.service_name = service_name
        self.lock_dir = Path(lock_dir)
        self.lock_file = self.lock_dir / f"{service_name}.pid.lock"
        
        self.current_pid = os.getpid()
        self.current_hostname = socket.gethostname()
        self.current_interpreter = sys.executable
        
        self.lock_ttl_seconds = 120  # 2 minutes
        self.force_start = os.getenv("FORCE_START", "false").lower() == "true"
    
    def acquire(self) -> Tuple[bool, str, int]:
        """
        Acquire PID lock with validation.
        
        Returns:
            (success, message, exit_code)
            
        Exit codes:
            0: Fresh start
            10: Stale lock purged, started OK
            11: Active process detected, aborted
            12: Lock permission issue
        """
        # Ensure lock directory exists
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        
        # Track if stale lock was purged
        was_stale_purged = False
        
        # Check if lock exists
        if self.lock_file.exists():
            is_stale, reason = self._validate_lock()
            
            if is_stale:
                # Stale lock - auto-purge
                print(f"[PIDLock] WARN: Stale lock detected ({reason}) - auto-purging")
                
                try:
                    self.lock_file.unlink()
                    print(f"[PIDLock] Stale lock purged: {self.lock_file}")
                    
                    # Mark that we purged a stale lock
                    was_stale_purged = True
                except Exception as e:
                    return False, f"Failed to purge stale lock: {e}", self.EXIT_LOCK_PERMISSION
            
            elif self.force_start:
                # FORCE_START override
                print(f"[PIDLock] AUDIT: FORCE_START override - purging lock")
                
                try:
                    self.lock_file.unlink()
                    print(f"[PIDLock] Lock purged by FORCE_START: {self.lock_file}")
                except Exception as e:
                    return False, f"Failed to force-purge lock: {e}", self.EXIT_LOCK_PERMISSION
            
            else:
                # Active process - abort
                lock_data = self._read_lock()
                active_pid = lock_data.get('pid', 'unknown')
                
                return False, f"Active process detected (PID {active_pid}) - start aborted", self.EXIT_ACTIVE_PROCESS
        
        # Write new lock
        lock_data = {
            'pid': self.current_pid,
            'hostname': self.current_hostname,
            'interpreter': self.current_interpreter,
            'service': self.service_name,
            'started_at': time.time(),
            'ts': time.time()
        }
        
        try:
            with open(self.lock_file, 'w', encoding='utf-8') as f:
                json.dump(lock_data, f, indent=2)
            
            # Determine exit code
            exit_code = self.EXIT_STALE_PURGED if was_stale_purged else 0
            
            return True, f"Lock acquired: {self.service_name} (PID {self.current_pid})", exit_code
        
        except Exception as e:
            return False, f"Failed to write lock: {e}", self.EXIT_LOCK_PERMISSION
    
    def release(self):
        """Release PID lock"""
        try:
            if self.lock_file.exists():
                # Verify we own this lock
                lock_data = self._read_lock()
                
                if lock_data.get('pid') == self.current_pid:
                    self.lock_file.unlink()
                    print(f"[PIDLock] Released: {self.service_name}")
                else:
                    print(f"[PIDLock] WARN: Lock owned by different PID - not releasing")
        
        except Exception as e:
            print(f"[PIDLock] Failed to release lock: {e}")
    
    def _validate_lock(self) -> Tuple[bool, str]:
        """
        Validate existing lock.
        
        Returns:
            (is_stale, reason)
        """
        lock_data = self._read_lock()
        
        if not lock_data:
            return True, "Invalid lock file (corrupted JSON)"
        
        # Check 1: PID exists and alive
        pid = lock_data.get('pid')
        if not pid:
            return True, "Missing PID in lock"
        
        if not self._is_pid_alive(pid):
            return True, f"PID {pid} not alive"
        
        # Check 2: Process path matches venv
        try:
            process = psutil.Process(pid)
            process_exe = process.exe()
            
            # Check if process is using our venv
            if 'venv_fixed' not in process_exe:
                return True, f"PID {pid} not using venv_fixed"
        
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return True, f"PID {pid} not accessible"
        
        # Check 3: Hostname matches
        hostname = lock_data.get('hostname')
        if hostname and hostname != self.current_hostname:
            return True, f"Hostname mismatch: {hostname} != {self.current_hostname}"
        
        # Check 4: Lock TTL
        lock_ts = lock_data.get('ts', 0)
        age = time.time() - lock_ts
        
        if age > self.lock_ttl_seconds:
            return True, f"Lock too old ({age:.0f}s > {self.lock_ttl_seconds}s)"
        
        # All checks passed - lock is valid
        return False, "Lock is valid"
    
    def _is_pid_alive(self, pid: int) -> bool:
        """Check if PID is alive"""
        try:
            return psutil.pid_exists(pid)
        except:
            return False
    
    def _read_lock(self) -> dict:
        """Read lock file data"""
        try:
            if not self.lock_file.exists():
                return {}
            
            with open(self.lock_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        except Exception as e:
            print(f"[PIDLock] Failed to read lock: {e}")
            return {}
    
    def print_diagnostics(self):
        """Print startup diagnostics"""
        print("")
        print("="*60)
        print(f" {self.service_name.upper()} - Startup Diagnostics")
        print("="*60)
        print(f"Python: {sys.version.split()[0]}")
        print(f"Interpreter: {self.current_interpreter}")
        print(f"venv: {'venv_fixed' if 'venv_fixed' in self.current_interpreter else 'OTHER'}")
        print(f"PID: {self.current_pid}")
        print(f"Hostname: {self.current_hostname}")
        print(f"Service: {self.service_name}")
        print("")
        print("Canonical Paths:")
        print(f"  Health: shared_data/health.json")
        print(f"  DataBus: shared_data/databus_snapshot.json")
        print(f"  Account: shared_data/account_snapshot.json")
        print("")
        
        # Lock status
        if self.lock_file.exists():
            lock_data = self._read_lock()
            is_stale, reason = self._validate_lock()
            
            if is_stale:
                print(f"Lock: STALE ({reason})")
            else:
                print(f"Lock: ACTIVE (PID {lock_data.get('pid')})")
        else:
            print("Lock: NONE (fresh start)")
        
        print("="*60)
        print("")


# Unit tests
if __name__ == "__main__":
    import shutil
    import tempfile
    
    print("Testing EnhancedPIDLock...")
    
    # Create temp directory
    test_dir = tempfile.mkdtemp()
    
    try:
        # Test 1: Fresh start
        print("\n1. Fresh start (no lock):")
        lock = EnhancedPIDLock("test_service", lock_dir=test_dir)
        success, message, exit_code = lock.acquire()
        
        assert success, "Fresh start should succeed"
        assert exit_code == 0, "Exit code should be 0"
        print(f"✅ {message}")
        
        lock.release()
        
        # Test 2: Stale lock (old timestamp)
        print("\n2. Stale lock (old timestamp):")
        
        # Create stale lock
        lock_file = Path(test_dir) / "test_service.pid.lock"
        stale_data = {
            'pid': os.getpid(),
            'hostname': socket.gethostname(),
            'interpreter': sys.executable,
            'ts': time.time() - 200  # 200 seconds ago
        }
        
        with open(lock_file, 'w') as f:
            json.dump(stale_data, f)
        
        lock2 = EnhancedPIDLock("test_service", lock_dir=test_dir)
        success, message, exit_code = lock2.acquire()
        
        assert success, "Should purge stale lock and succeed"
        assert exit_code == lock2.EXIT_STALE_PURGED, "Exit code should be 10"
        print(f"✅ {message}")
        
        lock2.release()
        
        # Test 3: Dead PID
        print("\n3. Stale lock (dead PID):")
        
        dead_pid = 99999  # Very unlikely to exist
        dead_lock = {
            'pid': dead_pid,
            'hostname': socket.gethostname(),
            'interpreter': sys.executable,
            'ts': time.time()
        }
        
        with open(lock_file, 'w') as f:
            json.dump(dead_lock, f)
        
        lock3 = EnhancedPIDLock("test_service", lock_dir=test_dir)
        success, message, exit_code = lock3.acquire()
        
        assert success, "Should purge dead PID lock"
        assert exit_code == lock3.EXIT_STALE_PURGED, "Exit code should be 10"
        print(f"✅ {message}")
        
        lock3.release()
        
        # Test 4: Diagnostics
        print("\n4. Startup diagnostics:")
        lock4 = EnhancedPIDLock("test_service", lock_dir=test_dir)
        lock4.print_diagnostics()
        print("✅ Diagnostics work")
        
        print("\n" + "="*50)
        print("All PID/Lock tests passed! ✅")
        print("="*50)
    
    finally:
        # Cleanup
        shutil.rmtree(test_dir, ignore_errors=True)

