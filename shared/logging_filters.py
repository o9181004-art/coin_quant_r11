#!/usr/bin/env python3
"""
Logging Filters
========================================
Centralized logging filters to prevent duplicate warnings.

Prevents log spam by:
- Deduplicating identical messages per session
- Rate-limiting frequent warnings
- Symbol mismatch warnings (idempotent)
"""

import time
from threading import Lock
from typing import Dict, Set


class LogDeduplicator:
    """
    Deduplicates log messages per process/session.
    
    Thread-safe singleton for preventing duplicate warnings.
    """
    
    _instance = None
    _lock = Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        
        # Track seen messages by category
        self.seen_symbol_mismatches: Set[str] = set()
        self.seen_warnings: Set[str] = set()
        
        # Rate limiting (message_key -> last_log_time)
        self.last_log_times: Dict[str, float] = {}
        self.rate_limit_seconds = 60  # Default: 1 minute
    
    def should_log_symbol_mismatch(self, symbol: str) -> bool:
        """
        Check if symbol mismatch warning should be logged.
        
        Prevents duplicate warnings for the same symbol in this session.
        
        Args:
            symbol: Symbol that had mismatch
        
        Returns:
            True if should log, False if already logged
        """
        with self._lock:
            if symbol in self.seen_symbol_mismatches:
                return False
            
            self.seen_symbol_mismatches.add(symbol)
            return True
    
    def should_log_rate_limited(self, message_key: str, rate_limit_sec: int = None) -> bool:
        """
        Check if rate-limited message should be logged.
        
        Args:
            message_key: Unique key for this message type
            rate_limit_sec: Rate limit in seconds (default: 60)
        
        Returns:
            True if should log, False if too soon
        """
        if rate_limit_sec is None:
            rate_limit_sec = self.rate_limit_seconds
        
        with self._lock:
            now = time.time()
            last_time = self.last_log_times.get(message_key, 0)
            
            if now - last_time < rate_limit_sec:
                return False
            
            self.last_log_times[message_key] = now
            return True
    
    def should_log_warning(self, warning_message: str, deduplicate: bool = True) -> bool:
        """
        Check if generic warning should be logged.
        
        Args:
            warning_message: Full warning message
            deduplicate: If True, suppress duplicates per session
        
        Returns:
            True if should log, False if duplicate
        """
        if not deduplicate:
            return True
        
        with self._lock:
            if warning_message in self.seen_warnings:
                return False
            
            self.seen_warnings.add(warning_message)
            return True
    
    def reset(self):
        """Reset all filters (for testing)"""
        with self._lock:
            self.seen_symbol_mismatches.clear()
            self.seen_warnings.clear()
            self.last_log_times.clear()
    
    def get_stats(self) -> Dict[str, int]:
        """Get deduplication statistics"""
        with self._lock:
            return {
                'symbol_mismatches_seen': len(self.seen_symbol_mismatches),
                'warnings_seen': len(self.seen_warnings),
                'rate_limited_messages': len(self.last_log_times)
            }


# Global singleton instance
_deduplicator = LogDeduplicator()


def should_log_symbol_mismatch(symbol: str) -> bool:
    """
    Check if symbol mismatch warning should be logged.
    
    Convenience function for global deduplicator.
    
    Args:
        symbol: Symbol that had mismatch
    
    Returns:
        True if should log, False if already logged
    """
    return _deduplicator.should_log_symbol_mismatch(symbol)


def should_log_rate_limited(message_key: str, rate_limit_sec: int = 60) -> bool:
    """
    Check if rate-limited message should be logged.
    
    Args:
        message_key: Unique key for this message type
        rate_limit_sec: Rate limit in seconds
    
    Returns:
        True if should log, False if too soon
    """
    return _deduplicator.should_log_rate_limited(message_key, rate_limit_sec)


def get_deduplicator() -> LogDeduplicator:
    """Get global log deduplicator instance"""
    return _deduplicator


# Unit tests
if __name__ == "__main__":
    print("Testing LogDeduplicator...")
    
    dedup = LogDeduplicator()
    dedup.reset()
    
    # Test symbol mismatch deduplication
    print("\n1. Symbol mismatch deduplication:")
    assert dedup.should_log_symbol_mismatch("BTCUSDT") == True, "First BTCUSDT should log"
    assert dedup.should_log_symbol_mismatch("BTCUSDT") == False, "Second BTCUSDT should NOT log"
    assert dedup.should_log_symbol_mismatch("ETHUSDT") == True, "First ETHUSDT should log"
    assert dedup.should_log_symbol_mismatch("ETHUSDT") == False, "Second ETHUSDT should NOT log"
    print("✅ Symbol mismatch deduplication works")
    
    # Test rate limiting
    print("\n2. Rate limiting:")
    assert dedup.should_log_rate_limited("test_msg", rate_limit_sec=1) == True, "First should log"
    assert dedup.should_log_rate_limited("test_msg", rate_limit_sec=1) == False, "Immediate repeat should NOT log"
    time.sleep(1.1)
    assert dedup.should_log_rate_limited("test_msg", rate_limit_sec=1) == True, "After rate limit should log"
    print("✅ Rate limiting works")
    
    # Test warning deduplication
    print("\n3. Warning deduplication:")
    assert dedup.should_log_warning("Warning 1") == True, "First warning should log"
    assert dedup.should_log_warning("Warning 1") == False, "Duplicate warning should NOT log"
    assert dedup.should_log_warning("Warning 2") == True, "Different warning should log"
    print("✅ Warning deduplication works")
    
    # Test stats
    print("\n4. Statistics:")
    stats = dedup.get_stats()
    print(f"Stats: {stats}")
    assert stats['symbol_mismatches_seen'] == 2, "Should have 2 symbols"
    assert stats['warnings_seen'] == 2, "Should have 2 warnings"
    print("✅ Statistics work")
    
    print("\n" + "="*50)
    print("All tests passed! ✅")
    print("="*50)

