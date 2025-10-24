#!/usr/bin/env python3
"""
Default/Random Signal Gating (Safety)
Ensures ALLOW_DEFAULT_SIGNALS defaults to false across all loaders
"""

import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class SignalGating:
    """Signal gating for safety controls"""
    
    def __init__(self):
        self.allow_default_signals = self._get_allow_default_signals()
        self._log_boot_status()
    
    def _get_allow_default_signals(self) -> bool:
        """Get ALLOW_DEFAULT_SIGNALS setting with safety defaults"""
        # In LIVE mode, force to false regardless of env
        if self._is_live_mode():
            return False
        
        # Default to false for safety
        env_value = os.getenv("ALLOW_DEFAULT_SIGNALS", "false").lower()
        return env_value in ("true", "1", "yes", "on")
    
    def _is_live_mode(self) -> bool:
        """Check if running in live trading mode"""
        # Check various indicators of live mode
        live_indicators = [
            os.getenv("LIVE_TRADING", "false").lower() in ("true", "1", "yes", "on"),
            os.getenv("DRY_RUN", "true").lower() in ("false", "0", "no", "off"),
            os.getenv("BINANCE_USE_TESTNET", "true").lower() in ("false", "0", "no", "off")
        ]
        
        return any(live_indicators)
    
    def _log_boot_status(self):
        """Log signal gating status at boot"""
        mode = "LIVE" if self._is_live_mode() else "TEST"
        status = "ENABLED" if self.allow_default_signals else "DISABLED"
        
        logger.info(f"Signal gating: {status} (mode: {mode})")
        
        if self._is_live_mode() and self.allow_default_signals:
            logger.warning("LIVE mode with default signals enabled - this should not happen!")
    
    def is_signal_allowed(self, signal_data: Dict[str, Any]) -> bool:
        """Check if signal is allowed based on gating rules"""
        # If default signals are disabled, check if this is a default signal
        if not self.allow_default_signals:
            if self._is_default_signal(signal_data):
                logger.debug("Blocking default signal (gating enabled)")
                return False
        
        return True
    
    def _is_default_signal(self, signal_data: Dict[str, Any]) -> bool:
        """Check if signal is a default/random signal"""
        # Check for indicators of default signals
        default_indicators = [
            signal_data.get("strategy") == "default",
            signal_data.get("confidence", 0) < 0.1,
            signal_data.get("source") == "random",
            signal_data.get("is_default", False),
            signal_data.get("fallback", False)
        ]
        
        return any(default_indicators)
    
    def get_gating_status(self) -> Dict[str, Any]:
        """Get current gating status"""
        return {
            "allow_default_signals": self.allow_default_signals,
            "is_live_mode": self._is_live_mode(),
            "gating_active": not self.allow_default_signals
        }

# Global instance
signal_gating = SignalGating()

def is_signal_allowed(signal_data: Dict[str, Any]) -> bool:
    """Check if signal is allowed (convenience function)"""
    return signal_gating.is_signal_allowed(signal_data)

def get_gating_status() -> Dict[str, Any]:
    """Get gating status (convenience function)"""
    return signal_gating.get_gating_status()
