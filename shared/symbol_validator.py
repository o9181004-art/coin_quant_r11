#!/usr/bin/env python3
"""
Symbol Subscription Validator
Ensures symbol list is valid before WebSocket subscription
"""
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


class SymbolValidationError(Exception):
    """Symbol validation error"""
    pass


def validate_symbol_list(symbols: List[str], min_required: int = 1) -> tuple[bool, str, List[str]]:
    """
    Validate symbol list for WebSocket subscription
    
    Args:
        symbols: List of symbols to validate
        min_required: Minimum number of symbols required
    
    Returns:
        (is_valid, error_message, sanitized_symbols)
    """
    if not symbols:
        return False, "Symbol list is empty", []
    
    if len(symbols) < min_required:
        return False, f"Symbol list has {len(symbols)} symbols, minimum {min_required} required", []
    
    # Sanitize symbols (lowercase, strip whitespace)
    sanitized = []
    for symbol in symbols:
        if not symbol:
            continue
        cleaned = symbol.strip().upper()
        if cleaned:
            sanitized.append(cleaned)
    
    if len(sanitized) < min_required:
        return False, f"After sanitization, only {len(sanitized)} valid symbols, minimum {min_required} required", sanitized
    
    return True, "", sanitized


def ensure_minimum_symbols(symbols: List[str], minimum_symbols: List[str] = None) -> List[str]:
    """
    Ensure symbol list includes minimum required symbols (e.g., BTCUSDT)
    
    Args:
        symbols: Current symbol list
        minimum_symbols: List of symbols that must be included (default: ["BTCUSDT"])
    
    Returns:
        Symbol list with minimum symbols added if missing
    """
    if minimum_symbols is None:
        minimum_symbols = ["BTCUSDT"]
    
    result = list(symbols) if symbols else []
    
    for min_symbol in minimum_symbols:
        if min_symbol.upper() not in [s.upper() for s in result]:
            logger.info(f"Adding minimum required symbol: {min_symbol}")
            result.append(min_symbol.upper())
    
    return result


def validate_and_sanitize(
    symbols: List[str], 
    min_required: int = 1,
    ensure_btc: bool = True
) -> tuple[bool, str, List[str]]:
    """
    Complete validation and sanitization pipeline
    
    Args:
        symbols: Symbol list to validate
        min_required: Minimum symbols required
        ensure_btc: Whether to ensure BTCUSDT is included
    
    Returns:
        (is_valid, error_message, sanitized_symbols)
    """
    # Step 1: Basic validation
    is_valid, error_msg, sanitized = validate_symbol_list(symbols, min_required)
    
    if not is_valid:
        # If empty, return minimum symbols
        if not sanitized:
            logger.warning(f"Empty symbol list, using minimum: BTCUSDT")
            return True, "", ["BTCUSDT"]
        return False, error_msg, sanitized
    
    # Step 2: Ensure minimum symbols
    if ensure_btc:
        sanitized = ensure_minimum_symbols(sanitized, ["BTCUSDT"])
    
    # Step 3: Remove duplicates while preserving order
    seen = set()
    unique_sanitized = []
    for symbol in sanitized:
        symbol_upper = symbol.upper()
        if symbol_upper not in seen:
            seen.add(symbol_upper)
            unique_sanitized.append(symbol_upper)
    
    logger.info(f"Symbol validation complete: {len(unique_sanitized)} symbols ready")
    return True, "", unique_sanitized

