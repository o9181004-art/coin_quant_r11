"""
Configuration Management for Coin Quant R11

Single Source of Truth (SSOT) for all configuration.
Load precedence: environment variables → shared_data/ssot/env.json → defaults.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Union
from coin_quant.shared.paths import get_data_dir


class ConfigManager:
    """Centralized configuration management with validation"""
    
    def __init__(self):
        self.data_dir = get_data_dir()
        self.ssot_file = self.data_dir / "ssot" / "env.json"
        self._config_cache: Optional[Dict[str, Any]] = None
        self._validation_errors: list[str] = []
        
        # Ensure SSOT directory exists
        self.ssot_file.parent.mkdir(parents=True, exist_ok=True)
    
    def _load_defaults(self) -> Dict[str, Any]:
        """Load default configuration values"""
        return {
            # API Configuration
            "BINANCE_API_KEY": "",
            "BINANCE_API_SECRET": "",
            "BINANCE_USE_TESTNET": True,
            
            # Trading Configuration
            "TRADING_MODE": "testnet",
            "SIMULATION_MODE": True,
            "PAPER_MODE": False,
            "LIVE_TRADING_ENABLED": False,
            
            # Signal Configuration
            "TEST_ALLOW_DEFAULT_SIGNAL": False,
            "ARES_FRESHNESS_THRESHOLD": 10.0,
            "ARES_HEARTBEAT_INTERVAL": 30.0,
            
            # Service Configuration
            "FEEDER_HEARTBEAT_INTERVAL": 5.0,
            "TRADER_ORDER_COOLDOWN": 1.0,
            "TRADER_BALANCE_CHECK_INTERVAL": 30.0,
            
            # Paths
            "SHARED_DATA_DIR": str(self.data_dir),
            "HEALTH_DIR": str(self.data_dir / "health"),
            "MEMORY_DIR": str(self.data_dir / "memory"),
            "LOGS_DIR": str(self.data_dir / "logs"),
            
            # Safety Flags
            "DISABLE_ORDER_GUARDRAILS": False,
            "DISABLE_HEALTH_CHECKS": False,
            "ENABLE_DEBUG_TRACING": False,
            
            # Memory Layer
            "MEMORY_INTEGRITY_CHECK_INTERVAL": 300.0,
            "MEMORY_SNAPSHOT_INTERVAL": 60.0,
            
            # Logging
            "LOG_LEVEL": "INFO",
            "LOG_ROTATION_SIZE": "10MB",
            "LOG_RETENTION_DAYS": 7,
        }
    
    def _load_ssot_file(self) -> Dict[str, Any]:
        """Load configuration from SSOT file"""
        if not self.ssot_file.exists():
            return {}
        
        try:
            with open(self.ssot_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Failed to load SSOT config file: {e}")
            return {}
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration with proper precedence"""
        if self._config_cache is not None:
            return self._config_cache
        
        # Start with defaults
        config = self._load_defaults()
        
        # Override with SSOT file
        ssot_config = self._load_ssot_file()
        config.update(ssot_config)
        
        # Override with environment variables
        for key in config.keys():
            env_value = os.environ.get(key)
            if env_value is not None:
                # Type conversion based on default value type
                default_value = self._load_defaults()[key]
                if isinstance(default_value, bool):
                    config[key] = env_value.lower() in ('true', '1', 'yes', 'on')
                elif isinstance(default_value, int):
                    try:
                        config[key] = int(env_value)
                    except ValueError:
                        config[key] = env_value
                elif isinstance(default_value, float):
                    try:
                        config[key] = float(env_value)
                    except ValueError:
                        config[key] = env_value
                else:
                    config[key] = env_value
        
        self._config_cache = config
        return config
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        config = self._load_config()
        return config.get(key, default)
    
    def get_string(self, key: str, default: str = "") -> str:
        """Get string configuration value"""
        return str(self.get(key, default))
    
    def get_bool(self, key: str, default: bool = False) -> bool:
        """Get boolean configuration value"""
        value = self.get(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ('true', '1', 'yes', 'on')
        return bool(value)
    
    def get_int(self, key: str, default: int = 0) -> int:
        """Get integer configuration value"""
        value = self.get(key, default)
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
    
    def get_float(self, key: str, default: float = 0.0) -> float:
        """Get float configuration value"""
        value = self.get(key, default)
        try:
            return float(value)
        except (ValueError, TypeError):
            return default
    
    def get_list(self, key: str, default: list = None) -> list:
        """Get list configuration value"""
        if default is None:
            default = []
        value = self.get(key, default)
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            # Split comma-separated string
            return [item.strip() for item in value.split(',') if item.strip()]
        return default
    
    def validate_config(self) -> bool:
        """Validate configuration and return True if valid"""
        self._validation_errors = []
        config = self._load_config()
        
        # Required fields validation
        required_fields = {
            "BINANCE_API_KEY": "Binance API Key is required",
            "BINANCE_API_SECRET": "Binance API Secret is required",
        }
        
        for field, message in required_fields.items():
            if not config.get(field):
                self._validation_errors.append(message)
        
        # Safety validation
        if not config.get("SIMULATION_MODE") and not config.get("PAPER_MODE"):
            if not config.get("LIVE_TRADING_ENABLED"):
                self._validation_errors.append(
                    "Live trading is disabled but simulation/paper mode is also disabled. "
                    "Enable SIMULATION_MODE=true or PAPER_MODE=true for safety."
                )
        
        # Signal safety validation
        if config.get("TEST_ALLOW_DEFAULT_SIGNAL") and not config.get("SIMULATION_MODE"):
            self._validation_errors.append(
                "TEST_ALLOW_DEFAULT_SIGNAL should only be enabled in simulation mode"
            )
        
        return len(self._validation_errors) == 0
    
    def get_validation_errors(self) -> list[str]:
        """Get list of validation errors"""
        return self._validation_errors.copy()
    
    def print_config_banner(self):
        """Print configuration banner with key settings"""
        config = self._load_config()
        
        print("=" * 60)
        print("Coin Quant R11 Configuration")
        print("=" * 60)
        print(f"Trading Mode: {config.get('TRADING_MODE', 'unknown')}")
        print(f"Simulation Mode: {config.get('SIMULATION_MODE', False)}")
        print(f"Paper Mode: {config.get('PAPER_MODE', False)}")
        print(f"Live Trading: {config.get('LIVE_TRADING_ENABLED', False)}")
        print(f"Default Signals: {config.get('TEST_ALLOW_DEFAULT_SIGNAL', False)}")
        print(f"Testnet: {config.get('BINANCE_USE_TESTNET', True)}")
        print(f"Data Directory: {config.get('SHARED_DATA_DIR', 'unknown')}")
        print(f"Debug Tracing: {config.get('ENABLE_DEBUG_TRACING', False)}")
        print("=" * 60)
    
    def print_validation_banner(self):
        """Print validation errors and exit if invalid"""
        if not self.validate_config():
            print("=" * 60)
            print("CONFIGURATION VALIDATION FAILED")
            print("=" * 60)
            for error in self._validation_errors:
                print(f"❌ {error}")
            print("=" * 60)
            print("Please fix the configuration errors above and try again.")
            print("=" * 60)
            sys.exit(1)
        
        print("✅ Configuration validation passed")
    
    def save_ssot_config(self, config: Dict[str, Any]) -> bool:
        """Save configuration to SSOT file"""
        try:
            with open(self.ssot_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            return True
        except IOError as e:
            print(f"Failed to save SSOT config: {e}")
            return False
    
    def get_feeder_config(self) -> Dict[str, Any]:
        """Get feeder-specific configuration"""
        config = self._load_config()
        return {
            "heartbeat_interval": config.get("FEEDER_HEARTBEAT_INTERVAL", 5.0),
            "symbols": config.get("FEEDER_SYMBOLS", []),
            "quote": config.get("FEEDER_QUOTE", "USDT"),
            "top_n": config.get("FEEDER_TOP_N", 40),
        }
    
    def get_ares_config(self) -> Dict[str, Any]:
        """Get ARES-specific configuration"""
        config = self._load_config()
        return {
            "freshness_threshold": config.get("ARES_FRESHNESS_THRESHOLD", 10.0),
            "heartbeat_interval": config.get("ARES_HEARTBEAT_INTERVAL", 30.0),
            "allow_default_signals": config.get("TEST_ALLOW_DEFAULT_SIGNAL", False),
            "max_symbols": config.get("ARES_MAX_SYMBOLS", 40),
            "signal_interval": config.get("ARES_SIGNAL_INTERVAL", 30),
        }
    
    def get_trader_config(self) -> Dict[str, Any]:
        """Get trader-specific configuration"""
        config = self._load_config()
        return {
            "order_cooldown": config.get("TRADER_ORDER_COOLDOWN", 1.0),
            "balance_check_interval": config.get("TRADER_BALANCE_CHECK_INTERVAL", 30.0),
            "disable_guardrails": config.get("DISABLE_ORDER_GUARDRAILS", False),
            "allow_without_uds": config.get("DISABLE_HEALTH_CHECKS", False),
        }
    
    def get_trading_config(self) -> Dict[str, Any]:
        """Get trading-specific configuration"""
        config = self._load_config()
        return {
            "mode": config.get("TRADING_MODE", "testnet"),
            "simulation": config.get("SIMULATION_MODE", True),
            "paper_mode": config.get("PAPER_MODE", False),
            "auto_trading": config.get("LIVE_TRADING_ENABLED", False),
            "default_symbol": config.get("DEFAULT_SYMBOL", "BTCUSDT"),
            "risk_profile": config.get("RISK_PROFILE", "conservative"),
            "disable_guardrails": config.get("DISABLE_ORDER_GUARDRAILS", False),
        }
    
    def get_cached(self, key: str) -> Any:
        """Get cached configuration value"""
        if self._config_cache is None:
            self._config_cache = self._load_config()
        return self._config_cache.get(key)
    
    def get_config_summary(self) -> Dict[str, Any]:
        """Get configuration summary for startup banners"""
        config = self._load_config()
        return {
            "config_hash": self._get_config_hash(config),
            "required_fields": self._get_required_fields(),
            "validation_errors": self._validation_errors.copy(),
            "ssot_file": str(self.ssot_file),
            "data_dir": str(self.data_dir)
        }


# Global configuration manager instance
config_manager = ConfigManager()