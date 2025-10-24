#!/usr/bin/env python3
"""
SSOT Watchlist Loader
Single source of truth for runtime symbols: env_ssot.json
"""

import json
import logging
from pathlib import Path
from typing import List

try:
    from .path_registry import get_absolute_path
except ImportError:
    from path_registry import get_absolute_path

logger = logging.getLogger(__name__)


class SSOTWatchlistError(Exception):
    """SSOT watchlist error"""

    pass


def load_ssot_symbols() -> List[str]:
    """
    Load symbols from SSOT (env_ssot.json).
    This is the ONLY source of truth for runtime symbols.

    Returns:
        List of uppercase symbols

    Raises:
        SSOTWatchlistError: If SSOT file is missing or malformed
    """
    ssot_path = get_absolute_path("shared_data", "env_ssot.json")

    if not ssot_path.exists():
        raise SSOTWatchlistError(
            f"SSOT file not found: {ssot_path}. "
            "Run bootstrap or ensure env_ssot.json exists."
        )

    try:
        with open(ssot_path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise SSOTWatchlistError(f"SSOT JSON parse error: {e}")
    except Exception as e:
        raise SSOTWatchlistError(f"Failed to read SSOT: {e}")

    # Validate structure
    if not isinstance(data, dict):
        raise SSOTWatchlistError(f"SSOT must be object, got {type(data)}")

    if "symbols" not in data:
        raise SSOTWatchlistError("SSOT missing 'symbols' field")

    symbols = data["symbols"]

    if not isinstance(symbols, list):
        raise SSOTWatchlistError(f"SSOT symbols must be array, got {type(symbols)}")

    if not symbols:
        raise SSOTWatchlistError("SSOT symbols array is empty")

    # Validate each symbol
    valid_symbols = []
    for sym in symbols:
        if not isinstance(sym, str):
            logger.warning(f"Skipping non-string symbol: {sym}")
            continue

        sym = sym.strip().upper()

        if not sym:
            logger.warning("Skipping empty symbol")
            continue

        if not sym.endswith("USDT"):
            logger.warning(f"Skipping invalid symbol (no USDT suffix): {sym}")
            continue

        valid_symbols.append(sym)

    if not valid_symbols:
        raise SSOTWatchlistError("No valid symbols found in SSOT")

    # Deduplicate and sort
    valid_symbols = sorted(list(set(valid_symbols)))

    logger.info(f"SSOT symbols loaded: {valid_symbols}")

    return valid_symbols


def validate_ssot_watchlist_match(actual_symbols: List[str]) -> None:
    """
    Validate that actual runtime symbols match SSOT.
    Fail-fast if mismatch detected.

    Args:
        actual_symbols: Symbols currently in use

    Raises:
        SSOTWatchlistError: If mismatch detected
    """
    ssot_symbols = load_ssot_symbols()

    # Normalize both lists
    ssot_set = set(s.upper() for s in ssot_symbols)
    actual_set = set(s.upper() for s in actual_symbols)

    if ssot_set != actual_set:
        missing = ssot_set - actual_set
        extra = actual_set - ssot_set

        error_parts = []
        if missing:
            error_parts.append(f"Missing from runtime: {sorted(missing)}")
        if extra:
            error_parts.append(f"Extra in runtime: {sorted(extra)}")

        raise SSOTWatchlistError(
            f"SSOT watchlist mismatch! {' | '.join(error_parts)}. "
            f"SSOT: {sorted(ssot_set)} vs Runtime: {sorted(actual_set)}"
        )

    logger.info(f"✅ SSOT watchlist match validated: {sorted(ssot_set)}")


def get_ssot_mode() -> str:
    """
    Get mode from SSOT.

    Returns:
        Mode string (TESTNET or MAINNET)
    """
    ssot_path = get_absolute_path("shared_data", "env_ssot.json")

    if not ssot_path.exists():
        return "TESTNET"  # Safe default

    try:
        with open(ssot_path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)

        mode = data.get("mode", "TESTNET").upper()
        return mode if mode in ["TESTNET", "MAINNET"] else "TESTNET"

    except Exception:
        return "TESTNET"


if __name__ == "__main__":
    # Self-test
    try:
        symbols = load_ssot_symbols()
        print(f"✅ SSOT symbols: {symbols}")

        mode = get_ssot_mode()
        print(f"✅ SSOT mode: {mode}")

        # Test validation (should pass with same list)
        validate_ssot_watchlist_match(symbols)
        print("✅ Validation passed")

    except SSOTWatchlistError as e:
        print(f"❌ SSOT Error: {e}")
        exit(1)
