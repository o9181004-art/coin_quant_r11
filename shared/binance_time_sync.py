#!/usr/bin/env python3
"""
Binance Time Synchronization
==================================================
Server time check and clock skew auto-correction.
"""

import logging
import time
from typing import Optional, Tuple

import requests

logger = logging.getLogger(__name__)


class TimeSync:
    """
    Binance server time synchronization.

    Features:
    - Server time query
    - Clock skew detection (>1000ms)
    - Auto-offset calculation and application
    """

    def __init__(self, base_url: str, max_skew_ms: int = 1000):
        """
        Initialize time sync.

        Args:
            base_url: Binance API base URL
            max_skew_ms: Maximum acceptable clock skew in milliseconds
        """
        self.base_url = base_url
        self.max_skew_ms = max_skew_ms
        self._offset_ms = 0
        self._last_sync_time = 0

    def get_server_time(self) -> Optional[int]:
        """
        Get server time from Binance API.

        Returns:
            Server timestamp in milliseconds, or None on error
        """
        try:
            url = f"{self.base_url}/api/v3/time"
            response = requests.get(url, timeout=5)
            response.raise_for_status()

            data = response.json()
            return data.get("serverTime")

        except Exception as e:
            logger.error(f"Failed to get server time: {e}")
            return None

    def check_and_sync(self) -> Tuple[bool, int, str]:
        """
        Check clock skew and calculate offset if needed.

        Returns:
            (success, offset_ms, message)
        """
        try:
            # Get local time before request
            local_before_ms = int(time.time() * 1000)

            # Get server time
            server_time_ms = self.get_server_time()

            if server_time_ms is None:
                return False, 0, "Failed to get server time"

            # Get local time after request
            local_after_ms = int(time.time() * 1000)

            # Estimate network latency (round trip time / 2)
            rtt_ms = local_after_ms - local_before_ms
            latency_ms = rtt_ms // 2

            # Estimated server time when request was sent
            estimated_server_time = server_time_ms - latency_ms

            # Calculate skew
            skew_ms = estimated_server_time - local_before_ms

            # Log result
            logger.info(f"Time sync check:")
            logger.info(f"  Local time: {local_before_ms}")
            logger.info(f"  Server time: {server_time_ms}")
            logger.info(f"  Network latency: {latency_ms}ms")
            logger.info(f"  Clock skew: {skew_ms}ms")

            # Check if skew exceeds threshold
            if abs(skew_ms) > self.max_skew_ms:
                logger.warning(
                    f"CLOCK_SKEW detected: {skew_ms}ms (threshold: {self.max_skew_ms}ms)"
                )
                logger.warning(f"  Applying auto-offset: {skew_ms}ms")

                self._offset_ms = skew_ms
                self._last_sync_time = time.time()

                return (
                    True,
                    skew_ms,
                    f"Clock skew detected: {skew_ms}ms (auto-corrected)",
                )

            else:
                logger.info(f"✅ Clock sync OK: skew={skew_ms}ms (within threshold)")

                self._offset_ms = 0
                self._last_sync_time = time.time()

                return True, 0, f"Clock sync OK: skew={skew_ms}ms"

        except Exception as e:
            logger.error(f"Time sync check failed: {e}")
            return False, 0, f"Time sync error: {e}"

    def get_offset(self) -> int:
        """Get current time offset in milliseconds"""
        return self._offset_ms

    def get_sync_age(self) -> float:
        """Get time since last sync in seconds"""
        if self._last_sync_time == 0:
            return float("inf")

        return time.time() - self._last_sync_time

    def should_resync(self, max_age_sec: int = 300) -> bool:
        """
        Check if resync is needed.

        Args:
            max_age_sec: Maximum age of sync in seconds

        Returns:
            True if resync is needed
        """
        return self.get_sync_age() > max_age_sec


if __name__ == "__main__":
    # Test time sync
    import os

    from dotenv import load_dotenv

    load_dotenv("config.env")

    # Determine base URL
    is_testnet = os.getenv("BINANCE_USE_TESTNET", "true").lower() == "true"

    if is_testnet:
        base_url = "https://testnet.binance.vision"
    else:
        base_url = "https://api.binance.com"

    print("=" * 60)
    print(" Binance Time Sync Test")
    print("=" * 60)
    print()
    print(f"Base URL: {base_url}")
    print()

    # Create time sync
    time_sync = TimeSync(base_url)

    # Check and sync
    success, offset_ms, message = time_sync.check_and_sync()

    print()

    if success:
        print(f"✅ {message}")

        if offset_ms != 0:
            print(f"   Recommended offset: {offset_ms}ms")
    else:
        print(f"❌ {message}")
