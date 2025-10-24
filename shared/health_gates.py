#!/usr/bin/env python3
"""
Health Gates Module
===================
Single Source of Truth for system health checking.

Provides:
- DataBus freshness check with mtime fallback
- UDS health freshness check
- Combined system health gate
- Age calculation utilities
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Rate limiting for fallback warnings
_last_fallback_warning = {}
_FALLBACK_WARNING_INTERVAL = 300  # 5 minutes


def _get_databus_file() -> Path:
    """Get DataBus snapshot file path"""
    return Path(__file__).parent.parent / "shared_data" / "databus_snapshot.json"


def _get_uds_file() -> Path:
    """Get UDS health file path"""
    # Check multiple possible locations
    candidates = [
        Path(__file__).parent.parent / "shared_data" / "health" / "uds.json",
        Path(__file__).parent.parent / "runtime" / "health" / "uds.json",
        Path(__file__).parent.parent / "shared_data" / "uds_health.json",
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    # Default to first candidate if none exist
    return candidates[0]


def _should_log_fallback_warning(key: str) -> bool:
    """Check if fallback warning should be logged (rate-limited)"""
    global _last_fallback_warning

    now = time.time()
    last_warn = _last_fallback_warning.get(key, 0)

    if now - last_warn >= _FALLBACK_WARNING_INTERVAL:
        _last_fallback_warning[key] = now
        return True

    return False


def is_databus_fresh(
    max_age_sec: int = 60, enable_mtime_fallback: bool = True
) -> Tuple[bool, Optional[str]]:
    """
    Check if DataBus snapshot is fresh.

    Args:
        max_age_sec: Maximum age in seconds before considered stale
        enable_mtime_fallback: If True, use file mtime as fallback when ts invalid

    Returns:
        (is_fresh: bool, reason: str | None)
        - (True, None): Fresh via ts
        - (True, "MTIME_FALLBACK"): Fresh via mtime fallback
        - (False, "STALE"): Stale
        - (False, "MISSING"): File not found
        - (False, "TS_INVALID"): ts invalid and fallback disabled
    """
    databus_file = _get_databus_file()

    if not databus_file.exists():
        return False, "MISSING"

    try:
        with open(databus_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Try to read ts (UTC epoch seconds)
        ts = data.get("ts")

        # Validate ts: must be integer or convertible to int, and reasonable value
        if ts is not None:
            try:
                ts_int = int(ts)

                # Sanity check: ts should be recent (not way in the past or future)
                # Allow ±1 year window
                now = time.time()
                if abs(now - ts_int) < 31536000:  # 1 year in seconds
                    # Valid ts, check freshness
                    age = now - ts_int

                    if age < max_age_sec:
                        return True, None
                    else:
                        return False, "STALE"
                else:
                    # ts is way off, treat as invalid
                    if _should_log_fallback_warning("databus_ts"):
                        logger.warning(
                            f"DATABUS_TS_INVALID: ts={ts_int}, now={int(now)}, "
                            f"diff={int(abs(now - ts_int))}s (>1 year)"
                        )
                    ts = None  # Force fallback

            except (ValueError, TypeError):
                # ts is not convertible to int
                if _should_log_fallback_warning("databus_ts"):
                    logger.warning(
                        f"DATABUS_TS_INVALID: Cannot convert ts to int: {ts}"
                    )
                ts = None  # Force fallback

        # If ts is invalid or missing
        if ts is None:
            if enable_mtime_fallback:
                # Fallback to file mtime
                if _should_log_fallback_warning("databus_mtime_fallback"):
                    logger.warning(
                        "DATABUS_TS_INVALID_FALLBACK_MTIME: Using file mtime as fallback. "
                        "This should not be relied upon."
                    )

                mtime = databus_file.stat().st_mtime
                age = time.time() - mtime

                if age < max_age_sec:
                    return True, "MTIME_FALLBACK"
                else:
                    return False, "STALE"
            else:
                # Fallback disabled
                return False, "TS_INVALID"

    except Exception as e:
        logger.error(f"Error reading DataBus file: {e}")
        return False, "ERROR"


def is_uds_fresh(
    max_age_sec: int = 60, enable_mtime_fallback: bool = True
) -> Tuple[bool, Optional[str]]:
    """
    Check if UDS health snapshot is fresh.

    Args:
        max_age_sec: Maximum age in seconds before considered stale
        enable_mtime_fallback: If True, use file mtime as fallback when ts invalid

    Returns:
        (is_fresh: bool, reason: str | None)
        - (True, None): Fresh via ts
        - (True, "MTIME_FALLBACK"): Fresh via mtime fallback
        - (False, "STALE"): Stale
        - (False, "MISSING"): File not found
        - (False, "TS_INVALID"): ts invalid and fallback disabled
    """
    uds_file = _get_uds_file()

    if not uds_file.exists():
        return False, "MISSING"

    try:
        with open(uds_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Try to read ts (UTC epoch seconds)
        ts = data.get("ts") or data.get("timestamp")

        # Validate ts
        if ts is not None:
            try:
                ts_int = int(ts)

                # Sanity check
                now = time.time()
                if abs(now - ts_int) < 31536000:  # 1 year
                    age = now - ts_int

                    if age < max_age_sec:
                        return True, None
                    else:
                        return False, "STALE"
                else:
                    if _should_log_fallback_warning("uds_ts"):
                        logger.warning(
                            f"UDS_TS_INVALID: ts={ts_int}, now={int(now)}, "
                            f"diff={int(abs(now - ts_int))}s (>1 year)"
                        )
                    ts = None

            except (ValueError, TypeError):
                if _should_log_fallback_warning("uds_ts"):
                    logger.warning(f"UDS_TS_INVALID: Cannot convert ts to int: {ts}")
                ts = None

        # Fallback to mtime if ts invalid
        if ts is None:
            if enable_mtime_fallback:
                if _should_log_fallback_warning("uds_mtime_fallback"):
                    logger.warning(
                        "UDS_TS_INVALID_FALLBACK_MTIME: Using file mtime as fallback"
                    )

                mtime = uds_file.stat().st_mtime
                age = time.time() - mtime

                if age < max_age_sec:
                    return True, "MTIME_FALLBACK"
                else:
                    return False, "STALE"
            else:
                return False, "TS_INVALID"

    except Exception as e:
        logger.error(f"Error reading UDS file: {e}")
        return False, "ERROR"


def is_system_healthy(
    require_databus: bool = True,
    require_uds: bool = True,
    max_age_sec: int = 60,
    enable_mtime_fallback: bool = True,
) -> Tuple[bool, str]:
    """
    Comprehensive system health check.

    Args:
        require_databus: Whether to check DataBus freshness
        require_uds: Whether to check UDS freshness
        max_age_sec: Maximum age threshold
        enable_mtime_fallback: Enable mtime fallback for both checks

    Returns:
        (healthy: bool, reason: str)

    Reason codes:
        - "OK" - All checks passed
        - "OK_MTIME_FALLBACK" - Passed but using mtime fallback
        - "DATABUS_STALE" - DataBus too old
        - "DATABUS_MISSING" - DataBus file not found
        - "DATABUS_TS_INVALID" - DataBus ts invalid (fallback disabled)
        - "UDS_STALE" - UDS too old
        - "UDS_MISSING" - UDS file not found
        - "UDS_TS_INVALID" - UDS ts invalid (fallback disabled)
    """
    using_fallback = False

    # Check DataBus
    if require_databus:
        databus_ok, databus_reason = is_databus_fresh(
            max_age_sec=max_age_sec, enable_mtime_fallback=enable_mtime_fallback
        )

        if not databus_ok:
            return False, f"DATABUS_{databus_reason}"

        if databus_reason == "MTIME_FALLBACK":
            using_fallback = True

    # Check UDS
    if require_uds:
        uds_ok, uds_reason = is_uds_fresh(
            max_age_sec=max_age_sec, enable_mtime_fallback=enable_mtime_fallback
        )

        if not uds_ok:
            return False, f"UDS_{uds_reason}"

        if uds_reason == "MTIME_FALLBACK":
            using_fallback = True

    # All checks passed
    if using_fallback:
        return True, "OK_MTIME_FALLBACK"
    else:
        return True, "OK"


def get_databus_age() -> Optional[float]:
    """
    Get DataBus age in seconds.

    Returns:
        Age in seconds, or None if file missing or ts invalid
    """
    databus_file = _get_databus_file()

    if not databus_file.exists():
        return None

    try:
        with open(databus_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        ts = data.get("ts")
        if ts is not None:
            try:
                ts_int = int(ts)
                now = time.time()

                # Sanity check
                if abs(now - ts_int) < 31536000:
                    return now - ts_int
            except (ValueError, TypeError):
                pass

        # Fallback to mtime
        mtime = databus_file.stat().st_mtime
        return time.time() - mtime

    except Exception:
        return None


def get_uds_age() -> Optional[float]:
    """
    Get UDS age in seconds.

    Returns:
        Age in seconds, or None if file missing or ts invalid
    """
    uds_file = _get_uds_file()

    if not uds_file.exists():
        return None

    try:
        with open(uds_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        ts = data.get("ts") or data.get("timestamp")
        if ts is not None:
            try:
                ts_int = int(ts)
                now = time.time()

                if abs(now - ts_int) < 31536000:
                    return now - ts_int
            except (ValueError, TypeError):
                pass

        # Fallback to mtime
        mtime = uds_file.stat().st_mtime
        return time.time() - mtime

    except Exception:
        return None


if __name__ == "__main__":
    # Test the gates
    import sys

    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("Health Gates Test")
    print("=" * 60)

    # Check DataBus
    databus_fresh, databus_reason = is_databus_fresh()
    print(f"\nDataBus: {'✅ FRESH' if databus_fresh else '❌ STALE/MISSING'}")
    print(f"  Reason: {databus_reason or 'N/A'}")

    databus_age = get_databus_age()
    if databus_age is not None:
        print(f"  Age: {databus_age:.1f}s")

    # Check UDS
    uds_fresh, uds_reason = is_uds_fresh()
    print(f"\nUDS: {'✅ FRESH' if uds_fresh else '❌ STALE/MISSING'}")
    print(f"  Reason: {uds_reason or 'N/A'}")

    uds_age = get_uds_age()
    if uds_age is not None:
        print(f"  Age: {uds_age:.1f}s")

    # Combined health
    healthy, reason = is_system_healthy()
    print(f"\nSystem: {'🟢 HEALTHY' if healthy else '🔴 UNHEALTHY'}")
    print(f"  Reason: {reason}")
    print("=" * 60)

    sys.exit(0 if healthy else 1)
