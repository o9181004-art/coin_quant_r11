#!/usr/bin/env python3
"""
Alert Cooldown Manager - Prevent alert spam
Implements cooldown logic for restart alerts and health warnings
"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Configuration
ALERT_COOLDOWN_MINUTES = 10
ALERT_STATE_FILE = "alerts_state.json"


class AlertCooldownManager:
    """Manages alert cooldowns to prevent spam"""
    
    def __init__(self, repo_root: Optional[Path] = None):
        if repo_root is None:
            repo_root = Path(__file__).parent.parent.absolute()
        
        self.repo_root = repo_root
        self.state_file = repo_root / "shared_data" / ALERT_STATE_FILE
        
        # Ensure directory exists
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing state
        self._state = self._load_state()
        
        logger.info("AlertCooldownManager initialized")
    
    def _load_state(self) -> Dict[str, Any]:
        """Load alert state from file"""
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load alert state: {e}")
        
        return {
            "last_alerts": {},
            "cooldown_minutes": ALERT_COOLDOWN_MINUTES,
            "version": "1.0"
        }
    
    def _save_state(self):
        """Save alert state to file"""
        try:
            self._state["last_updated"] = time.time()
            
            # Atomic write
            temp_file = self.state_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self._state, f, ensure_ascii=False, indent=2)
            
            temp_file.replace(self.state_file)
            
        except Exception as e:
            logger.error(f"Failed to save alert state: {e}")
    
    def can_send_alert(self, alert_type: str, service: str) -> bool:
        """Check if alert can be sent (not in cooldown)"""
        alert_key = f"{alert_type}:{service}"
        last_alert_ts = self._state["last_alerts"].get(alert_key, 0)
        
        cooldown_seconds = self._state["cooldown_minutes"] * 60
        time_since_last = time.time() - last_alert_ts
        
        can_send = time_since_last >= cooldown_seconds
        
        if not can_send:
            remaining_minutes = (cooldown_seconds - time_since_last) / 60
            logger.debug(
                f"alert_cooldown_active type={alert_type} service={service} "
                f"remaining_min={remaining_minutes:.1f}"
            )
        
        return can_send
    
    def record_alert_sent(self, alert_type: str, service: str):
        """Record that an alert was sent"""
        alert_key = f"{alert_type}:{service}"
        self._state["last_alerts"][alert_key] = time.time()
        self._save_state()
        
        logger.info(f"alert_recorded type={alert_type} service={service}")
    
    def get_remaining_cooldown(self, alert_type: str, service: str) -> float:
        """Get remaining cooldown time in minutes"""
        alert_key = f"{alert_type}:{service}"
        last_alert_ts = self._state["last_alerts"].get(alert_key, 0)
        
        cooldown_seconds = self._state["cooldown_minutes"] * 60
        time_since_last = time.time() - last_alert_ts
        
        if time_since_last >= cooldown_seconds:
            return 0.0
        
        return (cooldown_seconds - time_since_last) / 60.0
    
    def clear_cooldown(self, alert_type: str, service: str):
        """Clear cooldown for specific alert"""
        alert_key = f"{alert_type}:{service}"
        if alert_key in self._state["last_alerts"]:
            del self._state["last_alerts"][alert_key]
            self._save_state()
            logger.info(f"alert_cooldown_cleared type={alert_type} service={service}")
    
    def clear_all_cooldowns(self):
        """Clear all cooldowns"""
        self._state["last_alerts"] = {}
        self._save_state()
        logger.info("all_alert_cooldowns_cleared")


# Global instance
_alert_manager: Optional[AlertCooldownManager] = None


def get_alert_manager(repo_root: Optional[Path] = None) -> AlertCooldownManager:
    """Get singleton alert cooldown manager"""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertCooldownManager(repo_root)
    return _alert_manager


def can_send_alert(alert_type: str, service: str, repo_root: Optional[Path] = None) -> bool:
    """Check if alert can be sent"""
    manager = get_alert_manager(repo_root)
    return manager.can_send_alert(alert_type, service)


def record_alert_sent(alert_type: str, service: str, repo_root: Optional[Path] = None):
    """Record that an alert was sent"""
    manager = get_alert_manager(repo_root)
    manager.record_alert_sent(alert_type, service)
