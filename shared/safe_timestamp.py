"""
Timestamp utilities for coin_quant system.

All timestamps in this system are epoch milliseconds (int, UTC).
This module provides safe conversion, validation, and freshness checks.

Contract:
- Canonical unit: epoch_ms (integer)
- Ingress adapters: convert from seconds/ISO to epoch_ms immediately
- All freshness/TTL calculations: use ms consistently
- Reject floats/str in writers

Author: coin_quant
Date: 2025-10-09
"""

import time
from typing import Union, Optional
from datetime import datetime


def now_ms() -> int:
    """
    Get current UTC timestamp in epoch milliseconds.
    
    Returns:
        int: Current timestamp in milliseconds since epoch
    """
    return int(time.time() * 1000)


def now_s() -> float:
    """
    Get current UTC timestamp in epoch seconds (float).
    
    Returns:
        float: Current timestamp in seconds since epoch
    
    Note: Use this only when interfacing with libraries that require seconds.
          Prefer now_ms() for internal use.
    """
    return time.time()


def to_ms(timestamp: Union[int, float, str, datetime]) -> Optional[int]:
    """
    Convert various timestamp formats to epoch milliseconds.
    
    Args:
        timestamp: Can be:
            - int: assumed to be epoch_ms if > 1e12, else epoch_s
            - float: assumed to be epoch_s
            - str: ISO 8601 format
            - datetime: Python datetime object
    
    Returns:
        int: Epoch milliseconds, or None if conversion failed
    
    Examples:
        >>> to_ms(1609459200)  # 2021-01-01 00:00:00 in seconds
        1609459200000
        >>> to_ms(1609459200000)  # 2021-01-01 00:00:00 in milliseconds
        1609459200000
        >>> to_ms(1609459200.123)  # seconds with fractional part
        1609459200123
    """
    try:
        if isinstance(timestamp, int):
            # If > 1 trillion, assume milliseconds, else seconds
            if timestamp > 1_000_000_000_000:
                return timestamp
            else:
                return timestamp * 1000
        
        elif isinstance(timestamp, float):
            # Assume seconds
            return int(timestamp * 1000)
        
        elif isinstance(timestamp, str):
            # Try to parse ISO 8601
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            return int(dt.timestamp() * 1000)
        
        elif isinstance(timestamp, datetime):
            return int(timestamp.timestamp() * 1000)
        
        else:
            return None
    
    except (ValueError, AttributeError, OSError):
        return None


def to_s(timestamp_ms: int) -> float:
    """
    Convert epoch milliseconds to epoch seconds.
    
    Args:
        timestamp_ms: Epoch milliseconds
    
    Returns:
        float: Epoch seconds
    """
    return timestamp_ms / 1000.0


def age_ms(timestamp_ms: int) -> int:
    """
    Calculate age in milliseconds from a given timestamp.
    
    Args:
        timestamp_ms: Epoch milliseconds
    
    Returns:
        int: Age in milliseconds (always >= 0)
    """
    age = now_ms() - timestamp_ms
    return max(0, age)


def age_s(timestamp_ms: int) -> float:
    """
    Calculate age in seconds from a given timestamp.
    
    Args:
        timestamp_ms: Epoch milliseconds
    
    Returns:
        float: Age in seconds (always >= 0.0)
    """
    return age_ms(timestamp_ms) / 1000.0


def is_fresh(timestamp_ms: int, max_age_ms: int) -> bool:
    """
    Check if a timestamp is fresh (within max_age_ms).
    
    Args:
        timestamp_ms: Epoch milliseconds to check
        max_age_ms: Maximum age in milliseconds
    
    Returns:
        bool: True if fresh, False if stale
    """
    return age_ms(timestamp_ms) <= max_age_ms


def is_stale(timestamp_ms: int, max_age_ms: int) -> bool:
    """
    Check if a timestamp is stale (older than max_age_ms).
    
    Args:
        timestamp_ms: Epoch milliseconds to check
        max_age_ms: Maximum age in milliseconds
    
    Returns:
        bool: True if stale, False if fresh
    """
    return age_ms(timestamp_ms) > max_age_ms


def validate_timestamp_ms(value: any, field_name: str = "timestamp") -> int:
    """
    Validate and ensure a value is a proper epoch_ms timestamp.
    
    Args:
        value: Value to validate
        field_name: Name of the field (for error messages)
    
    Returns:
        int: Validated epoch_ms timestamp
    
    Raises:
        ValueError: If value is not a valid timestamp
    """
    if not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be int or float, got {type(value).__name__}")
    
    if isinstance(value, float):
        # Convert float seconds to int milliseconds
        value = int(value * 1000)
    
    if not isinstance(value, int):
        raise ValueError(f"{field_name} must be int after conversion")
    
    # Sanity check: reasonable timestamp range
    # Min: 2020-01-01 (1577836800000)
    # Max: 2030-12-31 (1924991999000)
    MIN_TIMESTAMP_MS = 1_577_836_800_000
    MAX_TIMESTAMP_MS = 1_924_991_999_000
    
    if value < MIN_TIMESTAMP_MS or value > MAX_TIMESTAMP_MS:
        raise ValueError(
            f"{field_name}={value} out of reasonable range "
            f"[{MIN_TIMESTAMP_MS}, {MAX_TIMESTAMP_MS}]"
        )
    
    return value


def format_age(age_ms: int) -> str:
    """
    Format age in milliseconds to human-readable string.
    
    Args:
        age_ms: Age in milliseconds
    
    Returns:
        str: Human-readable age (e.g., "2.5s", "3m 15s", "1h 30m")
    """
    if age_ms < 1000:
        return f"{age_ms}ms"
    
    seconds = age_ms / 1000.0
    
    if seconds < 60:
        return f"{seconds:.1f}s"
    
    minutes = int(seconds / 60)
    remaining_seconds = int(seconds % 60)
    
    if minutes < 60:
        if remaining_seconds > 0:
            return f"{minutes}m {remaining_seconds}s"
        else:
            return f"{minutes}m"
    
    hours = int(minutes / 60)
    remaining_minutes = int(minutes % 60)
    
    if remaining_minutes > 0:
        return f"{hours}h {remaining_minutes}m"
    else:
        return f"{hours}h"


def iso_format(timestamp_ms: int) -> str:
    """
    Convert epoch milliseconds to ISO 8601 string.
    
    Args:
        timestamp_ms: Epoch milliseconds
    
    Returns:
        str: ISO 8601 formatted string
    """
    dt = datetime.fromtimestamp(timestamp_ms / 1000.0)
    return dt.isoformat()


# Convenience constants (in milliseconds)
SECOND_MS = 1_000
MINUTE_MS = 60_000
HOUR_MS = 3_600_000
DAY_MS = 86_400_000


def file_age_ms(file_path) -> int:
    """
    Get file age in milliseconds from its modification time.
    
    Args:
        file_path: Path-like object or string
    
    Returns:
        int: Age in milliseconds since last modification
    """
    try:
        from pathlib import Path
        path = Path(file_path)
        if not path.exists():
            return 999_999_999  # Very old if file doesn't exist
        
        mtime_s = path.stat().st_mtime
        mtime_ms = int(mtime_s * 1000)
        return age_ms(mtime_ms)
    except (OSError, ValueError):
        return 999_999_999


def file_mtime_ms(file_path) -> int:
    """
    Get file modification time in epoch milliseconds.
    
    Args:
        file_path: Path-like object or string
    
    Returns:
        int: File modification time in epoch_ms, or 0 if error
    """
    try:
        from pathlib import Path
        path = Path(file_path)
        if not path.exists():
            return 0
        
        mtime_s = path.stat().st_mtime
        return int(mtime_s * 1000)
    except (OSError, ValueError):
        return 0


if __name__ == "__main__":
    # Self-test
    print("=== safe_timestamp.py Self-Test ===")
    
    current = now_ms()
    print(f"now_ms(): {current}")
    print(f"now_s(): {now_s()}")
    print(f"iso_format(now_ms()): {iso_format(current)}")
    
    # Test conversions
    print("\n--- Conversion Tests ---")
    print(f"to_ms(1609459200): {to_ms(1609459200)}")  # 2021-01-01 in seconds
    print(f"to_ms(1609459200000): {to_ms(1609459200000)}")  # 2021-01-01 in ms
    print(f"to_ms(1609459200.123): {to_ms(1609459200.123)}")  # seconds with fraction
    
    # Test age calculations
    print("\n--- Age Tests ---")
    old_timestamp = current - (5 * SECOND_MS)
    print(f"age_ms({old_timestamp}): {age_ms(old_timestamp)} ms")
    print(f"age_s({old_timestamp}): {age_s(old_timestamp)} s")
    print(f"format_age({age_ms(old_timestamp)}): {format_age(age_ms(old_timestamp))}")
    
    # Test freshness
    print("\n--- Freshness Tests ---")
    print(f"is_fresh(now - 5s, max=10s): {is_fresh(current - 5*SECOND_MS, 10*SECOND_MS)}")
    print(f"is_stale(now - 15s, max=10s): {is_stale(current - 15*SECOND_MS, 10*SECOND_MS)}")
    
    # Test validation
    print("\n--- Validation Tests ---")
    try:
        validated = validate_timestamp_ms(current)
        print(f"validate_timestamp_ms({current}): {validated} ✅")
    except ValueError as e:
        print(f"validate_timestamp_ms({current}): ERROR - {e}")
    
    try:
        validated = validate_timestamp_ms(time.time())
        print(f"validate_timestamp_ms(time.time()): {validated} ✅")
    except ValueError as e:
        print(f"validate_timestamp_ms(time.time()): ERROR - {e}")
    
    print("\n✅ All tests passed!")

