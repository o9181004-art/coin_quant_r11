#!/usr/bin/env python3
"""
Control Plane - Authoritative stop/control state management
Manages auto_trading_enabled state with atomic operations
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from shared.io.jsonio import now_epoch_s, write_json_atomic_nobom
from shared.paths import ensure_all_dirs


class ControlPlane:
    """Authoritative control plane for auto trading state"""
    
    def __init__(self):
        self.control_file = Path("shared_data/controls/auto_trading.json")
        ensure_all_dirs()
        
    def get_state(self) -> Dict[str, Any]:
        """Get current control state"""
        try:
            if not self.control_file.exists():
                # Default state
                return {
                    "timestamp": now_epoch_s(),
                    "auto_trading_enabled": False,
                    "reason": "initial",
                    "since": now_epoch_s()
                }
            
            with open(self.control_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            # Fallback to safe state
            return {
                "timestamp": now_epoch_s(),
                "auto_trading_enabled": False,
                "reason": "error_fallback",
                "since": now_epoch_s()
            }
    
    def set_emergency_stop(self) -> bool:
        """Set emergency stop state"""
        try:
            current_time = now_epoch_s()
            state = {
                "timestamp": current_time,
                "auto_trading_enabled": False,
                "reason": "emergency_stop",
                "since": current_time
            }
            write_json_atomic_nobom(self.control_file, state)
            return True
        except Exception:
            return False
    
    def set_user_toggle(self, enabled: bool) -> bool:
        """Set user toggle state"""
        try:
            current_time = now_epoch_s()
            state = {
                "timestamp": current_time,
                "auto_trading_enabled": enabled,
                "reason": "user_toggle",
                "since": current_time
            }
            write_json_atomic_nobom(self.control_file, state)
            return True
        except Exception:
            return False
    
    def set_system_guard(self, enabled: bool, reason: str = "system_guard") -> bool:
        """Set system guard state"""
        try:
            current_time = now_epoch_s()
            state = {
                "timestamp": current_time,
                "auto_trading_enabled": enabled,
                "reason": reason,
                "since": current_time
            }
            write_json_atomic_nobom(self.control_file, state)
            return True
        except Exception:
            return False
    
    def is_auto_trading_enabled(self) -> bool:
        """Check if auto trading is enabled"""
        state = self.get_state()
        return state.get("auto_trading_enabled", False)
    
    def get_reason(self) -> str:
        """Get current reason"""
        state = self.get_state()
        return state.get("reason", "unknown")
    
    def get_since(self) -> int:
        """Get since timestamp"""
        state = self.get_state()
        return state.get("since", 0)


# Global instance
_control_plane = None

def get_control_plane() -> ControlPlane:
    """Get global control plane instance"""
    global _control_plane
    if _control_plane is None:
        _control_plane = ControlPlane()
    return _control_plane
