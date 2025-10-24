"""
Positions schema compatibility layer.
Supports both map and list schemas, normalizes to uppercase symbol dict.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def normalize_positions(positions_data: Any) -> Dict[str, Dict]:
    """
    Normalize positions data to uppercase symbol-keyed dict.
    
    Accepts two schemas:
    1. Map format: {"positions": {"BTCUSDT": {...}, ...}}
    2. List format: {"positions": [{"symbol": "BTCUSDT", ...}, ...]}
    
    Returns: {"BTCUSDT": {...}, "ETHUSDT": {...}, ...}
    """
    if not positions_data:
        return {}
    
    # Handle both direct positions and wrapped in "positions" key
    if isinstance(positions_data, dict):
        if "positions" in positions_data:
            positions_data = positions_data["positions"]
    
    result = {}
    warned_symbols = set()  # Track missing symbols to warn only once
    
    # Case 1: Already a dict (map format)
    if isinstance(positions_data, dict):
        for symbol, position in positions_data.items():
            # Normalize symbol to uppercase
            norm_symbol = symbol.upper() if isinstance(symbol, str) else str(symbol).upper()
            
            # Ensure position has symbol field
            if isinstance(position, dict):
                if "symbol" not in position and norm_symbol not in warned_symbols:
                    logger.warning(f"Position missing 'symbol' field for {norm_symbol}, adding it")
                    warned_symbols.add(norm_symbol)
                    position = {**position, "symbol": norm_symbol}
                
                result[norm_symbol] = position
        
        return result
    
    # Case 2: List format
    if isinstance(positions_data, list):
        for position in positions_data:
            if not isinstance(position, dict):
                continue
            
            symbol = position.get("symbol")
            if not symbol:
                if "__missing__" not in warned_symbols:
                    logger.warning("Position in list missing 'symbol' field, skipping")
                    warned_symbols.add("__missing__")
                continue
            
            # Normalize symbol to uppercase
            norm_symbol = symbol.upper()
            result[norm_symbol] = {**position, "symbol": norm_symbol}
        
        return result
    
    # Unknown format
    logger.warning(f"Unknown positions format: {type(positions_data)}, returning empty dict")
    return {}


def get_position_for_symbol(positions: Dict[str, Dict], symbol: str) -> Optional[Dict]:
    """
    Get position for a specific symbol (case-insensitive).
    
    Args:
        positions: Normalized positions dict
        symbol: Symbol to look up (any case)
    
    Returns:
        Position dict or None if not found
    """
    if not positions or not symbol:
        return None
    
    norm_symbol = symbol.upper()
    return positions.get(norm_symbol)


def has_position(positions: Dict[str, Dict], symbol: str) -> bool:
    """
    Check if symbol has a position (case-insensitive).
    
    Args:
        positions: Normalized positions dict
        symbol: Symbol to check (any case)
    
    Returns:
        True if position exists, False otherwise
    """
    position = get_position_for_symbol(positions, symbol)
    if not position:
        return False
    
    # Check if position has non-zero quantity
    qty = position.get("positionAmt", position.get("qty", position.get("quantity", 0)))
    try:
        return float(qty) != 0
    except (ValueError, TypeError):
        return False


__all__ = ["normalize_positions", "get_position_for_symbol", "has_position"]

