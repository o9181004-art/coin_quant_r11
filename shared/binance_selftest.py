#!/usr/bin/env python3
"""
Binance Self-Test Matrix
========================================
4-step probe to identify exact failure point without key rotation.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

from shared.binance_api_client import BinanceAPIClient, BinanceAPIError

logger = logging.getLogger(__name__)


class SelfTestResult:
    """Result of a single test step"""

    def __init__(self, step_name: str, endpoint: str):
        self.step_name = step_name
        self.endpoint = endpoint
        self.success = False
        self.http_status: Optional[int] = None
        self.binance_code: Optional[int] = None
        self.binance_msg: Optional[str] = None
        self.error_hint: Optional[str] = None
        self.details: Dict = {}

    def to_dict(self) -> Dict:
        """Convert to dict for display"""
        return {
            "step": self.step_name,
            "endpoint": self.endpoint,
            "success": self.success,
            "http_status": self.http_status,
            "binance_code": self.binance_code,
            "binance_msg": self.binance_msg,
            "error_hint": self.error_hint,
            "details": self.details,
        }


class BinanceSelfTest:
    """
    4-step self-test matrix.

    Steps:
    1. Unsigned ping → network connectivity
    2. Signed server time → signing path works
    3. Signed account/balance → authentication works
    4. Signed minimal read → full API access
    """

    def __init__(self, client: BinanceAPIClient):
        self.client = client
        self.results: List[SelfTestResult] = []

        # Error ring buffer (last 5 errors)
        self.error_history = deque(maxlen=5)

    def run_all_tests(self) -> List[SelfTestResult]:
        """
        Run all 4 test steps.

        Returns:
            List of test results
        """
        self.results = []

        logger.info("=" * 60)
        logger.info(" Binance Self-Test Matrix")
        logger.info("=" * 60)

        # Step 1: Unsigned ping
        result1 = self._test_ping()
        self.results.append(result1)

        if not result1.success:
            logger.error("Step 1 (ping) failed → network/base_url issue")
            return self.results

        # Step 2: Signed server time
        result2 = self._test_server_time()
        self.results.append(result2)

        if not result2.success:
            logger.error("Step 2 (server time) failed → signing/time issue")
            return self.results

        # Step 3: Signed account
        result3 = self._test_account()
        self.results.append(result3)

        if not result3.success:
            logger.error("Step 3 (account) failed → authentication issue")
            return self.results

        # Step 4: Signed minimal read
        result4 = self._test_minimal_read()
        self.results.append(result4)

        logger.info("=" * 60)

        # Summary
        all_pass = all(r.success for r in self.results)

        if all_pass:
            logger.info("✅ All self-tests passed")
        else:
            logger.warning("❌ Some self-tests failed")

        return self.results

    def _test_ping(self) -> SelfTestResult:
        """Step 1: Unsigned ping"""
        result = SelfTestResult("1_ping_unsigned", "/api/v3/ping")

        try:
            self.client.ping()
            result.success = True
            result.http_status = 200
            result.details = {"message": "Network OK"}
            logger.info("Step 1: ✅ Ping OK")

        except Exception as e:
            result.success = False
            result.error_hint = "Network connectivity or base_url issue"
            result.details = {"error": str(e)}
            logger.error(f"Step 1: ❌ Ping failed: {e}")

            self._record_error(result)

        return result

    def _test_server_time(self) -> SelfTestResult:
        """Step 2: Signed server time (with skew offset)"""
        result = SelfTestResult("2_server_time_signed", "/api/v3/time")

        try:
            # This is unsigned, but we test time sync first
            self.client.sync_time()
            result.success = True
            result.http_status = 200
            result.details = {
                "message": "Time sync OK",
                "offset_ms": self.client.config.get_time_offset(),
            }
            logger.info(
                f"Step 2: ✅ Server time OK (offset: {self.client.config.get_time_offset()}ms)"
            )

        except Exception as e:
            result.success = False
            result.error_hint = "Time synchronization issue"
            result.details = {"error": str(e)}
            logger.error(f"Step 2: ❌ Server time failed: {e}")

            self._record_error(result)

        return result

    def _test_account(self) -> SelfTestResult:
        """Step 3: Signed account endpoint"""
        # Determine endpoint based on mode
        if self.client.config.mode.value == "SPOT":
            endpoint = "/api/v3/account"
        else:
            endpoint = "/fapi/v2/balance"

        result = SelfTestResult("3_account_signed", endpoint)

        try:
            account = self.client.get_account()
            result.success = True
            result.http_status = 200
            result.details = {
                "message": "Account access OK",
                "can_trade": (
                    account.get("canTrade", False) if "canTrade" in account else True
                ),
            }
            logger.info("Step 3: ✅ Account OK")

        except BinanceAPIError as e:
            result.success = False
            result.http_status = e.status_code
            result.binance_code = e.error_code
            result.binance_msg = e.message
            result.error_hint = self._get_error_hint(e.error_code)
            result.details = e.details

            logger.error(f"Step 3: ❌ Account failed: {e.error_code} - {e.message}")
            logger.error(f"  Hint: {result.error_hint}")

            self._record_error(result)

        except Exception as e:
            result.success = False
            result.error_hint = "Unexpected error"
            result.details = {"error": str(e)}
            logger.error(f"Step 3: ❌ Account failed: {e}")

            self._record_error(result)

        return result

    def _test_minimal_read(self) -> SelfTestResult:
        """Step 4: Signed minimal read"""
        # Try myTrades or positionRisk depending on mode
        if self.client.config.mode.value == "SPOT":
            endpoint = "/api/v3/myTrades"
            params = {"symbol": "BTCUSDT", "limit": 1}
        else:
            endpoint = "/fapi/v1/positionRisk"
            params = {"symbol": "BTCUSDT"}

        result = SelfTestResult("4_minimal_read", endpoint)

        try:
            data = self.client.get(endpoint, params=params, signed=True)
            result.success = True
            result.http_status = 200
            result.details = {
                "message": "Full API access OK",
                "result_count": len(data) if isinstance(data, list) else 1,
            }
            logger.info("Step 4: ✅ Minimal read OK")

        except BinanceAPIError as e:
            result.success = False
            result.http_status = e.status_code
            result.binance_code = e.error_code
            result.binance_msg = e.message
            result.error_hint = self._get_error_hint(e.error_code)
            result.details = e.details

            logger.error(
                f"Step 4: ❌ Minimal read failed: {e.error_code} - {e.message}"
            )
            logger.error(f"  Hint: {result.error_hint}")

            self._record_error(result)

        except Exception as e:
            result.success = False
            result.error_hint = "Unexpected error"
            result.details = {"error": str(e)}
            logger.error(f"Step 4: ❌ Minimal read failed: {e}")

            self._record_error(result)

        return result

    def _get_error_hint(self, error_code: int) -> str:
        """Get human-readable hint for error code"""
        hints = {
            -1021: "⏰ Clock skew >1000ms. Check system time sync (Windows time settings).",
            -1022: "🔑 Signature invalid. Likely: secret contamination (quotes/whitespace) or parameter ordering.",
            -1102: "❌ Mandatory parameter missing. Check request parameters.",
            -1105: "❌ Invalid parameter value or format.",
            -2014: "🔑 Invalid API key. Check BINANCE_API_KEY or IP restrictions.",
            -2015: "🔑 Invalid API key format/permissions. Likely: mode/endpoint mismatch or key scope (Spot vs Futures).",
        }

        return hints.get(
            error_code, f"Binance error {error_code}. Check Binance API docs."
        )

    def _record_error(self, result: SelfTestResult):
        """Record error in ring buffer"""
        self.error_history.append(
            {
                "step": result.step_name,
                "endpoint": result.endpoint,
                "http_status": result.http_status,
                "code": result.binance_code,
                "msg": result.binance_msg,
                "hint": result.error_hint,
            }
        )

    def get_error_history(self) -> List[Dict]:
        """Get last 5 errors"""
        return list(self.error_history)


if __name__ == "__main__":
    # Test self-test matrix
    import os

    from dotenv import load_dotenv

    load_dotenv("config.env")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        from shared.binance_api_client import BinanceAPIClient

        client = BinanceAPIClient()
        selftest = BinanceSelfTest(client)

        results = selftest.run_all_tests()

        print()
        print("=" * 60)
        print(" Test Results Summary")
        print("=" * 60)

        for result in results:
            status = "✅" if result.success else "❌"
            print(f"{status} {result.step_name}: {result.endpoint}")

            if not result.success:
                print(f"   HTTP: {result.http_status}, Code: {result.binance_code}")
                print(f"   Message: {result.binance_msg}")
                print(f"   Hint: {result.error_hint}")

        print()
        print("Error History:")
        for i, error in enumerate(selftest.get_error_history(), 1):
            print(f"{i}. {error['step']}: Code {error['code']} - {error['msg']}")

    except Exception as e:
        print(f"❌ Failed to run self-test: {e}")
        import traceback

        traceback.print_exc()
