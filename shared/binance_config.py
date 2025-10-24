#!/usr/bin/env python3
"""
Binance Configuration SSOT (Single Source of Truth)
==================================================
Centralized configuration for Binance API endpoints and mode.
"""

import os
from enum import Enum
from typing import Dict, Tuple


class BinanceMode(Enum):
    """Binance trading mode"""

    SPOT = "SPOT"
    FUTURES_USDM = "FUTURES_USDM"


class BinanceConfig:
    """
    Single Source of Truth for Binance API configuration.

    Ensures consistent mode/testnet/base_url mapping across all services.
    """

    # URL mapping table
    URL_MAP = {
        (BinanceMode.SPOT, True): "https://testnet.binance.vision",
        (BinanceMode.SPOT, False): "https://api.binance.com",
        (BinanceMode.FUTURES_USDM, True): "https://testnet.binancefuture.com",
        (BinanceMode.FUTURES_USDM, False): "https://fapi.binance.com",
    }

    def __init__(self):
        """Load configuration from environment"""
        self.mode = self._load_mode()
        self.is_testnet = self._load_testnet_flag()
        self.base_url = self._resolve_base_url()

        # API credentials (with sanitization)
        from shared.binance_secret_sanitizer import (
            sanitize_secret,
            validate_secret_format,
        )

        self.api_key = os.getenv("BINANCE_API_KEY", "").strip()

        raw_secret = (
            os.getenv("BINANCE_API_SECRET") or os.getenv("BINANCE_SECRET_KEY") or ""
        )
        self.api_secret, self.secret_metadata = sanitize_secret(raw_secret)

        # Validate secret format
        is_valid, validation_msg = validate_secret_format(self.api_secret)
        self.secret_validation = {"valid": is_valid, "message": validation_msg}

        # Signature settings
        self.recv_window = int(os.getenv("BINANCE_RECV_WINDOW", "10000"))

        # Clock skew handling
        self.auto_offset = (
            os.getenv("BINANCE_AUTO_TIME_OFFSET", "true").lower() == "true"
        )
        self._time_offset_ms = 0

    def _load_mode(self) -> BinanceMode:
        """Load Binance mode from environment"""
        mode_str = os.getenv("BINANCE_MODE", "SPOT").upper()

        if mode_str == "FUTURES_USDM" or mode_str == "FUTURES":
            return BinanceMode.FUTURES_USDM
        else:
            return BinanceMode.SPOT

    def _load_testnet_flag(self) -> bool:
        """Load testnet flag from environment"""
        # Try multiple env var names
        for key in ["BINANCE_USE_TESTNET", "USE_TESTNET", "IS_TESTNET"]:
            value = os.getenv(key, "").lower()
            if value in ("true", "1", "yes", "on"):
                return True

        return False

    def _resolve_base_url(self) -> str:
        """Resolve base URL from mode and testnet flag"""
        key = (self.mode, self.is_testnet)

        if key not in self.URL_MAP:
            raise ValueError(
                f"Invalid config: mode={self.mode}, testnet={self.is_testnet}"
            )

        return self.URL_MAP[key]

    def set_time_offset(self, offset_ms: int):
        """Set time offset for clock skew correction"""
        self._time_offset_ms = offset_ms

    def get_time_offset(self) -> int:
        """Get current time offset"""
        return self._time_offset_ms

    def get_config_summary(self) -> Dict[str, any]:
        """Get configuration summary for logging"""
        return {
            "mode": self.mode.value,
            "is_testnet": self.is_testnet,
            "base_url": self.base_url,
            "recv_window": self.recv_window,
            "auto_offset": self.auto_offset,
            "time_offset_ms": self._time_offset_ms,
            "has_api_key": bool(self.api_key),
            "has_api_secret": bool(self.api_secret),
            "secret_len": len(self.api_secret) if self.api_secret else 0,
            "secret_sanitized": self.secret_metadata.get("sanitized", False),
            "secret_printable_only": self.secret_metadata.get("printable_only", False),
            "secret_valid": self.secret_validation.get("valid", False),
        }

    def validate(self) -> Tuple[bool, str]:
        """
        Validate configuration.

        Returns:
            (success, error_message)
        """
        if not self.api_key:
            return False, "BINANCE_API_KEY not set"

        if not self.api_secret:
            return False, "BINANCE_API_SECRET not set"

        if not self.base_url:
            return False, "Base URL resolution failed"

        return True, ""


# Global singleton instance
_config_instance = None


def get_binance_config() -> BinanceConfig:
    """Get the singleton BinanceConfig instance"""
    global _config_instance

    if _config_instance is None:
        _config_instance = BinanceConfig()

    return _config_instance


def reset_config():
    """Reset configuration (for testing)"""
    global _config_instance
    _config_instance = None


if __name__ == "__main__":
    # Test configuration
    config = get_binance_config()

    print("=" * 60)
    print(" Binance Configuration SSOT")
    print("=" * 60)
    print()

    summary = config.get_config_summary()

    for key, value in summary.items():
        print(f"  {key}: {value}")

    print()

    valid, error = config.validate()

    if valid:
        print("✅ Configuration valid")
    else:
        print(f"❌ Configuration invalid: {error}")
