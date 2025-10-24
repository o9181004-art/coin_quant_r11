#!/usr/bin/env python3
"""
SSOT (Single Source of Truth) Baseline Manager
===============================================
Manages environment variable baseline for drift detection.

Features:
- Atomic baseline updates (using io_safe)
- Fingerprinting (no secrets in storage)
- Diff computation
- Baseline validation
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ====================================================
# Configuration
# ====================================================
SSOT_FILE = Path("shared_data") / "env_ssot.json"
SSOT_BACKUP_DIR = Path("shared_data") / "env_ssot_backups"


# ====================================================
# Baseline Storage
# ====================================================
def read_baseline() -> Optional[Dict]:
    """
    Read current SSOT baseline.

    Returns:
        Dict with baseline data, or None if missing/corrupt
    """
    from shared.io_safe import read_json_cooperative

    return read_json_cooperative(SSOT_FILE, default=None)


def write_baseline(baseline: Dict, backup_old: bool = True) -> bool:
    """
    Write new SSOT baseline atomically.

    Args:
        baseline: New baseline data
        backup_old: Whether to backup old baseline

    Returns:
        True if successful, False otherwise
    """
    from shared.io_safe import atomic_write_json

    # Backup old baseline if it exists
    if backup_old and SSOT_FILE.exists():
        try:
            old_baseline = read_baseline()
            if old_baseline:
                SSOT_BACKUP_DIR.mkdir(parents=True, exist_ok=True)

                timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                backup_file = SSOT_BACKUP_DIR / f"env_ssot_{timestamp_str}.json"

                result = atomic_write_json(backup_file, old_baseline)
                if result.success:
                    logger.info(f"Backed up old baseline to {backup_file.name}")
        except Exception as e:
            logger.warning(f"Failed to backup old baseline: {e}")

    # Write new baseline
    result = atomic_write_json(SSOT_FILE, baseline)

    if result.success:
        logger.info(f"Baseline updated successfully (attempts={result.attempts})")
        return True
    else:
        logger.error(f"Failed to update baseline: {result.error}")
        return False


def compute_current_baseline() -> Dict:
    """
    Compute baseline from current environment.

    Returns:
        Dict with fingerprinted environment variables

    Note: Does not save, only computes
    """
    from shared.auto_heal_config import compute_fingerprint

    # Keys to include in baseline
    keys_to_track = [
        # API Keys
        "BINANCE_API_KEY",
        "BINANCE_API_SECRET",
        "KIS_APPKEY",
        "KIS_APPSECRET",
        # Mode flags
        "IS_TESTNET",
        "USE_TESTNET",
        "BINANCE_USE_TESTNET",
        "TRADING_MODE",
        "LIVE_TRADING_ENABLED",
        "DRY_RUN",
        # System config
        "BASE_URL",
        "RISK_LIMITS",
        "DAILY_LOSS_LIMIT",
        "POSITION_LIMITS",
        # Others
        "LOG_LEVEL",
        "AUTO_REFRESH_INTERVAL",
    ]

    baseline = {
        "timestamp": time.time(),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "env_vars": {},
    }

    for key in keys_to_track:
        value = os.getenv(key, "")
        fp = compute_fingerprint(value)

        baseline["env_vars"][key] = {
            "hash": fp["hash"],
            "len": fp["len"],
            "type": fp["type"],
            "exists": bool(value),
        }

    return baseline


def compare_to_baseline() -> List[str]:
    """
    Compare current environment to baseline.

    Returns:
        List of keys that have drifted (fingerprint changed)
    """
    from shared.auto_heal_config import compute_fingerprint

    baseline = read_baseline()

    if not baseline:
        logger.warning("No baseline found - cannot detect drift")
        return []

    drifted_keys = []
    env_vars = baseline.get("env_vars", {})

    for key, baseline_fp in env_vars.items():
        current_value = os.getenv(key, "")
        current_fp = compute_fingerprint(current_value)

        # Compare fingerprints
        if current_fp["hash"] != baseline_fp["hash"]:
            drifted_keys.append(key)

    return drifted_keys


def show_diff() -> Dict:
    """
    Show diff between current env and baseline.

    Returns:
        Dict with:
        - drifted_keys: List of changed keys
        - details: {key: {old_fp, new_fp, severity}}
        - counts: {soft, medium, hard}
    """
    from shared.auto_heal_config import (
        categorize_drifts,
        classify_drift,
        compute_fingerprint,
    )

    baseline = read_baseline()

    if not baseline:
        return {
            "error": "No baseline found",
            "drifted_keys": [],
            "details": {},
            "counts": {"soft": 0, "medium": 0, "hard": 0},
        }

    # Determine env flags
    is_testnet = os.getenv("IS_TESTNET", "true").lower() == "true"
    dry_run = os.getenv("DRY_RUN", "true").lower() == "true"
    env_flags = {"is_testnet": is_testnet, "dry_run": dry_run}

    # Compare each key
    drifts = []
    env_vars = baseline.get("env_vars", {})

    for key, baseline_data in env_vars.items():
        current_value = os.getenv(key, "")
        current_fp = compute_fingerprint(current_value)

        if current_fp["hash"] != baseline_data["hash"]:
            # Drift detected
            old_fp_str = (
                f"sha256:{baseline_data['hash']}... (len={baseline_data['len']})"
            )
            new_fp_str = f"sha256:{current_fp['hash']}... (len={current_fp['len']})"

            drift = classify_drift(
                key=key,
                old_value=f"hash:{baseline_data['hash']}",  # Don't pass real value
                new_value=f"hash:{current_fp['hash']}",
                env_flags=env_flags,
            )

            drifts.append(drift)

    # Categorize
    categorized = categorize_drifts(drifts)

    # Build result
    details = {}
    for drift in drifts:
        details[drift.key] = {
            "old_fp": drift.old_fingerprint,
            "new_fp": drift.new_fingerprint,
            "severity": drift.severity,
            "hint": drift.hint,
        }

    return {
        "drifted_keys": [d.key for d in drifts],
        "details": details,
        "counts": {
            "soft": len(categorized["soft"]),
            "medium": len(categorized["medium"]),
            "hard": len(categorized["hard"]),
        },
        "system_state": (
            "RED" if categorized["hard"] else "YELLOW" if drifts else "GREEN"
        ),
    }


# ====================================================
# Baseline Operations
# ====================================================
def set_new_baseline(force: bool = False) -> bool:
    """
    Set current environment as new baseline.

    Args:
        force: If True, allow even with HARD drifts (use with caution)

    Returns:
        True if successful, False otherwise

    Safety:
        - Only allowed in TESTNET/PAPER mode (unless force=True)
        - Blocks if any HARD drifts exist (unless force=True)
        - Creates backup of old baseline
    """
    # Check mode
    is_testnet = os.getenv("IS_TESTNET", "true").lower() == "true"
    dry_run = os.getenv("DRY_RUN", "true").lower() == "true"

    if not force:
        if not is_testnet or not dry_run:
            logger.error(
                "Baseline updates not allowed in LIVE mode (use force=True to override)"
            )
            return False

        # Check for HARD drifts
        diff = show_diff()
        if diff.get("counts", {}).get("hard", 0) > 0:
            logger.error("Cannot set baseline with HARD drifts present")
            return False

    # Compute new baseline
    new_baseline = compute_current_baseline()

    # Write atomically
    success = write_baseline(new_baseline, backup_old=True)

    if success:
        logger.info("New baseline set successfully")
    else:
        logger.error("Failed to set new baseline")

    return success


def regenerate_baseline_minimal() -> bool:
    """
    Regenerate minimal baseline (emergency fallback).

    Use when baseline is missing or corrupt.
    Creates a baseline from current env with HARD state.

    Returns:
        True if successful
    """
    logger.warning("Regenerating minimal baseline (emergency)")

    baseline = compute_current_baseline()

    # Mark as emergency regeneration
    baseline["regenerated"] = True
    baseline["regeneration_reason"] = "missing or corrupt baseline"

    return write_baseline(baseline, backup_old=False)


# ====================================================
# Testing & Validation
# ====================================================
if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("SSOT Baseline Manager Test")
    print("=" * 60)

    # Test 1: Compute baseline
    print("\nTest 1: Compute Baseline")
    baseline = compute_current_baseline()
    print(f"  Timestamp: {baseline['timestamp_utc']}")
    print(f"  Env vars: {len(baseline['env_vars'])} keys")
    print(f"  Sample keys: {list(baseline['env_vars'].keys())[:5]}")

    # Test 2: Show diff
    print("\nTest 2: Show Diff")
    diff = show_diff()

    if "error" in diff:
        print(f"  ℹ️  {diff['error']} (expected for fresh install)")
    else:
        print(f"  Drifted keys: {len(diff['drifted_keys'])}")
        print(f"  SOFT: {diff['counts']['soft']}")
        print(f"  MEDIUM: {diff['counts']['medium']}")
        print(f"  HARD: {diff['counts']['hard']}")
        print(f"  System State: {diff['system_state']}")

    # Test 3: Fingerprinting (no secrets)
    print("\nTest 3: Fingerprint Safety")
    api_key = os.getenv("BINANCE_API_KEY", "test_key_123")

    from shared.auto_heal_config import compute_fingerprint

    fp = compute_fingerprint(api_key)
    fp_str = f"sha256:{fp['hash']}... (len={fp['len']})"

    print(f"  API Key: {api_key[:8]}...{api_key[-8:] if len(api_key) > 16 else ''}")
    print(f"  Fingerprint: {fp_str}")

    assert api_key not in fp_str, "❌ Secret leaked!"
    assert api_key not in json.dumps(baseline), "❌ Secret in baseline!"

    print("  ✅ No secrets in fingerprints or baseline")

    print("\n" + "=" * 60)
    print("✅ All SSOT baseline tests passed")
    print("=" * 60)

    sys.exit(0)
