#!/usr/bin/env python3
"""
UDS Health Checker
========================================
Check UDS (Unified Data Source) freshness and heartbeat.
"""

import json
import time
from pathlib import Path
from typing import Optional, Tuple

from shared.paths import HEALTH_UDS_PATH as UDS_HEALTH_PATH
from shared.paths import UDS_SNAPSHOT_PATH


def check_uds_health(ttl_sec: int = 30) -> Tuple[bool, str, dict]:
    """
    Check UDS health using heartbeat file.

    Args:
        ttl_sec: Maximum age in seconds before considering stale

    Returns:
        (is_healthy, status_message, details_dict)
    """
    now = time.time()
    details = {
        "heartbeat_age_sec": None,
        "snapshot_age_sec": None,
        "heartbeat_exists": False,
        "snapshot_exists": False,
    }

    # Check heartbeat file
    if UDS_HEALTH_PATH.exists():
        details["heartbeat_exists"] = True

        try:
            with open(UDS_HEALTH_PATH, "r", encoding="utf-8") as f:
                heartbeat = json.load(f)

            heartbeat_ts = heartbeat.get("ts", 0)

            if heartbeat_ts > 0:
                heartbeat_age = now - heartbeat_ts
                details["heartbeat_age_sec"] = int(heartbeat_age)

                if heartbeat_age > ttl_sec:
                    return (
                        False,
                        f"UDS heartbeat stale ({int(heartbeat_age)}s)",
                        details,
                    )
            else:
                details["heartbeat_age_sec"] = float("inf")
                return False, "UDS heartbeat ts=0 (invalid)", details

        except Exception as e:
            return False, f"UDS heartbeat read error: {e}", details

    else:
        return False, "UDS heartbeat missing", details

    # Check snapshot freshness (from embedded ts)
    if UDS_SNAPSHOT_PATH.exists():
        details["snapshot_exists"] = True

        try:
            with open(UDS_SNAPSHOT_PATH, "r", encoding="utf-8") as f:
                snapshot = json.load(f)

            snapshot_ts = snapshot.get("ts", 0)

            if snapshot_ts > 0:
                snapshot_age = now - snapshot_ts
                details["snapshot_age_sec"] = int(snapshot_age)

                if snapshot_age > ttl_sec:
                    return False, f"UDS snapshot stale ({int(snapshot_age)}s)", details
            else:
                # Fallback to file mtime
                try:
                    mtime = UDS_SNAPSHOT_PATH.stat().st_mtime
                    snapshot_age = now - mtime
                    details["snapshot_age_sec"] = int(snapshot_age)

                    if snapshot_age > ttl_sec:
                        return (
                            False,
                            f"UDS snapshot stale (mtime: {int(snapshot_age)}s)",
                            details,
                        )
                except:
                    details["snapshot_age_sec"] = float("inf")
                    return False, "UDS snapshot ts=0 and mtime unavailable", details

        except Exception as e:
            return False, f"UDS snapshot read error: {e}", details

    else:
        return False, "UDS snapshot missing", details

    # All checks passed
    return (
        True,
        f"UDS healthy (heartbeat: {details['heartbeat_age_sec']}s, snapshot: {details['snapshot_age_sec']}s)",
        details,
    )


def get_uds_age() -> Tuple[Optional[int], Optional[int]]:
    """
    Get UDS ages.

    Returns:
        (heartbeat_age_sec, snapshot_age_sec)
    """
    now = time.time()
    heartbeat_age = None
    snapshot_age = None

    # Heartbeat age
    if UDS_HEALTH_PATH.exists():
        try:
            with open(UDS_HEALTH_PATH, "r", encoding="utf-8") as f:
                heartbeat = json.load(f)

            ts = heartbeat.get("ts", 0)
            if ts > 0:
                heartbeat_age = int(now - ts)
        except:
            pass

    # Snapshot age
    if UDS_SNAPSHOT_PATH.exists():
        try:
            with open(UDS_SNAPSHOT_PATH, "r", encoding="utf-8") as f:
                snapshot = json.load(f)

            ts = snapshot.get("ts", 0)
            if ts > 0:
                snapshot_age = int(now - ts)
            else:
                # Fallback to mtime
                mtime = UDS_SNAPSHOT_PATH.stat().st_mtime
                snapshot_age = int(now - mtime)
        except:
            pass

    return heartbeat_age, snapshot_age


if __name__ == "__main__":
    # Test UDS health check
    print("=" * 60)
    print(" UDS Health Check")
    print("=" * 60)
    print()

    print(f"UDS Snapshot Path: {UDS_SNAPSHOT_PATH.absolute()}")
    print(f"UDS Health Path: {UDS_HEALTH_PATH.absolute()}")
    print()

    # Check health
    is_healthy, message, details = check_uds_health(ttl_sec=30)

    print(f"Status: {'✅ HEALTHY' if is_healthy else '❌ UNHEALTHY'}")
    print(f"Message: {message}")
    print()

    print("Details:")
    for key, value in details.items():
        print(f"  {key}: {value}")

    print()

    # Get ages
    hb_age, snap_age = get_uds_age()

    print("Ages:")
    print(f"  Heartbeat: {hb_age if hb_age is not None else 'N/A'}s")
    print(f"  Snapshot: {snap_age if snap_age is not None else 'N/A'}s")
