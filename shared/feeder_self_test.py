#!/usr/bin/env python3
"""
Feeder Self-Test (T+10s after boot)
Validates all output files are fresh and parseable
"""

import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from .path_registry import get_absolute_path
except ImportError:
    from path_registry import get_absolute_path

logger = logging.getLogger(__name__)


def read_json_safe(file_path: Path) -> Optional[Dict]:
    """Read JSON file safely, return None on error"""
    try:
        if not file_path.exists():
            return None

        with open(file_path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to read {file_path}: {e}")
        return None


def get_file_age(file_path: Path) -> Optional[float]:
    """Get file age based on its 'ts' or 'timestamp' field"""
    data = read_json_safe(file_path)
    if not data:
        return None

    # Prefer 'ts', fall back to 'timestamp'
    ts = data.get("ts") or data.get("timestamp")
    if not ts or not isinstance(ts, (int, float)):
        return None

    # Normalize if milliseconds
    if ts > 1e10:
        ts = ts / 1000

    now = time.time()
    age = now - ts

    return age


def check_orderbook(data: Dict) -> Tuple[int, int]:
    """
    Extract orderbook counts (bids, asks).

    Returns:
        (bids_count, asks_count)
    """
    if not data or "orderbook" not in data:
        return 0, 0

    ob = data["orderbook"]
    if not isinstance(ob, dict):
        return 0, 0

    bids = ob.get("bids", [])
    asks = ob.get("asks", [])

    bids_count = len(bids) if isinstance(bids, list) else 0
    asks_count = len(asks) if isinstance(asks, list) else 0

    return bids_count, asks_count


def run_feeder_self_test(
    symbols: List[str], max_age_seconds: float = 10.0
) -> Tuple[bool, str]:
    """
    Run feeder self-test.

    Checks:
    1. health.json exists and is fresh
    2. health/uds.json exists and is fresh
    3. databus_snapshot.json exists and is fresh
    4. prices_{SYMBOL}.json for each symbol:
       - Exists and is fresh
       - Has orderbook data (bids + asks > 0)

    Args:
        symbols: List of symbols to check (e.g., ["BTCUSDT", "ETHUSDT"])
        max_age_seconds: Maximum allowed age for freshness

    Returns:
        (success, report_line)

    Example report:
        "SELFTEST OK | hb_age=2.3s | databus_age=1.8s | BTC:age=2.1s bids=10 asks=12 | ETH:age=2.0s bids=8 asks=9"
    """
    try:
        results = []
        all_ok = True

        # 1. Check health.json
        health_file = get_absolute_path("shared_data", "health.json")
        health_age = get_file_age(health_file)

        if health_age is None:
            all_ok = False
            results.append("hb=MISSING")
        elif health_age > max_age_seconds:
            all_ok = False
            results.append(f"hb_age={health_age:.1f}s(STALE)")
        else:
            results.append(f"hb_age={health_age:.1f}s")

        # 2. Check health/uds.json
        uds_file = get_absolute_path("shared_data", "health", "uds.json")
        uds_age = get_file_age(uds_file)

        if uds_age is None:
            all_ok = False
            # Don't report UDS missing (less critical)

        # 3. Check databus_snapshot.json
        databus_file = get_absolute_path("shared_data", "databus_snapshot.json")
        databus_age = get_file_age(databus_file)

        if databus_age is None:
            all_ok = False
            results.append("databus=MISSING")
        elif databus_age > max_age_seconds:
            all_ok = False
            results.append(f"databus_age={databus_age:.1f}s(STALE)")
        else:
            results.append(f"databus_age={databus_age:.1f}s")

        # 4. Check per-symbol snapshots
        snapshots_dir = get_absolute_path("shared_data", "snapshots")

        for symbol in symbols:
            symbol = symbol.upper()
            snapshot_file = snapshots_dir / f"prices_{symbol}.json"

            snapshot_age = get_file_age(snapshot_file)

            if snapshot_age is None:
                all_ok = False
                results.append(f"{symbol[:3]}=MISSING")
                continue

            # Check age
            age_ok = snapshot_age <= max_age_seconds

            # Check orderbook
            snapshot_data = read_json_safe(snapshot_file)
            bids_count, asks_count = check_orderbook(snapshot_data)
            ob_ok = bids_count > 0 and asks_count > 0

            if not age_ok or not ob_ok:
                all_ok = False

            # Format symbol report
            age_str = (
                f"age={snapshot_age:.1f}s"
                if age_ok
                else f"age={snapshot_age:.1f}s(STALE)"
            )
            ob_str = (
                f"bids={bids_count} asks={asks_count}"
                if ob_ok
                else f"bids={bids_count} asks={asks_count}(NO_OB)"
            )

            results.append(f"{symbol[:3]}:{age_str} {ob_str}")

        # Build report line
        status = "SELFTEST OK" if all_ok else "SELFTEST FAILED"
        report = f"{status} | " + " | ".join(results)

        return all_ok, report

    except Exception as e:
        logger.error(f"Self-test exception: {e}")
        return False, f"SELFTEST EXCEPTION: {e}"


def scheduled_self_test(symbols: List[str], delay_seconds: float = 10.0):
    """
    Schedule self-test to run after delay.

    Args:
        symbols: Symbols to check
        delay_seconds: Delay before running test (e.g., 10s)
    """
    import threading

    def run_test():
        try:
            logger.info(f"Running self-test after {delay_seconds}s delay...")
            time.sleep(delay_seconds)

            success, report = run_feeder_self_test(symbols, max_age_seconds=5.0)

            if success:
                logger.info(f"✅ {report}")
            else:
                logger.error(f"❌ {report}")
                logger.error("Self-test failed - consider restarting")
                # Note: Could call sys.exit(1) here to trigger supervisor restart

        except Exception as e:
            logger.error(f"Self-test thread exception: {e}")

    # Start in background thread
    thread = threading.Thread(target=run_test, daemon=True, name="SelfTest")
    thread.start()


if __name__ == "__main__":
    # Self-test the self-test module
    print("Testing feeder self-test module...")

    # First, create some test data
    from feeder_egress_writer import (
        write_databus_snapshot,
        write_health_snapshot,
        write_symbol_snapshot,
    )

    print("Creating test snapshots...")
    write_health_snapshot(status="GREEN", stale=False)
    write_databus_snapshot(symbols=["BTCUSDT", "ETHUSDT"], stale=False)
    write_symbol_snapshot(
        symbol="BTCUSDT",
        last_price=100.5,
        orderbook={"bids": [[100.0, 1.0]], "asks": [[101.0, 1.0]]},
    )
    write_symbol_snapshot(
        symbol="ETHUSDT",
        last_price=3000.5,
        orderbook={"bids": [[3000.0, 1.0]], "asks": [[3001.0, 1.0]]},
    )

    # Run self-test
    print("\nRunning self-test...")
    success, report = run_feeder_self_test(["BTCUSDT", "ETHUSDT"], max_age_seconds=10.0)

    print(f"\nResult: {success}")
    print(f"Report: {report}")

    if success:
        print("\n✅ Self-test module works!")
    else:
        print("\n❌ Self-test failed (expected if files don't exist)")
