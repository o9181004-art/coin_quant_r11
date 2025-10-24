#!/usr/bin/env python3
"""
Binance 3-Step Health Probe
==================================================
Startup health check for Binance API connectivity.
"""

import logging
from enum import Enum
from typing import Dict, Tuple

from shared.binance_api_client import BinanceAPIClient, BinanceAPIError
from shared.binance_config import get_binance_config

logger = logging.getLogger(__name__)


class ProbeStatus(Enum):
    """Health probe status"""

    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"


class BinanceHealthProbe:
    """
    3-step health probe for Binance API.

    Steps:
    1. Ping (unsigned) - network connectivity
    2. Account (signed) - authentication & signature
    3. Trades (signed) - full API access
    """

    def __init__(self, client: BinanceAPIClient = None):
        """
        Initialize health probe.

        Args:
            client: BinanceAPIClient instance (creates new if None)
        """
        self.client = client or BinanceAPIClient()
        self.results = {}

    def probe_ping(self) -> Tuple[ProbeStatus, str]:
        """
        Step 1: Ping test (unsigned).

        Returns:
            (status, message)
        """
        try:
            self.client.ping()
            return ProbeStatus.PASS, "Ping OK (network connected)"

        except Exception as e:
            return ProbeStatus.FAIL, f"Ping failed: {e}"

    def probe_account(self) -> Tuple[ProbeStatus, str]:
        """
        Step 2: Account test (signed).

        Returns:
            (status, message)
        """
        try:
            account = self.client.get_account()

            can_trade = account.get("canTrade", False)
            balances = [
                b
                for b in account.get("balances", [])
                if float(b["free"]) > 0 or float(b["locked"]) > 0
            ]

            return (
                ProbeStatus.PASS,
                f"Account OK (canTrade={can_trade}, {len(balances)} assets)",
            )

        except BinanceAPIError as e:
            diagnosis = e.get_diagnosis()
            return ProbeStatus.FAIL, f"Account failed: {diagnosis}"

        except Exception as e:
            return ProbeStatus.FAIL, f"Account error: {e}"

    def probe_trades(self, symbol: str = "BTCUSDT") -> Tuple[ProbeStatus, str]:
        """
        Step 3: Trades test (signed read).

        Args:
            symbol: Symbol to query

        Returns:
            (status, message)
        """
        try:
            # Try to get recent trades
            result = self.client.get(
                "/api/v3/myTrades", params={"symbol": symbol, "limit": 1}, signed=True
            )

            return ProbeStatus.PASS, f"Trades OK ({len(result)} trades for {symbol})"

        except BinanceAPIError as e:
            # Empty trades list is OK
            if e.error_code == -1121:  # Invalid symbol
                return ProbeStatus.SKIP, f"Symbol {symbol} not available"

            diagnosis = e.get_diagnosis()
            return ProbeStatus.FAIL, f"Trades failed: {diagnosis}"

        except Exception as e:
            return ProbeStatus.FAIL, f"Trades error: {e}"

    def run_all(self, skip_trades: bool = False) -> Dict[str, Tuple[ProbeStatus, str]]:
        """
        Run all health probes.

        Args:
            skip_trades: Skip trades probe (optional)

        Returns:
            Dict of results: {step_name: (status, message)}
        """
        results = {}

        logger.info("=" * 60)
        logger.info(" Binance Health Probe")
        logger.info("=" * 60)

        # Step 0: Time sync
        logger.info("Step 0: Time sync")
        success, offset_ms, message = self.client.sync_time()
        if success:
            logger.info(f"  ✅ {message}")
            if offset_ms != 0:
                logger.warning(f"  ⚠️  Applied time offset: {offset_ms}ms")
        else:
            logger.error(f"  ❌ {message}")

        results["time_sync"] = (
            ProbeStatus.PASS if success else ProbeStatus.FAIL,
            message,
        )

        # Step 1: Ping
        logger.info("Step 1: Ping (unsigned)")
        status, message = self.probe_ping()
        logger.info(f"  {'✅' if status == ProbeStatus.PASS else '❌'} {message}")
        results["ping"] = (status, message)

        if status == ProbeStatus.FAIL:
            logger.error("  Ping failed → base_url invalid or network issue")
            logger.error("  Stopping probe")
            return results

        # Step 2: Account
        logger.info("Step 2: Account (signed)")
        status, message = self.probe_account()
        logger.info(f"  {'✅' if status == ProbeStatus.PASS else '❌'} {message}")
        results["account"] = (status, message)

        if status == ProbeStatus.FAIL:
            logger.error(
                "  Account failed → mode/base_url mismatch or signature/timestamp issue"
            )

            if "Signature error" in message:
                logger.error(
                    "  → Check API keys (might be invalid, expired, or wrong testnet)"
                )

            if "Timestamp error" in message:
                logger.error("  → Check system clock (should be synced with NTP)")

        # Step 3: Trades (optional)
        if (
            not skip_trades
            and results.get("account", (ProbeStatus.FAIL,))[0] == ProbeStatus.PASS
        ):
            logger.info("Step 3: Trades (signed read)")
            status, message = self.probe_trades()
            logger.info(f"  {'✅' if status == ProbeStatus.PASS else '⚠️'} {message}")
            results["trades"] = (status, message)

        logger.info("=" * 60)

        # Summary
        all_pass = all(
            status == ProbeStatus.PASS
            for status, _ in results.values()
            if status != ProbeStatus.SKIP
        )

        if all_pass:
            logger.info("✅ All probes passed - API ready")
        else:
            logger.warning("❌ Some probes failed - check configuration")

        logger.info("=" * 60)

        self.results = results
        return results

    def is_healthy(self) -> bool:
        """Check if all critical probes passed"""
        if not self.results:
            return False

        critical_probes = ["ping", "account"]

        for probe in critical_probes:
            if probe not in self.results:
                return False

            status, _ = self.results[probe]
            if status != ProbeStatus.PASS:
                return False

        return True


if __name__ == "__main__":
    # Test health probe
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    probe = BinanceHealthProbe()
    results = probe.run_all(skip_trades=True)

    print()
    print("=" * 60)
    print(f" Health Status: {'✅ HEALTHY' if probe.is_healthy() else '❌ UNHEALTHY'}")
    print("=" * 60)
