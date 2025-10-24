"""
Health Contracts & Readiness Gates for Coin Quant R11

Centralized health status management with readiness gates.
Enforces health contracts across all services.
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional, List
from coin_quant.shared.io import atomic_write_json, safe_read_json
from coin_quant.shared.paths import get_health_dir, get_feeder_health_path, get_ares_health_path, get_trader_health_path, get_memory_health_path
from coin_quant.shared.time import utc_now_seconds, age_seconds


class HealthManager:
    """Centralized health status manager with readiness gates"""
    
    def __init__(self):
        self.health_dir = get_health_dir()
        self.health_dir.mkdir(parents=True, exist_ok=True)
        
        # Health file paths
        self.feeder_health_path = get_feeder_health_path()
        self.ares_health_path = get_ares_health_path()
        self.trader_health_path = get_trader_health_path()
        self.memory_health_path = get_memory_health_path()
        
        # Health thresholds
        self.freshness_threshold = 10.0  # seconds
        self.stale_threshold = 30.0  # seconds
    
    def _write_health_file(self, file_path: Path, health_data: Dict[str, Any]) -> bool:
        """Write health data to file atomically"""
        try:
            health_data["last_update_ts"] = utc_now_seconds()
            health_data["updated_within_sec"] = 0
            return atomic_write_json(file_path, health_data)
        except Exception as e:
            print(f"Failed to write health file {file_path}: {e}")
            return False
    
    def _read_health_file(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """Read health data from file"""
        try:
            health_data = safe_read_json(file_path)
            if health_data:
                # Calculate age
                last_update = health_data.get("last_update_ts", 0)
                health_data["updated_within_sec"] = age_seconds(last_update) or 0
            return health_data
        except Exception as e:
            print(f"Failed to read health file {file_path}: {e}")
            return None
    
    def set_feeder_health(self, status: str, symbols: List[str] = None, **kwargs) -> bool:
        """
        Set feeder health status.
        
        Args:
            status: Health status (ok, degraded, error)
            symbols: List of monitored symbols
            **kwargs: Additional health metrics
        """
        health_data = {
            "service": "feeder",
            "status": status,
            "symbols": symbols or [],
            **kwargs
        }
        return self._write_health_file(self.feeder_health_path, health_data)
    
    def set_ares_health(self, status: str, signal_count: int = 0, **kwargs) -> bool:
        """
        Set ARES health status.
        
        Args:
            status: Health status (ok, degraded, error)
            signal_count: Number of signals generated
            **kwargs: Additional health metrics
        """
        health_data = {
            "service": "ares",
            "status": status,
            "signal_count": signal_count,
            **kwargs
        }
        return self._write_health_file(self.ares_health_path, health_data)
    
    def set_trader_health(self, status: str, orders_count: int = 0, **kwargs) -> bool:
        """
        Set trader health status.
        
        Args:
            status: Health status (ok, degraded, error)
            orders_count: Number of orders executed
            **kwargs: Additional health metrics
        """
        health_data = {
            "service": "trader",
            "status": status,
            "orders_count": orders_count,
            **kwargs
        }
        return self._write_health_file(self.trader_health_path, health_data)
    
    def set_memory_health(self, status: str, integrity_ok: bool = True, **kwargs) -> bool:
        """
        Set memory layer health status.
        
        Args:
            status: Health status (ok, degraded, error)
            integrity_ok: Memory integrity status
            **kwargs: Additional health metrics
        """
        health_data = {
            "service": "memory",
            "status": status,
            "integrity_ok": integrity_ok,
            **kwargs
        }
        return self._write_health_file(self.memory_health_path, health_data)
    
    def get_feeder_health(self) -> Optional[Dict[str, Any]]:
        """Get feeder health status"""
        return self._read_health_file(self.feeder_health_path)
    
    def get_ares_health(self) -> Optional[Dict[str, Any]]:
        """Get ARES health status"""
        return self._read_health_file(self.ares_health_path)
    
    def get_trader_health(self) -> Optional[Dict[str, Any]]:
        """Get trader health status"""
        return self._read_health_file(self.trader_health_path)
    
    def get_memory_health(self) -> Optional[Dict[str, Any]]:
        """Get memory layer health status"""
        return self._read_health_file(self.memory_health_path)
    
    def is_feeder_healthy(self) -> bool:
        """Check if feeder is healthy and fresh"""
        health = self.get_feeder_health()
        if not health:
            return False
        
        return (
            health.get("status") == "ok" and
            health.get("updated_within_sec", 0) <= self.freshness_threshold
        )
    
    def is_ares_healthy(self) -> bool:
        """Check if ARES is healthy and fresh"""
        health = self.get_ares_health()
        if not health:
            return False
        
        return (
            health.get("status") == "ok" and
            health.get("updated_within_sec", 0) <= self.freshness_threshold
        )
    
    def is_trader_healthy(self) -> bool:
        """Check if trader is healthy and fresh"""
        health = self.get_trader_health()
        if not health:
            return False
        
        return (
            health.get("status") == "ok" and
            health.get("updated_within_sec", 0) <= self.freshness_threshold
        )
    
    def is_memory_healthy(self) -> bool:
        """Check if memory layer is healthy and fresh"""
        health = self.get_memory_health()
        if not health:
            return False
        
        return (
            health.get("status") == "ok" and
            health.get("integrity_ok", False) and
            health.get("updated_within_sec", 0) <= self.freshness_threshold
        )
    
    def get_overall_health(self) -> Dict[str, Any]:
        """Get overall system health status"""
        feeder_health = self.get_feeder_health()
        ares_health = self.get_ares_health()
        trader_health = self.get_trader_health()
        memory_health = self.get_memory_health()
        
        # Determine overall status
        all_healthy = all([
            self.is_feeder_healthy(),
            self.is_ares_healthy(),
            self.is_trader_healthy(),
            self.is_memory_healthy()
        ])
        
        any_degraded = any([
            health and health.get("status") == "degraded"
            for health in [feeder_health, ares_health, trader_health, memory_health]
        ])
        
        any_error = any([
            health and health.get("status") == "error"
            for health in [feeder_health, ares_health, trader_health, memory_health]
        ])
        
        if any_error:
            overall_status = "error"
        elif any_degraded:
            overall_status = "degraded"
        elif all_healthy:
            overall_status = "ok"
        else:
            overall_status = "degraded"
        
        return {
            "overall_status": overall_status,
            "all_healthy": all_healthy,
            "components": {
                "feeder": feeder_health,
                "ares": ares_health,
                "trader": trader_health,
                "memory": memory_health
            },
            "timestamp": utc_now_seconds()
        }


class HealthGate:
    """Readiness gate for service dependencies"""
    
    def __init__(self, health_manager: HealthManager):
        self.health_manager = health_manager
        self.freshness_threshold = 10.0
    
    def check_feeder_readiness(self) -> tuple[bool, str]:
        """
        Check if feeder is ready for ARES signal generation.
        
        Returns:
            Tuple of (is_ready, reason)
        """
        feeder_health = self.health_manager.get_feeder_health()
        
        if not feeder_health:
            return False, "No feeder health status available"
        
        if feeder_health.get("status") != "ok":
            return False, f"Feeder status is {feeder_health.get('status')}, not ok"
        
        age = feeder_health.get("updated_within_sec", 0)
        if age > self.freshness_threshold:
            return False, f"Feeder data is stale: {age:.1f}s > {self.freshness_threshold}s"
        
        return True, "Feeder is ready"
    
    def check_ares_readiness(self) -> tuple[bool, str]:
        """
        Check if ARES is ready for trader order execution.
        
        Returns:
            Tuple of (is_ready, reason)
        """
        ares_health = self.health_manager.get_ares_health()
        
        if not ares_health:
            return False, "No ARES health status available"
        
        if ares_health.get("status") != "ok":
            return False, f"ARES status is {ares_health.get('status')}, not ok"
        
        age = ares_health.get("updated_within_sec", 0)
        if age > self.freshness_threshold:
            return False, f"ARES data is stale: {age:.1f}s > {self.freshness_threshold}s"
        
        return True, "ARES is ready"
    
    def check_account_readiness(self) -> tuple[bool, str]:
        """
        Check if account is ready for order execution.
        
        Returns:
            Tuple of (is_ready, reason)
        """
        # This would check account health file
        # For now, return True as placeholder
        return True, "Account is ready"
    
    def wait_for_feeder(self, timeout: float = 60.0) -> bool:
        """
        Wait for feeder to become ready.
        
        Args:
            timeout: Maximum time to wait in seconds
            
        Returns:
            True if feeder becomes ready, False if timeout
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            is_ready, reason = self.check_feeder_readiness()
            if is_ready:
                return True
            
            print(f"Waiting for feeder: {reason}")
            time.sleep(1.0)
        
        return False
    
    def wait_for_ares(self, timeout: float = 60.0) -> bool:
        """
        Wait for ARES to become ready.
        
        Args:
            timeout: Maximum time to wait in seconds
            
        Returns:
            True if ARES becomes ready, False if timeout
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            is_ready, reason = self.check_ares_readiness()
            if is_ready:
                return True
            
            print(f"Waiting for ARES: {reason}")
            time.sleep(1.0)
        
        return False


# Global health manager instance
health_manager = HealthManager()

# Global health gate instance
health_gate = HealthGate(health_manager)