#!/usr/bin/env python3
"""
Canonical Symbol Utilities
========================================
Single source of truth for symbol canonicalization.

Canonical form: all-lowercase, no spaces, USDT suffix unchanged
Examples: btcusdt, ethusdt, xrpusdt
"""

import re
from typing import Optional


def canonical_symbol(sym: str) -> str:
    """
    Convert symbol to canonical form (lowercase).
    
    Canonical form:
    - All lowercase
    - No leading/trailing spaces
    - USDT suffix unchanged (already lowercase after conversion)
    
    Args:
        sym: Raw symbol string (e.g., "BTCUSDT", "BtcUsdt", " ethusdt ")
    
    Returns:
        Canonical symbol (e.g., "btcusdt", "ethusdt")
    
    Examples:
        >>> canonical_symbol("BTCUSDT")
        'btcusdt'
        >>> canonical_symbol("BtcUsdt")
        'btcusdt'
        >>> canonical_symbol(" ETHUSDT ")
        'ethusdt'
        >>> canonical_symbol("")
        ''
        >>> canonical_symbol(None)
        ''
    """
    if not sym:
        return ""
    
    # Strip whitespace and convert to lowercase
    canonical = str(sym).strip().lower()
    
    # Optional: Handle legacy aliases (future extension point)
    # For now, just return canonical form
    
    return canonical


def is_valid_symbol(sym: str) -> bool:
    """
    Check if symbol is valid (non-empty, alphanumeric).
    
    Args:
        sym: Symbol string
    
    Returns:
        True if valid, False otherwise
    """
    if not sym:
        return False
    
    canonical = canonical_symbol(sym)
    
    # Valid symbol: 3+ chars, alphanumeric, ends with 'usdt'
    if len(canonical) < 3:
        return False
    
    if not re.match(r'^[a-z0-9]+usdt$', canonical):
        return False
    
    return True


def normalize_symbol_dict(data: dict) -> dict:
    """
    Normalize all symbol keys in a dictionary to canonical form.
    
    Args:
        data: Dictionary with symbol keys
    
    Returns:
        New dictionary with canonicalized keys
    
    Example:
        >>> normalize_symbol_dict({"BTCUSDT": 100, "ETHUSDT": 200})
        {'btcusdt': 100, 'ethusdt': 200}
    """
    if not isinstance(data, dict):
        return data
    
    normalized = {}
    for key, value in data.items():
        # Only normalize keys that look like symbols (contain USDT)
        if isinstance(key, str) and 'usdt' in key.lower():
            canonical_key = canonical_symbol(key)
            normalized[canonical_key] = value
        else:
            normalized[key] = value
    
    return normalized


# Unit tests
if __name__ == "__main__":
    import sys

    # Test cases
    test_cases = [
        # (input, expected_output)
        ("BTCUSDT", "btcusdt"),
        ("btcusdt", "btcusdt"),
        ("BtcUsdt", "btcusdt"),
        ("ETHUSDT", "ethusdt"),
        ("XRP USDT", "xrp usdt"),  # Space preserved (not a valid symbol anyway)
        (" BTCUSDT ", "btcusdt"),
        ("  ethusdt  ", "ethusdt"),
        ("", ""),
        (None, ""),
        ("SOLUSDT", "solusdt"),
        ("ADAUSDT", "adausdt"),
        ("DOGEUSDT", "dogeusdt"),
        ("1000PEPEUSDT", "1000pepeusdt"),  # With numbers
        ("btc usdt", "btc usdt"),  # Invalid (space in middle)
        ("BTCUSD", "btcusd"),  # Different suffix
        ("   ", ""),
    ]
    
    print("Running canonical_symbol tests...")
    passed = 0
    failed = 0
    
    for input_sym, expected in test_cases:
        result = canonical_symbol(input_sym)
        if result == expected:
            passed += 1
            print(f"✅ canonical_symbol({repr(input_sym)}) = {repr(result)}")
        else:
            failed += 1
            print(f"❌ canonical_symbol({repr(input_sym)}) = {repr(result)}, expected {repr(expected)}")
    
    print(f"\n{'='*50}")
    print(f"Tests: {passed} passed, {failed} failed")
    print(f"{'='*50}")
    
    # Validation tests
    print("\nRunning is_valid_symbol tests...")
    
    valid_symbols = ["btcusdt", "ethusdt", "xrpusdt", "1000pepeusdt"]
    invalid_symbols = ["", "btc", "BTCUSD", "btc usdt", "  ", None]
    
    for sym in valid_symbols:
        is_valid = is_valid_symbol(sym)
        status = "✅" if is_valid else "❌"
        print(f"{status} is_valid_symbol({repr(sym)}) = {is_valid} (expected True)")
    
    for sym in invalid_symbols:
        is_valid = is_valid_symbol(sym)
        status = "✅" if not is_valid else "❌"
        print(f"{status} is_valid_symbol({repr(sym)}) = {is_valid} (expected False)")
    
    sys.exit(0 if failed == 0 else 1)

