#!/usr/bin/env python3
"""
Per-Symbol Snapshot Writer
Writes individual snapshot files for each symbol: shared_data/snapshots/prices_{SYMBOL}.json
"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .atomic_io import atomic_write
except ImportError:
    from atomic_io import atomic_write

try:
    from .path_registry import get_absolute_path
except ImportError:
    from path_registry import get_absolute_path

logger = logging.getLogger(__name__)


def write_symbol_snapshot(
    symbol: str,
    orderbook: Optional[Dict[str, List]] = None,
    last_kline_ts: Optional[int] = None,
    additional_data: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Write per-symbol snapshot file.

    File: shared_data/snapshots/prices_{SYMBOL}.json
    Structure:
    {
        "symbol": "BTCUSDT",
        "timestamp": <unix_seconds>,
        "orderbook": {
            "bids": [[price, qty], ...],
            "asks": [[price, qty], ...]
        },
        "last_kline_ts": <unix_seconds>,
        "state": "ACTIVE" | "STALE_NO_OB" | "DISCONNECTED"
    }

    Args:
        symbol: Trading symbol (UPPERCASE)
        orderbook: Orderbook data {"bids": [...], "asks": [...]}
        last_kline_ts: Last kline timestamp (unix seconds)
        additional_data: Additional fields to include

    Returns:
        True if write succeeded, False otherwise
    """
    try:
        # Validate symbol
        symbol = symbol.upper().strip()
        if not symbol or not symbol.endswith("USDT"):
            logger.error(f"Invalid symbol for snapshot: {symbol}")
            return False

        # Ensure snapshots directory
        snapshots_dir = get_absolute_path("shared_data", "snapshots")
        snapshots_dir.mkdir(parents=True, exist_ok=True)

        snapshot_file = snapshots_dir / f"prices_{symbol}.json"

        # Build snapshot data
        now_ts = int(time.time())

        snapshot = {
            "symbol": symbol,
            "timestamp": now_ts,  # Always fresh timestamp
        }

        # Add orderbook
        if orderbook and isinstance(orderbook, dict):
            bids = orderbook.get("bids", [])
            asks = orderbook.get("asks", [])

            snapshot["orderbook"] = {
                "bids": bids if isinstance(bids, list) else [],
                "asks": asks if isinstance(asks, list) else [],
            }

            # Determine state
            has_bids = len(snapshot["orderbook"]["bids"]) > 0
            has_asks = len(snapshot["orderbook"]["asks"]) > 0

            if has_bids and has_asks:
                snapshot["state"] = "ACTIVE"
            else:
                snapshot["state"] = "STALE_NO_OB"
                logger.warning(
                    f"[{symbol}] No orderbook data (bids={has_bids}, asks={has_asks})"
                )
        else:
            snapshot["orderbook"] = {"bids": [], "asks": []}
            snapshot["state"] = "STALE_NO_OB"
            logger.warning(f"[{symbol}] No orderbook provided")

        # Add last_kline_ts
        if last_kline_ts and isinstance(last_kline_ts, (int, float)):
            # Normalize to seconds
            if last_kline_ts > 1e10:
                last_kline_ts = int(last_kline_ts / 1000)
            snapshot["last_kline_ts"] = int(last_kline_ts)
        else:
            snapshot["last_kline_ts"] = now_ts

        # Add additional data
        if additional_data and isinstance(additional_data, dict):
            for key, value in additional_data.items():
                if key not in snapshot:  # Don't overwrite core fields
                    snapshot[key] = value

        # Write atomically
        json_str = json.dumps(snapshot, indent=2, ensure_ascii=False)
        atomic_write(snapshot_file, json_str, make_backup=False)

        logger.debug(
            f"[{symbol}] Snapshot written: ts={now_ts}, state={snapshot.get('state')}"
        )
        return True

    except Exception as e:
        logger.error(f"Failed to write snapshot for {symbol}: {e}")
        return False


def read_symbol_snapshot(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Read per-symbol snapshot file.

    Args:
        symbol: Trading symbol (UPPERCASE)

    Returns:
        Snapshot data or None if not found/invalid
    """
    try:
        symbol = symbol.upper().strip()
        snapshots_dir = get_absolute_path("shared_data", "snapshots")
        snapshot_file = snapshots_dir / f"prices_{symbol}.json"

        if not snapshot_file.exists():
            return None

        with open(snapshot_file, "r", encoding="utf-8-sig") as f:
            data = json.load(f)

        return data if isinstance(data, dict) else None

    except Exception as e:
        logger.error(f"Failed to read snapshot for {symbol}: {e}")
        return None


def get_snapshot_age(symbol: str) -> Optional[float]:
    """
    Get age of symbol snapshot in seconds.

    Args:
        symbol: Trading symbol (UPPERCASE)

    Returns:
        Age in seconds, or None if snapshot not found
    """
    snapshot = read_symbol_snapshot(symbol)
    if not snapshot:
        return None

    ts = snapshot.get("timestamp")
    if not ts or not isinstance(ts, (int, float)):
        return None

    now = time.time()
    age = now - ts

    return age


def check_symbol_snapshot_fresh(symbol: str, max_age_seconds: int = 60) -> bool:
    """
    Check if symbol snapshot is fresh (within max_age_seconds).

    Args:
        symbol: Trading symbol (UPPERCASE)
        max_age_seconds: Maximum allowed age in seconds

    Returns:
        True if fresh, False otherwise
    """
    age = get_snapshot_age(symbol)
    if age is None:
        return False

    return age <= max_age_seconds


if __name__ == "__main__":
    # Self-test
    test_symbol = "TESTUSDT"

    # Write test snapshot
    success = write_symbol_snapshot(
        symbol=test_symbol,
        orderbook={
            "bids": [[100.5, 1.0], [100.4, 2.0]],
            "asks": [[100.6, 1.5], [100.7, 2.5]],
        },
        last_kline_ts=int(time.time()),
    )

    print(f"Write test: {success}")
    assert success, "Write should succeed"

    # Read test snapshot
    snapshot = read_symbol_snapshot(test_symbol)
    print(f"Read test: {snapshot is not None}")
    assert snapshot is not None, "Read should succeed"
    assert snapshot["symbol"] == test_symbol, "Symbol should match"
    assert "timestamp" in snapshot, "Should have timestamp"
    assert "orderbook" in snapshot, "Should have orderbook"

    # Check age
    age = get_snapshot_age(test_symbol)
    print(f"Age test: {age}s")
    assert age is not None, "Age should be available"
    assert age < 5, "Age should be very recent"

    # Check freshness
    is_fresh = check_symbol_snapshot_fresh(test_symbol, max_age_seconds=60)
    print(f"Freshness test: {is_fresh}")
    assert is_fresh, "Should be fresh"

    # Clean up
    snapshots_dir = get_absolute_path("shared_data", "snapshots")
    test_file = snapshots_dir / f"prices_{test_symbol}.json"
    if test_file.exists():
        test_file.unlink()

    print("✅ All tests passed")
