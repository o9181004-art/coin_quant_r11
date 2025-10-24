#!/usr/bin/env python3
"""
Risk Profiles - Centralized profile application
Manages AGGRESSIVE and SAFE mode configurations
"""

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Optional

import yaml
from dotenv import load_dotenv

from shared.state.risk_mode_store import get_risk_mode_store


# Load environment
config_path = Path(__file__).parent.parent.parent / "config.env"
load_dotenv(config_path)


@dataclass
class RiskProfile:
    """Risk profile configuration"""
    name: str
    daily_loss_limit_pct: float
    trade_risk_per_position_pct: float
    vol_target_pct: float
    max_concurrent_positions: int
    slippage_bps: int = 15
    cooldown_min: int = 30
    description: str = ""


class RiskProfileManager:
    """Manages risk profiles and applies them to the system"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        # Load profiles from config
        self.profiles = self._load_profiles()

        # Current active profile
        self._current_profile: Optional[RiskProfile] = None

    def _load_profiles(self) -> Dict[str, RiskProfile]:
        """Load risk profiles from environment and config files"""
        profiles = {}

        # AGGRESSIVE profile
        profiles["AGGRESSIVE"] = RiskProfile(
            name="AGGRESSIVE",
            daily_loss_limit_pct=float(os.getenv("DAILY_LOSS_LIMIT_PCT", "3.0")),
            trade_risk_per_position_pct=float(os.getenv("TRADE_RISK_PER_POSITION_PCT", "0.5")),
            vol_target_pct=float(os.getenv("VOL_TARGET_PCT", "30")),
            max_concurrent_positions=int(os.getenv("MAX_CONCURRENT_POSITIONS", "12")),
            slippage_bps=25,
            cooldown_min=30,
            description="High risk, larger positions, aggressive strategy selection"
        )

        # SAFE profile
        profiles["SAFE"] = RiskProfile(
            name="SAFE",
            daily_loss_limit_pct=float(os.getenv("DAILY_LOSS_LIMIT_PCT_SAFE", "1.0")),
            trade_risk_per_position_pct=float(os.getenv("TRADE_RISK_PER_POSITION_PCT_SAFE", "0.15")),
            vol_target_pct=float(os.getenv("VOL_TARGET_PCT_SAFE", "15")),
            max_concurrent_positions=int(os.getenv("MAX_CONCURRENT_POSITIONS_SAFE", "3")),
            slippage_bps=15,
            cooldown_min=60,
            description="Low risk, small positions, conservative strategy selection"
        )

        self.logger.info(f"Loaded risk profiles: {list(profiles.keys())}")
        return profiles

    def get_profile(self, mode: str) -> Optional[RiskProfile]:
        """Get profile by mode name"""
        return self.profiles.get(mode.upper())

    def apply_profile(self, mode: str) -> bool:
        """
        Apply risk profile to the system

        This updates the active configuration that will be read by:
        - Trader (position sizing, order caps)
        - ARES (strategy selection, budget allocation)
        - UI (display limits and warnings)

        No service restarts required - components re-read config dynamically
        """
        try:
            profile = self.get_profile(mode)
            if not profile:
                self.logger.error(f"Profile not found: {mode}")
                return False

            self._current_profile = profile

            # Log profile application
            self.logger.info(
                f"Applied {profile.name} profile: "
                f"daily_loss={profile.daily_loss_limit_pct}%, "
                f"risk_per_pos={profile.trade_risk_per_position_pct}%, "
                f"vol_target={profile.vol_target_pct}%, "
                f"max_positions={profile.max_concurrent_positions}"
            )

            # Emit CONFIG_UPDATED event for live components
            self._emit_config_updated_event(profile)

            return True

        except Exception as e:
            self.logger.error(f"Failed to apply profile {mode}: {e}")
            return False

    def _emit_config_updated_event(self, profile: RiskProfile):
        """Emit configuration update event for live components"""
        try:
            # Write event to shared_data for components to pick up
            event_file = Path("shared_data/events/config_updated.json")
            event_file.parent.mkdir(parents=True, exist_ok=True)

            import json
            import time

            event = {
                "event": "CONFIG_UPDATED",
                "timestamp": time.time(),
                "profile": profile.name,
                "config": {
                    "daily_loss_limit_pct": profile.daily_loss_limit_pct,
                    "trade_risk_per_position_pct": profile.trade_risk_per_position_pct,
                    "vol_target_pct": profile.vol_target_pct,
                    "max_concurrent_positions": profile.max_concurrent_positions,
                    "slippage_bps": profile.slippage_bps,
                    "cooldown_min": profile.cooldown_min,
                }
            }

            with open(event_file, 'w', encoding='utf-8') as f:
                json.dump(event, f, indent=2)

            self.logger.debug(f"Emitted CONFIG_UPDATED event for {profile.name}")

        except Exception as e:
            self.logger.warning(f"Failed to emit config update event: {e}")

    def get_current_profile(self) -> Optional[RiskProfile]:
        """Get currently active profile"""
        if self._current_profile is None:
            # Load from risk mode store
            store = get_risk_mode_store()
            current_mode = store.get_mode()
            self._current_profile = self.get_profile(current_mode)

        return self._current_profile

    def get_profile_config(self, mode: str = None) -> Dict[str, Any]:
        """Get profile configuration as dictionary"""
        if mode is None:
            profile = self.get_current_profile()
        else:
            profile = self.get_profile(mode)

        if not profile:
            return {}

        return {
            "name": profile.name,
            "daily_loss_limit_pct": profile.daily_loss_limit_pct,
            "trade_risk_per_position_pct": profile.trade_risk_per_position_pct,
            "vol_target_pct": profile.vol_target_pct,
            "max_concurrent_positions": profile.max_concurrent_positions,
            "slippage_bps": profile.slippage_bps,
            "cooldown_min": profile.cooldown_min,
            "description": profile.description,
        }


# Global instance
_global_profile_manager: Optional[RiskProfileManager] = None


def get_profile_manager() -> RiskProfileManager:
    """Get global risk profile manager"""
    global _global_profile_manager
    if _global_profile_manager is None:
        _global_profile_manager = RiskProfileManager()
    return _global_profile_manager


# Convenience functions
def apply_profile_aggressive() -> bool:
    """Apply AGGRESSIVE profile"""
    return get_profile_manager().apply_profile("AGGRESSIVE")


def apply_profile_safe() -> bool:
    """Apply SAFE profile"""
    return get_profile_manager().apply_profile("SAFE")


def get_current_profile() -> Optional[RiskProfile]:
    """Get current active profile"""
    return get_profile_manager().get_current_profile()


def get_profile_config(mode: str = None) -> Dict[str, Any]:
    """Get profile configuration"""
    return get_profile_manager().get_profile_config(mode)
