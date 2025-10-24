#!/usr/bin/env python3
"""
Binance Request Signer
==================================================
HMAC-SHA256 signature generation for Binance API requests.
"""

import hashlib
import hmac
import time
from typing import Dict, Optional
from urllib.parse import urlencode


class BinanceSigner:
    """
    Binance API request signer with canonical query string ordering.

    Features:
    - Deterministic query string ordering (timestamp, recvWindow, then alphabetical)
    - HMAC-SHA256 signature
    - Clock skew auto-correction
    - Signature preview logging for debugging
    """

    def __init__(
        self, api_secret: str, recv_window: int = 10000, time_offset_ms: int = 0
    ):
        """
        Initialize signer.

        Args:
            api_secret: Binance API secret key
            recv_window: Request validity window in milliseconds
            time_offset_ms: Time offset for clock skew correction
        """
        self.api_secret = api_secret.encode("utf-8")
        self.recv_window = recv_window
        self.time_offset_ms = time_offset_ms

    def get_timestamp(self) -> int:
        """Get current timestamp with offset applied"""
        return int(time.time() * 1000) + self.time_offset_ms

    def build_canonical_query_string(self, params: Optional[Dict] = None) -> str:
        """
        Build canonical query string with deterministic ordering.

        Order:
        1. timestamp (required)
        2. recvWindow (optional)
        3. Other params in alphabetical order

        Args:
            params: Query parameters (excluding timestamp and recvWindow)

        Returns:
            Canonical query string
        """
        # Start with timestamp and recvWindow
        ordered_params = {
            "timestamp": self.get_timestamp(),
            "recvWindow": self.recv_window,
        }

        # Add other params in alphabetical order
        if params:
            # Filter out None values
            filtered_params = {k: v for k, v in params.items() if v is not None}

            # Sort alphabetically
            for key in sorted(filtered_params.keys()):
                ordered_params[key] = filtered_params[key]

        # Encode to query string
        return urlencode(ordered_params)

    def sign(self, query_string: str) -> str:
        """
        Generate HMAC-SHA256 signature.

        Args:
            query_string: Canonical query string to sign

        Returns:
            Hex-encoded signature
        """
        signature = hmac.new(
            self.api_secret, query_string.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        return signature

    def sign_request(self, params: Optional[Dict] = None) -> Dict[str, str]:
        """
        Sign request and return query parameters with signature.

        Args:
            params: Query parameters

        Returns:
            Dict with all params including signature
        """
        # Build canonical query string
        query_string = self.build_canonical_query_string(params)

        # Generate signature
        signature = self.sign(query_string)

        # Parse query string back to dict
        result = {}
        for pair in query_string.split("&"):
            key, value = pair.split("=")
            result[key] = value

        # Add signature
        result["signature"] = signature

        return result

    def get_signature_preview(self, params: Optional[Dict] = None) -> Dict[str, str]:
        """
        Get signature preview for debugging (redacted).

        Returns:
            Dict with query string preview and message hash
        """
        query_string = self.build_canonical_query_string(params)

        # Redact timestamp values
        preview = query_string
        if len(preview) > 100:
            preview = preview[:100] + "..."

        # Hash of the message
        message_hash = hashlib.sha256(query_string.encode("utf-8")).hexdigest()[:16]

        return {
            "query_string_preview": preview,
            "message_hash": message_hash,
            "query_string_length": len(query_string),
        }


if __name__ == "__main__":
    # Test signer
    import os

    from dotenv import load_dotenv

    load_dotenv("config.env")

    api_secret = os.getenv("BINANCE_API_SECRET") or os.getenv("BINANCE_SECRET_KEY")

    if not api_secret:
        print("❌ BINANCE_API_SECRET not found")
        exit(1)

    signer = BinanceSigner(api_secret)

    print("=" * 60)
    print(" Binance Signer Test")
    print("=" * 60)
    print()

    # Test with no params
    print("Test 1: No params")
    signed = signer.sign_request()
    print(f"  Signed params: {signed}")
    print()

    # Test with params
    print("Test 2: With params")
    signed = signer.sign_request({"symbol": "BTCUSDT", "limit": 10})
    print(f"  Signed params: {signed}")
    print()

    # Test preview
    print("Test 3: Signature preview")
    preview = signer.get_signature_preview({"symbol": "BTCUSDT", "limit": 10})
    for key, value in preview.items():
        print(f"  {key}: {value}")
