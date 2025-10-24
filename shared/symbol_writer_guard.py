#!/usr/bin/env python3
"""
Symbol Writer Guard - Enforce Uppercase at Source
=================================================
Helpers to ensure all data writers enforce uppercase symbols.

Usage:
    from shared.symbol_writer_guard import ensure_upper, guard_symbol_dict

    # Before writing
    symbol = ensure_upper(input_symbol)
    data = guard_symbol_dict(data, canonical_symbol)
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def ensure_upper(
    symbol: str, source: str = "unknown", abort_on_empty: bool = True
) -> str:
    """
    Ensure symbol is uppercase before writing.

    Args:
        symbol: Input symbol (any case)
        source: Source location for logging
        abort_on_empty: If True, raise on empty symbol; if False, return empty

    Returns:
        Uppercase symbol

    Raises:
        ValueError: If symbol is not a string or is empty (when abort_on_empty=True)
    """
    if not isinstance(symbol, str):
        error_msg = f"Symbol must be string, got {type(symbol)} (source: {source})"
        logger.error(f"❌ WRITER_GUARD: {error_msg}")
        if abort_on_empty:
            raise ValueError(error_msg)
        return ""

    if not symbol or not symbol.strip():
        error_msg = f"Symbol cannot be empty (source: {source})"
        logger.error(f"❌ WRITER_GUARD: {error_msg}")
        if abort_on_empty:
            raise ValueError(error_msg)
        return ""

    upper_symbol = symbol.strip().upper()

    # Validate it's a valid symbol format (alphanumeric, ends with USDT)
    if not upper_symbol.endswith("USDT"):
        # Throttled warning for invalid format
        from shared.pattern_mismatch_throttler import should_log_pattern_mismatch

        if should_log_pattern_mismatch(f"invalid_format_{upper_symbol}"):
            logger.warning(
                f"[WRITER_GUARD] Symbol doesn't end with USDT: '{upper_symbol}' (source: {source})"
            )

    # Log if conversion happened (throttled to 1 per symbol per 10 min)
    if symbol != upper_symbol:
        from shared.pattern_mismatch_throttler import should_log_pattern_mismatch

        if should_log_pattern_mismatch(f"conversion_{symbol}"):
            logger.warning(
                f"[WRITER_GUARD] Converted symbol at write: '{symbol}' → '{upper_symbol}' "
                f"(source: {source})"
            )

    return upper_symbol


def guard_symbol_dict(
    data: Dict[str, Any],
    canonical_symbol: str,
    source: str = "unknown",
    abort_on_invalid: bool = True,
) -> Dict[str, Any]:
    """
    Ensure "symbol" field in dict is uppercase canonical and non-empty.

    Args:
        data: Data dictionary
        canonical_symbol: Canonical uppercase symbol (derived from context)
        source: Source location for logging
        abort_on_invalid: If True, raise on invalid symbol

    Returns:
        Data with corrected symbol field

    Raises:
        ValueError: If canonical_symbol is empty and abort_on_invalid=True
    """
    if not isinstance(data, dict):
        return data

    # Ensure canonical is uppercase and non-empty
    try:
        canonical_upper = ensure_upper(
            canonical_symbol, source=source, abort_on_empty=abort_on_invalid
        )
    except ValueError as e:
        if abort_on_invalid:
            logger.error(
                f"❌ WRITER_GUARD: Cannot write snapshot with invalid symbol (source: {source})"
            )
            raise
        logger.warning(
            f"⚠️ WRITER_GUARD: Invalid canonical symbol, skipping write (source: {source})"
        )
        return data

    # Abort if computed symbol is empty
    if not canonical_upper:
        error_msg = f"Computed symbol is empty, aborting write (source: {source})"
        logger.error(f"❌ WRITER_GUARD: {error_msg}")
        if abort_on_invalid:
            raise ValueError(error_msg)
        return data

    # Set symbol field to canonical
    if "symbol" in data:
        if data["symbol"] != canonical_upper:
            logger.debug(
                f"[WRITER_GUARD] Correcting symbol field: '{data['symbol']}' → '{canonical_upper}' "
                f"(source: {source})"
            )
            data["symbol"] = canonical_upper
    else:
        # Add missing symbol field
        data["symbol"] = canonical_upper
        logger.debug(
            f"[WRITER_GUARD] Added missing symbol field: '{canonical_upper}' (source: {source})"
        )

    return data


def guard_snapshot_keys(
    snapshot: Dict[str, Any], source: str = "unknown"
) -> Dict[str, Any]:
    """
    Ensure all symbol keys in snapshot are uppercase.

    Args:
        snapshot: Snapshot dictionary with symbol keys
        source: Source location for logging

    Returns:
        Snapshot with uppercase symbol keys
    """
    if not isinstance(snapshot, dict):
        return snapshot

    result = {}
    conversions = []

    for key, value in snapshot.items():
        # Check if key looks like a symbol (ends with usdt, case-insensitive)
        if isinstance(key, str) and key.lower().endswith("usdt"):
            upper_key = ensure_upper(key, source=source)
            if key != upper_key:
                conversions.append((key, upper_key))
            result[upper_key] = value
        else:
            result[key] = value

    if conversions:
        logger.warning(
            f"[WRITER_GUARD] Converted {len(conversions)} snapshot keys (source: {source}): "
            f"{conversions[:5]}"  # Show first 5
        )

    return result


# Convenience function for common pattern
def prepare_symbol_for_write(symbol: str, source: str = "unknown") -> str:
    """
    Prepare symbol for writing (alias for ensure_upper).

    Args:
        symbol: Input symbol
        source: Source location

    Returns:
        Uppercase symbol ready for writing
    """
    return ensure_upper(symbol, source=source)


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")

    print("=" * 60)
    print("Symbol Writer Guard Test")
    print("=" * 60)

    # Test 1: ensure_upper
    print("\n[Test 1] ensure_upper")
    assert ensure_upper("BTCUSDT", "test1") == "BTCUSDT"
    assert ensure_upper("btcusdt", "test1") == "BTCUSDT"
    print("  ✅ Passed")

    # Test 2: guard_symbol_dict
    print("\n[Test 2] guard_symbol_dict")
    data = {"symbol": "btcusdt", "price": 50000}
    result = guard_symbol_dict(data, "BTCUSDT", "test2")
    assert result["symbol"] == "BTCUSDT"
    assert result["price"] == 50000
    print("  ✅ Passed")

    # Test 3: guard_snapshot_keys
    print("\n[Test 3] guard_snapshot_keys")
    snapshot = {"btcusdt": {"age_sec": 1.2}, "ethusdt": {"age_sec": 2.3}}
    result = guard_snapshot_keys(snapshot, "test3")
    assert "BTCUSDT" in result
    assert "ETHUSDT" in result
    assert "btcusdt" not in result
    print("  ✅ Passed")

    print("\n" + "=" * 60)
    print("✅ All tests passed")
    print("=" * 60)

    sys.exit(0)
