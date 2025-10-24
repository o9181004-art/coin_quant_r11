#!/usr/bin/env python3
"""
Freshness Gates - Health State Thresholds
==========================================
Define OK/YELLOW/RED thresholds for health checks.

Thresholds:
- UDS: OK ≤30s / YELLOW ≤120s / RED >120s
- DataBus: OK ≤60s / YELLOW ≤180s / RED >180s
"""

import logging
from enum import Enum
from typing import Dict, Tuple

logger = logging.getLogger(__name__)


class HealthState(Enum):
    """Health state levels"""

    OK = "OK"
    YELLOW = "YELLOW"
    RED = "RED"
    UNKNOWN = "UNKNOWN"


# ====================================================
# Thresholds
# ====================================================
UDS_OK_THRESHOLD = 30  # seconds
UDS_YELLOW_THRESHOLD = 120  # seconds

DATABUS_OK_THRESHOLD = 60  # seconds
DATABUS_YELLOW_THRESHOLD = 180  # seconds


def evaluate_uds_freshness(age_seconds: float) -> HealthState:
    """
    Evaluate UDS health state based on age.

    Args:
        age_seconds: Age in seconds

    Returns:
        HealthState (OK/YELLOW/RED)
    """
    if age_seconds <= UDS_OK_THRESHOLD:
        return HealthState.OK
    elif age_seconds <= UDS_YELLOW_THRESHOLD:
        return HealthState.YELLOW
    else:
        return HealthState.RED


def evaluate_databus_freshness(age_seconds: float) -> HealthState:
    """
    Evaluate DataBus health state based on age.

    Args:
        age_seconds: Age in seconds

    Returns:
        HealthState (OK/YELLOW/RED)
    """
    if age_seconds <= DATABUS_OK_THRESHOLD:
        return HealthState.OK
    elif age_seconds <= DATABUS_YELLOW_THRESHOLD:
        return HealthState.YELLOW
    else:
        return HealthState.RED


def evaluate_overall_health() -> Tuple[HealthState, Dict]:
    """
    Evaluate overall system health.

    Returns:
        (HealthState, details dict)
    """
    from shared.health_gates import get_databus_age, get_uds_age

    databus_age = get_databus_age()
    uds_age = get_uds_age()

    if databus_age is None or uds_age is None:
        return HealthState.UNKNOWN, {
            "databus_age": databus_age,
            "uds_age": uds_age,
            "databus_state": "MISSING",
            "uds_state": "MISSING",
        }

    databus_state = evaluate_databus_freshness(databus_age)
    uds_state = evaluate_uds_freshness(uds_age)

    # Overall state is worst of components
    if databus_state == HealthState.RED or uds_state == HealthState.RED:
        overall = HealthState.RED
    elif databus_state == HealthState.YELLOW or uds_state == HealthState.YELLOW:
        overall = HealthState.YELLOW
    else:
        overall = HealthState.OK

    return overall, {
        "databus_age": databus_age,
        "uds_age": uds_age,
        "databus_state": databus_state.value,
        "uds_state": uds_state.value,
    }


def should_block_trading(health_state: HealthState) -> bool:
    """
    Determine if trading should be blocked based on health state.

    Args:
        health_state: Current health state

    Returns:
        True if trading should be blocked
    """
    return health_state == HealthState.RED


def format_health_summary(details: Dict) -> str:
    """
    Format one-line health summary.

    Args:
        details: Details dict from evaluate_overall_health()

    Returns:
        One-line summary string
    """
    databus_age = details.get("databus_age", 0)
    uds_age = details.get("uds_age", 0)
    databus_state = details.get("databus_state", "UNKNOWN")
    uds_state = details.get("uds_state", "UNKNOWN")

    return (
        f"UDS={uds_age:.1f}s ({uds_state}) "
        f"DataBus={databus_age:.1f}s ({databus_state})"
    )


# ====================================================
# Testing
# ====================================================
if __name__ == "__main__":
    print("=" * 60)
    print("Freshness Gates Test")
    print("=" * 60)

    # Test thresholds
    test_cases = [
        # (age, expected_state_uds, expected_state_databus)
        (10, HealthState.OK, HealthState.OK),
        (45, HealthState.YELLOW, HealthState.OK),
        (90, HealthState.YELLOW, HealthState.YELLOW),
        (150, HealthState.RED, HealthState.YELLOW),
        (200, HealthState.RED, HealthState.RED),
    ]

    print("\nUDS & DataBus State Evaluation:")
    for age, expected_uds, expected_databus in test_cases:
        uds_state = evaluate_uds_freshness(age)
        databus_state = evaluate_databus_freshness(age)

        uds_ok = "✅" if uds_state == expected_uds else "❌"
        databus_ok = "✅" if databus_state == expected_databus else "❌"

        print(
            f"  Age {age}s: "
            f"UDS={uds_ok} {uds_state.value} (exp: {expected_uds.value}), "
            f"DataBus={databus_ok} {databus_state.value} (exp: {expected_databus.value})"
        )

    # Test overall health
    print("\nOverall Health Evaluation:")
    state, details = evaluate_overall_health()
    summary = format_health_summary(details)

    print(f"  State: {state.value}")
    print(f"  Summary: {summary}")
    print(f"  Block Trading: {should_block_trading(state)}")

    print("\n" + "=" * 60)
    print("✅ Freshness gates test complete")
    print("=" * 60)

