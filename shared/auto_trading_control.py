"""
Auto Trading Control
Control plane for trading ON/OFF with GREEN-by-Design gating
"""
import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from .env_loader import get_env_hash
from .health_v2 import is_system_ready_for_auto_trading, validate_health_v2
from .path_registry import get_absolute_path
from .io_safe import atomic_write


@dataclass
class AutoTradingState:
    """Auto trading state"""
    enabled: bool = False
    last_enabled_ts: float = 0.0
    last_disabled_ts: float = 0.0
    enabled_by: str = ""
    disabled_by: str = ""
    reason: str = ""
    health_status: str = "UNKNOWN"
    green_count: int = 0
    total_probes: int = 7
    timestamp: float = 0.0


class AutoTradingController:
    """Auto trading controller with GREEN-by-Design gating"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.state_file = get_absolute_path('shared_data_ops') / 'auto_trading_state.json'
        self.env_hash = get_env_hash()
    
    def get_current_state(self) -> AutoTradingState:
        """Get current auto trading state"""
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return AutoTradingState(**data)
        except Exception as e:
            self.logger.error(f"Failed to load auto trading state: {e}")
        
        return AutoTradingState()
    
    def save_state(self, state: AutoTradingState):
        """Save auto trading state"""
        try:
            state.timestamp = time.time()
            atomic_write(self.state_file, json.dumps(asdict(state), indent=2))
        except Exception as e:
            self.logger.error(f"Failed to save auto trading state: {e}")
    
    def enable_auto_trading(self, enabled_by: str = "manual") -> Dict[str, Any]:
        """Enable auto trading with GREEN validation"""
        try:
            # Check system readiness
            if not is_system_ready_for_auto_trading():
                health_status = validate_health_v2()
                return {
                    "success": False,
                    "reason": "System not ready for auto trading",
                    "health_status": health_status.global_status,
                    "green_count": health_status.green_count,
                    "failed_probes": [p.probe_name for p in health_status.probe_results if not p.status]
                }
            
            # Get current state
            current_state = self.get_current_state()
            
            # Update state
            current_state.enabled = True
            current_state.last_enabled_ts = time.time()
            current_state.enabled_by = enabled_by
            current_state.reason = "System ready for auto trading"
            current_state.health_status = "GREEN"
            current_state.green_count = 7
            
            # Save state
            self.save_state(current_state)
            
            self.logger.info(f"Auto trading enabled by {enabled_by}")
            
            return {
                "success": True,
                "reason": "Auto trading enabled successfully",
                "health_status": "GREEN",
                "green_count": 7
            }
            
        except Exception as e:
            self.logger.error(f"Failed to enable auto trading: {e}")
            return {
                "success": False,
                "reason": f"Error enabling auto trading: {e}",
                "health_status": "ERROR",
                "green_count": 0
            }
    
    def disable_auto_trading(self, disabled_by: str = "manual", reason: str = "Manual stop") -> Dict[str, Any]:
        """Disable auto trading"""
        try:
            # Get current state
            current_state = self.get_current_state()
            
            # Update state
            current_state.enabled = False
            current_state.last_disabled_ts = time.time()
            current_state.disabled_by = disabled_by
            current_state.reason = reason
            
            # Save state
            self.save_state(current_state)
            
            self.logger.info(f"Auto trading disabled by {disabled_by}: {reason}")
            
            return {
                "success": True,
                "reason": "Auto trading disabled successfully"
            }
            
        except Exception as e:
            self.logger.error(f"Failed to disable auto trading: {e}")
            return {
                "success": False,
                "reason": f"Error disabling auto trading: {e}"
            }
    
    def emergency_stop(self, reason: str = "Emergency stop") -> Dict[str, Any]:
        """Emergency stop auto trading"""
        return self.disable_auto_trading("emergency", reason)
    
    def get_status(self) -> Dict[str, Any]:
        """Get auto trading status"""
        try:
            current_state = self.get_current_state()
            health_status = validate_health_v2()
            
            return {
                "enabled": current_state.enabled,
                "health_status": health_status.global_status,
                "green_count": health_status.green_count,
                "total_probes": health_status.total_probes,
                "safe_to_trade": health_status.safe_to_trade,
                "last_enabled": current_state.last_enabled_ts,
                "last_disabled": current_state.last_disabled_ts,
                "enabled_by": current_state.enabled_by,
                "disabled_by": current_state.disabled_by,
                "reason": current_state.reason,
                "timestamp": current_state.timestamp
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get auto trading status: {e}")
            return {
                "enabled": False,
                "health_status": "ERROR",
                "green_count": 0,
                "total_probes": 7,
                "safe_to_trade": False,
                "error": str(e)
            }
    
    def validate_trading_conditions(self) -> Dict[str, Any]:
        """Validate current trading conditions"""
        try:
            health_status = validate_health_v2()
            current_state = self.get_current_state()
            
            # Check if auto trading is enabled
            if not current_state.enabled:
                return {
                    "can_trade": False,
                    "reason": "Auto trading is disabled",
                    "health_status": health_status.global_status,
                    "green_count": health_status.green_count
                }
            
            # Check system health
            if not health_status.safe_to_trade:
                return {
                    "can_trade": False,
                    "reason": "System not safe for trading",
                    "health_status": health_status.global_status,
                    "green_count": health_status.green_count,
                    "failed_probes": [p.probe_name for p in health_status.probe_results if not p.status]
                }
            
            return {
                "can_trade": True,
                "reason": "All conditions met",
                "health_status": health_status.global_status,
                "green_count": health_status.green_count
            }
            
        except Exception as e:
            self.logger.error(f"Failed to validate trading conditions: {e}")
            return {
                "can_trade": False,
                "reason": f"Validation error: {e}",
                "health_status": "ERROR",
                "green_count": 0
            }


# Global instance
_auto_trading_controller = AutoTradingController()


def enable_auto_trading(enabled_by: str = "manual") -> Dict[str, Any]:
    """Enable auto trading"""
    return _auto_trading_controller.enable_auto_trading(enabled_by)


def disable_auto_trading(disabled_by: str = "manual", reason: str = "Manual stop") -> Dict[str, Any]:
    """Disable auto trading"""
    return _auto_trading_controller.disable_auto_trading(disabled_by, reason)


def emergency_stop(reason: str = "Emergency stop") -> Dict[str, Any]:
    """Emergency stop auto trading"""
    return _auto_trading_controller.emergency_stop(reason)


def get_auto_trading_status() -> Dict[str, Any]:
    """Get auto trading status"""
    return _auto_trading_controller.get_status()


def validate_trading_conditions() -> Dict[str, Any]:
    """Validate current trading conditions"""
    return _auto_trading_controller.validate_trading_conditions()


def is_auto_trading_enabled() -> bool:
    """Check if auto trading is enabled"""
    status = get_auto_trading_status()
    return status.get("enabled", False)


if __name__ == '__main__':
    # Test auto trading control
    print("Auto Trading Control Test:")
    
    # Get initial status
    status = get_auto_trading_status()
    print(f"Initial status: {status}")
    
    # Try to enable
    result = enable_auto_trading("test")
    print(f"Enable result: {result}")
    
    # Get updated status
    status = get_auto_trading_status()
    print(f"Updated status: {status}")
    
    # Validate conditions
    conditions = validate_trading_conditions()
    print(f"Trading conditions: {conditions}")
    
    # Disable
    result = disable_auto_trading("test", "Test complete")
    print(f"Disable result: {result}")
    
    # Final status
    status = get_auto_trading_status()
    print(f"Final status: {status}")
