"""
Order gating system - prevents orders unless services are GREEN.
"""

import logging
import time
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class OrderGate:
    """Global order gate - no orders unless Feeder & Trader are GREEN"""
    
    def __init__(self):
        self.feeder_heartbeat_path = Path("shared_data/heartbeats/feeder.json")
        self.trader_heartbeat_path = Path("shared_data/heartbeats/trader.json")
        self.health_age_threshold = 60  # seconds
        
        # Track last log time per symbol to avoid spam
        self._last_log_time = {}
        self._log_throttle_sec = 60  # Log once per minute per symbol
    
    def check_services_ready(self) -> Dict:
        """
        Check if both Feeder and Trader are GREEN.
        
        Returns:
            {
                "ok": bool,
                "feeder_ok": bool,
                "trader_ok": bool,
                "reason": str,
                "feeder_age": float,
                "trader_age": float
            }
        """
        feeder_ok, feeder_age = self._check_heartbeat("feeder")
        trader_ok, trader_age = self._check_heartbeat("trader")
        
        ok = feeder_ok and trader_ok
        
        if not ok:
            reasons = []
            if not feeder_ok:
                reasons.append(f"Feeder not ready (age: {feeder_age:.1f}s)")
            if not trader_ok:
                reasons.append(f"Trader not ready (age: {trader_age:.1f}s)")
            reason = "; ".join(reasons)
        else:
            reason = "All services GREEN"
        
        return {
            "ok": ok,
            "feeder_ok": feeder_ok,
            "trader_ok": trader_ok,
            "reason": reason,
            "feeder_age": feeder_age,
            "trader_age": trader_age
        }
    
    def can_place_order(self, symbol: str) -> tuple[bool, str]:
        """
        Check if order can be placed for a symbol.
        
        Args:
            symbol: Trading symbol
        
        Returns:
            (can_place, reason)
        """
        status = self.check_services_ready()
        
        if status["ok"]:
            return True, "Services ready"
        
        # Not ready - log once per minute per symbol to avoid spam
        self._log_throttled(symbol, status["reason"])
        
        return False, f"SERVICE_NOT_READY: {status['reason']}"
    
    def _check_heartbeat(self, service: str) -> tuple[bool, float]:
        """
        Check if service heartbeat is fresh.
        
        Returns:
            (is_fresh, age_in_seconds)
        """
        if service == "feeder":
            hb_path = self.feeder_heartbeat_path
        elif service == "trader":
            hb_path = self.trader_heartbeat_path
        else:
            return False, float('inf')
        
        if not hb_path.exists():
            return False, float('inf')
        
        try:
            import json
            with open(hb_path, 'r') as f:
                hb_data = json.load(f)
            
            timestamp = hb_data.get('timestamp', 0)
            age = time.time() - timestamp
            
            is_fresh = age <= self.health_age_threshold
            return is_fresh, age
            
        except Exception as e:
            logger.debug(f"Error reading {service} heartbeat: {e}")
            return False, float('inf')
    
    def _log_throttled(self, symbol: str, reason: str):
        """Log service not ready message, throttled to once per minute per symbol"""
        now = time.time()
        last_log = self._last_log_time.get(symbol, 0)
        
        if (now - last_log) >= self._log_throttle_sec:
            logger.warning(f"Order gate blocked for {symbol}: {reason}")
            self._last_log_time[symbol] = now


# Global order gate instance
_order_gate: Optional[OrderGate] = None


def get_order_gate() -> OrderGate:
    """Get global order gate instance"""
    global _order_gate
    if _order_gate is None:
        _order_gate = OrderGate()
    return _order_gate


def check_order_allowed(symbol: str) -> tuple[bool, str]:
    """
    Check if order is allowed for a symbol.
    
    Returns:
        (allowed, reason)
    """
    gate = get_order_gate()
    return gate.can_place_order(symbol)


__all__ = ["OrderGate", "get_order_gate", "check_order_allowed"]

