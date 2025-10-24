#!/usr/bin/env python3
"""
Manual Override Manager
Controls STOP.TXT creation when user manually starts/stops system
Prevents Auto-Heal from creating STOP.TXT during manual override window
"""

import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from .atomic_io import atomic_write
from .path_registry import get_absolute_path


@dataclass
class ManualOverride:
    """Manual override state"""
    active: bool
    started_by: str  # 'ui', 'cli', 'api'
    started_at: float
    expires_at: float
    ttl_seconds: int
    reason: str = ""


class ManualOverrideManager:
    """
    Manages manual override state for STOP.TXT control
    When override is active, Auto-Heal must not create STOP.TXT
    """
    
    DEFAULT_TTL_SECONDS = 600  # 10 minutes
    
    def __init__(self):
        self.logger = logging.getLogger('ManualOverride')
        self.override_path = get_absolute_path('shared_data') / 'manual_override.json'
        self.stop_path = get_absolute_path('shared_data') / 'STOP.TXT'
        
        self.override_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.override: Optional[ManualOverride] = None
        self._load_override()
    
    def _load_override(self):
        """Load override state from file"""
        if self.override_path.exists():
            try:
                with open(self.override_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                self.override = ManualOverride(**data)
                
                # Check if expired
                if time.time() > self.override.expires_at:
                    self.logger.info("Manual override expired, clearing...")
                    self.override = None
                    self._save_override()
            except Exception as e:
                self.logger.error(f"Failed to load override: {e}")
    
    def _save_override(self):
        """Save override state to file"""
        try:
            if self.override:
                data = asdict(self.override)
                atomic_write(self.override_path, json.dumps(data, indent=2))
            else:
                # Clear override file
                if self.override_path.exists():
                    self.override_path.unlink()
        except Exception as e:
            self.logger.error(f"Failed to save override: {e}")
    
    def activate_override(
        self, 
        started_by: str = 'ui', 
        ttl_seconds: Optional[int] = None,
        reason: str = ""
    ):
        """
        Activate manual override
        
        Args:
            started_by: Source of the activation ('ui', 'cli', 'api')
            ttl_seconds: Time to live in seconds (default: 10 minutes)
            reason: Optional reason for activation
        """
        if ttl_seconds is None:
            ttl_seconds = self.DEFAULT_TTL_SECONDS
        
        now = time.time()
        
        self.override = ManualOverride(
            active=True,
            started_by=started_by,
            started_at=now,
            expires_at=now + ttl_seconds,
            ttl_seconds=ttl_seconds,
            reason=reason or f"Manual start by {started_by}"
        )
        
        self._save_override()
        
        self.logger.info(
            f"✅ Manual override ACTIVATED by {started_by} (TTL: {ttl_seconds}s)"
        )
    
    def deactivate_override(self):
        """Deactivate manual override"""
        if self.override:
            self.logger.info(
                f"Manual override DEACTIVATED (was active for {time.time() - self.override.started_at:.1f}s)"
            )
        
        self.override = None
        self._save_override()
    
    def is_override_active(self) -> bool:
        """Check if manual override is currently active"""
        if not self.override:
            return False
        
        # Check expiration
        if time.time() > self.override.expires_at:
            self.logger.info("Manual override expired")
            self.deactivate_override()
            return False
        
        return True
    
    def get_override_status(self) -> dict:
        """Get override status for UI display"""
        if not self.is_override_active():
            return {
                "active": False,
                "message": "No manual override active"
            }
        
        remaining_seconds = self.override.expires_at - time.time()
        
        return {
            "active": True,
            "started_by": self.override.started_by,
            "started_at": self.override.started_at,
            "expires_at": self.override.expires_at,
            "remaining_seconds": remaining_seconds,
            "reason": self.override.reason,
            "message": f"Override active ({remaining_seconds:.0f}s remaining)"
        }
    
    def can_autoheal_create_stop(self) -> tuple[bool, str]:
        """
        Check if Auto-Heal can create STOP.TXT
        
        Returns:
            (can_create, reason)
        """
        if self.is_override_active():
            return False, "Manual override active - STOP.TXT creation blocked"
        
        return True, "OK"
    
    def log_would_block_event(self, reason: str):
        """Log when Auto-Heal would create STOP.TXT but is blocked"""
        self.logger.warning(
            f"⚠️ Auto-Heal would create STOP.TXT but override is active: {reason}"
        )
        
        # Log to events file
        events_path = get_absolute_path('shared_data') / 'autoheal_events.jsonl'
        try:
            with open(events_path, 'a', encoding='utf-8') as f:
                event = {
                    "event": "would_block_stop",
                    "reason": reason,
                    "override_active": True,
                    "ts": time.time()
                }
                f.write(json.dumps(event, ensure_ascii=False) + '\n')
        except Exception as e:
            self.logger.error(f"Failed to log would_block event: {e}")
    
    def extend_override(self, additional_seconds: int = 300):
        """Extend current override by additional seconds"""
        if self.is_override_active():
            self.override.expires_at += additional_seconds
            self._save_override()
            self.logger.info(f"Override extended by {additional_seconds}s")
            return True
        return False


# Global instance
_override_manager = ManualOverrideManager()


def activate_override(started_by: str = 'ui', ttl_seconds: Optional[int] = None, reason: str = ""):
    """Activate manual override"""
    _override_manager.activate_override(started_by, ttl_seconds, reason)


def deactivate_override():
    """Deactivate manual override"""
    _override_manager.deactivate_override()


def is_override_active() -> bool:
    """Check if override is active"""
    return _override_manager.is_override_active()


def get_override_status() -> dict:
    """Get override status"""
    return _override_manager.get_override_status()


def can_autoheal_create_stop() -> tuple[bool, str]:
    """Check if Auto-Heal can create STOP.TXT"""
    return _override_manager.can_autoheal_create_stop()


def log_would_block_event(reason: str):
    """Log would_block event"""
    _override_manager.log_would_block_event(reason)


def extend_override(additional_seconds: int = 300) -> bool:
    """Extend override"""
    return _override_manager.extend_override(additional_seconds)

