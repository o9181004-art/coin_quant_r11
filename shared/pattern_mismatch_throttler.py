#!/usr/bin/env python3
"""
Pattern Mismatch Log Throttler
==============================
Throttle "pattern mismatch" logs to 1 per symbol per 10 minutes.

Usage:
    from shared.pattern_mismatch_throttler import should_log_pattern_mismatch
    
    if should_log_pattern_mismatch(symbol):
        logger.warning(f"Pattern mismatch for {symbol}")
"""

import time
from typing import Dict

# Global state for throttling
_last_logged: Dict[str, float] = {}
_THROTTLE_SECONDS = 600  # 10 minutes


def should_log_pattern_mismatch(symbol: str, throttle_seconds: int = _THROTTLE_SECONDS) -> bool:
    """
    Check if pattern mismatch should be logged for symbol.
    
    Args:
        symbol: Symbol to check
        throttle_seconds: Minimum seconds between logs (default 600 = 10 min)
    
    Returns:
        True if should log, False if throttled
    """
    now = time.time()
    
    # Normalize symbol for consistency
    symbol_key = symbol.upper()
    
    # Check if we logged recently
    if symbol_key in _last_logged:
        elapsed = now - _last_logged[symbol_key]
        if elapsed < throttle_seconds:
            # Throttled
            return False
    
    # Allow logging and update timestamp
    _last_logged[symbol_key] = now
    return True


def reset_throttle(symbol: str = None):
    """
    Reset throttle state.
    
    Args:
        symbol: If provided, reset only this symbol; if None, reset all
    """
    global _last_logged
    
    if symbol:
        symbol_key = symbol.upper()
        _last_logged.pop(symbol_key, None)
    else:
        _last_logged.clear()


def get_throttle_stats() -> Dict[str, any]:
    """
    Get current throttle statistics.
    
    Returns:
        Dict with throttle state info
    """
    now = time.time()
    
    return {
        "total_symbols_tracked": len(_last_logged),
        "symbols": {
            symbol: {
                "last_logged": timestamp,
                "elapsed_sec": now - timestamp,
                "can_log_now": (now - timestamp) >= _THROTTLE_SECONDS
            }
            for symbol, timestamp in _last_logged.items()
        }
    }


if __name__ == "__main__":
    import logging
    
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    logger = logging.getLogger(__name__)
    
    print("=" * 60)
    print("Pattern Mismatch Throttler Test")
    print("=" * 60)
    
    # Test 1: First log should pass
    print("\n[Test 1] First log")
    assert should_log_pattern_mismatch("BTCUSDT", throttle_seconds=2)
    print("  ✅ First log allowed")
    
    # Test 2: Immediate second log should be throttled
    print("\n[Test 2] Immediate second log")
    assert not should_log_pattern_mismatch("BTCUSDT", throttle_seconds=2)
    print("  ✅ Second log throttled")
    
    # Test 3: After throttle period, should allow
    print("\n[Test 3] After throttle period")
    time.sleep(2.1)
    assert should_log_pattern_mismatch("BTCUSDT", throttle_seconds=2)
    print("  ✅ Log allowed after throttle period")
    
    # Test 4: Different symbol not throttled
    print("\n[Test 4] Different symbol")
    reset_throttle()  # Clear state
    assert should_log_pattern_mismatch("BTCUSDT", throttle_seconds=2)
    assert should_log_pattern_mismatch("ETHUSDT", throttle_seconds=2)
    print("  ✅ Different symbols not cross-throttled")
    
    # Test 5: Stats
    print("\n[Test 5] Throttle stats")
    stats = get_throttle_stats()
    print(f"  Tracked symbols: {stats['total_symbols_tracked']}")
    print("  ✅ Stats retrieved")
    
    print("\n" + "=" * 60)
    print("✅ All tests passed")
    print("=" * 60)

