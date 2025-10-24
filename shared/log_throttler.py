#!/usr/bin/env python3
"""
Log Throttler - Collapse repetitive log messages
========================================
Prevents log spam by throttling repetitive messages.

Usage:
    from shared.log_throttler import LogThrottler
    
    throttler = LogThrottler()
    
    # Instead of:
    # logger.warning(f"Feeder missing - age {age}s")
    
    # Use:
    # throttler.log_once("feeder_missing", 
    #                    logger.warning, 
    #                    f"Feeder missing - age {age}s (throttled)", 
    #                    interval=10.0)
"""

import time
from typing import Any, Callable, Dict


class LogThrottler:
    """Throttle repetitive log messages"""
    
    def __init__(self):
        self._last_log_time: Dict[str, float] = {}
        self._log_count: Dict[str, int] = {}
    
    def log_once(self, key: str, log_fn: Callable, message: str, interval: float = 10.0) -> bool:
        """
        Log a message at most once per interval.
        
        Args:
            key: Unique key for this log message
            log_fn: Logging function (e.g., logger.warning)
            message: Message to log
            interval: Minimum interval between logs (seconds)
        
        Returns:
            True if message was logged, False if throttled
        """
        current_time = time.time()
        last_time = self._last_log_time.get(key, 0)
        
        if current_time - last_time >= interval:
            # Log the message
            count = self._log_count.get(key, 0)
            if count > 0:
                log_fn(f"{message} (suppressed {count}x since last)")
            else:
                log_fn(message)
            
            # Reset state
            self._last_log_time[key] = current_time
            self._log_count[key] = 0
            return True
        else:
            # Throttle the message
            self._log_count[key] = self._log_count.get(key, 0) + 1
            return False
    
    def reset(self, key: str = None):
        """
        Reset throttle state for a specific key or all keys.
        
        Args:
            key: Specific key to reset, or None to reset all
        """
        if key:
            self._last_log_time.pop(key, None)
            self._log_count.pop(key, None)
        else:
            self._last_log_time.clear()
            self._log_count.clear()


# Global instance for easy access
_global_throttler: LogThrottler = None


def get_log_throttler() -> LogThrottler:
    """Get global log throttler instance"""
    global _global_throttler
    if _global_throttler is None:
        _global_throttler = LogThrottler()
    return _global_throttler


if __name__ == "__main__":
    # Test the throttler
    import logging
    
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    throttler = LogThrottler()
    
    print("Testing log throttler...")
    for i in range(10):
        throttler.log_once("test", logger.warning, f"Test message {i}", interval=2.0)
        time.sleep(0.5)
    
    print("\nDone - should see fewer messages than iterations")

