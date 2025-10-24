"""
Time utilities for Coin Quant R11

Consistent timestamp normalization and age calculation.
Provides UTC timestamps, epoch conversion, and age calculations.
"""

import time
from datetime import datetime, timezone
from typing import Any, Optional


def utc_now_ms() -> int:
    """
    Get current UTC timestamp in milliseconds.
    
    Returns:
        int: Current UTC timestamp in milliseconds
    """
    return int(time.time() * 1000)


def utc_now_seconds() -> float:
    """
    Get current UTC timestamp in seconds.
    
    Returns:
        float: Current UTC timestamp in seconds
    """
    return time.time()


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
            # If >= 1 trillion, assume it's already in milliseconds
            if timestamp >= 1_000_000_000_000:
                return int(timestamp)
            # Otherwise, treat as seconds and convert to milliseconds
            return int(timestamp * 1000)
        
        # Handle string timestamps (ISO format)
        if isinstance(timestamp, str):
            # Try parsing as ISO format
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
            
    except (ValueError, TypeError, OverflowError):
        pass
    
    return None


def to_epoch_seconds(timestamp: Any) -> Optional[float]:
    """
    Convert various timestamp formats to UTC epoch seconds.
    
    Args:
        timestamp: Can be int, float, str (ISO), or None
        
    Returns:
        Epoch seconds (float) or None if invalid
    """
    ms = to_epoch_ms(timestamp)
    return ms / 1000.0 if ms is not None else None


def age_seconds(timestamp: Any) -> Optional[float]:
    """
    Calculate age of timestamp in seconds from now.
    
    Args:
        timestamp: Can be int, float, str (ISO), or None
        
    Returns:
        Age in seconds (float) or None if invalid
    """
    ts_seconds = to_epoch_seconds(timestamp)
    if ts_seconds is None:
        return None
    
    return utc_now_seconds() - ts_seconds


def age_minutes(timestamp: Any) -> Optional[float]:
    """
    Calculate age of timestamp in minutes from now.
    
    Args:
        timestamp: Can be int, float, str (ISO), or None
        
    Returns:
        Age in minutes (float) or None if invalid
    """
    age_sec = age_seconds(timestamp)
    return age_sec / 60.0 if age_sec is not None else None


def age_hours(timestamp: Any) -> Optional[float]:
    """
    Calculate age of timestamp in hours from now.
    
    Args:
        timestamp: Can be int, float, str (ISO), or None
        
    Returns:
        Age in hours (float) or None if invalid
    """
    age_sec = age_seconds(timestamp)
    return age_sec / 3600.0 if age_sec is not None else None


def format_age(timestamp: Any) -> str:
    """
    Format age as human-readable string.
    
    Args:
        timestamp: Can be int, float, str (ISO), or None
        
    Returns:
        Human-readable age string
    """
    age_sec = age_seconds(timestamp)
    if age_sec is None:
        return "Unknown"
    
    if age_sec < 60:
        return f"{age_sec:.1f}s"
    elif age_sec < 3600:
        return f"{age_sec/60:.1f}m"
    else:
        return f"{age_sec/3600:.1f}h"


def is_fresh(timestamp: Any, threshold_seconds: float) -> bool:
    """
    Check if timestamp is fresh within threshold.
    
    Args:
        timestamp: Can be int, float, str (ISO), or None
        threshold_seconds: Freshness threshold in seconds
        
    Returns:
        True if fresh, False otherwise
    """
    age_sec = age_seconds(timestamp)
    return age_sec is not None and age_sec <= threshold_seconds


def format_timestamp(timestamp: Any) -> str:
    """
    Format timestamp as ISO string.
    
    Args:
        timestamp: Can be int, float, str (ISO), or None
        
    Returns:
        ISO formatted timestamp string
    """
    ts_seconds = to_epoch_seconds(timestamp)
    if ts_seconds is None:
        return "Unknown"
    
    dt = datetime.fromtimestamp(ts_seconds, tz=timezone.utc)
    return dt.isoformat()
