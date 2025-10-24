#!/usr/bin/env python3
"""
Error Rate Limiter - Prevent log spam by rate-limiting duplicate errors
Categorizes errors into: LOOP, WS/HTTP, SYMBOL, IO
Limits same stack trace to once per 30s with counter
"""
import hashlib
import time
import traceback
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class ErrorRecord:
    """Error occurrence record"""
    first_seen: float
    last_seen: float
    count: int
    category: str
    message: str
    stacktrace_hash: str


class ErrorRateLimiter:
    """Rate limiter for error logging"""
    
    def __init__(self, rate_limit_seconds: int = 30):
        self.rate_limit_seconds = rate_limit_seconds
        self.error_records: Dict[str, ErrorRecord] = {}
        self.last_cleanup = time.time()
        self.cleanup_interval = 300  # 5 minutes
    
    def categorize_error(self, exc: Exception, context: str = "") -> str:
        """Categorize error into LOOP, WS/HTTP, SYMBOL, or IO"""
        exc_str = str(exc).lower()
        exc_type = type(exc).__name__.lower()
        
        # WebSocket/HTTP errors
        if any(x in exc_str for x in ['websocket', 'connection', 'timeout', 'http', 'ssl', '4xx', '5xx']):
            return "WS/HTTP"
        
        # Symbol-related errors
        if any(x in exc_str for x in ['symbol', 'ticker', 'subscription', 'casing']):
            return "SYMBOL"
        
        # IO errors
        if any(x in exc_str for x in ['file', 'disk', 'permission', 'io', 'write', 'read']):
            return "IO"
        
        # Loop/async errors
        if any(x in exc_str for x in ['loop', 'asyncio', 'event', 'coroutine', 'task']):
            return "LOOP"
        
        # Context-based categorization
        if context:
            context_lower = context.lower()
            if 'loop' in context_lower:
                return "LOOP"
            elif any(x in context_lower for x in ['ws', 'websocket', 'http']):
                return "WS/HTTP"
            elif 'symbol' in context_lower:
                return "SYMBOL"
            elif any(x in context_lower for x in ['file', 'io']):
                return "IO"
        
        # Default
        return "GENERAL"
    
    def get_stacktrace_hash(self, exc: Exception) -> str:
        """Get hash of exception stacktrace for deduplication"""
        tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
        # Only hash the actual traceback, not the exception message
        tb_structure = [line for line in tb_lines if 'File "' in line or 'line ' in line]
        tb_text = ''.join(tb_structure)
        return hashlib.md5(tb_text.encode()).hexdigest()[:8]
    
    def should_log(self, exc: Exception, context: str = "") -> tuple[bool, str, int]:
        """
        Check if error should be logged based on rate limiting
        
        Returns:
            (should_log, category, count)
        """
        category = self.categorize_error(exc, context)
        stacktrace_hash = self.get_stacktrace_hash(exc)
        key = f"{category}:{stacktrace_hash}"
        
        current_time = time.time()
        
        # Periodic cleanup
        if current_time - self.last_cleanup > self.cleanup_interval:
            self._cleanup_old_records(current_time)
            self.last_cleanup = current_time
        
        if key in self.error_records:
            record = self.error_records[key]
            record.count += 1
            record.last_seen = current_time
            
            # Check if enough time has passed since last log
            time_since_last = current_time - record.last_seen
            if time_since_last >= self.rate_limit_seconds:
                # Log with count
                return True, category, record.count
            else:
                # Too soon, suppress
                return False, category, record.count
        else:
            # First occurrence, always log
            self.error_records[key] = ErrorRecord(
                first_seen=current_time,
                last_seen=current_time,
                count=1,
                category=category,
                message=str(exc),
                stacktrace_hash=stacktrace_hash
            )
            return True, category, 1
    
    def _cleanup_old_records(self, current_time: float):
        """Remove error records older than 10 minutes"""
        cutoff_time = current_time - 600  # 10 minutes
        self.error_records = {
            k: v for k, v in self.error_records.items()
            if v.last_seen >= cutoff_time
        }
    
    def get_error_summary(self) -> Dict[str, int]:
        """Get summary of error counts by category"""
        summary = defaultdict(int)
        for record in self.error_records.values():
            summary[record.category] += record.count
        return dict(summary)


# Global instance
_rate_limiter = ErrorRateLimiter(rate_limit_seconds=30)


def should_log_error(exc: Exception, context: str = "") -> tuple[bool, str, int]:
    """
    Check if error should be logged
    
    Returns:
        (should_log, category, count)
    """
    return _rate_limiter.should_log(exc, context)


def get_error_summary() -> Dict[str, int]:
    """Get error summary by category"""
    return _rate_limiter.get_error_summary()

