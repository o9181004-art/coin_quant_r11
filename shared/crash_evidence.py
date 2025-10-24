#!/usr/bin/env python3
"""
Crash Evidence - Low-noise logging and crash evidence collection
Writes concise error lines and dumps last exception to shared_data/health/last_crash.json
"""

import json
import logging
import time
import traceback
from pathlib import Path
from typing import Any, Dict, Optional

from shared.io.jsonio import now_epoch_s, write_json_atomic_nobom
from shared.paths import ensure_all_dirs


class CrashEvidence:
    """Crash evidence collector with rate limiting"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.crash_file = Path("shared_data/health/last_crash.json")
        self.rate_limit_window = 60  # seconds
        self.max_errors_per_window = 5
        self.error_times = []
        ensure_all_dirs()
    
    def _is_rate_limited(self) -> bool:
        """Check if we're rate limited"""
        current_time = time.time()
        
        # Remove old errors outside the window
        self.error_times = [
            t for t in self.error_times 
            if current_time - t < self.rate_limit_window
        ]
        
        # Check if we've exceeded the limit
        return len(self.error_times) >= self.max_errors_per_window
    
    def _record_error_time(self):
        """Record error time for rate limiting"""
        self.error_times.append(time.time())
    
    def log_crash(self, exception: Exception, context: str = "", 
                  trace_id: Optional[str] = None) -> bool:
        """
        Log a crash with concise error line and dump to crash file
        
        Args:
            exception: The exception that occurred
            context: Additional context about where the crash occurred
            trace_id: Optional trace ID for correlation
            
        Returns:
            True if logged, False if rate limited
        """
        try:
            # Check rate limiting
            if self._is_rate_limited():
                self.logger.warning("Crash logging rate limited - skipping")
                return False
            
            # Generate trace ID if not provided
            if not trace_id:
                trace_id = f"crash_{now_epoch_s()}"
            
            # Log concise error line
            error_msg = f"CRASH {trace_id}: {type(exception).__name__}: {str(exception)}"
            if context:
                error_msg += f" (context: {context})"
            
            self.logger.error(error_msg)
            
            # Dump detailed crash evidence
            crash_evidence = {
                "timestamp": now_epoch_s(),
                "trace_id": trace_id,
                "exception_type": type(exception).__name__,
                "exception_message": str(exception),
                "context": context,
                "traceback": traceback.format_exc(),
                "python_version": f"{traceback.sys.version_info.major}.{traceback.sys.version_info.minor}.{traceback.sys.version_info.micro}"
            }
            
            # Write crash evidence atomically
            write_json_atomic_nobom(self.crash_file, crash_evidence)
            
            # Record error time for rate limiting
            self._record_error_time()
            
            return True
            
        except Exception as e:
            # Fallback logging if crash evidence collection fails
            self.logger.error(f"Failed to collect crash evidence: {e}")
            return False
    
    def get_last_crash(self) -> Optional[Dict[str, Any]]:
        """Get the last crash evidence"""
        try:
            if not self.crash_file.exists():
                return None
            
            with open(self.crash_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None
    
    def clear_crash_evidence(self) -> bool:
        """Clear crash evidence file"""
        try:
            if self.crash_file.exists():
                self.crash_file.unlink()
            return True
        except Exception as e:
            self.logger.error(f"Failed to clear crash evidence: {e}")
            return False


# Global instance
_crash_evidence = None

def get_crash_evidence() -> CrashEvidence:
    """Get global crash evidence instance"""
    global _crash_evidence
    if _crash_evidence is None:
        _crash_evidence = CrashEvidence()
    return _crash_evidence


def log_crash(exception: Exception, context: str = "", trace_id: Optional[str] = None) -> bool:
    """Convenience function to log a crash"""
    return get_crash_evidence().log_crash(exception, context, trace_id)
