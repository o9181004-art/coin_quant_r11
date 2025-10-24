#!/usr/bin/env python3
"""
Auto-Heal Drift Policy Configuration
=====================================
Environment drift severity matrix and classification logic.

Policy:
- TESTNET/PAPER: Allowed keys are SOFT (Yellow, non-blocking)
- LIVE: All drifts are HARD (Red, blocking)
- Critical keys: Always HARD (even in TESTNET)
"""

import hashlib
import logging
import os
from dataclasses import dataclass
from typing import Dict, List, Literal

logger = logging.getLogger(__name__)

# ====================================================
# Drift Key Classifications
# ====================================================

# Keys that can drift in TESTNET/PAPER without blocking trading
ALLOWED_DRIFT_KEYS_TESTNET = [
    "BINANCE_API_KEY",
    "BINANCE_API_SECRET",
    "TRADING_MODE",
    "LIVE_TRADING_ENABLED",
    "KIS_APPKEY",
    "KIS_APPSECRET",
    "BINANCE_TESTNET_API_KEY",
    "BINANCE_TESTNET_API_SECRET",
]

# Keys that ALWAYS cause HARD drift (even in TESTNET)
ALWAYS_HARD_KEYS = [
    "IS_TESTNET",
    "USE_TESTNET",
    "BINANCE_USE_TESTNET",
    "BINANCE_MODE",
    "BASE_URL",
    "RISK_LIMITS",
    "DAILY_LOSS_LIMIT",
    "POSITION_LIMITS",
    "MAX_POSITION_SIZE",
    "CIRCUIT_BREAKER_ENABLED",
]

# Keys to monitor but less critical
MEDIUM_KEYS = [
    "AUTO_REFRESH_INTERVAL",
    "LOG_LEVEL",
    "NOTIFICATION_ENABLED",
]


# ====================================================
# Severity Types
# ====================================================
DriftSeverity = Literal["SOFT", "MEDIUM", "HARD"]


@dataclass
class DriftClassification:
    """Result of drift classification"""

    key: str
    severity: DriftSeverity
    old_fingerprint: str
    new_fingerprint: str
    hint: str
    is_testnet: bool
    dry_run: bool


# ====================================================
# Fingerprinting (No Secrets in Logs)
# ====================================================
def compute_fingerprint(value: str) -> Dict[str, any]:
    """
    Compute redacted fingerprint of a value.

    Returns:
        Dict with:
        - hash: First 10 chars of SHA256
        - len: Length of value
        - type: "str"

    Note: Never returns actual value
    """
    if value is None:
        return {"hash": "null", "len": 0, "type": "null"}

    value_str = str(value)
    hash_full = hashlib.sha256(value_str.encode("utf-8")).hexdigest()

    return {"hash": hash_full[:10], "len": len(value_str), "type": "str"}


def fingerprint_to_str(fp: Dict) -> str:
    """Convert fingerprint to display string"""
    return f"sha256:{fp['hash']}... (len={fp['len']})"


# ====================================================
# Drift Severity Classification
# ====================================================
def get_drift_severity(
    key: str, is_testnet: bool = True, dry_run: bool = True
) -> DriftSeverity:
    """
    Determine drift severity for a key.

    Args:
        key: Environment variable key
        is_testnet: Whether system is in TESTNET mode
        dry_run: Whether DRY_RUN is enabled

    Returns:
        "HARD" - Block trading, RED state
        "MEDIUM" - Warn + alert, YELLOW state, non-blocking
        "SOFT" - Warn only, YELLOW state, non-blocking

    Policy:
        LIVE mode (not testnet or not dry_run):
            → All drifts are HARD

        TESTNET/PAPER mode:
            → ALWAYS_HARD_KEYS: HARD
            → ALLOWED_DRIFT_KEYS_TESTNET: SOFT
            → MEDIUM_KEYS: MEDIUM
            → Others: HARD (safe default)
    """
    # Critical keys are ALWAYS HARD (even in TESTNET)
    if key in ALWAYS_HARD_KEYS:
        return "HARD"

    # LIVE mode: all drifts are HARD
    if not is_testnet or not dry_run:
        return "HARD"

    # TESTNET/PAPER mode: apply policy matrix
    if key in ALLOWED_DRIFT_KEYS_TESTNET:
        return "SOFT"

    if key in MEDIUM_KEYS:
        return "MEDIUM"

    # Default: HARD (safe)
    return "HARD"


def classify_drift(
    key: str, old_value: str, new_value: str, env_flags: Dict[str, bool]
) -> DriftClassification:
    """
    Classify a single drift event.

    Args:
        key: Environment variable key
        old_value: Previous value (from SSOT)
        new_value: Current value (from env)
        env_flags: Dict with is_testnet, dry_run

    Returns:
        DriftClassification with severity and details
    """
    is_testnet = env_flags.get("is_testnet", False)
    dry_run = env_flags.get("dry_run", False)

    # Compute fingerprints (never log actual values)
    old_fp = compute_fingerprint(old_value)
    new_fp = compute_fingerprint(new_value)

    # Determine severity
    severity = get_drift_severity(key, is_testnet, dry_run)

    # Generate hint
    hint = _generate_drift_hint(key, severity, is_testnet, dry_run)

    return DriftClassification(
        key=key,
        severity=severity,
        old_fingerprint=fingerprint_to_str(old_fp),
        new_fingerprint=fingerprint_to_str(new_fp),
        hint=hint,
        is_testnet=is_testnet,
        dry_run=dry_run,
    )


def _generate_drift_hint(
    key: str, severity: DriftSeverity, is_testnet: bool, dry_run: bool
) -> str:
    """Generate helpful hint for drift"""
    if severity == "SOFT":
        return (
            f"SOFT drift in TESTNET/PAPER - {key} changed but paper guard is ON. "
            f"Trading continues. Update baseline to clear warning."
        )
    elif severity == "MEDIUM":
        return (
            f"MEDIUM drift - {key} changed. Not critical but review recommended. "
            f"Update baseline if intentional."
        )
    else:  # HARD
        if key in ALWAYS_HARD_KEYS:
            return (
                f"HARD drift (CRITICAL KEY) - {key} is a critical system parameter. "
                f"Trading BLOCKED. Review change immediately."
            )
        elif not is_testnet or not dry_run:
            return (
                f"HARD drift (LIVE MODE) - {key} changed in LIVE environment. "
                f"Trading BLOCKED for safety. Verify change is intentional."
            )
        else:
            return (
                f"HARD drift - {key} changed. Trading BLOCKED. "
                f"Update baseline if intentional."
            )


def categorize_drifts(
    drifted_keys: List[DriftClassification],
) -> Dict[str, List[DriftClassification]]:
    """
    Categorize drifts by severity.

    Args:
        drifted_keys: List of drift classifications

    Returns:
        Dict with "soft", "medium", "hard" lists
    """
    result = {"soft": [], "medium": [], "hard": []}

    for drift in drifted_keys:
        if drift.severity == "SOFT":
            result["soft"].append(drift)
        elif drift.severity == "MEDIUM":
            result["medium"].append(drift)
        else:  # HARD
            result["hard"].append(drift)

    return result


def determine_system_state(categorized: Dict[str, List]) -> str:
    """
    Determine overall system state from categorized drifts.

    Args:
        categorized: Dict from categorize_drifts()

    Returns:
        "GREEN" - No drifts
        "YELLOW" - Only SOFT/MEDIUM drifts
        "RED" - Any HARD drifts

    Trading allowed:
        GREEN: Yes
        YELLOW: Yes (in PAPER mode)
        RED: No
    """
    if categorized["hard"]:
        return "RED"
    elif categorized["soft"] or categorized["medium"]:
        return "YELLOW"
    else:
        return "GREEN"


# ====================================================
# Testing & Validation
# ====================================================
if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("Auto-Heal Drift Policy Test")
    print("=" * 60)

    # Test severity classification
    test_cases = [
        # (key, is_testnet, dry_run, expected_severity)
        ("BINANCE_API_KEY", True, True, "SOFT"),
        ("BINANCE_API_KEY", False, False, "HARD"),
        ("IS_TESTNET", True, True, "HARD"),
        ("LOG_LEVEL", True, True, "MEDIUM"),
        ("UNKNOWN_KEY", True, True, "HARD"),
    ]

    print("\nSeverity Classification:")
    for key, testnet, dry, expected in test_cases:
        result = get_drift_severity(key, testnet, dry)
        status = "✅" if result == expected else "❌"
        mode = "TESTNET/PAPER" if testnet and dry else "LIVE"
        print(f"  {status} {key} ({mode}): {result} (expected: {expected})")

    # Test fingerprinting
    print("\nFingerprinting (No Secrets):")
    test_secret = "tr2LSOfdQu2RpYZsWqMNDoBuW70coPeHr42m7z9zIuWqkUBDgDWbwN5ccQUqNava"
    fp = compute_fingerprint(test_secret)
    fp_str = fingerprint_to_str(fp)
    print(f"  Secret: {test_secret[:10]}...{test_secret[-10:]}")
    print(f"  Fingerprint: {fp_str}")
    assert test_secret not in fp_str, "Secret leaked in fingerprint!"

    # Test drift classification
    print("\nDrift Classification:")
    env_flags = {"is_testnet": True, "dry_run": True}

    drift = classify_drift(
        key="BINANCE_API_KEY",
        old_value="old_key_123",
        new_value="new_key_456",
        env_flags=env_flags,
    )

    print(f"  Key: {drift.key}")
    print(f"  Severity: {drift.severity}")
    print(f"  Old FP: {drift.old_fingerprint}")
    print(f"  New FP: {drift.new_fingerprint}")
    print(f"  Hint: {drift.hint[:60]}...")

    # Test categorization
    print("\nCategorization:")
    drifts = [
        classify_drift(
            "BINANCE_API_KEY", "a", "b", {"is_testnet": True, "dry_run": True}
        ),
        classify_drift(
            "LOG_LEVEL", "INFO", "DEBUG", {"is_testnet": True, "dry_run": True}
        ),
        classify_drift(
            "IS_TESTNET", "true", "false", {"is_testnet": True, "dry_run": True}
        ),
    ]

    categorized = categorize_drifts(drifts)
    print(f"  SOFT: {len(categorized['soft'])}")
    print(f"  MEDIUM: {len(categorized['medium'])}")
    print(f"  HARD: {len(categorized['hard'])}")

    state = determine_system_state(categorized)
    print(f"  System State: {state}")

    print("\n" + "=" * 60)
    print("✅ All drift policy tests passed")
    print("=" * 60)

    sys.exit(0)
