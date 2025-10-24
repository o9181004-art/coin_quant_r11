#!/usr/bin/env python3
"""
Enhanced Singleton Lock with Auto-Heal Stale Lock
Cross-process file lock with PID & start time, auto-heal stale lock if PID not alive or mtime>5min.
"""

import json
import logging
import os
import psutil
import time
from pathlib import Path
from typing import Optional


logger = logging.getLogger(__name__)


class SingletonLock:
    """Enhanced singleton lock with auto-heal"""

    def __init__(self, name: str, lock_dir: Optional[Path] = None):
        """
        Args:
            name: Process name (e.g., "feeder", "trader")
            lock_dir: Lock directory (default: shared_data)
        """
        self.name = name
        self.project_root = Path(__file__).parent.parent

        if lock_dir is None:
            lock_dir = self.project_root / "shared_data"

        lock_dir.mkdir(parents=True, exist_ok=True)

        self.lock_file = lock_dir / f"{name}.singleton.lock"
        self.lock_fd = None
        self.is_locked = False

        # Stale lock threshold (5 minutes)
        self.stale_threshold_sec = 300

    def _is_stale_lock(self) -> bool:
        """Check if lock file is stale"""
        try:
            if not self.lock_file.exists():
                return False

            # Check file modification time
            mtime = self.lock_file.stat().st_mtime
            age = time.time() - mtime

            if age > self.stale_threshold_sec:
                logger.warning(f"Lock file is stale (age: {age:.0f}s > {self.stale_threshold_sec}s)")
                return True

            # Check if PID is alive
            try:
                with open(self.lock_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()

                if content:
                    lock_data = json.loads(content)
                    pid = lock_data.get("pid")

                    if pid and not psutil.pid_exists(pid):
                        logger.warning(f"Lock file PID {pid} is not alive")
                        return True

            except (json.JSONDecodeError, ValueError):
                # Invalid lock file content
                logger.warning("Lock file has invalid content")
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to check stale lock: {e}")
            return False

    def _heal_stale_lock(self) -> bool:
        """Heal stale lock by removing it"""
        try:
            if self.lock_file.exists():
                logger.info(f"Healing stale lock: {self.lock_file}")
                self.lock_file.unlink()
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to heal stale lock: {e}")
            return False

    def _write_lock_info(self):
        """Write lock information to file"""
        try:
            lock_info = {
                "pid": os.getpid(),
                "name": self.name,
                "start_time": time.time(),
                "start_time_str": time.strftime("%Y-%m-%d %H:%M:%S"),
                "hostname": os.environ.get("COMPUTERNAME", "unknown")
            }

            self.lock_fd.seek(0)
            self.lock_fd.truncate()
            self.lock_fd.write(json.dumps(lock_info, indent=2))
            self.lock_fd.flush()

        except Exception as e:
            logger.error(f"Failed to write lock info: {e}")

    def acquire(self) -> bool:
        """
        Acquire singleton lock

        Returns:
            True if lock acquired successfully

        Raises:
            RuntimeError: If lock cannot be acquired
        """
        try:
            # Check for stale lock
            if self._is_stale_lock():
                logger.warning("Detected stale lock, attempting to heal...")
                if self._heal_stale_lock():
                    logger.info("✅ Stale lock healed")
                else:
                    logger.error("❌ Failed to heal stale lock")

            # Open lock file
            self.lock_fd = open(self.lock_file, 'w', encoding='utf-8')

            # Try to acquire lock (non-blocking)
            try:
                if os.name == 'nt':
                    # Windows: msvcrt
                    import msvcrt
                    msvcrt.locking(self.lock_fd.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    # Unix: fcntl
                    import fcntl
                    fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

                # Lock acquired
                self.is_locked = True
                self._write_lock_info()

                logger.info(f"✅ Singleton lock acquired for {self.name} (PID: {os.getpid()})")
                return True

            except (IOError, OSError) as e:
                # Lock already held
                logger.error(f"❌ Singleton lock already held for {self.name}")

                # Try to read lock info
                try:
                    self.lock_fd.seek(0)
                    content = self.lock_fd.read()
                    if content:
                        lock_data = json.loads(content)
                        logger.error(f"   Held by PID: {lock_data.get('pid')}")
                        logger.error(f"   Started: {lock_data.get('start_time_str')}")
                except:
                    pass

                self.lock_fd.close()
                self.lock_fd = None

                raise RuntimeError(f"Another instance of {self.name} is already running")

        except RuntimeError:
            raise
        except Exception as e:
            logger.error(f"Failed to acquire lock: {e}")
            if self.lock_fd:
                self.lock_fd.close()
                self.lock_fd = None
            raise RuntimeError(f"Failed to acquire lock: {e}")

    def release(self):
        """Release singleton lock"""
        if not self.is_locked:
            return

        try:
            if self.lock_fd:
                # Clear lock file
                self.lock_fd.seek(0)
                self.lock_fd.truncate()

                # Release lock
                if os.name == 'nt':
                    import msvcrt
                    try:
                        msvcrt.locking(self.lock_fd.fileno(), msvcrt.LK_UNLCK, 1)
                    except:
                        pass
                else:
                    import fcntl
                    try:
                        fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
                    except:
                        pass

                self.lock_fd.close()
                self.lock_fd = None

            # Remove lock file
            if self.lock_file.exists():
                self.lock_file.unlink()

            self.is_locked = False
            logger.info(f"✅ Singleton lock released for {self.name}")

        except Exception as e:
            logger.error(f"Failed to release lock: {e}")

    def __enter__(self):
        """Context manager entry"""
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.release()
        return False

    def __del__(self):
        """Destructor"""
        self.release()


def acquire_singleton_lock(name: str, lock_dir: Optional[Path] = None) -> SingletonLock:
    """
    Acquire singleton lock

    Args:
        name: Process name
        lock_dir: Lock directory (optional)

    Returns:
        SingletonLock instance

    Raises:
        RuntimeError: If lock cannot be acquired
    """
    lock = SingletonLock(name, lock_dir)
    lock.acquire()
    return lock


def is_running(name: str, lock_dir: Optional[Path] = None) -> Optional[dict]:
    """
    Check if process is running

    Args:
        name: Process name
        lock_dir: Lock directory (optional)

    Returns:
        Lock info dict if running, None otherwise
    """
    lock = SingletonLock(name, lock_dir)

    try:
        # Check if lock file exists
        if not lock.lock_file.exists():
            return None

        # Check if stale
        if lock._is_stale_lock():
            return None

        # Read lock info
        with open(lock.lock_file, 'r', encoding='utf-8') as f:
            content = f.read().strip()

        if content:
            return json.loads(content)

        return None

    except Exception as e:
        logger.error(f"Failed to check if running: {e}")
        return None


if __name__ == "__main__":
    import sys

    # Test
    if len(sys.argv) < 2:
        print("Usage: python singleton.py <name>")
        sys.exit(1)

    name = sys.argv[1]

    print(f"Testing singleton lock for: {name}")

    # Check if already running
    info = is_running(name)
    if info:
        print(f"Already running: PID={info.get('pid')}, started={info.get('start_time_str')}")
    else:
        print("Not running")

    # Try to acquire lock
    try:
        with SingletonLock(name) as lock:
            print(f"Lock acquired! PID={os.getpid()}")
            print("Press Ctrl+C to release...")

            # Keep running
            while True:
                time.sleep(1)

    except RuntimeError as e:
        print(f"Failed to acquire lock: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nReleasing lock...")
