#!/usr/bin/env python3
"""
Trader Resilience
========================================
Makes Trader resilient to UDS staleness.

Features:
- Continue running in DEGRADED mode when UDS stale
- Retry/backoff on missing/stale data
- Detailed staleness reasons
- No service stoppage on data issues
"""

import json
import time
from pathlib import Path
from typing import Dict, Optional, Tuple


class StalenessPolicies:
    """Staleness detection policies"""

    STALE_THRESHOLD_SEC = 120  # 2 minutes

    @staticmethod
    def check_uds_freshness(uds_path: Path) -> Tuple[str, Optional[str]]:
        """
        Check UDS freshness.

        Returns:
            (status, reason)

        Status:
            - LIVE: UDS is fresh
            - DEGRADED: UDS stale but readable
            - ERROR: UDS missing/corrupt

        Reason:
            - None: OK
            - no_file: File missing
            - json_error: Corrupt JSON
            - stale_Xs: Stale by X seconds
        """
        # Check if file exists
        if not uds_path.exists():
            return "ERROR", "no_file"

        # Try to read
        try:
            with open(uds_path, "r", encoding="utf-8") as f:
                data = json.load(f)

        except json.JSONDecodeError as e:
            return "ERROR", f"json_error:{e}"

        except Exception as e:
            return "ERROR", f"read_error:{e}"

        # Check timestamp
        ts = data.get("ts", 0)

        if ts == 0:
            return "DEGRADED", "no_timestamp"

        # Convert to seconds if milliseconds
        if ts > 1e12:
            ts = ts / 1000.0

        age = time.time() - ts

        if age > StalenessPolicies.STALE_THRESHOLD_SEC:
            return "DEGRADED", f"stale_{int(age)}s"

        # Fresh
        return "LIVE", None

    @staticmethod
    def get_retry_backoff(attempt: int) -> float:
        """
        Get retry backoff delay.

        Args:
            attempt: Retry attempt number (0-based)

        Returns:
            Delay in seconds

        Backoff: 1s → 2s → 4s → 8s → 16s (max)
        """
        backoff_levels = [1, 2, 4, 8, 16]
        idx = min(attempt, len(backoff_levels) - 1)
        return backoff_levels[idx]


def format_staleness_log(status: str, reason: Optional[str], uds_path: Path) -> str:
    """
    Format staleness log message.

    Args:
        status: LIVE, DEGRADED, ERROR
        reason: Staleness reason
        uds_path: UDS file path

    Returns:
        Formatted log message
    """
    if status == "LIVE":
        return f"[Trader] UDS: LIVE ({uds_path.name})"

    elif status == "DEGRADED":
        if reason == "no_timestamp":
            return f"[Trader] UDS: DEGRADED (no timestamp) - {uds_path.name}"
        elif reason and reason.startswith("stale_"):
            age_str = reason.replace("stale_", "")
            return f"[Trader] UDS: DEGRADED (stale {age_str}) - continuing with retry"
        else:
            return f"[Trader] UDS: DEGRADED ({reason}) - {uds_path.name}"

    elif status == "ERROR":
        if reason == "no_file":
            return f"[Trader] UDS: ERROR (file missing: {uds_path}) - will retry"
        elif reason and reason.startswith("json_error"):
            return f"[Trader] UDS: ERROR (corrupt JSON) - will retry"
        else:
            return f"[Trader] UDS: ERROR ({reason}) - will retry"

    return f"[Trader] UDS: {status} ({reason})"


# Unit tests
if __name__ == "__main__":
    import shutil
    import tempfile

    print("Testing Trader resilience...")

    test_dir = Path(tempfile.mkdtemp())

    try:
        # Test 1: Missing file
        print("\n1. Missing UDS file:")
        missing_path = test_dir / "missing.json"

        status, reason = StalenessPolicies.check_uds_freshness(missing_path)
        assert status == "ERROR", "Should be ERROR"
        assert reason == "no_file", "Should detect missing file"

        log_msg = format_staleness_log(status, reason, missing_path)
        print(f"  {log_msg}")
        print("✅ Missing file detection works")

        # Test 2: Corrupt JSON
        print("\n2. Corrupt JSON:")
        corrupt_path = test_dir / "corrupt.json"
        corrupt_path.write_text("{invalid json}")

        status, reason = StalenessPolicies.check_uds_freshness(corrupt_path)
        assert status == "ERROR", "Should be ERROR"
        assert "json_error" in reason, "Should detect JSON error"

        log_msg = format_staleness_log(status, reason, corrupt_path)
        print(f"  {log_msg}")
        print("✅ Corrupt JSON detection works")

        # Test 3: Stale timestamp
        print("\n3. Stale timestamp:")
        stale_path = test_dir / "stale.json"

        stale_data = {
            "ts": int((time.time() - 200) * 1000),  # 200 seconds ago
            "status": "LIVE",
        }

        with open(stale_path, "w") as f:
            json.dump(stale_data, f)

        status, reason = StalenessPolicies.check_uds_freshness(stale_path)
        assert status == "DEGRADED", "Should be DEGRADED"
        assert "stale_" in reason, "Should show staleness"

        log_msg = format_staleness_log(status, reason, stale_path)
        print(f"  {log_msg}")
        print("✅ Stale detection works")

        # Test 4: Fresh data
        print("\n4. Fresh data:")
        fresh_path = test_dir / "fresh.json"

        fresh_data = {
            "ts": int(time.time() * 1000),
            "status": "LIVE",
            "symbols": ["btcusdt", "ethusdt"],
        }

        with open(fresh_path, "w") as f:
            json.dump(fresh_data, f)

        status, reason = StalenessPolicies.check_uds_freshness(fresh_path)
        assert status == "LIVE", "Should be LIVE"
        assert reason is None, "Should have no reason"

        log_msg = format_staleness_log(status, reason, fresh_path)
        print(f"  {log_msg}")
        print("✅ Fresh detection works")

        # Test 5: Retry backoff
        print("\n5. Retry backoff:")

        for i in range(6):
            delay = StalenessPolicies.get_retry_backoff(i)
            print(f"  Attempt {i}: {delay}s")

        assert StalenessPolicies.get_retry_backoff(0) == 1, "First should be 1s"
        assert StalenessPolicies.get_retry_backoff(4) == 16, "Max should be 16s"
        assert StalenessPolicies.get_retry_backoff(10) == 16, "Should cap at 16s"

        print("✅ Retry backoff works")

        print("\n" + "=" * 50)
        print("All trader resilience tests passed! ✅")
        print("=" * 50)

    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
