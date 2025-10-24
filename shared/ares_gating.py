#!/usr/bin/env python3
"""
ARES Gating & Log Throttling
Gates signal generation on snapshot freshness + orderbook presence
"""

import logging
import time
from collections import defaultdict
from typing import Dict, List, Optional

try:
    from .trader_reader_tolerant import SnapshotStatus, check_snapshot_status
except ImportError:
    from trader_reader_tolerant import SnapshotStatus, check_snapshot_status

logger = logging.getLogger(__name__)


class AresGate:
    """Gates ARES signal generation on data freshness"""

    def __init__(self, max_age_seconds: int = 10, log_throttle_seconds: int = 60):
        """
        Args:
            max_age_seconds: Max allowed snapshot age
            log_throttle_seconds: Min time between repeated logs for same symbol
        """
        self.max_age_seconds = max_age_seconds
        self.log_throttle_seconds = log_throttle_seconds
        self.last_log_time: Dict[str, float] = defaultdict(float)
        self.last_status: Dict[str, SnapshotStatus] = {}

    def can_generate_signal(self, symbol: str) -> tuple[bool, Optional[str]]:
        """
        Check if signal generation is allowed for symbol.

        Args:
            symbol: Trading symbol

        Returns:
            (can_generate, reason_if_blocked)
        """
        symbol = symbol.upper()

        # Check snapshot status
        status, details = check_snapshot_status(
            symbol, max_age_seconds=self.max_age_seconds, require_orderbook=True
        )

        # Track status changes
        prev_status = self.last_status.get(symbol)
        self.last_status[symbol] = status

        # Log status changes
        if prev_status and prev_status != status:
            if status == SnapshotStatus.OK:
                logger.info(f"✅ DATA_RESUMED(symbol={symbol})")
            elif prev_status == SnapshotStatus.OK:
                logger.warning(f"⚠️  DATA_LOST(symbol={symbol}): {status.value}")

        # Allow if OK
        if status == SnapshotStatus.OK:
            return True, None

        # Throttle logging for non-OK statuses
        now = time.time()
        last_log = self.last_log_time[symbol]

        if now - last_log >= self.log_throttle_seconds:
            logger.warning(
                f"NO_REALTIME_DATA(symbol={symbol}): {status.value} - {details}"
            )
            self.last_log_time[symbol] = now

        return False, f"{status.value}: {details}"

    def check_all_symbols(self, symbols: List[str]) -> Dict[str, bool]:
        """
        Check all symbols and return eligibility map.

        Args:
            symbols: List of symbols to check

        Returns:
            Dict mapping symbol → can_generate
        """
        results = {}
        for symbol in symbols:
            can_generate, _ = self.can_generate_signal(symbol)
            results[symbol.upper()] = can_generate
        return results

    def reset_throttle(self, symbol: Optional[str] = None):
        """Reset log throttle (for testing or manual reset)"""
        if symbol:
            self.last_log_time[symbol.upper()] = 0
        else:
            self.last_log_time.clear()


if __name__ == "__main__":
    # Self-test
    print("Testing ARES gating...")

    from feeder_egress_writer import write_symbol_snapshot

    gate = AresGate(max_age_seconds=10, log_throttle_seconds=2)

    # Test 1: Fresh snapshot with OB - should allow
    write_symbol_snapshot(
        symbol="TESTUSDT",
        last_price=100.0,
        orderbook={"bids": [[100.0, 1.0]], "asks": [[101.0, 1.0]]},
    )

    can_gen, reason = gate.can_generate_signal("TESTUSDT")
    print(f"Test 1 (fresh with OB): can_generate={can_gen}, reason={reason}")
    assert can_gen, "Should allow when fresh with OB"

    # Test 2: Fresh but no OB - should block
    write_symbol_snapshot(
        symbol="TESTUSDT",
        last_price=100.0,
        orderbook={"bids": [], "asks": []},
    )

    can_gen, reason = gate.can_generate_signal("TESTUSDT")
    print(f"Test 2 (fresh NO OB): can_generate={can_gen}, reason={reason}")
    assert not can_gen, "Should block when no OB"

    # Test 3: Log throttling - call twice rapidly
    gate.reset_throttle("TESTUSDT")
    can_gen1, _ = gate.can_generate_signal("TESTUSDT")
    time.sleep(0.5)  # < throttle_seconds
    can_gen2, _ = gate.can_generate_signal("TESTUSDT")
    print(
        f"Test 3 (throttling): both blocked={not can_gen1 and not can_gen2} (logs should be throttled)"
    )

    # Test 4: Check all symbols
    write_symbol_snapshot(
        "SYM1USDT", 100.0, {"bids": [[100.0, 1.0]], "asks": [[101.0, 1.0]]}
    )
    write_symbol_snapshot("SYM2USDT", 200.0, {"bids": [], "asks": []})

    results = gate.check_all_symbols(["SYM1USDT", "SYM2USDT"])
    print(f"Test 4 (check all): {results}")
    assert results["SYM1USDT"] == True, "SYM1USDT should be allowed"
    assert results["SYM2USDT"] == False, "SYM2USDT should be blocked"

    # Cleanup
    from path_registry import get_absolute_path

    snapshots_dir = get_absolute_path("shared_data", "snapshots")
    for symbol in ["TESTUSDT", "SYM1USDT", "SYM2USDT"]:
        test_file = snapshots_dir / f"prices_{symbol}.json"
        if test_file.exists():
            test_file.unlink()

    print("\n✅ ARES gating works!")
