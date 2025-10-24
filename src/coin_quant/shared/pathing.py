#!/usr/bin/env python3
"""
Robust Path Resolution for Coin Quant R11

Provides consistent path resolution independent of working directory.
All paths are resolved relative to project root with environment overrides.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any


def get_project_root() -> Path:
    """
    Walk upward from current file until finding pyproject.toml or src/coin_quant.
    Returns the project root directory.
    """
    current_path = Path(__file__).resolve().parent
    
    # Check current directory and parent directories
    for path in [current_path] + list(current_path.parents):
        if (path / "pyproject.toml").exists() or (path / "src" / "coin_quant").exists():
            return path
    
    # Fallback to current directory
    return current_path


@dataclass
class Paths:
    """Centralized path configuration with environment overrides"""
    
    def __init__(self):
        # Get project root (can be overridden by env)
        project_root = os.getenv("COIN_QUANT_ROOT")
        if project_root:
            self.project_root = Path(project_root).resolve()
        else:
            self.project_root = get_project_root()
        
        # Base directories
        self.shared_data = self._get_path("SHARED_DATA_DIR", self.project_root / "shared_data")
        self.health_dir = self._get_path("HEALTH_DIR", self.shared_data / "health")
        self.logs_dir = self._get_path("LOGS_DIR", self.shared_data / "logs")
        self.memory_dir = self._get_path("MEMORY_DIR", self.shared_data / "memory")
        self.snapshots_dir = self._get_path("SNAPSHOTS_DIR", self.shared_data / "snapshots")
        self.signals_dir = self._get_path("SIGNALS_DIR", self.shared_data / "signals")
        self.prices_dir = self._get_path("PRICES_DIR", self.shared_data / "prices")
        
        # Specific files
        self.databus_snapshot = self._get_path("DATABUS_SNAPSHOT", self.shared_data / "databus_snapshot.json")
        self.account_snapshot = self._get_path("ACCOUNT_SNAPSHOT", self.shared_data / "account_snapshot.json")
        self.account_info = self._get_path("ACCOUNT_INFO", self.shared_data / "account_info.json")
        self.positions_file = self._get_path("POSITIONS_FILE", self.shared_data / "positions_snapshot.json")
        self.auto_trading_state = self._get_path("AUTO_TRADING_STATE", self.shared_data / "auto_trading_state.json")
        self.ssot_env_file = self._get_path("SSOT_ENV_FILE", self.shared_data / "ssot" / "env.json")
        self.coin_watchlist = self._get_path("COIN_WATCHLIST", self.shared_data / "coin_watchlist.json")
        
        # ARES specific
        self.ares_dir = self._get_path("ARES_DIR", self.shared_data / "ares")
        self.ares_signals = self._get_path("ARES_SIGNALS", self.shared_data / "ares_signals.json")
        
        # Health files
        self.health_file = self.health_dir / "health.json"
        self.feeder_health = self.health_dir / "feeder_health.json"
        self.ares_health = self.health_dir / "ares_health.json"
        self.trader_health = self.health_dir / "trader_health.json"
        self.memory_health = self.health_dir / "memory_health.json"
    
    def _get_path(self, env_key: str, default_path: Path) -> Path:
        """Get path from environment variable or use default"""
        env_value = os.getenv(env_key)
        if env_value:
            return Path(env_value).resolve()
        return default_path
    
    def to_jsonable(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Path objects to strings for JSON serialization"""
        def convert_paths(obj):
            if isinstance(obj, Path):
                return str(obj)
            elif isinstance(obj, dict):
                return {k: convert_paths(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_paths(item) for item in obj]
            else:
                return obj
        
        return convert_paths(data)
    
    def ensure_directories(self):
        """Create all necessary directories"""
        directories = [
            self.shared_data,
            self.health_dir,
            self.logs_dir,
            self.memory_dir,
            self.snapshots_dir,
            self.signals_dir,
            self.prices_dir,
            self.ares_dir,
            self.ssot_env_file.parent
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
    
    def get_symbol_snapshot_path(self, symbol: str) -> Path:
        """Get snapshot file path for a specific symbol"""
        symbol_lower = symbol.lower()
        return self.snapshots_dir / f"prices_{symbol_lower}.json"
    
    def get_symbol_positions_path(self, symbol: str) -> Path:
        """Get positions file path for a specific symbol"""
        symbol_lower = symbol.lower()
        return self.shared_data / f"positions_{symbol_lower}.json"


# Global paths instance
paths = Paths()


def get_paths() -> Paths:
    """Get the global paths instance"""
    return paths
