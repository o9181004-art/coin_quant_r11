"""
Memory Watchdog
Monitors system memory usage and implements soft/hard limits with trading blocks.
"""
import psutil
import time
import threading
from typing import Dict, Any, Optional
from pathlib import Path


class MemoryWatchdog:
    """Memory usage watchdog with soft and hard limits"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.status_file = self.project_root / "shared_data" / "memory_status.json"
        
        # Memory limits
        self.soft_limit = 85.0  # 85% - start GC hints
        self.hard_limit = 92.0  # 92% - block trading and stop new WebSocket sessions
        
        # State tracking
        self.trading_blocked_reason: Optional[str] = None
        self.last_gc_hint_time = 0
        self.last_status_update = 0
        self.running = False
        self.thread = None
        
    def _get_memory_usage(self) -> float:
        """Get current memory usage percentage"""
        try:
            return psutil.virtual_memory().percent
        except Exception:
            return 0.0
    
    def _update_status(self, memory_percent: float, trading_blocked: bool, reason: str = None):
        """Update internal status and write to file"""
        self.trading_blocked_reason = reason if trading_blocked else None
        self.last_status_update = time.time()
        
        status_data = {
            "memory_percent": memory_percent,
            "soft_limit": self.soft_limit,
            "hard_limit": self.hard_limit,
            "trading_blocked": trading_blocked,
            "trading_blocked_reason": self.trading_blocked_reason,
            "last_check": self.last_status_update
        }
        
        try:
            with open(self.status_file, "w", encoding="utf-8") as f:
                import json
                json.dump(status_data, f, indent=2)
        except Exception as e:
            print(f"[MEMORY_WATCHDOG] Failed to write status: {e}")
    
    def _trigger_gc_hint(self):
        """Trigger garbage collection hint"""
        now = time.time()
        if now - self.last_gc_hint_time > 60:  # Once per minute
            print(f"[MEMORY_WATCHDOG] GC hint triggered at {self._get_memory_usage():.1f}%")
            self.last_gc_hint_time = now
            
            # Try to trigger GC in Python
            import gc
            gc.collect()
    
    def _check_memory_limits(self) -> tuple[bool, str]:
        """Check memory limits and return (can_trade, reason)"""
        memory_percent = self._get_memory_usage()
        
        if memory_percent >= self.hard_limit:
            return False, f"MEMORY_HARD_LIMIT: {memory_percent:.1f}% >= {self.hard_limit}%"
        elif memory_percent >= self.soft_limit:
            # Soft limit - trigger GC but don't block trading
            self._trigger_gc_hint()
            return True, f"MEMORY_SOFT_WARNING: {memory_percent:.1f}% >= {self.soft_limit}%"
        
        return True, "OK"
    
    def _watchdog_loop(self):
        """Main watchdog loop"""
        print("[MEMORY_WATCHDOG] Starting memory monitoring...")
        
        while self.running:
            try:
                memory_percent = self._get_memory_usage()
                can_trade, reason = self._check_memory_limits()
                
                trading_blocked = not can_trade
                self._update_status(memory_percent, trading_blocked, reason)
                
                if trading_blocked:
                    # Log once per minute when blocked
                    now = time.time()
                    if now - self.last_status_update > 60:
                        print(f"[MEMORY_WATCHDOG] TRADING_BLOCKED: {reason}")
                
                time.sleep(10)  # Check every 10 seconds
                
            except Exception as e:
                print(f"[MEMORY_WATCHDOG] Error in loop: {e}")
                time.sleep(30)  # Wait longer on error
    
    def start(self):
        """Start the watchdog thread"""
        if self.running:
            return
            
        self.running = True
        self.thread = threading.Thread(target=self._watchdog_loop, daemon=True)
        self.thread.start()
        print("[MEMORY_WATCHDOG] Started")
    
    def stop(self):
        """Stop the watchdog thread"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        print("[MEMORY_WATCHDOG] Stopped")
    
    def is_trading_blocked(self) -> tuple[bool, str]:
        """Check if trading is blocked due to high memory"""
        if self.trading_blocked_reason:
            return True, self.trading_blocked_reason
        return False, "OK"
    
    def should_stop_new_websockets(self) -> bool:
        """Check if new WebSocket sessions should be stopped"""
        memory_percent = self._get_memory_usage()
        return memory_percent >= self.hard_limit
    
    def get_status(self) -> Dict[str, Any]:
        """Get current watchdog status"""
        memory_percent = self._get_memory_usage()
        can_trade, reason = self._check_memory_limits()
        
        return {
            "memory_percent": memory_percent,
            "soft_limit": self.soft_limit,
            "hard_limit": self.hard_limit,
            "trading_blocked": not can_trade,
            "reason": reason,
            "last_check": self.last_status_update,
            "should_stop_websockets": self.should_stop_new_websockets()
        }


# Global instance
_memory_watchdog = None

def get_memory_watchdog() -> MemoryWatchdog:
    """Get singleton memory watchdog instance"""
    global _memory_watchdog
    if _memory_watchdog is None:
        _memory_watchdog = MemoryWatchdog()
    return _memory_watchdog
