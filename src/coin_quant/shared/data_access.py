#!/usr/bin/env python3
"""
Data Access Layer for Coin Quant R11

Provides a unified interface for accessing data from different backends (file, HTTP).
Handles missing data gracefully and normalizes data formats.
"""

import json
import logging
import os
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol
from datetime import datetime, timedelta

from .pathing import get_paths

logger = logging.getLogger(__name__)


class PriceSnapshotRepo(Protocol):
    """Protocol for price snapshot data access"""
    
    def get_latest(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get latest price snapshot for symbol"""
        ...
    
    def get_age_seconds(self, symbol: str) -> Optional[float]:
        """Get age of latest snapshot in seconds"""
        ...


class SignalRepo(Protocol):
    """Protocol for signal data access"""
    
    def get_latest(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get latest signal for symbol"""
        ...
    
    def get_age_seconds(self, symbol: str) -> Optional[float]:
        """Get age of latest signal in seconds"""
        ...


class PositionRepo(Protocol):
    """Protocol for position data access"""
    
    def get_all(self) -> Dict[str, Dict[str, Any]]:
        """Get all positions"""
        ...
    
    def get_by_symbol(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get position for specific symbol"""
        ...


class HealthRepo(Protocol):
    """Protocol for health data access"""
    
    def get_component_status(self, name: str) -> Optional[Dict[str, Any]]:
        """Get health status for component"""
        ...
    
    def get_all(self) -> Dict[str, Any]:
        """Get all health data"""
        ...


class MetricsRepo(Protocol):
    """Protocol for metrics data access"""
    
    def get(self) -> Dict[str, Any]:
        """Get metrics data"""
        ...


class FileBackend:
    """File-based data backend"""
    
    def __init__(self):
        self.paths = get_paths()
        self.paths.ensure_directories()
    
    def _safe_read_json(self, file_path: Path, default: Any = None) -> Any:
        """Safely read JSON file with error handling"""
        try:
            if not file_path.exists():
                return default
            
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError, OSError) as e:
            logger.warning(f"Failed to read {file_path}: {e}")
            return default
    
    def _get_file_age_seconds(self, file_path: Path) -> Optional[float]:
        """Get file age in seconds"""
        try:
            if not file_path.exists():
                return None
            
            mtime = file_path.stat().st_mtime
            return time.time() - mtime
        except OSError:
            return None


class FilePriceSnapshotRepo(FileBackend, PriceSnapshotRepo):
    """File-based price snapshot repository"""
    
    def get_latest(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get latest price snapshot for symbol"""
        snapshot_path = self.paths.get_symbol_snapshot_path(symbol)
        data = self._safe_read_json(snapshot_path)
        
        if data and isinstance(data, dict):
            # Normalize data structure
            return {
                "symbol": data.get("symbol", symbol),
                "price": data.get("price", data.get("last_price", 0.0)),
                "timestamp": data.get("timestamp", data.get("last_update", 0)),
                "volume": data.get("volume", 0.0),
                "change_24h": data.get("change_24h", 0.0)
            }
        return None
    
    def get_age_seconds(self, symbol: str) -> Optional[float]:
        """Get age of latest snapshot in seconds"""
        snapshot_path = self.paths.get_symbol_snapshot_path(symbol)
        return self._get_file_age_seconds(snapshot_path)


class FileSignalRepo(FileBackend, SignalRepo):
    """File-based signal repository"""
    
    def get_latest(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get latest signal for symbol"""
        # Check ARES signals file first
        signals_data = self._safe_read_json(self.paths.ares_signals)
        if signals_data and isinstance(signals_data, dict):
            symbol_signals = signals_data.get(symbol, {})
            if symbol_signals:
                return {
                    "symbol": symbol,
                    "signal": symbol_signals.get("signal", "HOLD"),
                    "confidence": symbol_signals.get("confidence", 0.0),
                    "timestamp": symbol_signals.get("timestamp", 0),
                    "reason": symbol_signals.get("reason", "")
                }
        
        # Fallback to individual ARES files
        ares_files = list(self.paths.ares_dir.glob("*.json"))
        for signal_file in ares_files:
            data = self._safe_read_json(signal_file)
            if data and isinstance(data, dict) and data.get("symbol") == symbol:
                return {
                    "symbol": symbol,
                    "signal": data.get("signal", "HOLD"),
                    "confidence": data.get("confidence", 0.0),
                    "timestamp": data.get("timestamp", 0),
                    "reason": data.get("reason", "")
                }
        
        return None
    
    def get_age_seconds(self, symbol: str) -> Optional[float]:
        """Get age of latest signal in seconds"""
        # Check ARES signals file first
        if self.paths.ares_signals.exists():
            signals_data = self._safe_read_json(self.paths.ares_signals)
            if signals_data and isinstance(signals_data, dict):
                symbol_signals = signals_data.get(symbol, {})
                if symbol_signals and "timestamp" in symbol_signals:
                    return time.time() - symbol_signals["timestamp"]
        
        # Fallback to individual files
        ares_files = list(self.paths.ares_dir.glob("*.json"))
        latest_time = 0
        for signal_file in ares_files:
            data = self._safe_read_json(signal_file)
            if data and isinstance(data, dict) and data.get("symbol") == symbol:
                timestamp = data.get("timestamp", 0)
                if timestamp > latest_time:
                    latest_time = timestamp
        
        if latest_time > 0:
            return time.time() - latest_time
        
        return None


class FilePositionRepo(FileBackend, PositionRepo):
    """File-based position repository"""
    
    def get_all(self) -> Dict[str, Dict[str, Any]]:
        """Get all positions"""
        positions_data = self._safe_read_json(self.paths.positions_file, {})
        
        if not positions_data or not isinstance(positions_data, dict):
            return {}
        
        # Normalize position data
        normalized = {}
        for symbol, pos_data in positions_data.items():
            if isinstance(pos_data, dict):
                normalized[symbol] = {
                    "symbol": symbol,
                    "side": pos_data.get("side", "NONE"),
                    "size": pos_data.get("size", 0.0),
                    "entry_price": pos_data.get("entry_price", 0.0),
                    "current_price": pos_data.get("current_price", 0.0),
                    "unrealized_pnl": pos_data.get("unrealized_pnl", 0.0),
                    "timestamp": pos_data.get("timestamp", 0)
                }
        
        return normalized
    
    def get_by_symbol(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get position for specific symbol"""
        all_positions = self.get_all()
        return all_positions.get(symbol)


class FileHealthRepo(FileBackend, HealthRepo):
    """File-based health repository"""
    
    def get_component_status(self, name: str) -> Optional[Dict[str, Any]]:
        """Get health status for component"""
        health_file_map = {
            "feeder": self.paths.feeder_health,
            "ares": self.paths.ares_health,
            "trader": self.paths.trader_health,
            "memory": self.paths.memory_health
        }
        
        health_file = health_file_map.get(name)
        if not health_file:
            return None
        
        return self._safe_read_json(health_file)
    
    def get_all(self) -> Dict[str, Any]:
        """Get all health data"""
        health_data = {
            "timestamp": time.time(),
            "components": {}
        }
        
        components = ["feeder", "ares", "trader", "memory"]
        for component in components:
            status = self.get_component_status(component)
            if status:
                health_data["components"][component] = status
        
        return health_data


class FileMetricsRepo(FileBackend, MetricsRepo):
    """File-based metrics repository"""
    
    def get(self) -> Dict[str, Any]:
        """Get metrics data"""
        # This would typically read from metrics files
        # For now, return basic system info
        return {
            "timestamp": time.time(),
            "system": {
                "uptime": time.time(),
                "memory_usage": 0.0,
                "cpu_usage": 0.0
            }
        }


class HTTPBackend:
    """HTTP-based data backend (placeholder for future implementation)"""
    
    def __init__(self, endpoint: str):
        self.endpoint = endpoint
        self.file_backend = FileBackend()
    
    def get_data(self, endpoint: str) -> Optional[Dict[str, Any]]:
        """Get data from HTTP endpoint with fallback to file backend"""
        # TODO: Implement HTTP client with timeout and error handling
        # For now, fall back to file backend
        logger.warning(f"HTTP backend not implemented, falling back to file backend for {endpoint}")
        return None


class DataBus:
    """Unified data access interface"""
    
    def __init__(self, backend_type: str = "file", endpoint: Optional[str] = None):
        self.backend_type = backend_type
        
        if backend_type == "http" and endpoint:
            self.backend = HTTPBackend(endpoint)
        else:
            self.backend = FileBackend()
        
        # Initialize repositories
        self.prices = FilePriceSnapshotRepo()
        self.signals = FileSignalRepo()
        self.positions = FilePositionRepo()
        self.health = FileHealthRepo()
        self.metrics = FileMetricsRepo()
    
    def get_symbol_data(self, symbol: str) -> Dict[str, Any]:
        """Get comprehensive data for a symbol"""
        price_data = self.prices.get_latest(symbol)
        signal_data = self.signals.get_latest(symbol)
        position_data = self.positions.get_by_symbol(symbol)
        price_age = self.prices.get_age_seconds(symbol)
        signal_age = self.signals.get_age_seconds(symbol)
        
        return {
            "symbol": symbol,
            "price": price_data,
            "signal": signal_data,
            "position": position_data,
            "price_age_seconds": price_age,
            "signal_age_seconds": signal_age,
            "has_price_data": price_data is not None,
            "has_signal_data": signal_data is not None,
            "has_position_data": position_data is not None
        }
    
    def get_all_symbols_data(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """Get data for multiple symbols"""
        result = {}
        for symbol in symbols:
            result[symbol] = self.get_symbol_data(symbol)
        return result
    
    def get_health_summary(self) -> Dict[str, Any]:
        """Get health summary"""
        return self.health.get_all()
    
    def get_positions_summary(self) -> Dict[str, Any]:
        """Get positions summary"""
        return self.positions.get_all()
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get metrics summary"""
        return self.metrics.get()


def create_data_bus() -> DataBus:
    """Create DataBus instance with configuration from environment"""
    backend_type = os.getenv("MONITORING_BACKEND", "file")
    endpoint = os.getenv("MONITORING_ENDPOINT")
    
    return DataBus(backend_type=backend_type, endpoint=endpoint)


# Global data bus instance
_data_bus = None


def get_data_bus() -> DataBus:
    """Get global DataBus instance"""
    global _data_bus
    if _data_bus is None:
        _data_bus = create_data_bus()
    return _data_bus
