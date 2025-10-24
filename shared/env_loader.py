"""
Environment SSOT (Single Source of Truth) & Drift Detection
Loads config.env and .env, provides stable ENV_HASH for service validation
"""
import os
import sys
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional, Union
from .path_registry import get_absolute_path


class EnvironmentLoader:
    """Centralized environment loader with drift detection"""
    
    _instance: Optional['EnvironmentLoader'] = None
    _env_hash: Optional[str] = None
    _loaded_env: Optional[Dict[str, str]] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._loaded_env is not None:
            return  # Already initialized
            
        self._load_environment()
        self._compute_hash()
    
    def _load_environment(self):
        """Load environment from config files"""
        self._loaded_env = {}
        
        # Priority order: .env (highest) -> config.env (lower)
        config_files = [
            get_absolute_path('config') / '.env',
            get_absolute_path('config') / 'config.env',
            Path.cwd() / '.env',
            get_absolute_path('repo_root') / 'config.env'
        ]
        
        # Load each config file (later files override earlier ones)
        for config_file in config_files:
            if config_file.exists():
                try:
                    self._load_env_file(config_file)
                except Exception as e:
                    print(f"Warning: Failed to load {config_file}: {e}")
        
        # Override with actual environment variables
        for key, value in os.environ.items():
            if key.startswith(('KIS_', 'BINANCE_', 'TRADER_', 'FEEDER_', 'ARES_', 'AUTO_')):
                self._loaded_env[key] = value
    
    def _load_env_file(self, file_path: Path):
        """Load environment variables from a file"""
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                
                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue
                
                # Parse KEY=VALUE
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # Remove quotes if present
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]
                    
                    self._loaded_env[key] = value
                else:
                    print(f"Warning: Invalid line {line_num} in {file_path}: {line}")
    
    def _compute_hash(self):
        """Compute stable hash of environment variables"""
        # Sort keys for consistent hash
        sorted_items = sorted(self._loaded_env.items())
        
        # Create hash string
        hash_string = '\n'.join(f"{key}={value}" for key, value in sorted_items)
        
        # Compute SHA-256 hash
        self._env_hash = hashlib.sha256(hash_string.encode('utf-8')).hexdigest()
    
    def get_env(self, key: str, default: Any = None, cast_type: type = str) -> Any:
        """Get environment variable with type casting"""
        value = self._loaded_env.get(key, default)
        
        if value is None:
            return None
        
        try:
            if cast_type == bool:
                return str(value).lower() in ('true', '1', 'yes', 'on')
            elif cast_type == int:
                return int(value)
            elif cast_type == float:
                return float(value)
            else:
                return str(value)
        except (ValueError, TypeError):
            print(f"Warning: Failed to cast {key}={value} to {cast_type.__name__}")
            return default
    
    def get_env_hash(self) -> str:
        """Get stable environment hash"""
        return self._env_hash
    
    def get_all_env(self) -> Dict[str, str]:
        """Get all loaded environment variables"""
        return self._loaded_env.copy()
    
    def validate_required_keys(self, required_keys: list[str]) -> list[str]:
        """Validate that required keys are present"""
        missing_keys = []
        for key in required_keys:
            if key not in self._loaded_env or not self._loaded_env[key]:
                missing_keys.append(key)
        return missing_keys
    
    def fail_fast_if_missing(self, required_keys: list[str]):
        """Fail fast if required keys are missing"""
        missing = self.validate_required_keys(required_keys)
        if missing:
            raise RuntimeError(
                f"REQUIRED_ENV_MISSING: Missing required environment variables: {', '.join(missing)}"
            )


# Global instance
_env_loader = EnvironmentLoader()


def get_env(key: str, default: Any = None, cast_type: type = str) -> Any:
    """Get environment variable with type casting"""
    return _env_loader.get_env(key, default, cast_type)


def get_env_hash() -> str:
    """Get stable environment hash for service validation"""
    return _env_loader.get_env_hash()


def get_all_env() -> Dict[str, str]:
    """Get all environment variables"""
    return _env_loader.get_all_env()


def validate_required_env(required_keys: list[str]) -> list[str]:
    """Validate required environment variables"""
    return _env_loader.validate_required_keys(required_keys)


def fail_fast_if_missing(required_keys: list[str]):
    """Fail fast if required environment variables are missing"""
    _env_loader.fail_fast_if_missing(required_keys)


# Service-specific environment validation
def validate_feeder_env():
    """Validate Feeder service environment"""
    required = ['BINANCE_API_KEY', 'BINANCE_API_SECRET']
    fail_fast_if_missing(required)


def validate_trader_env():
    """Validate Trader service environment"""
    required = ['BINANCE_API_KEY', 'BINANCE_API_SECRET', 'TRADING_MODE']
    fail_fast_if_missing(required)


def validate_kis_env():
    """Validate KIS API environment"""
    required = ['KIS_APPKEY', 'KIS_APPSECRET', 'KIS_ACCOUNT']
    fail_fast_if_missing(required)


if __name__ == '__main__':
    # Test environment loading
    print("Environment Loader Test:")
    print(f"ENV_HASH: {get_env_hash()}")
    print(f"Loaded keys: {list(get_all_env().keys())}")
    
    # Test type casting
    print(f"TESTNET mode: {get_env('TESTNET', 'false', bool)}")
    print(f"Refresh seconds: {get_env('AUTO_REFRESH_SEC', '5', int)}")
