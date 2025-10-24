#!/usr/bin/env python3
"""
Trader Reader - Tolerant Parsing & Precise Diagnostics
Reads Feeder snapshots with robust error handling and clear reason codes
"""

import json
import logging
import time
from enum import Enum
from pathlib import Path
from typing import Dict, Optional, Tuple

try:
    from .path_registry import get_absolute_path
except ImportError:
    from path_registry import get_absolute_path

logger = logging.getLogger(__name__)


class SnapshotStatus(Enum):
    """Snapshot status codes with precise diagnostics"""

    OK = "OK"
    HEALTH_BAD_JSON = "HEALTH_BAD_JSON"
    SNAPSHOT_MISSING_TS = "SNAPSHOT_MISSING_TS"
    SNAPSHOT_ZERO_TIMESTAMP = "SNAPSHOT_ZERO_TIMESTAMP"
    WATCHLIST_MISMATCH = "WATCHLIST_MISMATCH"
    NO_ORDERBOOK_DATA = "NO_ORDERBOOK_DATA"
    STALE = "STALE"
    MISSING = "MISSING"


def read_json_tolerant(file_path: Path) -> Tuple[Optional[Dict], Optional[str]]:
    """
    Read JSON file with tolerance for various issues.

    Returns:
        (data, error_reason)
    """
    if not file_path.exists():
        return None, "MISSING"

    try:
        with open(file_path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        return data, None
    except json.JSONDecodeError as e:
        return None, f"BAD_JSON: {e}"
    except Exception as e:
        return None, f"READ_ERROR: {e}"


def extract_timestamp(data: Dict) -> Tuple[Optional[int], Optional[str]]:
    """
    Extract timestamp from data, preferring 'ts' over 'timestamp'.
    Handles ms → s conversion.

    Returns:
        (timestamp_seconds, error_reason)
    """
    # Prefer 'ts', fall back to 'timestamp'
    ts = data.get("ts") or data.get("timestamp")

    if ts is None:
        return None, "MISSING_TS"

    if not isinstance(ts, (int, float)):
        return None, f"INVALID_TS_TYPE: {type(ts)}"

    ts = int(ts)

    if ts == 0:
        return None, "ZERO_TIMESTAMP"

    # Convert ms → s if needed
    if ts > 1e10:
        logger.warning(f"Converting ms → s: {ts} → {ts // 1000}")
        ts = ts // 1000

    return ts, None


def check_snapshot_status(
    symbol: str, max_age_seconds: int = 60, require_orderbook: bool = True
) -> Tuple[SnapshotStatus, Optional[str]]:
    """
    Check symbol snapshot status with precise diagnostics.

    Args:
        symbol: Trading symbol (UPPERCASE)
        max_age_seconds: Max allowed age
        require_orderbook: Whether to require orderbook data

    Returns:
        (status, details)
    """
    symbol = symbol.upper()
    snapshots_dir = get_absolute_path("shared_data", "snapshots")
    snapshot_file = snapshots_dir / f"prices_{symbol}.json"

    # Read file
    data, error = read_json_tolerant(snapshot_file)

    if data is None:
        if error == "MISSING":
            return SnapshotStatus.MISSING, f"File not found: {snapshot_file}"
        else:
            return SnapshotStatus.HEALTH_BAD_JSON, error

    # Extract timestamp
    ts, error = extract_timestamp(data)

    if ts is None:
        if error == "MISSING_TS":
            return SnapshotStatus.SNAPSHOT_MISSING_TS, "No 'ts' or 'timestamp' field"
        elif error == "ZERO_TIMESTAMP":
            return SnapshotStatus.SNAPSHOT_ZERO_TIMESTAMP, "Timestamp is 0"
        else:
            return SnapshotStatus.SNAPSHOT_MISSING_TS, error

    # Check age
    now = time.time()
    age = now - ts

    if age > max_age_seconds:
        return SnapshotStatus.STALE, f"Age {age:.1f}s > {max_age_seconds}s"

    # Check orderbook (if required)
    if require_orderbook:
        ob = data.get("orderbook")
        if not ob or not isinstance(ob, dict):
            return SnapshotStatus.NO_ORDERBOOK_DATA, "Missing orderbook field"

        bids = ob.get("bids", [])
        asks = ob.get("asks", [])

        if not isinstance(bids, list) or not isinstance(asks, list):
            return SnapshotStatus.NO_ORDERBOOK_DATA, "Orderbook not list"

        if len(bids) == 0 or len(asks) == 0:
            # Fresh timestamp but empty OB - this is NO_ORDERBOOK_DATA, not a restart trigger
            return (
                SnapshotStatus.NO_ORDERBOOK_DATA,
                f"Empty OB (bids={len(bids)}, asks={len(asks)})",
            )

    return SnapshotStatus.OK, f"Fresh (age={age:.1f}s)"


def should_restart_feeder(status: SnapshotStatus) -> bool:
    """
    Determine if Feeder should be restarted based on snapshot status.

    Policy:
    - RESTART: HEALTH_BAD_JSON, SNAPSHOT_MISSING_TS, SNAPSHOT_ZERO_TIMESTAMP, STALE
    - NO RESTART: NO_ORDERBOOK_DATA (just warn), OK
    - MISSING: Log error but don't restart (might be initializing)
    """
    restart_statuses = {
        SnapshotStatus.HEALTH_BAD_JSON,
        SnapshotStatus.SNAPSHOT_MISSING_TS,
        SnapshotStatus.SNAPSHOT_ZERO_TIMESTAMP,
        SnapshotStatus.STALE,
    }

    return status in restart_statuses


if __name__ == "__main__":
    # Self-test
    print("Testing trader reader...")

    from feeder_egress_writer import write_symbol_snapshot

    # Test 1: Fresh snapshot with OB
    write_symbol_snapshot(
        symbol="TESTUSDT",
        last_price=100.0,
        orderbook={"bids": [[100.0, 1.0]], "asks": [[101.0, 1.0]]},
    )

    status, details = check_snapshot_status("TESTUSDT", max_age_seconds=60)
    print(f"Test 1 (fresh with OB): {status.value} - {details}")
    assert status == SnapshotStatus.OK
    assert not should_restart_feeder(status)

    # Test 2: Fresh snapshot but NO OB
    write_symbol_snapshot(
        symbol="TESTUSDT",
        last_price=100.0,
        orderbook={"bids": [], "asks": []},  # Empty
    )

    status, details = check_snapshot_status("TESTUSDT", max_age_seconds=60)
    print(f"Test 2 (fresh NO OB): {status.value} - {details}")
    assert status == SnapshotStatus.NO_ORDERBOOK_DATA
    assert not should_restart_feeder(status), "Should NOT restart on NO_ORDERBOOK_DATA"

    # Test 3: Missing file
    status, details = check_snapshot_status("NONEXISTENT", max_age_seconds=60)
    print(f"Test 3 (missing): {status.value} - {details}")
    assert status == SnapshotStatus.MISSING

    # Clean up
    snapshots_dir = get_absolute_path("shared_data", "snapshots")
    test_file = snapshots_dir / "prices_TESTUSDT.json"
    if test_file.exists():
        test_file.unlink()

    print("\n✅ Trader reader works!")
