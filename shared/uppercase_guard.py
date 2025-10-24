#!/usr/bin/env python3
"""
Uppercase Symbol Guard - Runtime Enforcement
===========================================
Runtime guards to prevent lowercase symbols from entering critical paths.

Usage:
    from shared.uppercase_guard import assert_uppercase, guard_dict_keys
    
    # Before subscription
    assert_uppercase("BTCUSDT", origin="StreamBus.subscribe")
    
    # Before saving
    data = guard_dict_keys({"btcusdt": 50000}, origin="DataBus.write")
"""

import logging
import sys
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Track violations
_violations: List[Dict[str, Any]] = []
_MAX_VIOLATIONS = 100


def assert_uppercase(
    symbol: str,
    origin: str = "unknown",
    action: str = "fail"
) -> bool:
    """
    Assert that symbol is UPPERCASE. Take action on violation.
    
    Args:
        symbol: Symbol to check
        origin: Module/function where check occurs
        action: "fail" (raise), "warn" (log), or "silent" (return bool)
    
    Returns:
        True if uppercase, False otherwise
    
    Raises:
        ValueError: If action="fail" and symbol not uppercase
    """
    if not isinstance(symbol, str):
        msg = f"Symbol must be string, got {type(symbol)} (origin: {origin})"
        if action == "fail":
            logger.error(f"❌ {msg}")
            raise ValueError(msg)
        return False
    
    if symbol != symbol.upper():
        # Record violation
        violation = {
            "symbol": symbol,
            "uppercase": symbol.upper(),
            "origin": origin,
        }
        
        if len(_violations) < _MAX_VIOLATIONS:
            _violations.append(violation)
        
        msg = f"Symbol must be UPPERCASE. Got: '{symbol}' (expected: '{symbol.upper()}', origin: {origin})"
        
        if action == "fail":
            logger.error(f"❌ UPPERCASE_VIOLATION: {msg}")
            raise ValueError(msg)
        elif action == "warn":
            logger.warning(f"⚠️ UPPERCASE_VIOLATION: {msg}")
        
        return False
    
    return True


def assert_uppercase_list(
    symbols: List[str],
    origin: str = "unknown",
    action: str = "fail"
) -> bool:
    """
    Assert that all symbols in list are UPPERCASE.
    
    Args:
        symbols: List of symbols to check
        origin: Module/function where check occurs
        action: "fail" (raise), "warn" (log), or "silent" (return bool)
    
    Returns:
        True if all uppercase, False otherwise
    
    Raises:
        ValueError: If action="fail" and any symbol not uppercase
    """
    violations = [s for s in symbols if s != s.upper()]
    
    if violations:
        msg = (
            f"All symbols must be UPPERCASE. "
            f"Violations: {violations} "
            f"(origin: {origin})"
        )
        
        for s in violations:
            violation = {
                "symbol": s,
                "uppercase": s.upper(),
                "origin": origin,
            }
            if len(_violations) < _MAX_VIOLATIONS:
                _violations.append(violation)
        
        if action == "fail":
            logger.error(f"❌ UPPERCASE_VIOLATION: {msg}")
            raise ValueError(msg)
        elif action == "warn":
            logger.warning(f"⚠️ UPPERCASE_VIOLATION: {msg}")
        
        return False
    
    return True


def guard_dict_keys(
    data: Dict[str, Any],
    origin: str = "unknown",
    action: str = "fail"
) -> Dict[str, Any]:
    """
    Guard dict keys - ensure all are UPPERCASE.
    
    Args:
        data: Dict with symbol keys
        origin: Module/function where check occurs
        action: "fail" (raise), "warn" (log+fix), or "silent" (fix)
    
    Returns:
        Dict with UPPERCASE keys
    
    Raises:
        ValueError: If action="fail" and any key not uppercase
    """
    violations = {k: v for k, v in data.items() if k != k.upper()}
    
    if violations:
        msg = (
            f"All symbol keys must be UPPERCASE. "
            f"Violations: {list(violations.keys())} "
            f"(origin: {origin})"
        )
        
        for k in violations.keys():
            violation = {
                "symbol": k,
                "uppercase": k.upper(),
                "origin": origin,
            }
            if len(_violations) < _MAX_VIOLATIONS:
                _violations.append(violation)
        
        if action == "fail":
            logger.error(f"❌ UPPERCASE_VIOLATION: {msg}")
            raise ValueError(msg)
        elif action == "warn":
            logger.warning(f"⚠️ UPPERCASE_VIOLATION: {msg} - auto-fixing")
        
        # Auto-fix: convert all keys to uppercase
        return {k.upper(): v for k, v in data.items()}
    
    return data


def get_violations() -> List[Dict[str, Any]]:
    """Get recorded violations"""
    return _violations.copy()


def clear_violations():
    """Clear violation history"""
    global _violations
    _violations.clear()


def report_violations(exit_on_violations: bool = False):
    """
    Report all violations to log.
    
    Args:
        exit_on_violations: If True, exit process if violations exist
    """
    if not _violations:
        logger.info("✅ No UPPERCASE violations detected")
        return
    
    logger.warning(f"⚠️ UPPERCASE violations detected: {len(_violations)}")
    
    # Group by origin
    by_origin: Dict[str, List[str]] = {}
    for v in _violations:
        origin = v["origin"]
        symbol = v["symbol"]
        if origin not in by_origin:
            by_origin[origin] = []
        by_origin[origin].append(symbol)
    
    # Log grouped violations
    for origin, symbols in by_origin.items():
        unique = list(set(symbols))
        logger.warning(f"  {origin}: {unique}")
    
    if exit_on_violations:
        logger.error("❌ Exiting due to UPPERCASE violations")
        sys.exit(1)


# ====================================================
# Context manager for violation tracking
# ====================================================

class ViolationTracker:
    """Context manager to track violations in a code block"""
    
    def __init__(self, name: str, fail_on_exit: bool = False):
        """
        Args:
            name: Name of tracked block
            fail_on_exit: If True, raise on violations
        """
        self.name = name
        self.fail_on_exit = fail_on_exit
        self.start_count = 0
    
    def __enter__(self):
        self.start_count = len(_violations)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        new_violations = len(_violations) - self.start_count
        
        if new_violations > 0:
            logger.warning(
                f"⚠️ [{self.name}] {new_violations} UPPERCASE violations detected"
            )
            
            if self.fail_on_exit:
                report_violations(exit_on_violations=True)
        
        return False  # Don't suppress exceptions


# ====================================================
# Testing
# ====================================================
if __name__ == "__main__":
    import sys
    
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    
    print("=" * 60)
    print("Uppercase Guard Test")
    print("=" * 60)
    
    # Test 1: assert_uppercase (pass)
    print("\n[Test 1] assert_uppercase (pass)")
    try:
        assert_uppercase("BTCUSDT", origin="test1", action="fail")
        print("  ✅ BTCUSDT passed")
    except ValueError as e:
        print(f"  ❌ Unexpected error: {e}")
    
    # Test 2: assert_uppercase (fail)
    print("\n[Test 2] assert_uppercase (fail)")
    try:
        assert_uppercase("btcusdt", origin="test2", action="fail")
        print("  ❌ Should have raised ValueError")
    except ValueError as e:
        print(f"  ✅ Caught expected error: {e}")
    
    # Test 3: assert_uppercase_list
    print("\n[Test 3] assert_uppercase_list")
    try:
        assert_uppercase_list(["BTCUSDT", "ETHUSDT"], origin="test3", action="fail")
        print("  ✅ All uppercase list passed")
    except ValueError as e:
        print(f"  ❌ Unexpected error: {e}")
    
    # Test 4: assert_uppercase_list (fail)
    print("\n[Test 4] assert_uppercase_list (fail)")
    try:
        assert_uppercase_list(["BTCUSDT", "ethusdt"], origin="test4", action="fail")
        print("  ❌ Should have raised ValueError")
    except ValueError as e:
        print(f"  ✅ Caught expected error")
    
    # Test 5: guard_dict_keys (auto-fix)
    print("\n[Test 5] guard_dict_keys (auto-fix)")
    data = {"btcusdt": 50000, "ETHUSDT": 3000}
    fixed = guard_dict_keys(data, origin="test5", action="warn")
    print(f"  Input keys:  {list(data.keys())}")
    print(f"  Output keys: {list(fixed.keys())}")
    if "BTCUSDT" in fixed and "btcusdt" not in fixed:
        print("  ✅ Keys auto-fixed to UPPERCASE")
    else:
        print("  ❌ Keys not fixed")
    
    # Test 6: Violation tracking
    print("\n[Test 6] Violation Tracking")
    clear_violations()
    assert_uppercase("btcusdt", origin="test6", action="warn")
    assert_uppercase("ethusdt", origin="test6", action="warn")
    violations = get_violations()
    print(f"  Recorded violations: {len(violations)}")
    if len(violations) == 2:
        print("  ✅ Violations tracked correctly")
    else:
        print(f"  ❌ Expected 2 violations, got {len(violations)}")
    
    # Test 7: Report violations
    print("\n[Test 7] Report Violations")
    report_violations(exit_on_violations=False)
    
    print("\n" + "=" * 60)
    print("✅ Tests complete")
    print("=" * 60)

