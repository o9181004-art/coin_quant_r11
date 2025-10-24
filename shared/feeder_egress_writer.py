#!/usr/bin/env python3
"""
Feeder Egress Writer
Canonical timestamp enforcement (ts + timestamp) with schema validation
"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .atomic_io import atomic_write
    from .path_registry import get_absolute_path
except ImportError:
    from atomic_io import atomic_write
    from path_registry import get_absolute_path

logger = logging.getLogger(__name__)

# Feature flags (configurable via env)
import os

FEEDER_ENFORCE_TS = os.getenv("FEEDER_ENFORCE_TS", "1") == "1"
FEEDER_WRITE_TIMESTAMP = os.getenv("FEEDER_WRITE_TIMESTAMP", "1") == "1"


def canonical_timestamp() -> Dict[str, int]:
    """
    Get canonical timestamp dict with both ts and timestamp (backward compat).

    Returns:
        {"ts": <unix_seconds>, "timestamp": <unix_seconds>}
    """
    now = int(time.time())
    return {"ts": now, "timestamp": now}


def normalize_timestamp(value: Any) -> Optional[int]:
    """
    Normalize timestamp value to unix seconds.
    Handles ms → s conversion.

    Args:
        value: Timestamp value (can be int, float, or None)

    Returns:
        Unix seconds (int) or None if invalid
    """
    if value is None:
        return None

    if not isinstance(value, (int, float)):
        logger.warning(f"Invalid timestamp type: {type(value)}")
        return None

    # Convert to int
    ts = int(value)

    # If > 1e10, assume milliseconds
    if ts > 1e10:
        logger.warning(f"Converting ms → s: {ts} → {ts // 1000}")
        ts = ts // 1000

    return ts


def validate_health_schema(data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate health.json schema.

    Required:
    {
        "service": "feeder",
        "status": "GREEN" | "YELLOW" | "RED",
        "ts": <int>,
        "timestamp": <int>,
        "stale": <bool>
    }

    Returns:
        (is_valid, error_message)
    """
    if not isinstance(data, dict):
        return False, f"Must be dict, got {type(data)}"

    # Check required fields
    required = ["service", "status", "ts", "stale"]
    for field in required:
        if field not in data:
            return False, f"Missing required field: {field}"

    # Validate service
    if data["service"] != "feeder":
        return False, f"service must be 'feeder', got {data['service']}"

    # Validate status
    if data["status"] not in ["GREEN", "YELLOW", "RED"]:
        return False, f"status must be GREEN/YELLOW/RED, got {data['status']}"

    # Validate ts
    ts = data["ts"]
    if not isinstance(ts, int):
        return False, f"ts must be int, got {type(ts)}"

    if ts > 1e10:
        return False, f"ts appears to be milliseconds: {ts}"

    # Validate stale
    if not isinstance(data["stale"], bool):
        return False, f"stale must be bool, got {type(data['stale'])}"

    # Validate timestamp (if present)
    if "timestamp" in data:
        timestamp = data["timestamp"]
        if not isinstance(timestamp, int):
            return False, f"timestamp must be int, got {type(timestamp)}"

    return True, None


def validate_databus_schema(data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate databus_snapshot.json schema.

    Required:
    {
        "ts": <int>,
        "timestamp": <int>,
        "symbols": ["BTCUSDT", ...],
        "stale": <bool>,
        "source": "feeder"
    }

    Returns:
        (is_valid, error_message)
    """
    if not isinstance(data, dict):
        return False, f"Must be dict, got {type(data)}"

    # Check required fields
    required = ["ts", "symbols", "stale", "source"]
    for field in required:
        if field not in data:
            return False, f"Missing required field: {field}"

    # Validate ts
    ts = data["ts"]
    if not isinstance(ts, int):
        return False, f"ts must be int, got {type(ts)}"

    if ts > 1e10:
        return False, f"ts appears to be milliseconds: {ts}"

    # Validate symbols
    symbols = data["symbols"]
    if not isinstance(symbols, list):
        return False, f"symbols must be list, got {type(symbols)}"

    for sym in symbols:
        if not isinstance(sym, str):
            return False, f"Symbol must be string, got {type(sym)}"
        if sym != sym.upper():
            return False, f"Symbol must be UPPERCASE: {sym}"

    # Validate stale
    if not isinstance(data["stale"], bool):
        return False, f"stale must be bool, got {type(data['stale'])}"

    # Validate source
    if data["source"] != "feeder":
        return False, f"source must be 'feeder', got {data['source']}"

    return True, None


def validate_symbol_snapshot_schema(data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate prices_{SYMBOL}.json schema.

    Required:
    {
        "symbol": "BTCUSDT",
        "ts": <int>,
        "timestamp": <int>,
        "last_price": <number>,
        "orderbook": {"bids": [...], "asks": [...]},
        "source": "feeder"
    }

    Returns:
        (is_valid, error_message)
    """
    if not isinstance(data, dict):
        return False, f"Must be dict, got {type(data)}"

    # Check required fields
    required = ["symbol", "ts", "source"]
    for field in required:
        if field not in data:
            return False, f"Missing required field: {field}"

    # Validate symbol
    symbol = data["symbol"]
    if not isinstance(symbol, str):
        return False, f"symbol must be string, got {type(symbol)}"

    if symbol != symbol.upper():
        return False, f"symbol must be UPPERCASE: {symbol}"

    if not symbol.endswith("USDT"):
        return False, f"symbol must end with USDT: {symbol}"

    # Validate ts
    ts = data["ts"]
    if not isinstance(ts, int):
        return False, f"ts must be int, got {type(ts)}"

    if ts > 1e10:
        return False, f"ts appears to be milliseconds: {ts}"

    # Validate source
    if data["source"] != "feeder":
        return False, f"source must be 'feeder', got {data['source']}"

    # Validate orderbook (if present)
    if "orderbook" in data:
        ob = data["orderbook"]
        if not isinstance(ob, dict):
            return False, f"orderbook must be dict, got {type(ob)}"

        for side in ["bids", "asks"]:
            if side in ob:
                if not isinstance(ob[side], list):
                    return False, f"orderbook.{side} must be list, got {type(ob[side])}"

    return True, None


def write_health_snapshot(
    status: str = "GREEN",
    stale: bool = False,
    components: Optional[Dict] = None,
    telemetry: Optional[Dict] = None,
) -> bool:
    """
    Write health.json with canonical timestamp.

    Args:
        status: GREEN/YELLOW/RED
        stale: Stale flag
        components: Optional components data
        telemetry: Optional telemetry data

    Returns:
        True if written successfully
    """
    try:
        # Build data
        data = {
            "service": "feeder",
            "status": status,
            **canonical_timestamp(),
            "stale": stale,
        }

        if components:
            data["components"] = components

        if telemetry:
            data["telemetry"] = telemetry

        # Validate
        if FEEDER_ENFORCE_TS:
            is_valid, error = validate_health_schema(data)
            if not is_valid:
                logger.error(f"WRITE_SKIPPED_BAD_SCHEMA(health.json): {error}")
                return False

        # Write
        health_file = get_absolute_path("shared_data", "health.json")
        json_str = json.dumps(data, indent=2, ensure_ascii=False)
        atomic_write(health_file, json_str, make_backup=False)

        # Also write uds.json
        uds_dir = get_absolute_path("shared_data", "health")
        uds_dir.mkdir(parents=True, exist_ok=True)
        uds_file = uds_dir / "uds.json"
        atomic_write(uds_file, json_str, make_backup=False)

        logger.debug(f"Health snapshot written: status={status}, stale={stale}")
        return True

    except Exception as e:
        logger.error(f"Failed to write health snapshot: {e}")
        return False


def write_databus_snapshot(
    symbols: List[str],
    stale: bool = False,
    additional_data: Optional[Dict] = None,
) -> bool:
    """
    Write databus_snapshot.json with canonical timestamp.

    Args:
        symbols: List of symbols (will be uppercased)
        stale: Stale flag
        additional_data: Optional additional fields

    Returns:
        True if written successfully
    """
    try:
        # Normalize symbols
        symbols = [s.upper() for s in symbols if s]
        symbols = sorted(list(set(symbols)))  # Deduplicate and sort

        # Build data
        data = {
            **canonical_timestamp(),
            "symbols": symbols,
            "stale": stale,
            "source": "feeder",
        }

        if additional_data:
            for key, value in additional_data.items():
                if key not in data:  # Don't overwrite core fields
                    data[key] = value

        # Validate
        if FEEDER_ENFORCE_TS:
            is_valid, error = validate_databus_schema(data)
            if not is_valid:
                logger.error(
                    f"WRITE_SKIPPED_BAD_SCHEMA(databus_snapshot.json): {error}"
                )
                return False

        # Write
        databus_file = get_absolute_path("shared_data", "databus_snapshot.json")
        json_str = json.dumps(data, indent=2, ensure_ascii=False)
        atomic_write(databus_file, json_str, make_backup=False)

        logger.debug(f"Databus snapshot written: symbols={len(symbols)}, stale={stale}")
        return True

    except Exception as e:
        logger.error(f"Failed to write databus snapshot: {e}")
        return False


def write_symbol_snapshot(
    symbol: str,
    last_price: Optional[float] = None,
    orderbook: Optional[Dict[str, List]] = None,
    last_kline_ts: Optional[int] = None,
    additional_data: Optional[Dict] = None,
) -> bool:
    """
    Write prices_{SYMBOL}.json with canonical timestamp.

    Args:
        symbol: Trading symbol (will be uppercased)
        last_price: Last trade price
        orderbook: {"bids": [[p,q], ...], "asks": [[p,q], ...]}
        last_kline_ts: Last kline timestamp (unix seconds)
        additional_data: Optional additional fields

    Returns:
        True if written successfully
    """
    try:
        # Normalize symbol
        symbol = symbol.upper().strip()
        if not symbol or not symbol.endswith("USDT"):
            logger.error(f"Invalid symbol: {symbol}")
            return False

        # Build data
        data = {
            "symbol": symbol,
            **canonical_timestamp(),
            "source": "feeder",
        }

        if last_price is not None:
            data["last_price"] = last_price

        # Handle orderbook
        if orderbook and isinstance(orderbook, dict):
            bids = orderbook.get("bids", [])
            asks = orderbook.get("asks", [])

            data["orderbook"] = {
                "bids": bids if isinstance(bids, list) else [],
                "asks": asks if isinstance(asks, list) else [],
            }

            # Set state based on OB presence
            has_bids = len(data["orderbook"]["bids"]) > 0
            has_asks = len(data["orderbook"]["asks"]) > 0

            if not (has_bids and has_asks):
                data["orderbook_state"] = "STALE_NO_OB"
                logger.warning(
                    f"[{symbol}] Writing snapshot with empty OB (bids={has_bids}, asks={has_asks})"
                )
        else:
            data["orderbook"] = {"bids": [], "asks": []}
            data["orderbook_state"] = "STALE_NO_OB"

        if last_kline_ts is not None:
            data["last_kline_ts"] = normalize_timestamp(last_kline_ts) or data["ts"]

        if additional_data:
            for key, value in additional_data.items():
                if key not in data:
                    data[key] = value

        # Validate
        if FEEDER_ENFORCE_TS:
            is_valid, error = validate_symbol_snapshot_schema(data)
            if not is_valid:
                logger.error(f"WRITE_SKIPPED_BAD_SCHEMA(prices_{symbol}.json): {error}")
                return False

        # Write
        snapshots_dir = get_absolute_path("shared_data", "snapshots")
        snapshots_dir.mkdir(parents=True, exist_ok=True)
        snapshot_file = snapshots_dir / f"prices_{symbol}.json"

        json_str = json.dumps(data, indent=2, ensure_ascii=False)
        atomic_write(snapshot_file, json_str, make_backup=False)

        logger.debug(f"[{symbol}] Snapshot written: ts={data['ts']}")
        return True

    except Exception as e:
        logger.error(f"Failed to write snapshot for {symbol}: {e}")
        return False


if __name__ == "__main__":
    # Self-test
    print("Testing feeder egress writer...")

    # Test canonical timestamp
    ts_data = canonical_timestamp()
    print(f"✅ Canonical timestamp: {ts_data}")
    assert "ts" in ts_data
    assert "timestamp" in ts_data
    assert ts_data["ts"] == ts_data["timestamp"]

    # Test normalize_timestamp
    assert normalize_timestamp(1760253025) == 1760253025  # seconds
    assert normalize_timestamp(1760253025000) == 1760253025  # ms → s
    assert normalize_timestamp(None) is None
    print("✅ Timestamp normalization works")

    # Test write_health_snapshot
    success = write_health_snapshot(status="GREEN", stale=False)
    print(f"✅ Health snapshot write: {success}")

    # Test write_databus_snapshot
    success = write_databus_snapshot(symbols=["BTCUSDT", "ETHUSDT"], stale=False)
    print(f"✅ Databus snapshot write: {success}")

    # Test write_symbol_snapshot
    success = write_symbol_snapshot(
        symbol="BTCUSDT",
        last_price=100.5,
        orderbook={"bids": [[100.0, 1.0]], "asks": [[101.0, 1.0]]},
    )
    print(f"✅ Symbol snapshot write: {success}")

    print("\n✅ All tests passed!")
