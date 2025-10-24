"""
Symbol utilities for Coin Quant R11

Symbol normalization, validation, and management utilities.
Provides consistent symbol handling across all services.
"""

import re
from typing import List, Optional, Set


class SymbolNormalizer:
    """Symbol normalization utilities"""
    
    @staticmethod
    def normalize(symbol: str) -> str:
        """
        Normalize symbol to uppercase.
        
        Args:
            symbol: Symbol to normalize
            
        Returns:
            Normalized symbol
        """
        if not symbol:
            return ""
        return symbol.upper().strip()
    
    @staticmethod
    def is_valid(symbol: str) -> bool:
        """
        Check if symbol is valid.
        
        Args:
            symbol: Symbol to validate
            
        Returns:
            True if valid, False otherwise
        """
        if not symbol:
            return False
        
        # Basic validation: alphanumeric characters only
        if not re.match(r'^[A-Z0-9]+$', symbol.upper()):
            return False
        
        # Must be at least 3 characters
        if len(symbol) < 3:
            return False
        
        return True
    
    @staticmethod
    def extract_base_quote(symbol: str) -> tuple[Optional[str], Optional[str]]:
        """
        Extract base and quote currencies from symbol.
        
        Args:
            symbol: Symbol to parse
            
        Returns:
            Tuple of (base, quote) or (None, None) if invalid
        """
        if not symbol or len(symbol) < 3:
            return None, None
        
        symbol = symbol.upper()
        
        # Common quote currencies
        quote_currencies = ['USDT', 'USDC', 'BUSD', 'BTC', 'ETH', 'BNB']
        
        for quote in quote_currencies:
            if symbol.endswith(quote):
                base = symbol[:-len(quote)]
                if base:
                    return base, quote
        
        return None, None
    
    @staticmethod
    def is_usdt_pair(symbol: str) -> bool:
        """
        Check if symbol is a USDT pair.
        
        Args:
            symbol: Symbol to check
            
        Returns:
            True if USDT pair, False otherwise
        """
        return symbol.upper().endswith('USDT')
    
    @staticmethod
    def is_btc_pair(symbol: str) -> bool:
        """
        Check if symbol is a BTC pair.
        
        Args:
            symbol: Symbol to check
            
        Returns:
            True if BTC pair, False otherwise
        """
        return symbol.upper().endswith('BTC')
    
    @staticmethod
    def is_eth_pair(symbol: str) -> bool:
        """
        Check if symbol is an ETH pair.
        
        Args:
            symbol: Symbol to check
            
        Returns:
            True if ETH pair, False otherwise
        """
        return symbol.upper().endswith('ETH')


class SymbolValidator:
    """Symbol validation utilities"""
    
    def __init__(self, allowed_symbols: Optional[Set[str]] = None):
        self.allowed_symbols = allowed_symbols or set()
        self.blocked_symbols = {'WALUSDT'}  # Known invalid symbols
    
    def is_allowed(self, symbol: str) -> bool:
        """
        Check if symbol is allowed.
        
        Args:
            symbol: Symbol to check
            
        Returns:
            True if allowed, False otherwise
        """
        normalized = SymbolNormalizer.normalize(symbol)
        
        # Check if blocked
        if normalized in self.blocked_symbols:
            return False
        
        # Check if in allowed list (if specified)
        if self.allowed_symbols and normalized not in self.allowed_symbols:
            return False
        
        # Basic validation
        return SymbolNormalizer.is_valid(normalized)
    
    def validate_symbols(self, symbols: List[str]) -> List[str]:
        """
        Validate list of symbols.
        
        Args:
            symbols: List of symbols to validate
            
        Returns:
            List of valid symbols
        """
        valid_symbols = []
        for symbol in symbols:
            if self.is_allowed(symbol):
                valid_symbols.append(SymbolNormalizer.normalize(symbol))
        return valid_symbols
    
    def add_allowed_symbol(self, symbol: str) -> None:
        """
        Add symbol to allowed list.
        
        Args:
            symbol: Symbol to add
        """
        normalized = SymbolNormalizer.normalize(symbol)
        if SymbolNormalizer.is_valid(normalized):
            self.allowed_symbols.add(normalized)
    
    def remove_allowed_symbol(self, symbol: str) -> None:
        """
        Remove symbol from allowed list.
        
        Args:
            symbol: Symbol to remove
        """
        normalized = SymbolNormalizer.normalize(symbol)
        self.allowed_symbols.discard(normalized)
    
    def add_blocked_symbol(self, symbol: str) -> None:
        """
        Add symbol to blocked list.
        
        Args:
            symbol: Symbol to block
        """
        normalized = SymbolNormalizer.normalize(symbol)
        self.blocked_symbols.add(normalized)
    
    def remove_blocked_symbol(self, symbol: str) -> None:
        """
        Remove symbol from blocked list.
        
        Args:
            symbol: Symbol to unblock
        """
        normalized = SymbolNormalizer.normalize(symbol)
        self.blocked_symbols.discard(normalized)


class SymbolManager:
    """Symbol management utilities"""
    
    def __init__(self):
        self.validator = SymbolValidator()
        self._cache: Set[str] = set()
    
    def load_symbols(self, symbols: List[str]) -> List[str]:
        """
        Load and validate symbols.
        
        Args:
            symbols: List of symbols to load
            
        Returns:
            List of valid symbols
        """
        valid_symbols = self.validator.validate_symbols(symbols)
        self._cache.update(valid_symbols)
        return valid_symbols
    
    def get_symbols(self) -> Set[str]:
        """
        Get cached symbols.
        
        Returns:
            Set of cached symbols
        """
        return self._cache.copy()
    
    def add_symbol(self, symbol: str) -> bool:
        """
        Add symbol to cache.
        
        Args:
            symbol: Symbol to add
            
        Returns:
            True if added, False if invalid
        """
        if self.validator.is_allowed(symbol):
            normalized = SymbolNormalizer.normalize(symbol)
            self._cache.add(normalized)
            return True
        return False
    
    def remove_symbol(self, symbol: str) -> bool:
        """
        Remove symbol from cache.
        
        Args:
            symbol: Symbol to remove
            
        Returns:
            True if removed, False if not found
        """
        normalized = SymbolNormalizer.normalize(symbol)
        return self._cache.discard(normalized) is not None
    
    def has_symbol(self, symbol: str) -> bool:
        """
        Check if symbol is in cache.
        
        Args:
            symbol: Symbol to check
            
        Returns:
            True if in cache, False otherwise
        """
        normalized = SymbolNormalizer.normalize(symbol)
        return normalized in self._cache
    
    def clear_cache(self) -> None:
        """Clear symbol cache"""
        self._cache.clear()
    
    def get_usdt_symbols(self) -> List[str]:
        """
        Get USDT symbols from cache.
        
        Returns:
            List of USDT symbols
        """
        return [symbol for symbol in self._cache if SymbolNormalizer.is_usdt_pair(symbol)]
    
    def get_btc_symbols(self) -> List[str]:
        """
        Get BTC symbols from cache.
        
        Returns:
            List of BTC symbols
        """
        return [symbol for symbol in self._cache if SymbolNormalizer.is_btc_pair(symbol)]
    
    def get_eth_symbols(self) -> List[str]:
        """
        Get ETH symbols from cache.
        
        Returns:
            List of ETH symbols
        """
        return [symbol for symbol in self._cache if SymbolNormalizer.is_eth_pair(symbol)]


# Convenience functions for backward compatibility
def normalize_symbol(symbol: str) -> str:
    """Convenience function for symbol normalization"""
    return SymbolNormalizer.normalize(symbol)

def is_valid_symbol(symbol: str) -> bool:
    """Convenience function for symbol validation"""
    return SymbolNormalizer.is_valid(symbol)

def is_usdt_pair(symbol: str) -> bool:
    """Convenience function for USDT pair check"""
    return SymbolNormalizer.is_usdt_pair(symbol)

def is_btc_pair(symbol: str) -> bool:
    """Convenience function for BTC pair check"""
    return SymbolNormalizer.is_btc_pair(symbol)

def is_eth_pair(symbol: str) -> bool:
    """Convenience function for ETH pair check"""
    return SymbolNormalizer.is_eth_pair(symbol)
