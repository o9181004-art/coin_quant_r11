#!/usr/bin/env python3
"""
Startup Guards - Hard Fail Fast
================================
Preflight checks that must pass before service starts.

Guards:
- Writeability test (shared_data must be writable)
- PID singleton (no duplicate processes)
- Directory structure (critical folders exist)
"""

import logging
import os
import sys
import time
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)


def test_writeability(directory: Path) -> bool:
    """
    Test if directory is writable via atomic write test.

    Args:
        directory: Directory to test

    Returns:
        True if writable, False otherwise
    """
    from shared.io_safe import atomic_write

    test_file = directory / f".writetest_{uuid.uuid4().hex[:8]}.tmp"

    try:
        # Attempt write
        result = atomic_write(test_file, b"test", max_attempts=3)

        # Clean up
        if test_file.exists():
            test_file.unlink()

        return result.success

    except Exception as e:
        logger.error(f"Writeability test failed: {e}")
        return False


def check_pid_singleton(service_name: str, pid_file: Path) -> bool:
    """
    Check if another instance of this service is running.

    Args:
        service_name: Service name for logging
        pid_file: PID file path

    Returns:
        True if this is the only instance, False if duplicate detected
    """
    import psutil

    # Create PID file parent
    pid_file.parent.mkdir(parents=True, exist_ok=True)

    # Check if PID file exists
    if pid_file.exists():
        try:
            with open(pid_file, "r") as f:
                old_pid = int(f.read().strip())

            # Check if process is still alive
            if psutil.pid_exists(old_pid):
                try:
                    proc = psutil.Process(old_pid)
                    if proc.is_running():
                        logger.error(
                            f"DUPLICATE_PROCESS: Another {service_name} instance "
                            f"is running (PID {old_pid})"
                        )
                        return False
                except psutil.NoSuchProcess:
                    pass  # Process died, continue

        except Exception as e:
            logger.warning(f"Failed to read old PID file: {e}")

    # Write our PID
    try:
        from shared.io_safe import atomic_write

        current_pid = os.getpid()
        result = atomic_write(pid_file, str(current_pid).encode())

        if result.success:
            logger.info(f"{service_name} PID {current_pid} registered")
            return True
        else:
            logger.error(f"Failed to write PID file: {result.error}")
            return False

    except Exception as e:
        logger.error(f"PID singleton check failed: {e}")
        return False


def ensure_directory_structure() -> bool:
    """
    Ensure critical directory structure exists.

    Returns:
        True if all directories exist or were created
    """
    critical_dirs = [
        "shared_data",
        "shared_data/health",
        "shared_data/history",
        "shared_data/positions",
        "shared_data/trades",
        "shared_data/snapshots",
        "logs",
        "logs/audit",
        "logs/migrations",
    ]

    try:
        for dir_path in critical_dirs:
            Path(dir_path).mkdir(parents=True, exist_ok=True)

        logger.info(f"Directory structure validated ({len(critical_dirs)} dirs)")
        return True

    except Exception as e:
        logger.error(f"Failed to create directory structure: {e}")
        return False


def run_startup_guards(service_name: str, pid_file: Path) -> bool:
    """
    Run all startup guards.

    Args:
        service_name: Service name
        pid_file: PID file for singleton check

    Returns:
        True if all guards pass, False otherwise

    Side Effects:
        Exits process if any guard fails
    """
    print("=" * 60)
    print(f"{service_name} - Startup Guards")
    print("=" * 60)

    # Guard 1: Directory structure
    print("\n[1/3] Ensuring directory structure...")
    if not ensure_directory_structure():
        print("❌ FAILED: Cannot create directory structure")
        sys.exit(1)
    print("✅ OK: Directory structure ready")

    # Guard 2: Writeability test
    print("\n[2/3] Testing writeability...")
    if not test_writeability(Path("shared_data")):
        print("❌ FAILED: shared_data is not writable")
        print("   Check permissions and AV interference")
        print(f"   Path: {Path('shared_data').absolute()}")
        sys.exit(1)
    print("✅ OK: shared_data is writable")

    # Guard 3: PID singleton
    print("\n[3/3] Checking for duplicate processes...")
    if not check_pid_singleton(service_name, pid_file):
        print(f"❌ FAILED: Another {service_name} is already running")
        print(f"   Action: Stop other instance first")
        sys.exit(1)
    print(f"✅ OK: No duplicate {service_name} detected")

    print("\n" + "=" * 60)
    print(f"✅ All startup guards passed for {service_name}")
    print("=" * 60)

    return True


# ====================================================
# Testing
# ====================================================
if __name__ == "__main__":
    # Test guards
    test_pid = Path("shared_data") / "test_service.pid"

    try:
        run_startup_guards("TEST_SERVICE", test_pid)
        print("\n✅ Startup guards test passed")
    finally:
        # Cleanup
        if test_pid.exists():
            test_pid.unlink()

