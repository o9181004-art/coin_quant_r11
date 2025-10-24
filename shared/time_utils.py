#!/usr/bin/env python3
"""
Dashboard Time Utilities
========================

Provides consistent timestamp normalization and age calculation for the dashboard.
Fixes the age rendering bug by normalizing timestamps (ms vs s vs ISO) and computing 
age = now_utc_ms - ts_ms.

Usage:
    from shared.time_utils import utc_now_ms, to_epoch_ms, age_seconds
    
    # Get current UTC timestamp in milliseconds
    now = utc_now_ms()
    
    # Convert various timestamp formats to epoch milliseconds
    ts_ms = to_epoch_ms(timestamp)  # Handles numeric, ISO strings, etc.
    
    # Calculate age in seconds
    age = age_seconds(timestamp)    # Returns seconds or None
"""

import time
from datetime import datetime
from typing import Any, Optional


def utc_now_ms() -> int:
    """Get current UTC timestamp in milliseconds"""
    return int(time.time() * 1000)


def to_epoch_ms(timestamp: Any) -> Optional[int]:
    """
    Convert various timestamp formats to UTC epoch milliseconds.
    
    Rules:
    - Numeric: >= 1_000_000_000_000 → ms, else treat as seconds × 1000
    - ISO strings: parse as UTC to epoch ms
    - Missing/invalid: return None
    
    Args:
        timestamp: Can be int, float, str (ISO), or None
        
    Returns:
        Epoch milliseconds (int) or None if invalid
    """
    if timestamp is None:
        return None
    
    try:
        # Handle numeric timestamps
        if isinstance(timestamp, (int, float)):
            ts_float = float(timestamp)
            
            # If >= 1e12, treat as milliseconds
            if ts_float >= 1_000_000_000_000:
                return int(ts_float)
            else:
                # Treat as seconds, convert to milliseconds
                return int(ts_float * 1000)
        
        # Handle ISO string timestamps
        elif isinstance(timestamp, str):
            # Try parsing ISO format
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            return int(dt.timestamp() * 1000)
        
        return None
        
    except (ValueError, TypeError, OverflowError):
        return None


def age_seconds(timestamp: Any) -> Optional[float]:
    """
    Calculate age in seconds from timestamp to now.
    
    Args:
        timestamp: Can be int, float, str (ISO), or None
        
    Returns:
        Age in seconds (float) or None if invalid.
        Clamps negative ages to 0.
    """
    ts_ms = to_epoch_ms(timestamp)
    if ts_ms is None:
        return None
    
    now_ms = utc_now_ms()
    age_ms = now_ms - ts_ms
    age_sec = age_ms / 1000.0
    
    # Clamp negative ages to 0
    return max(0.0, age_sec)


def format_age_display(age_sec: Optional[float], stale_threshold_days: float = 7.0) -> str:
    """
    Format age for display in the dashboard.
    
    Args:
        age_sec: Age in seconds
        stale_threshold_days: Days after which to mark as "Stale"
        
    Returns:
        Formatted age string (e.g., "2.3s", "1.2m", "Stale")
    """
    if age_sec is None:
        return "N/A"
    
    stale_threshold_sec = stale_threshold_days * 24 * 3600
    
    if age_sec > stale_threshold_sec:
        return "Stale"
    elif age_sec < 60:
        return f"{age_sec:.1f}s"
    elif age_sec < 3600:
        minutes = age_sec / 60
        return f"{minutes:.1f}m"
    else:
        hours = age_sec / 3600
        return f"{hours:.1f}h"


def get_timestamp_info(timestamp: Any) -> dict:
    """
    Get detailed timestamp information for debugging.
    
    Args:
        timestamp: Any timestamp value
        
    Returns:
        Dictionary with ts_ms, ts_iso, age_s, and source info
    """
    ts_ms = to_epoch_ms(timestamp)
    age_s = age_seconds(timestamp)
    
    info = {
        "ts_ms": ts_ms,
        "ts_iso": None,
        "age_s": age_s,
        "source": type(timestamp).__name__
    }
    
    if ts_ms is not None:
        try:
            dt = datetime.fromtimestamp(ts_ms / 1000)
            info["ts_iso"] = dt.isoformat() + "Z"
        except (ValueError, OSError):
            pass
    
    return info


# Dev toggle for detailed timestamp display
SHOW_TIMESTAMP_DEBUG = False  # Set to True to show detailed timestamp info


def debug_timestamp(timestamp: Any, label: str = "") -> dict:
    """
    Get debug information for a timestamp (only if SHOW_TIMESTAMP_DEBUG is True).
    
    Args:
        timestamp: Any timestamp value
        label: Optional label for the timestamp
        
    Returns:
        Debug info dict or empty dict if debugging disabled
    """
    if not SHOW_TIMESTAMP_DEBUG:
        return {}
    
    info = get_timestamp_info(timestamp)
    info["label"] = label
    return info


