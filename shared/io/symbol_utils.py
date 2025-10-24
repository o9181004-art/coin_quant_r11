#!/usr/bin/env python3
"""
Symbol utilities for consistent casing
"""

def to_public_symbol(s: str) -> str:
    """
    Convert symbol to public format (UPPERCASE)
    
    Args:
        s: Input symbol string
        
    Returns:
        Uppercase, stripped symbol
    """
    return s.strip().upper()


def from_public_symbol(s: str) -> str:
    """
    Convert public symbol to internal format
    
    Args:
        s: Public symbol (UPPERCASE)
        
    Returns:
        Internal normalized form (currently same as input)
    """
    return s.strip().upper()


def normalize_symbols(symbols: list) -> list:
    """
    Normalize a list of symbols to public format
    
    Args:
        symbols: List of symbol strings
        
    Returns:
        List of uppercase symbols
    """
    return [to_public_symbol(s) for s in symbols if s]
