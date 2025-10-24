#!/usr/bin/env python3
"""
Timestamp Utilities
========================================
UTC-only timestamp generation and parsing.

All timestamps in this system use UTC epoch seconds.
NO localtime-sensitive formats.
"""

import time
from datetime import datetime, timezone
from typing import Union


def now_utc() -> float:
    """
    Get current UTC timestamp (epoch seconds).

    Returns:
        UTC timestamp (float)
    """
    return time.time()


def now_utc_ms() -> int:
    """
    Get current UTC timestamp (epoch milliseconds).

    Returns:
        UTC timestamp (int milliseconds)
    """
    return int(time.time() * 1000)


def now_utc_int() -> int:
    """
    Get current UTC timestamp (epoch seconds as int).

    Returns:
        UTC timestamp (int seconds)
    """
    return int(time.time())


def datetime_utc_now() -> datetime:
    """
    Get current datetime in UTC.

    Returns:
        datetime object (UTC timezone)
    """
    return datetime.now(timezone.utc)


def to_utc_timestamp(dt: datetime) -> float:
    """
    Convert datetime to UTC timestamp.

    Args:
        dt: datetime object

    Returns:
        UTC timestamp (float)
    """
    return dt.timestamp()


def parse_timestamp(ts: Union[int, float, None], default: float = 0.0) -> float:
    """
    Parse timestamp safely.

    Handles:
    - Milliseconds (> 1e12) → convert to seconds
    - None → return default
    - Negative → return default
    - Future (> now + 1 day) → return default

    Args:
        ts: Timestamp (seconds or milliseconds)
        default: Default value for invalid timestamps

    Returns:
        Parsed timestamp (seconds) or default
    """
    if ts is None or ts == 0:
        return default

    # Convert to float
    try:
        ts = float(ts)
    except (ValueError, TypeError):
        return default

    # Negative timestamp
    if ts < 0:
        return default

    # Convert milliseconds to seconds
    if ts > 1e12:
        ts = ts / 1000.0

    # Future check (more than 1 day in future)
    if ts > time.time() + 86400:
        return default

    return ts


def get_age_seconds(ts: Union[int, float, None]) -> float:
    """
    Get age in seconds from timestamp.

    Args:
        ts: Timestamp (seconds or milliseconds)

    Returns:
        Age in seconds, or inf for invalid timestamps
    """
    parsed_ts = parse_timestamp(ts, default=0)

    if parsed_ts == 0:
        return float("inf")

    age = time.time() - parsed_ts

    # Negative age (future timestamp) → treat as invalid
    if age < 0:
        return float("inf")

    return age


def format_age(ts: Union[int, float, None]) -> str:
    """
    Format age as human-readable string.

    Args:
        ts: Timestamp

    Returns:
        "12.3s", "2.5m", "1.2h", or "awaiting data"
    """
    age = get_age_seconds(ts)

    if age == float("inf"):
        return "awaiting data"

    if age < 60:
        return f"{age:.1f}s"
    elif age < 3600:
        return f"{age/60:.1f}m"
    else:
        return f"{age/3600:.1f}h"


# Unit tests
if __name__ == "__main__":
    print("Testing timestamp utilities...")

    # Test 1: UTC timestamp generation
    print("\n1. UTC timestamp generation:")

    ts_float = now_utc()
    ts_ms = now_utc_ms()
    ts_int = now_utc_int()

    assert isinstance(ts_float, float), "Should be float"
    assert isinstance(ts_ms, int), "Should be int (ms)"
    assert isinstance(ts_int, int), "Should be int (s)"
    assert ts_ms > ts_int * 1000, "Milliseconds should be larger"

    print(f"  UTC (float): {ts_float}")
    print(f"  UTC (ms): {ts_ms}")
    print(f"  UTC (int): {ts_int}")
    print("✅ UTC generation works")

    # Test 2: Timestamp parsing
    print("\n2. Timestamp parsing:")

    test_cases = [
        (time.time(), time.time()),  # Current time
        (time.time() * 1000, time.time()),  # Milliseconds
        (0, 0),  # Zero
        (None, 0),  # None
        (-100, 0),  # Negative
        (time.time() + 200000, 0),  # Future
    ]

    for input_ts, expected_range in test_cases:
        parsed = parse_timestamp(input_ts, default=0)

        if expected_range == 0:
            assert parsed == 0, f"Should return default for {input_ts}"
            print(f"  ✅ parse_timestamp({input_ts}) = 0 (default)")
        else:
            assert (
                abs(parsed - expected_range) < 10
            ), f"Should be close to {expected_range}"
            print(f"  ✅ parse_timestamp({input_ts}) ≈ {parsed:.2f}")

    print("✅ Timestamp parsing works")

    # Test 3: Age calculation
    print("\n3. Age calculation:")

    current = time.time()

    age1 = get_age_seconds(current - 10)
    assert 9 < age1 < 11, "Should be ~10s"
    print(f"  ✅ Age (10s ago): {age1:.1f}s")

    age2 = get_age_seconds(0)
    assert age2 == float("inf"), "Zero should return inf"
    print(f"  ✅ Age (ts=0): {age2}")

    age3 = get_age_seconds(None)
    assert age3 == float("inf"), "None should return inf"
    print(f"  ✅ Age (None): {age3}")

    print("✅ Age calculation works")

    # Test 4: Age formatting
    print("\n4. Age formatting:")

    assert "s" in format_age(time.time() - 10), "Should show seconds"
    assert "m" in format_age(time.time() - 120), "Should show minutes"
    assert "h" in format_age(time.time() - 7200), "Should show hours"
    assert format_age(0) == "awaiting data", "Zero should show awaiting"
    assert format_age(None) == "awaiting data", "None should show awaiting"

    print("✅ Age formatting works")

    print("\n" + "=" * 50)
    print("All timestamp utility tests passed! ✅")
    print("=" * 50)
