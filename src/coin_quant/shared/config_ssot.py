#!/usr/bin/env python3
"""
Configuration SSOT (Single Source of Truth) for Coin Quant R11

Authoritative configuration management with strict validation and precedence rules.
Provides centralized config access with environment variable override support.
"""

import os
import json
import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union, List
from dataclasses import dataclass
from dotenv import load_dotenv

from coin_quant.shared.io import AtomicWriter, AtomicReader
from coin_quant.shared.paths import get_data_dir

logger = logging.getLogger(__name__)


@dataclass
class ConfigValidationError(Exception):
    """Configuration validation error"""
    field: str
    message: str
    remediation: str


class ConfigSSOT:
    """Single Source of Truth configuration manager"""
    
    def __init__(self, config_file: Optional[Path] = None):
        self.config_file = config_file or get_data_dir() / "ssot" / "env.json"
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        self.writer = AtomicWriter()
        self.reader = AtomicReader()
        
        # Load configuration with precedence
        self._config_cache: Dict[str, Any] = {}
        self._config_hash: Optional[str] = None
        self._load_configuration()
        
        logger.info(f"ConfigSSOT initialized: {self.config_file}")
    
    def _load_configuration(self) -> None:
        """Load configuration with precedence: env vars > file > defaults"""
        # 1. Load defaults
        defaults = self._get_default_config()
        
        # 2. Load from file
        file_config = self.reader.read_json(self.config_file, default={})
        
        # 3. Load environment variables
        env_config = self._load_env_vars()
        
        # 4. Merge with precedence: env > file > defaults
        self._config_cache = {**defaults, **file_config, **env_config}
        
        # 5. Generate config hash for reproducibility
        self._config_hash = self._generate_config_hash()
        
        logger.debug(f"Configuration loaded: {len(self._config_cache)} keys, hash: {self._config_hash[:8]}")
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration values"""
        return {
            # Trading Configuration
            "TRADING_MODE": "testnet",
            "SIMULATION_MODE": True,
            "PAPER_MODE": False,
            "LIVE_TRADING_ENABLED": False,
            "AUTO_TRADING_ENABLED": False,
            "TEST_ALLOW_DEFAULT_SIGNAL": False,  # CRITICAL: Default OFF
            
            # Binance Configuration
            "BINANCE_USE_TESTNET": True,
            "BINANCE_API_KEY": "",
            "BINANCE_API_SECRET": "",
            
            # Service Configuration
            "ARES_FRESHNESS_THRESHOLD": 10.0,
            "FEEDER_HEARTBEAT_INTERVAL": 5.0,
            "TRADER_ORDER_COOLDOWN": 1.0,
            "DISABLE_ORDER_GUARDRAILS": False,
            "ALLOW_TRADES_WITHOUT_UDS": False,
            
            # Symbol Configuration
            "SYMBOL": "BTCUSDT",
            "KLINE_INTERVAL": "1m",
            "FEEDER_QUOTE": "USDT",
            "UNIVERSE_TOP_N": 40,
            "MAX_SYMBOLS": 40,
            
            # Risk Management
            "DRY_RUN": True,
            "RISK_PROFILE": "conservative",
            
            # Logging Configuration
            "LOG_LEVEL": "INFO",
            "LOG_TO_FILE": True,
            "ENABLE_DEBUG_TRACING": False,
            
            # Data Directory
            "COIN_QUANT_DATA_DIR": "./shared_data"
        }
    
    def _load_env_vars(self) -> Dict[str, Any]:
        """Load environment variables"""
        env_config = {}
        
        # Load from .env file if exists
        env_file = Path(".env")
        if env_file.exists():
            load_dotenv(env_file)
        
        # Load from config.env if exists
        config_env = Path("config.env")
        if config_env.exists():
            load_dotenv(config_env)
        
        # Map environment variables
        env_mapping = {
            "TRADING_MODE": "TRADING_MODE",
            "SIMULATION_MODE": "SIMULATION_MODE",
            "PAPER_MODE": "PAPER_MODE",
            "LIVE_TRADING_ENABLED": "LIVE_TRADING_ENABLED",
            "AUTO_TRADING_ENABLED": "AUTO_TRADING_ENABLED",
            "TEST_ALLOW_DEFAULT_SIGNAL": "TEST_ALLOW_DEFAULT_SIGNAL",
            "BINANCE_USE_TESTNET": "BINANCE_USE_TESTNET",
            "BINANCE_API_KEY": "BINANCE_API_KEY",
            "BINANCE_API_SECRET": "BINANCE_API_SECRET",
            "ARES_FRESHNESS_THRESHOLD": "ARES_FRESHNESS_THRESHOLD",
            "FEEDER_HEARTBEAT_INTERVAL": "FEEDER_HEARTBEAT_INTERVAL",
            "TRADER_ORDER_COOLDOWN": "TRADER_ORDER_COOLDOWN",
            "DISABLE_ORDER_GUARDRAILS": "DISABLE_ORDER_GUARDRAILS",
            "ALLOW_TRADES_WITHOUT_UDS": "ALLOW_TRADES_WITHOUT_UDS",
            "SYMBOL": "SYMBOL",
            "KLINE_INTERVAL": "KLINE_INTERVAL",
            "FEEDER_QUOTE": "FEEDER_QUOTE",
            "UNIVERSE_TOP_N": "UNIVERSE_TOP_N",
            "MAX_SYMBOLS": "MAX_SYMBOLS",
            "DRY_RUN": "DRY_RUN",
            "RISK_PROFILE": "RISK_PROFILE",
            "LOG_LEVEL": "LOG_LEVEL",
            "LOG_TO_FILE": "LOG_TO_FILE",
            "ENABLE_DEBUG_TRACING": "ENABLE_DEBUG_TRACING",
            "COIN_QUANT_DATA_DIR": "COIN_QUANT_DATA_DIR"
        }
        
        for key, env_var in env_mapping.items():
            value = os.environ.get(env_var)
            if value is not None:
                # Convert string values to appropriate types
                env_config[key] = self._convert_value(value)
        
        return env_config
    
    def _convert_value(self, value: str) -> Any:
        """Convert string value to appropriate type"""
        if value.lower() in ("true", "false"):
            return value.lower() == "true"
        
        try:
            # Try integer
            if "." not in value:
                return int(value)
        except ValueError:
            pass
        
        try:
            # Try float
            return float(value)
        except ValueError:
            pass
        
        # Return as string
        return value
    
    def _generate_config_hash(self) -> str:
        """Generate configuration hash for reproducibility"""
        # Create deterministic config representation
        config_str = json.dumps(self._config_cache, sort_keys=True)
        return hashlib.sha256(config_str.encode()).hexdigest()
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        return self._config_cache.get(key, default)
    
    def get_bool(self, key: str, default: bool = False) -> bool:
        """Get boolean configuration value"""
        value = self.get(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes", "on")
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
    
    def get_list(self, key: str, default: Optional[List] = None, separator: str = ",") -> List:
        """Get list configuration value"""
        if default is None:
            default = []
        
        value = self.get(key)
        if not value:
            return default
        
        if isinstance(value, list):
            return value
        
        return [item.strip() for item in str(value).split(separator) if item.strip()]
    
    def validate_configuration(self) -> List[ConfigValidationError]:
        """Validate configuration and return errors"""
        errors = []
        
        # Required fields validation
        required_fields = {
            "BINANCE_API_KEY": "Binance API key is required for trading",
            "BINANCE_API_SECRET": "Binance API secret is required for trading"
        }
        
        for field, message in required_fields.items():
            if not self.get(field):
                errors.append(ConfigValidationError(
                    field=field,
                    message=message,
                    remediation=f"Set {field} environment variable or add to {self.config_file}"
                ))
        
        # Consistency validation
        if self.get_bool("LIVE_TRADING_ENABLED") and not self.get_bool("BINANCE_USE_TESTNET"):
            errors.append(ConfigValidationError(
                field="BINANCE_USE_TESTNET",
                message="Live trading requires testnet mode for safety",
                remediation="Set BINANCE_USE_TESTNET=true or disable LIVE_TRADING_ENABLED"
            ))
        
        if self.get_bool("TEST_ALLOW_DEFAULT_SIGNAL") and self.get_bool("LIVE_TRADING_ENABLED"):
            errors.append(ConfigValidationError(
                field="TEST_ALLOW_DEFAULT_SIGNAL",
                message="Default signals are dangerous in live trading",
                remediation="Set TEST_ALLOW_DEFAULT_SIGNAL=false for live trading"
            ))
        
        # Threshold validation
        freshness_threshold = self.get_float("ARES_FRESHNESS_THRESHOLD")
        if freshness_threshold <= 0 or freshness_threshold > 300:
            errors.append(ConfigValidationError(
                field="ARES_FRESHNESS_THRESHOLD",
                message="Freshness threshold must be between 0 and 300 seconds",
                remediation="Set ARES_FRESHNESS_THRESHOLD to a reasonable value (e.g., 10.0)"
            ))
        
        return errors
    
    def save_configuration(self) -> bool:
        """Save current configuration to file"""
        return self.writer.write_json(self.config_file, self._config_cache)
    
    def reload_configuration(self) -> None:
        """Reload configuration from sources"""
        self._load_configuration()
        logger.info("Configuration reloaded")
    
    def get_config_summary(self) -> Dict[str, Any]:
        """Get configuration summary for startup banner"""
        return {
            "config_hash": self._config_hash,
            "required_fields": ["BINANCE_API_KEY", "BINANCE_API_SECRET", "TRADING_MODE"],
            "trading_mode": self.get("TRADING_MODE"),
            "simulation_mode": self.get_bool("SIMULATION_MODE"),
            "live_trading": self.get_bool("LIVE_TRADING_ENABLED"),
            "testnet": self.get_bool("BINANCE_USE_TESTNET"),
            "default_signals": self.get_bool("TEST_ALLOW_DEFAULT_SIGNAL"),
            "data_dir": self.get("COIN_QUANT_DATA_DIR"),
            "log_level": self.get("LOG_LEVEL"),
            "freshness_threshold": self.get_float("ARES_FRESHNESS_THRESHOLD"),
            "max_symbols": self.get_int("MAX_SYMBOLS")
        }
    
    def get_binance_config(self) -> Dict[str, str]:
        """Get Binance API configuration"""
        return {
            "api_key": self.get("BINANCE_API_KEY", ""),
            "api_secret": self.get("BINANCE_API_SECRET", ""),
            "use_testnet": str(self.get_bool("BINANCE_USE_TESTNET"))
        }
    
    def get_trading_config(self) -> Dict[str, Any]:
        """Get trading configuration"""
        return {
            "mode": self.get("TRADING_MODE"),
            "simulation": self.get_bool("SIMULATION_MODE"),
            "paper_mode": self.get_bool("PAPER_MODE"),
            "live_trading": self.get_bool("LIVE_TRADING_ENABLED"),
            "auto_trading": self.get_bool("AUTO_TRADING_ENABLED"),
            "default_signals": self.get_bool("TEST_ALLOW_DEFAULT_SIGNAL"),
            "symbol": self.get("SYMBOL"),
            "risk_profile": self.get("RISK_PROFILE"),
            "disable_guardrails": self.get_bool("DISABLE_ORDER_GUARDRAILS")
        }
    
    def get_service_config(self) -> Dict[str, Any]:
        """Get service configuration"""
        return {
            "ares_freshness_threshold": self.get_float("ARES_FRESHNESS_THRESHOLD"),
            "feeder_heartbeat_interval": self.get_float("FEEDER_HEARTBEAT_INTERVAL"),
            "trader_order_cooldown": self.get_float("TRADER_ORDER_COOLDOWN"),
            "max_symbols": self.get_int("MAX_SYMBOLS"),
            "universe_top_n": self.get_int("UNIVERSE_TOP_N"),
            "feeder_quote": self.get("FEEDER_QUOTE"),
            "kline_interval": self.get("KLINE_INTERVAL")
        }


def validate_and_exit_on_error(config: ConfigSSOT) -> None:
    """Validate configuration and exit with error banner if invalid"""
    errors = config.validate_configuration()
    
    if errors:
        print("\n" + "="*80)
        print("CONFIGURATION VALIDATION FAILED")
        print("="*80)
        
        for error in errors:
            print(f"\n❌ {error.field}: {error.message}")
            print(f"   💡 {error.remediation}")
        
        print(f"\n📁 Configuration file: {config.config_file}")
        print(f"🔑 Environment variables take precedence over file values")
        print("\n" + "="*80)
        
        exit(1)


def print_startup_banner(service_name: str, config: ConfigSSOT) -> None:
    """Print standardized startup banner"""
    summary = config.get_config_summary()
    
    print("\n" + "="*80)
    print(f"🚀 {service_name.upper()} SERVICE STARTING")
    print("="*80)
    print(f"📦 Package Version: 1.0.0-rc1")
    print(f"🐍 Python Version: {os.sys.version.split()[0]}")
    print(f"🔑 Config Hash: {summary['config_hash'][:12]}...")
    print(f"📁 Data Directory: {summary['data_dir']}")
    print(f"🎯 Trading Mode: {summary['trading_mode']}")
    print(f"🧪 Simulation: {summary['simulation_mode']}")
    print(f"🌐 Testnet: {summary['testnet']}")
    print(f"⚠️  Default Signals: {summary['default_signals']}")
    print(f"📊 Max Symbols: {summary['max_symbols']}")
    print(f"⏱️  Freshness Threshold: {summary['freshness_threshold']}s")
    print(f"📝 Log Level: {summary['log_level']}")
    print("="*80 + "\n")


# Global configuration instance
config_ssot = ConfigSSOT()


def get_config() -> ConfigSSOT:
    """Get global configuration instance"""
    return config_ssot
