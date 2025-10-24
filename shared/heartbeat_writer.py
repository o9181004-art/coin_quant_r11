#!/usr/bin/env python3
"""
Heartbeat Writer
========================================
Write component heartbeat files for dashboard monitoring.

Features:
- Write health/{component}.json every 5s
- Atomic writes
- Schema: {ts, status, message}
"""

import time
from pathlib import Path
from typing import Dict

from shared.io_atomic import atomic_write_json


class HeartbeatWriter:
    """Component heartbeat writer"""

    def __init__(self, component: str, interval_sec: float = 5.0):
        """
        Initialize heartbeat writer.

        Args:
            component: Component name (feeder, trader, ares)
            interval_sec: Heartbeat interval (default: 5s)
        """
        self.component = component
        self.interval_sec = interval_sec

        self.health_dir = Path("shared_data/health")
        self.health_file = self.health_dir / f"{component}.json"

        self.last_heartbeat = 0

    def write_heartbeat(self, status: str, message: str = ""):
        """
        Write heartbeat if interval elapsed.

        Args:
            status: Status (GREEN, YELLOW, RED, DEGRADED, ERROR)
            message: Optional status message

        Returns:
            True if written, False if debounced
        """
        now = time.time()

        # Check interval
        if now - self.last_heartbeat < self.interval_sec:
            return False

        # Prepare data
        heartbeat_data = {
            "ts": now,
            "status": status,
            "message": message,
            "component": self.component,
        }

        # Write atomically
        success = atomic_write_json(
            self.health_file,
            heartbeat_data,
            debounce=False,  # We handle debounce ourselves
        )

        if success:
            self.last_heartbeat = now

        return success

    def force_write(self, status: str, message: str = ""):
        """
        Force write heartbeat (ignore interval).

        Args:
            status: Status
            message: Message
        """
        heartbeat_data = {
            "ts": time.time(),
            "status": status,
            "message": message,
            "component": self.component,
        }

        atomic_write_json(self.health_file, heartbeat_data, debounce=False)

        self.last_heartbeat = time.time()


# Unit tests
if __name__ == "__main__":
    import json
    import shutil
    import tempfile

    print("Testing HeartbeatWriter...")

    test_dir = Path(tempfile.mkdtemp())

    try:
        # Override health dir for testing
        import shared.heartbeat_writer as hb_module

        original_dir = hb_module.Path("shared_data/health")

        # Test 1: Write heartbeat
        print("\n1. Write heartbeat:")

        writer = HeartbeatWriter("test_component", interval_sec=1.0)
        writer.health_dir = test_dir
        writer.health_file = test_dir / "test_component.json"

        success = writer.write_heartbeat("GREEN", "All systems go")
        assert success, "First write should succeed"

        # Verify file
        assert writer.health_file.exists(), "File should exist"

        with open(writer.health_file, "r") as f:
            data = json.load(f)

        assert data["status"] == "GREEN", "Status should match"
        assert data["component"] == "test_component", "Component should match"
        print("✅ Write heartbeat works")

        # Test 2: Debounce
        print("\n2. Debounce (interval):")

        success2 = writer.write_heartbeat("YELLOW", "Warning")
        assert not success2, "Immediate second write should be debounced"
        print("✅ Debounce works")

        # Test 3: After interval
        print("\n3. After interval:")

        time.sleep(1.1)  # Wait > 1s

        success3 = writer.write_heartbeat("RED", "Error")
        assert success3, "Write after interval should succeed"

        with open(writer.health_file, "r") as f:
            data = json.load(f)

        assert data["status"] == "RED", "Status should update"
        print("✅ Interval write works")

        # Test 4: Force write
        print("\n4. Force write:")

        writer.force_write("GREEN", "Forced")

        with open(writer.health_file, "r") as f:
            data = json.load(f)

        assert data["message"] == "Forced", "Should force write"
        print("✅ Force write works")

        print("\n" + "=" * 50)
        print("All heartbeat writer tests passed! ✅")
        print("=" * 50)

    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
