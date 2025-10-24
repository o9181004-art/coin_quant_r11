#!/usr/bin/env python3
"""
Binance Mode/Endpoint Validator
========================================
Enforce strict mode-endpoint parity.
"""

import logging
from enum import Enum
from typing import Tuple

logger = logging.getLogger(__name__)


class BinanceMode(Enum):
    """Binance trading mode"""

    SPOT = "SPOT"
    FUTURES_USDM = "FUTURES_USDM"


class ModeEndpointValidator:
    """
    Validate mode/endpoint consistency.

    Enforces strict one-to-one mapping:
    - SPOT + TESTNET → https://testnet.binance.vision
    - SPOT + LIVE → https://api.binance.com
    - FUTURES_USDM + TESTNET → https://testnet.binancefuture.com
    - FUTURES_USDM + LIVE → https://fapi.binance.com
    """

    # Canonical mapping
    MODE_ENDPOINT_MAP = {
        (BinanceMode.SPOT, True): "https://testnet.binance.vision",
        (BinanceMode.SPOT, False): "https://api.binance.com",
        (BinanceMode.FUTURES_USDM, True): "https://testnet.binancefuture.com",
        (BinanceMode.FUTURES_USDM, False): "https://fapi.binance.com",
    }

    @staticmethod
    def get_canonical_endpoint(mode: BinanceMode, is_testnet: bool) -> str:
        """
        Get canonical endpoint for mode/testnet combination.

        Args:
            mode: Trading mode
            is_testnet: Testnet flag

        Returns:
            Canonical base URL
        """
        key = (mode, is_testnet)

        if key not in ModeEndpointValidator.MODE_ENDPOINT_MAP:
            raise ValueError(
                f"Invalid mode/testnet combination: {mode.value}, testnet={is_testnet}"
            )

        return ModeEndpointValidator.MODE_ENDPOINT_MAP[key]

    @staticmethod
    def validate_endpoint(
        mode: BinanceMode, is_testnet: bool, actual_endpoint: str
    ) -> Tuple[bool, str]:
        """
        Validate that endpoint matches mode/testnet.

        Args:
            mode: Trading mode
            is_testnet: Testnet flag
            actual_endpoint: Actual base URL being used

        Returns:
            (is_valid, error_message)
        """
        expected = ModeEndpointValidator.get_canonical_endpoint(mode, is_testnet)

        # Normalize URLs (remove trailing slash)
        expected_normalized = expected.rstrip("/")
        actual_normalized = actual_endpoint.rstrip("/")

        if expected_normalized != actual_normalized:
            return (
                False,
                f"MODE_ENDPOINT_MISMATCH: mode={mode.value}, testnet={is_testnet}, expected={expected}, got={actual_endpoint}",
            )

        return True, "OK"

    @staticmethod
    def check_cross_component_parity(
        feeder_config: dict, account_config: dict
    ) -> Tuple[bool, str]:
        """
        Check if Feeder and Account Service use the same mode/endpoint.

        Args:
            feeder_config: Feeder config dict with {mode, is_testnet, base_url}
            account_config: Account config dict with {mode, is_testnet, base_url}

        Returns:
            (is_consistent, error_message)
        """
        # Check mode
        if feeder_config.get("mode") != account_config.get("mode"):
            return (
                False,
                f"MODE_DRIFT: feeder={feeder_config.get('mode')}, account={account_config.get('mode')}",
            )

        # Check testnet flag
        if feeder_config.get("is_testnet") != account_config.get("is_testnet"):
            return (
                False,
                f"TESTNET_DRIFT: feeder={feeder_config.get('is_testnet')}, account={account_config.get('is_testnet')}",
            )

        # Check base URL
        feeder_url = feeder_config.get("base_url", "").rstrip("/")
        account_url = account_config.get("base_url", "").rstrip("/")

        if feeder_url != account_url:
            return False, f"BASE_URL_DRIFT: feeder={feeder_url}, account={account_url}"

        return True, "OK"


if __name__ == "__main__":
    # Test mode/endpoint validation
    print("=" * 60)
    print(" Mode/Endpoint Validator Tests")
    print("=" * 60)
    print()

    test_cases = [
        (BinanceMode.SPOT, True, "https://testnet.binance.vision", True),
        (BinanceMode.SPOT, True, "https://api.binance.com", False),  # Wrong endpoint
        (BinanceMode.FUTURES_USDM, True, "https://testnet.binancefuture.com", True),
        (
            BinanceMode.FUTURES_USDM,
            True,
            "https://testnet.binance.vision",
            False,
        ),  # Wrong endpoint
    ]

    for mode, is_testnet, endpoint, should_pass in test_cases:
        is_valid, msg = ModeEndpointValidator.validate_endpoint(
            mode, is_testnet, endpoint
        )

        status = "✅" if is_valid == should_pass else "❌"
        print(f"{status} mode={mode.value}, testnet={is_testnet}, endpoint={endpoint}")
        print(f"   Result: {is_valid}, Message: {msg}")
        print()

    # Test cross-component parity
    print("Cross-component parity tests:")
    print()

    feeder = {
        "mode": "SPOT",
        "is_testnet": True,
        "base_url": "https://testnet.binance.vision",
    }
    account_ok = {
        "mode": "SPOT",
        "is_testnet": True,
        "base_url": "https://testnet.binance.vision",
    }
    account_bad = {
        "mode": "SPOT",
        "is_testnet": True,
        "base_url": "https://api.binance.com",
    }

    is_ok, msg = ModeEndpointValidator.check_cross_component_parity(feeder, account_ok)
    print(f"✅ Same config: {is_ok}, {msg}")

    is_ok, msg = ModeEndpointValidator.check_cross_component_parity(feeder, account_bad)
    print(f"❌ Different URL: {is_ok}, {msg}")
