#!/usr/bin/env python3
"""
Feeder Zombie Detection
Detects when symbol snapshots are stale (>60s) despite process being alive
"""

import logging
import time
from collections import defaultdict
from typing import Dict, List

try:
    from .feeder_self_test import get_file_age
    from .path_registry import get_absolute_path
except ImportError:
    from feeder_self_test import get_file_age
    from path_registry import get_absolute_path

logger = logging.getLogger(__name__)


class ZombieDetector:
    """Detects zombie feeder state (stale snapshots despite alive process)"""

    def __init__(self, max_age_seconds: int = 60, consecutive_checks: int = 3):
        """
        Args:
            max_age_seconds: Max allowed snapshot age before considered stale
            consecutive_checks: Number of consecutive stale checks before zombie declared
        """
        self.max_age_seconds = max_age_seconds
        self.consecutive_checks = consecutive_checks
        self.stale_counts: Dict[str, int] = defaultdict(int)
        self.last_check_time = 0
        self.check_interval = 20  # Check every 20s

    def check_symbols(self, symbols: List[str], force: bool = False) -> bool:
        """
        Check if any symbols are zombie (stale for consecutive checks).

        Args:
            symbols: List of symbols to check
            force: If True, skip rate limiting

        Returns:
            True if zombie detected, False otherwise
        """
        now = time.time()

        # Rate limit checks (unless forced)
        if not force and now - self.last_check_time < self.check_interval:
            return False

        self.last_check_time = now

        snapshots_dir = get_absolute_path("shared_data", "snapshots")
        zombie_detected = False

        for symbol in symbols:
            symbol = symbol.upper()
            snapshot_file = snapshots_dir / f"prices_{symbol}.json"

            age = get_file_age(snapshot_file)

            if age is None:
                # File missing
                self.stale_counts[symbol] += 1
                logger.warning(
                    f"[{symbol}] Snapshot missing (count: {self.stale_counts[symbol]})"
                )
            elif age > self.max_age_seconds:
                # Stale
                self.stale_counts[symbol] += 1
                logger.warning(
                    f"[{symbol}] Snapshot stale: age={age:.1f}s "
                    f"(count: {self.stale_counts[symbol]}/{self.consecutive_checks})"
                )
            else:
                # Fresh - reset count
                if self.stale_counts[symbol] > 0:
                    logger.info(
                        f"[{symbol}] Snapshot recovered (was stale {self.stale_counts[symbol]} times)"
                    )
                self.stale_counts[symbol] = 0

            # Check if zombie threshold reached
            if self.stale_counts[symbol] >= self.consecutive_checks:
                logger.error(
                    f"🧟 ZOMBIE_FEEDER_DETECTED: [{symbol}] stale for {self.stale_counts[symbol]} "
                    f"consecutive checks (age={age:.1f}s > {self.max_age_seconds}s)"
                )
                zombie_detected = True

        return zombie_detected

    def reset(self):
        """Reset all stale counts"""
        self.stale_counts.clear()

    def get_status(self) -> Dict[str, int]:
        """Get current stale counts for all symbols"""
        return dict(self.stale_counts)


if __name__ == "__main__":
    # Self-test
    print("Testing zombie detector...")

    from feeder_egress_writer import write_symbol_snapshot

    # Create fresh snapshot
    write_symbol_snapshot(
        symbol="TESTUSDT",
        last_price=100.0,
        orderbook={"bids": [[100.0, 1.0]], "asks": [[101.0, 1.0]]},
    )

    detector = ZombieDetector(max_age_seconds=5, consecutive_checks=2)

    # Check 1: Fresh (should be OK)
    zombie = detector.check_symbols(["TESTUSDT"])
    print(f"Check 1 (fresh): zombie={zombie}, counts={detector.get_status()}")
    assert not zombie, "Should not be zombie when fresh"

    # Wait to make it stale
    print("Waiting 6s to make snapshot stale...")
    time.sleep(6)

    # Check 2: Stale once (not zombie yet)
    zombie = detector.check_symbols(["TESTUSDT"], force=True)
    print(f"Check 2 (stale 1x): zombie={zombie}, counts={detector.get_status()}")
    assert not zombie, "Should not be zombie after 1 stale check"

    # Check 3: Stale twice (zombie!)
    zombie = detector.check_symbols(["TESTUSDT"], force=True)
    print(f"Check 3 (stale 2x): zombie={zombie}, counts={detector.get_status()}")
    assert zombie, "Should be zombie after 2 consecutive stale checks"

    # Cleanup
    snapshots_dir = get_absolute_path("shared_data", "snapshots")
    test_file = snapshots_dir / "prices_TESTUSDT.json"
    if test_file.exists():
        test_file.unlink()

    print("\n✅ Zombie detector works!")
