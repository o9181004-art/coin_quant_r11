"""
Account Freshness Watchdog
Background task that monitors account snapshot freshness and sets trading blocks.
"""
import json
import time
import threading
from pathlib import Path
from typing import Dict, Any


class AccountFreshnessWatchdog:
    """Background watchdog for account snapshot freshness"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.snapshot_file = self.project_root / "shared_data" / "account_snapshot.json"
        self.status_file = self.project_root / "shared_data" / "account_freshness_status.json"
        self.running = False
        self.thread = None
        self.trading_blocked_reason = None
        self.last_update_time = 0
        
    def _update_status(self, is_fresh: bool, age_seconds: float, reason: str = None):
        """Update internal status and write to file"""
        self.trading_blocked_reason = None if is_fresh else reason
        self.last_update_time = time.time()
        
        status_data = {
            "is_fresh": is_fresh,
            "age_seconds": age_seconds,
            "trading_blocked_reason": self.trading_blocked_reason,
            "last_check": self.last_update_time,
            "threshold_seconds": 180
        }
        
        try:
            with open(self.status_file, "w", encoding="utf-8") as f:
                json.dump(status_data, f, indent=2)
        except Exception as e:
            print(f"[ACCOUNT_WATCHDOG] Failed to write status: {e}")
    
    def _check_freshness(self) -> tuple[bool, float, str]:
        """Check account snapshot freshness"""
        if not self.snapshot_file.exists():
            return False, 0, "ACCOUNT_MISSING: snapshot file not found"
        
        try:
            file_age = time.time() - self.snapshot_file.stat().st_mtime
            if file_age > 180:
                return False, file_age, f"ACCOUNT_STALE: {file_age:.1f}s > 180s limit"
            return True, file_age, "OK"
        except Exception as e:
            return False, 0, f"ACCOUNT_ERROR: {str(e)}"
    
    def _watchdog_loop(self):
        """Main watchdog loop"""
        print("[ACCOUNT_WATCHDOG] Starting freshness monitoring...")
        
        while self.running:
            try:
                is_fresh, age_seconds, reason = self._check_freshness()
                self._update_status(is_fresh, age_seconds, reason)
                
                if not is_fresh:
                    # Log once per minute when stale
                    now = time.time()
                    if now - self.last_update_time > 60:
                        print(f"[ACCOUNT_WATCHDOG] STALE: {reason}")
                
                time.sleep(10)  # Check every 10 seconds
                
            except Exception as e:
                print(f"[ACCOUNT_WATCHDOG] Error in loop: {e}")
                time.sleep(30)  # Wait longer on error
    
    def start(self):
        """Start the watchdog thread"""
        if self.running:
            return
            
        self.running = True
        self.thread = threading.Thread(target=self._watchdog_loop, daemon=True)
        self.thread.start()
        print("[ACCOUNT_WATCHDOG] Started")
    
    def stop(self):
        """Stop the watchdog thread"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        print("[ACCOUNT_WATCHDOG] Stopped")
    
    def is_trading_blocked(self) -> tuple[bool, str]:
        """Check if trading is blocked due to stale account"""
        if self.trading_blocked_reason:
            return True, self.trading_blocked_reason
        return False, "OK"
    
    def get_status(self) -> Dict[str, Any]:
        """Get current watchdog status"""
        is_fresh, age_seconds, reason = self._check_freshness()
        
        return {
            "is_fresh": is_fresh,
            "age_seconds": age_seconds,
            "trading_blocked": not is_fresh,
            "reason": reason,
            "last_check": self.last_update_time,
            "threshold_seconds": 180
        }


# Global instance
_account_watchdog = None

def get_account_watchdog() -> AccountFreshnessWatchdog:
    """Get singleton account watchdog instance"""
    global _account_watchdog
    if _account_watchdog is None:
        _account_watchdog = AccountFreshnessWatchdog()
    return _account_watchdog
