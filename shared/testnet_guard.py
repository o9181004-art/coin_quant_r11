#!/usr/bin/env python3
"""
Testnet-Only Guard
========================================
Force TESTNET/PAPER mode only - abort if live mode detected.

This guard ensures the system NEVER executes live orders.
"""

import os
import sys
from typing import Tuple


def check_testnet_only_guard() -> Tuple[bool, str]:
    """
    Check if system is running in TESTNET/PAPER mode only.
    
    Returns:
        (is_testnet_only, error_message)
    """
    # Expected values
    expected_testnet = "true"
    expected_trading_mode = "paper"
    expected_live_enabled = "false"
    
    # Current values
    current_testnet = os.getenv("BINANCE_USE_TESTNET", "true").lower()
    current_trading_mode = os.getenv("TRADING_MODE", "paper").lower()
    current_live_enabled = os.getenv("LIVE_TRADING_ENABLED", "false").lower()
    
    # Check each requirement
    errors = []
    
    if current_testnet != expected_testnet:
        errors.append(f"BINANCE_USE_TESTNET={current_testnet} (expected: {expected_testnet})")
    
    if current_trading_mode != expected_trading_mode:
        errors.append(f"TRADING_MODE={current_trading_mode} (expected: {expected_trading_mode})")
    
    if current_live_enabled != expected_live_enabled:
        errors.append(f"LIVE_TRADING_ENABLED={current_live_enabled} (expected: {expected_live_enabled})")
    
    if errors:
        error_msg = "TESTNET_ONLY_GUARD: abort (expected paper mode) - " + "; ".join(errors)
        return False, error_msg
    
    return True, "TESTNET/PAPER mode confirmed"


def enforce_testnet_only():
    """
    Enforce TESTNET-only mode.
    Exit immediately if live mode detected.
    No retries.
    """
    is_testnet_only, message = check_testnet_only_guard()
    
    if not is_testnet_only:
        # Single-line error log
        print(f"❌ {message}", file=sys.stderr)
        print("   Hint: Set BINANCE_USE_TESTNET=true, TRADING_MODE=paper, LIVE_TRADING_ENABLED=false", file=sys.stderr)
        sys.exit(1)
    
    # Success - log confirmation
    print(f"✅ {message}", file=sys.stderr)


def get_mode_display() -> str:
    """
    Get current mode display string.
    
    Returns:
        Display string (e.g., "TESTNET/PAPER", "LIVE")
    """
    testnet = os.getenv("BINANCE_USE_TESTNET", "true").lower() == "true"
    trading_mode = os.getenv("TRADING_MODE", "paper").upper()
    
    if testnet:
        return f"TESTNET/{trading_mode}"
    else:
        return f"MAINNET/{trading_mode}"


def is_testnet_mode() -> bool:
    """Check if currently in testnet mode"""
    return os.getenv("BINANCE_USE_TESTNET", "true").lower() == "true"


def is_paper_mode() -> bool:
    """Check if currently in paper trading mode"""
    return os.getenv("TRADING_MODE", "paper").lower() == "paper"


if __name__ == "__main__":
    # Test guard
    try:
        enforce_testnet_only()
        print("✅ Testnet-only guard passed")
        print(f"   Mode: {get_mode_display()}")
    except SystemExit:
        print("❌ Testnet-only guard failed")

