#!/usr/bin/env python3
"""
Drift Audit Logger
==================
Log drift events to structured audit log.
"""

import time
from collections import deque
from pathlib import Path
from typing import Dict, List

# ====================================================
# Configuration
# ====================================================
AUDIT_LOG_PATH = Path("logs/audit/drift_events.jsonl")
ROLLING_WINDOW_24H = 86400  # 24 hours in seconds


# ====================================================
# Rolling Counters (24h window)
# ====================================================
_rolling_events = deque(maxlen=1000)  # Last 1000 events


def log_drift_event(key: str, severity: str, old_fp: str, new_fp: str, hint: str):
    """
    Log drift event to audit log.

    Args:
        key: Environment variable key
        severity: SOFT/MEDIUM/HARD
        old_fp: Old fingerprint
        new_fp: New fingerprint
        hint: Human-readable hint
    """
    from shared.io_safe import append_ndjson_safe

    # Create audit directory
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Build event record (no secrets)
    event = {
        "timestamp": time.time(),
        "event_type": "drift_detected",
        "key": key,
        "severity": severity,
        "old_fp": old_fp,
        "new_fp": new_fp,
        "hint": hint,
    }

    # Append to audit log
    append_ndjson_safe(AUDIT_LOG_PATH, event)

    # Add to rolling buffer
    _rolling_events.append(event)


def log_drift_state(state: str, counts: Dict[str, int]):
    """
    Log overall drift state.

    Args:
        state: GREEN/YELLOW/RED
        counts: {soft, medium, hard}
    """
    from shared.io_safe import append_ndjson_safe

    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    event = {
        "timestamp": time.time(),
        "event_type": "drift_state",
        "state": state,
        "counts": counts,
    }

    append_ndjson_safe(AUDIT_LOG_PATH, event)


def get_24h_counts() -> Dict[str, int]:
    """
    Get drift counts for last 24 hours.

    Returns:
        Dict with soft, medium, hard counts
    """
    now = time.time()
    cutoff = now - ROLLING_WINDOW_24H

    counts = {"soft": 0, "medium": 0, "hard": 0}

    for event in _rolling_events:
        if event.get("timestamp", 0) < cutoff:
            continue

        if event.get("event_type") != "drift_detected":
            continue

        severity = event.get("severity", "").lower()
        if severity in counts:
            counts[severity] += 1

    return counts


def get_last_hard_drift_ts() -> float | None:
    """
    Get timestamp of last HARD drift.

    Returns:
        Timestamp or None
    """
    for event in reversed(_rolling_events):
        if (
            event.get("event_type") == "drift_detected"
            and event.get("severity") == "HARD"
        ):
            return event.get("timestamp")

    return None


def format_drift_summary() -> str:
    """
    Format one-line drift summary for Operator Summary.

    Returns:
        String like "drift=YELLOW soft=2 medium=1 hard=0 (24h)"
    """
    from shared.ssot_baseline_manager import show_diff

    diff = show_diff()

    if "error" in diff:
        return "drift=UNKNOWN (no baseline)"

    state = diff.get("system_state", "UNKNOWN")
    counts_24h = get_24h_counts()

    return (
        f"drift={state} "
        f"soft={counts_24h['soft']} "
        f"medium={counts_24h['medium']} "
        f"hard={counts_24h['hard']} (24h)"
    )
