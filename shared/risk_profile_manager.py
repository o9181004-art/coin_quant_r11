"""
Risk Profile Manager
Loads and applies risk profile presets from config/risk_profiles.yaml
Only affects new entries; existing positions are not modified
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

logger = logging.getLogger(__name__)

class RiskProfileManager:
    """Manages risk profile presets and applies them to new entries only"""
    
    def __init__(self):
        self.profiles = {}
        self.current_profile = None
        self.profile_data = {}
        self._load_profiles()
        self._load_current_profile()
    
    def _load_profiles(self):
        """Load risk profiles from config/risk_profiles.yaml"""
        try:
            config_file = Path("config/risk_profiles.yaml")
            if not config_file.exists():
                logger.error("Risk profiles config not found: config/risk_profiles.yaml")
                return
            
            with open(config_file, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            
            self.profiles = config.get("profiles", {})
            self.validation_rules = config.get("validation", {})
            self.default_profile = config.get("default", "conservative")
            
            logger.info(f"Loaded {len(self.profiles)} risk profiles: {list(self.profiles.keys())}")
            
        except Exception as e:
            logger.error(f"Failed to load risk profiles: {e}")
            self.profiles = {}
    
    def _load_current_profile(self):
        """Load current profile from environment variable"""
        try:
            profile_name = os.getenv("RISK_PROFILE", self.default_profile)
            
            if profile_name not in self.profiles:
                logger.warning(f"Profile '{profile_name}' not found, using default: {self.default_profile}")
                profile_name = self.default_profile
            
            self.current_profile = profile_name
            self.profile_data = self.profiles[profile_name].copy()
            
            # Validate profile data
            if self._validate_profile(self.profile_data):
                logger.info(f"Risk profile loaded: {profile_name} - {self.profile_data.get('description', '')}")
            else:
                logger.error(f"Invalid profile data for {profile_name}")
                self._load_default_profile()
                
        except Exception as e:
            logger.error(f"Failed to load current profile: {e}")
            self._load_default_profile()
    
    def _load_default_profile(self):
        """Load default profile as fallback"""
        try:
            self.current_profile = self.default_profile
            self.profile_data = self.profiles.get(self.default_profile, {}).copy()
            logger.info(f"Using default profile: {self.default_profile}")
        except Exception as e:
            logger.error(f"Failed to load default profile: {e}")
            self.profile_data = {}
    
    def _validate_profile(self, profile_data: Dict[str, Any]) -> bool:
        """Validate profile data against rules"""
        try:
            rules = self.validation_rules
            
            # Check required fields
            required_fields = ["pos_size_pct", "max_concurrent", "daily_max_loss_pct", "slippage_bps", "cooldown_min"]
            for field in required_fields:
                if field not in profile_data:
                    logger.error(f"Missing required field: {field}")
                    return False
            
            # Validate ranges
            validations = [
                ("pos_size_pct", rules.get("min_pos_size_pct", 0.1), rules.get("max_pos_size_pct", 2.0)),
                ("max_concurrent", rules.get("min_max_concurrent", 1), rules.get("max_max_concurrent", 10)),
                ("daily_max_loss_pct", rules.get("min_daily_max_loss_pct", 0.5), rules.get("max_daily_max_loss_pct", 5.0)),
                ("slippage_bps", rules.get("min_slippage_bps", 5), rules.get("max_slippage_bps", 100)),
                ("cooldown_min", rules.get("min_cooldown_min", 5), rules.get("max_cooldown_min", 300))
            ]
            
            for field, min_val, max_val in validations:
                value = profile_data[field]
                if not (min_val <= value <= max_val):
                    logger.error(f"Field {field} value {value} out of range [{min_val}, {max_val}]")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Profile validation error: {e}")
            return False
    
    def get_current_profile(self) -> str:
        """Get current profile name"""
        return self.current_profile or self.default_profile
    
    def get_profile_data(self) -> Dict[str, Any]:
        """Get current profile data"""
        return self.profile_data.copy()
    
    def get_pos_size_pct(self) -> float:
        """Get position size percentage for new entries"""
        return self.profile_data.get("pos_size_pct", 0.5)
    
    def get_max_concurrent(self) -> int:
        """Get maximum concurrent positions for new entries"""
        return self.profile_data.get("max_concurrent", 3)
    
    def get_daily_max_loss_pct(self) -> float:
        """Get daily maximum loss percentage for new entries"""
        return self.profile_data.get("daily_max_loss_pct", 1.0)
    
    def get_slippage_bps(self) -> int:
        """Get acceptable slippage in basis points for new entries"""
        return self.profile_data.get("slippage_bps", 15)
    
    def get_cooldown_min(self) -> int:
        """Get cooldown between trades in minutes for new entries"""
        return self.profile_data.get("cooldown_min", 60)
    
    def reload_profile(self):
        """Reload profiles and current profile (useful for runtime changes)"""
        self._load_profiles()
        self._load_current_profile()
    
    def get_available_profiles(self) -> list:
        """Get list of available profile names"""
        return list(self.profiles.keys())
    
    def get_profile_summary(self) -> Dict[str, Any]:
        """Get summary of current profile for logging/monitoring"""
        return {
            "profile_name": self.get_current_profile(),
            "pos_size_pct": self.get_pos_size_pct(),
            "max_concurrent": self.get_max_concurrent(),
            "daily_max_loss_pct": self.get_daily_max_loss_pct(),
            "slippage_bps": self.get_slippage_bps(),
            "cooldown_min": self.get_cooldown_min(),
            "description": self.profile_data.get("description", "")
        }

# Global instance
_risk_profile_manager = None

def get_risk_profile_manager() -> RiskProfileManager:
    """Get global risk profile manager instance"""
    global _risk_profile_manager
    if _risk_profile_manager is None:
        _risk_profile_manager = RiskProfileManager()
    return _risk_profile_manager

def apply_risk_profile_to_new_entry(symbol: str, side: str, available_balance: float) -> Dict[str, Any]:
    """
    Apply current risk profile to a new entry
    Returns calculated position size and risk parameters
    """
    try:
        manager = get_risk_profile_manager()
        
        # Calculate position size based on available balance and profile
        pos_size_pct = manager.get_pos_size_pct()
        position_size = available_balance * (pos_size_pct / 100.0)
        
        return {
            "symbol": symbol,
            "side": side,
            "position_size": position_size,
            "pos_size_pct": pos_size_pct,
            "max_concurrent": manager.get_max_concurrent(),
            "daily_max_loss_pct": manager.get_daily_max_loss_pct(),
            "slippage_bps": manager.get_slippage_bps(),
            "cooldown_min": manager.get_cooldown_min(),
            "profile_name": manager.get_current_profile()
        }
        
    except Exception as e:
        logger.error(f"Failed to apply risk profile to new entry: {e}")
        # Return conservative defaults
        return {
            "symbol": symbol,
            "side": side,
            "position_size": available_balance * 0.005,  # 0.5% default
            "pos_size_pct": 0.5,
            "max_concurrent": 3,
            "daily_max_loss_pct": 1.0,
            "slippage_bps": 15,
            "cooldown_min": 60,
            "profile_name": "conservative"
        }
