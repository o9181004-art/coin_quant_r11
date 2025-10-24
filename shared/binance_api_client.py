#!/usr/bin/env python3
"""
Binance API Client with Full Diagnostics
==================================================
Robust API client with signature, time sync, and error diagnostics.
"""

import hashlib
import logging
from typing import Any, Dict, Optional, Tuple

import requests

from shared.binance_config import BinanceConfig, get_binance_config
from shared.binance_signer import BinanceSigner
from shared.binance_time_sync import TimeSync

logger = logging.getLogger(__name__)


class BinanceAPIError(Exception):
    """Binance API error with full diagnostics"""

    def __init__(self, status_code: int, error_code: int, message: str, details: Dict):
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.details = details
        super().__init__(f"[{status_code}] Code {error_code}: {message}")

    def get_diagnosis(self) -> str:
        """Get human-readable diagnosis"""
        if self.error_code == -1021:
            return "⏰ Timestamp error: System clock out of sync with Binance servers (>1000ms). Check Windows time sync."

        elif self.error_code == -1022:
            return "🔑 Signature error: API signature invalid. Check API keys or signature generation logic."

        elif self.error_code == -1102:
            return "❌ Mandatory parameter missing: Check request parameters."

        elif self.error_code == -1105:
            return "❌ Parameter error: Invalid parameter value or format."

        elif self.error_code == -2014:
            return "🔑 API key invalid: Check BINANCE_API_KEY in config.env."

        elif self.error_code == -2015:
            return "🔑 API key format invalid: Check API key format."

        else:
            return f"❌ Binance API error {self.error_code}: {self.message}"


class BinanceAPIClient:
    """
    Binance API client with full diagnostics.

    Features:
    - Automatic time sync and clock skew correction
    - HMAC-SHA256 signature with canonical query string
    - Full HTTP triage on errors
    - Human-readable error diagnostics
    """

    def __init__(self, config: Optional[BinanceConfig] = None):
        """
        Initialize API client.

        Args:
            config: BinanceConfig instance (uses singleton if None)
        """
        self.config = config or get_binance_config()

        # Validate config
        valid, error = self.config.validate()
        if not valid:
            raise ValueError(f"Invalid Binance config: {error}")

        # Initialize components
        self.time_sync = TimeSync(self.config.base_url)
        self.signer = BinanceSigner(
            self.config.api_secret,
            recv_window=self.config.recv_window,
            time_offset_ms=self.config.get_time_offset(),
        )

        # Session for connection pooling
        self.session = requests.Session()
        self.session.headers.update(
            {
                "X-MBX-APIKEY": self.config.api_key,
            }
        )

    def sync_time(self) -> Tuple[bool, int, str]:
        """
        Sync time with server and update offset.

        Returns:
            (success, offset_ms, message)
        """
        success, offset_ms, message = self.time_sync.check_and_sync()

        if success and offset_ms != 0:
            # Update signer offset
            self.signer.time_offset_ms = offset_ms
            self.config.set_time_offset(offset_ms)

            logger.warning(f"Applied time offset: {offset_ms}ms")

        return success, offset_ms, message

    def _log_http_triage(
        self, method: str, url: str, params: Dict, response: requests.Response
    ):
        """Log full HTTP triage for debugging"""
        logger.error("=" * 60)
        logger.error(" HTTP Request Triage")
        logger.error("=" * 60)
        logger.error(f"Method: {method}")
        logger.error(f"URL: {url}")
        logger.error(f"Base URL: {self.config.base_url}")
        logger.error(f"Status: {response.status_code}")
        logger.error(f"Headers: {dict(response.headers)}")

        # Redact sensitive params
        safe_params = {
            k: "***" if k in ("signature", "timestamp") else v
            for k, v in params.items()
        }
        logger.error(f"Params: {safe_params}")

        # Response body
        try:
            body = response.json()
            logger.error(f"Response: {body}")
        except:
            logger.error(f"Response: {response.text[:200]}")

        logger.error("=" * 60)

    def _handle_error_response(
        self, method: str, url: str, params: Dict, response: requests.Response
    ):
        """Handle error response and raise BinanceAPIError"""
        # Log full triage
        self._log_http_triage(method, url, params, response)

        # Parse error
        try:
            error_data = response.json()
            error_code = error_data.get("code", -1)
            error_msg = error_data.get("msg", "Unknown error")
        except:
            error_code = -1
            error_msg = response.text[:100]

        # Build details
        details = {
            "method": method,
            "url": url,
            "status_code": response.status_code,
            "headers": dict(response.headers),
        }

        # Raise with diagnostics
        raise BinanceAPIError(response.status_code, error_code, error_msg, details)

    def get(
        self, endpoint: str, params: Optional[Dict] = None, signed: bool = False
    ) -> Dict[str, Any]:
        """
        GET request to Binance API.

        Args:
            endpoint: API endpoint (e.g., "/api/v3/account")
            params: Query parameters
            signed: Whether to sign the request

        Returns:
            Response JSON

        Raises:
            BinanceAPIError: On API error
        """
        url = f"{self.config.base_url}{endpoint}"

        if signed:
            # Sign request
            signed_params = self.signer.sign_request(params)

            # Log signature preview
            preview = self.signer.get_signature_preview(params)
            logger.debug(f"Signature preview: {preview}")
        else:
            signed_params = params or {}

        # Make request
        try:
            response = self.session.get(url, params=signed_params, timeout=10)

            # Check for errors
            if response.status_code != 200:
                self._handle_error_response("GET", url, signed_params, response)

            return response.json()

        except BinanceAPIError:
            raise

        except Exception as e:
            logger.error(f"Request failed: {e}")
            raise

    def get_account(self) -> Dict[str, Any]:
        """
        Get account information.

        Returns:
            Account data
        """
        return self.get("/api/v3/account", signed=True)

    def ping(self) -> Dict[str, Any]:
        """
        Ping server.

        Returns:
            Empty dict on success
        """
        return self.get("/api/v3/ping", signed=False)

    def get_server_time(self) -> Dict[str, Any]:
        """
        Get server time.

        Returns:
            {"serverTime": <timestamp>}
        """
        return self.get("/api/v3/time", signed=False)


if __name__ == "__main__":
    # Test API client
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    print("=" * 60)
    print(" Binance API Client Test")
    print("=" * 60)
    print()

    try:
        # Create client
        client = BinanceAPIClient()

        # Show config
        config = client.config.get_config_summary()
        print("Configuration:")
        for key, value in config.items():
            print(f"  {key}: {value}")
        print()

        # Test 1: Ping
        print("Test 1: Ping (unsigned)")
        result = client.ping()
        print(f"  ✅ Ping OK: {result}")
        print()

        # Test 2: Server time
        print("Test 2: Server time (unsigned)")
        result = client.get_server_time()
        print(f"  ✅ Server time: {result}")
        print()

        # Test 3: Time sync
        print("Test 3: Time sync")
        success, offset_ms, message = client.sync_time()
        print(f"  {'✅' if success else '❌'} {message}")
        if offset_ms != 0:
            print(f"  Applied offset: {offset_ms}ms")
        print()

        # Test 4: Account (signed)
        print("Test 4: Account info (signed)")
        account = client.get_account()
        print(f"  ✅ Account retrieved")
        print(f"  Can trade: {account.get('canTrade', False)}")

        balances = [
            b
            for b in account.get("balances", [])
            if float(b["free"]) > 0 or float(b["locked"]) > 0
        ]
        print(f"  Balances: {len(balances)} assets")

        for balance in balances[:5]:
            print(
                f"    {balance['asset']}: Free={float(balance['free']):,.2f}, Locked={float(balance['locked']):,.2f}"
            )

        print()
        print("=" * 60)
        print(" ✅ All tests passed!")
        print("=" * 60)

    except BinanceAPIError as e:
        print()
        print("=" * 60)
        print(" ❌ API Error")
        print("=" * 60)
        print(f"Status: {e.status_code}")
        print(f"Code: {e.error_code}")
        print(f"Message: {e.message}")
        print()
        print(f"Diagnosis: {e.get_diagnosis()}")
        print("=" * 60)

    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
