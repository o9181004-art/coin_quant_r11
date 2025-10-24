#!/usr/bin/env python3
"""
Unified Data Source (UDS) Configuration
========================================
Single source of truth for databus snapshot path.

Features:
- Configurable via UDS_SNAPSHOT_PATH env
- Default: shared_data/databus_snapshot.json
- Logged at startup (absolute path)
"""

import os
from pathlib import Path


def get_uds_snapshot_path() -> Path:
    """
    Get UDS snapshot path from environment or default.

    Returns:
        Absolute path to UDS snapshot file
    """
    # Check environment variable
    env_path = os.getenv("UDS_SNAPSHOT_PATH")

    if env_path:
        return Path(env_path).absolute()

    # Default path
    return Path("shared_data/databus_snapshot.json").absolute()


def log_uds_config(service_name: str):
    """
    Log UDS configuration at startup.

    Args:
        service_name: Service name (Feeder, Trader, etc.)
    """
    uds_path = get_uds_snapshot_path()

    print(f"[{service_name}] UDS Snapshot Path: {uds_path}")
    print(f"[{service_name}] UDS exists: {uds_path.exists()}")

    if uds_path.exists():
        try:
            import json
            import time

            with open(uds_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            ts = data.get("ts", 0)

            if ts > 0:
                # Convert to seconds if milliseconds
                if ts > 1e12:
                    ts = ts / 1000.0

                age = time.time() - ts
                print(f"[{service_name}] UDS ts: {ts:.3f}, age: {age:.1f}s")
            else:
                print(f"[{service_name}] UDS ts: 0 (awaiting data)")

        except Exception as e:
            print(f"[{service_name}] UDS read error: {e}")


# Unit tests
if __name__ == "__main__":
    import json
    import tempfile
    import time

    print("Testing UDS configuration...")

    # Test 1: Default path
    print("\n1. Default path:")
    default_path = get_uds_snapshot_path()
    print(f"Default: {default_path}")
    assert "databus_snapshot.json" in str(default_path), "Should use default"
    print("✅ Default path works")

    # Test 2: Custom path via env
    print("\n2. Custom path via env:")
    os.environ["UDS_SNAPSHOT_PATH"] = "custom/path/snapshot.json"
    custom_path = get_uds_snapshot_path()
    print(f"Custom: {custom_path}")
    assert "custom" in str(custom_path), "Should use custom path"

    # Cleanup env
    del os.environ["UDS_SNAPSHOT_PATH"]
    print("✅ Custom path works")

    # Test 3: Log UDS config
    print("\n3. Log UDS config:")

    # Create temp UDS file
    test_dir = Path(tempfile.mkdtemp())
    test_uds = test_dir / "test_snapshot.json"

    test_data = {
        "ts": int(time.time() * 1000),
        "status": "LIVE",
        "symbols": ["btcusdt", "ethusdt"],
    }

    with open(test_uds, "w", encoding="utf-8") as f:
        json.dump(test_data, f)

    os.environ["UDS_SNAPSHOT_PATH"] = str(test_uds)

    log_uds_config("TestService")

    del os.environ["UDS_SNAPSHOT_PATH"]

    # Cleanup
    import shutil

    shutil.rmtree(test_dir, ignore_errors=True)

    print("✅ Log config works")

    print("\n" + "=" * 50)
    print("All UDS config tests passed! ✅")
    print("=" * 50)
