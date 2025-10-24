#!/usr/bin/env python3
"""
Canary Mode
LIVE-only safety mode with fixed notional and stricter limits
"""

import logging
import os
from typing import Any, Dict, Tuple

logger = logging.getLogger(__name__)

class CanaryMode:
    """Canary mode for LIVE trading with enhanced safety"""
    
    def __init__(self):
        self.is_live = os.getenv("BINANCE_USE_TESTNET", "true").lower() == "false"
        self.is_enabled = os.getenv("CANARY_MODE", "false").lower() == "true"
        
        # Canary mode settings (LIVE only)
        self.fixed_notional_usdt = 15.0  # Fixed notional per trade
        self.max_concurrent = 2  # Stricter concurrent limit
        self.failsafe_threshold = 2  # Stricter failsafe threshold
        self.max_daily_loss_pct = 0.5  # Stricter daily loss limit (0.5%)
        self.cooldown_min = 120  # Longer cooldown (2 hours)
        
        if self.is_enabled and not self.is_live:
            logger.warning("CANARY_MODE is enabled but BINANCE_USE_TESTNET=true - canary mode ignored")
            self.is_enabled = False
    
    def is_active(self) -> bool:
        """Check if canary mode is active"""
        return self.is_enabled and self.is_live
    
    def get_trade_parameters(self, symbol: str, side: str, available_balance: float) -> Dict[str, Any]:
        """Get canary mode trade parameters"""
        if not self.is_active():
            return {}
        
        return {
            "notional_usdt": self.fixed_notional_usdt,
            "max_concurrent": self.max_concurrent,
            "failsafe_threshold": self.failsafe_threshold,
            "max_daily_loss_pct": self.max_daily_loss_pct,
            "cooldown_min": self.cooldown_min,
            "canary_mode": True
        }
    
    def override_risk_limits(self, base_limits: Dict[str, Any]) -> Dict[str, Any]:
        """Override risk limits for canary mode"""
        if not self.is_active():
            return base_limits
        
        # Calculate canary limits
        canary_limits = base_limits.copy()
        
        # Override with canary settings
        canary_limits.update({
            "max_concurrent": self.max_concurrent,
            "max_daily_loss_pct": self.max_daily_loss_pct,
            "cooldown_min": self.cooldown_min,
            "canary_mode": True
        })
        
        logger.info(f"Canary mode active - limits overridden: max_concurrent={self.max_concurrent}, "
                   f"max_daily_loss_pct={self.max_daily_loss_pct}%, cooldown={self.cooldown_min}min")
        
        return canary_limits
    
    def get_position_size(self, symbol: str, side: str, available_balance: float, current_price: float) -> Tuple[float, str]:
        """Calculate position size for canary mode"""
        if not self.is_active():
            return 0.0, "canary_disabled"
        
        # Fixed notional approach
        notional_usdt = self.fixed_notional_usdt
        
        # Calculate quantity based on current price
        if current_price > 0:
            quantity = notional_usdt / current_price
        else:
            quantity = 0.0
            logger.warning(f"Canary mode: invalid price for {symbol}: {current_price}")
        
        logger.info(f"Canary mode position size: {symbol} {side} {quantity:.6f} @ {current_price} "
                   f"(notional: ${notional_usdt})")
        
        return quantity, "canary_fixed_notional"
    
    def should_allow_trade(self, symbol: str, current_positions: int, daily_pnl_usdt: float) -> Tuple[bool, str]:
        """Check if trade should be allowed in canary mode"""
        if not self.is_active():
            return True, "canary_disabled"
        
        # Check concurrent position limit
        if current_positions >= self.max_concurrent:
            return False, f"canary_max_concurrent_exceeded ({current_positions}/{self.max_concurrent})"
        
        # Check daily loss limit (stricter in canary mode)
        max_daily_loss_usdt = 10000.0 * (self.max_daily_loss_pct / 100.0)  # Assume 10k base
        if daily_pnl_usdt < -max_daily_loss_usdt:
            return False, f"canary_daily_loss_exceeded ({daily_pnl_usdt:.2f} < -{max_daily_loss_usdt:.2f})"
        
        return True, "canary_allowed"
    
    def get_status(self) -> Dict[str, Any]:
        """Get canary mode status"""
        return {
            "is_live": self.is_live,
            "is_enabled": self.is_enabled,
            "is_active": self.is_active(),
            "settings": {
                "fixed_notional_usdt": self.fixed_notional_usdt,
                "max_concurrent": self.max_concurrent,
                "failsafe_threshold": self.failsafe_threshold,
                "max_daily_loss_pct": self.max_daily_loss_pct,
                "cooldown_min": self.cooldown_min
            }
        }

# Global instance
_canary_mode = None

def get_canary_mode() -> CanaryMode:
    """Get global canary mode instance"""
    global _canary_mode
    if _canary_mode is None:
        _canary_mode = CanaryMode()
    return _canary_mode

def is_canary_mode_active() -> bool:
    """Check if canary mode is active"""
    return get_canary_mode().is_active()

def get_canary_trade_parameters(symbol: str, side: str, available_balance: float) -> Dict[str, Any]:
    """Get canary mode trade parameters"""
    return get_canary_mode().get_trade_parameters(symbol, side, available_balance)

def override_risk_limits_for_canary(base_limits: Dict[str, Any]) -> Dict[str, Any]:
    """Override risk limits for canary mode"""
    return get_canary_mode().override_risk_limits(base_limits)

def get_canary_position_size(symbol: str, side: str, available_balance: float, current_price: float) -> Tuple[float, str]:
    """Calculate position size for canary mode"""
    return get_canary_mode().get_position_size(symbol, side, available_balance, current_price)

def check_canary_trade_allowed(symbol: str, current_positions: int, daily_pnl_usdt: float) -> Tuple[bool, str]:
    """Check if trade should be allowed in canary mode"""
    return get_canary_mode().should_allow_trade(symbol, current_positions, daily_pnl_usdt)

def get_canary_status() -> Dict[str, Any]:
    """Get canary mode status"""
    return get_canary_mode().get_status()
