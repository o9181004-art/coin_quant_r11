#!/usr/bin/env python3
"""
Symbol Normalizer - UPPERCASE Enforcement
==========================================
Central, dependency-free module for symbol case normalization.

Guarantees:
- All symbols are UPPERCASE (exchange standard)
- One-shot warnings for violations
- Metrics tracking
- No external dependencies (stdlib only)
"""

import json
import logging
import time
from pathlib import Path
from typing import Dict, Iterable, List, Set

logger = logging.getLogger(__name__)

# ====================================================
# State Tracking
# ====================================================
_warned_sources: Set[str] = set()
_metrics = {
    "total_normalized": 0,
    "total_changed": 0,
    "first_seen": {},  # {source: timestamp}
    "changed_today": 0,
    "last_reset": time.time(),
}

_METRICS_SNAPSHOT_PATH = Path("shared_data") / "symbol_norm_metrics.json"
_METRICS_SNAPSHOT_INTERVAL = 300  # 5 minutes


def to_exchange_case(symbol: str) -> str:
    """
    Normalize symbol to exchange-standard UPPERCASE.

    Args:
        symbol: Raw symbol (any case)

    Returns:
        Normalized symbol (UPPERCASE)

    Examples:
        >>> to_exchange_case("btcusdt")
        'BTCUSDT'
        >>> to_exchange_case("ETHUSDT")
        'ETHUSDT'
        >>> to_exchange_case("BnbUsdt")
        'BNBUSDT'
    """
    return symbol.upper()


def normalize_symbol(symbol: str, source: str = "unknown", stack_tag: str = "") -> str:
    """
    Normalize symbol to UPPERCASE with violation tracking.

    Args:
        symbol: Raw symbol (any case)
        source: Source module/function for logging
        stack_tag: Optional stack trace tag

    Returns:
        Normalized symbol (UPPERCASE)

    Side Effects:
        - Increments metrics
        - Logs SYMBOL_CASE_VIOLATION once per source
        - Updates changed_today counter
    """
    global _metrics, _warned_sources

    normalized = to_exchange_case(symbol)

    _metrics["total_normalized"] += 1

    # Check if case changed
    if symbol != normalized:
        _metrics["total_changed"] += 1
        _metrics["changed_today"] += 1

        # Log one-shot warning per source
        source_key = f"{source}:{symbol}"

        if source_key not in _warned_sources:
            _warned_sources.add(source_key)

            # Record first seen
            if source not in _metrics["first_seen"]:
                _metrics["first_seen"][source] = time.time()

            # Log violation
            logger.warning(
                f"SYMBOL_CASE_VIOLATION: '{symbol}' → '{normalized}' "
                f"(source={source}, stack={stack_tag})"
            )

    # Snapshot metrics periodically
    _maybe_snapshot_metrics()

    return normalized


def normalize_list(symbols: Iterable[str], source: str = "unknown") -> List[str]:
    """
    Normalize list of symbols to UPPERCASE with deduplication.

    Args:
        symbols: Iterable of symbols (any case)
        source: Source for logging

    Returns:
        Deduplicated list of UPPERCASE symbols

    Examples:
        >>> normalize_list(["btcusdt", "ETHUSDT", "btcusdt"])
        ['BTCUSDT', 'ETHUSDT']
    """
    # Normalize and deduplicate (preserve order)
    seen = set()
    result = []

    for symbol in symbols:
        normalized = normalize_symbol(symbol, source=source)
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)

    return result


def normalize_dict_keys(
    data: Dict[str, any], source: str = "unknown"
) -> Dict[str, any]:
    """
    Normalize all symbol keys in dict to UPPERCASE.

    Args:
        data: Dict with symbol keys
        source: Source for logging

    Returns:
        New dict with UPPERCASE keys

    Warning:
        If duplicate keys exist after normalization, later value wins

    Examples:
        >>> normalize_dict_keys({"btcusdt": 50000, "ETHUSDT": 3000})
        {'BTCUSDT': 50000, 'ETHUSDT': 3000}
    """
    return {normalize_symbol(k, source=source): v for k, v in data.items()}


def get_metrics() -> Dict:
    """
    Get current normalization metrics.

    Returns:
        Dict with:
        - total_normalized: Total symbols processed
        - total_changed: Total case corrections
        - changed_today: Changes since last reset
        - sources: List of sources with violations
        - first_seen: {source: timestamp}
    """
    return {
        "total_normalized": _metrics["total_normalized"],
        "total_changed": _metrics["total_changed"],
        "changed_today": _metrics["changed_today"],
        "sources": list(_metrics["first_seen"].keys()),
        "first_seen": _metrics["first_seen"],
        "last_reset": _metrics["last_reset"],
    }


def reset_daily_counter():
    """Reset changed_today counter (call daily at midnight)"""
    global _metrics

    _metrics["changed_today"] = 0
    _metrics["last_reset"] = time.time()

    logger.info("Symbol normalization daily counter reset")


def _maybe_snapshot_metrics():
    """Snapshot metrics to file every N minutes"""
    global _metrics

    now = time.time()

    # Check if snapshot interval elapsed
    if hasattr(_maybe_snapshot_metrics, "_last_snapshot"):
        elapsed = now - _maybe_snapshot_metrics._last_snapshot
        if elapsed < _METRICS_SNAPSHOT_INTERVAL:
            return

    # Time to snapshot
    _maybe_snapshot_metrics._last_snapshot = now

    try:
        _METRICS_SNAPSHOT_PATH.parent.mkdir(exist_ok=True)

        snapshot = {"timestamp": now, "metrics": get_metrics()}

        with open(_METRICS_SNAPSHOT_PATH, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2, ensure_ascii=False)

    except Exception as e:
        logger.debug(f"Failed to snapshot symbol norm metrics: {e}")


def load_metrics_snapshot() -> Dict | None:
    """Load metrics snapshot from file"""
    if not _METRICS_SNAPSHOT_PATH.exists():
        return None

    try:
        with open(_METRICS_SNAPSHOT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# ====================================================
# Testing & Validation
# ====================================================
if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("Symbol Normalizer Test")
    print("=" * 60)

    # Test basic normalization
    test_cases = [
        ("btcusdt", "BTCUSDT"),
        ("ETHUSDT", "ETHUSDT"),
        ("BnbUsdt", "BNBUSDT"),
        ("lisTAusdt", "LISTAUSDT"),
    ]

    print("\nBasic Normalization:")
    for input_sym, expected in test_cases:
        result = to_exchange_case(input_sym)
        status = "✅" if result == expected else "❌"
        print(f"  {status} '{input_sym}' → '{result}' (expected: '{expected}')")
        assert result == expected

    # Test normalize_symbol with warnings
    print("\nNormalize with Warnings:")
    logging.basicConfig(level=logging.WARNING)

    result1 = normalize_symbol("btcusdt", source="test_ingress")
    print(f"  First call: {result1} (should warn)")

    result2 = normalize_symbol("btcusdt", source="test_ingress")
    print(f"  Second call: {result2} (should NOT warn - suppressed)")

    # Test list normalization
    print("\nList Normalization:")
    test_list = ["btcusdt", "ETHUSDT", "btcusdt", "BnbUsdt"]
    result_list = normalize_list(test_list, source="test_list")
    print(f"  Input:  {test_list}")
    print(f"  Output: {result_list}")
    assert result_list == ["BTCUSDT", "ETHUSDT", "BNBUSDT"]

    # Test dict normalization
    print("\nDict Key Normalization:")
    test_dict = {"btcusdt": 50000, "ETHUSDT": 3000, "BnbUsdt": 600}
    result_dict = normalize_dict_keys(test_dict, source="test_dict")
    print(f"  Input keys:  {list(test_dict.keys())}")
    print(f"  Output keys: {list(result_dict.keys())}")
    assert "BTCUSDT" in result_dict
    assert "btcusdt" not in result_dict

    # Show metrics
    print("\nMetrics:")
    metrics = get_metrics()
    print(f"  Total normalized: {metrics['total_normalized']}")
    print(f"  Total changed: {metrics['total_changed']}")
    print(f"  Sources: {metrics['sources']}")

    print("\n" + "=" * 60)
    print("✅ All tests passed")
    print("=" * 60)

    sys.exit(0)
