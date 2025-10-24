#!/usr/bin/env python3
"""
Health Contracts & Readiness Gates for Coin Quant R11

This module implements the canonical health schema and readiness gates for all services.
Provides centralized health management with freshness thresholds and dependency checks.
"""

import json
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum

from coin_quant.shared.io import AtomicWriter, AtomicReader
from coin_quant.shared.paths import get_health_dir, get_data_dir
from coin_quant.shared.time import utc_now_seconds, age_seconds

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status enumeration"""
    GREEN = "ok"
    YELLOW = "degraded" 
    RED = "error"


@dataclass
class HealthThresholds:
    """Health freshness thresholds per service"""
    feeder_freshness_sec: float = 10.0
    ares_freshness_sec: float = 30.0
    trader_freshness_sec: float = 60.0
    memory_freshness_sec: float = 5.0
    account_freshness_sec: float = 30.0


class HealthSchema:
    """Canonical health schema definitions"""
    
    FEEDER_SCHEMA = {
        "service": str,
        "status": str,  # "ok", "degraded", "error"
        "last_update_ts": float,
        "updated_within_sec": float,
        "symbols": List[str],
        "ws_connected": bool,
        "rest_api_ok": bool,
        "symbols_count": int,
        "last_symbol_update": float,
        "data_freshness_ok": bool,
        "error_count": int,
        "warning_count": int
    }
    
    ARES_SCHEMA = {
        "service": str,
        "status": str,
        "last_update_ts": float,
        "updated_within_sec": float,
        "signal_count": int,
        "last_signal_time": float,
        "feeder_health_ok": bool,
        "default_signals_blocked": bool,
        "active_strategies": List[str],
        "latency_ms_p50": float,
        "data_freshness_ok": bool,
        "health_gate_passed": bool,
        "blocked_reason": Optional[str]
    }
    
    TRADER_SCHEMA = {
        "service": str,
        "status": str,
        "last_update_ts": float,
        "updated_within_sec": float,
        "orders_count": int,
        "fills_count": int,
        "last_order_time": float,
        "account_balance_ok": bool,
        "ares_health_ok": bool,
        "quarantined_symbols": List[str],
        "active_positions": int,
        "readiness_gate_passed": bool,
        "blocked_reason": Optional[str],
        "balance_freshness_ok": bool
    }
    
    MEMORY_SCHEMA = {
        "service": str,
        "status": str,
        "last_update_ts": float,
        "updated_within_sec": float,
        "integrity_ok": bool,
        "events_count": int,
        "snapshots_count": int,
        "last_integrity_check": float,
        "merkle_root": Optional[str],
        "chain_length": int,
        "integrity_errors": List[str],
        "quarantine_active": bool
    }


class HealthManager:
    """Centralized health status manager with readiness gates"""
    
    def __init__(self, health_file: Optional[Path] = None):
        self.health_file = health_file if health_file else get_health_dir() / "health.json"
        self.health_file.parent.mkdir(parents=True, exist_ok=True)
        self.writer = AtomicWriter()
        self.reader = AtomicReader()
        self.thresholds = HealthThresholds()
        
        logger.info(f"HealthManager initialized: {self.health_file}")
    
    def _load_health_data(self) -> Dict[str, Any]:
        """Load current health data"""
        data = self.reader.read_json(self.health_file, default={})
        if not data or "components" not in data:
            data = {
                "timestamp": utc_now_seconds(),
                "components": {}
            }
        return data
    
    def _save_health_data(self, data: Dict[str, Any]) -> bool:
        """Atomically save health data"""
        data["timestamp"] = utc_now_seconds()
        return self.writer.write_json(self.health_file, data)
    
    def update_feeder_health(self, symbols: List[str], ws_connected: bool, 
                            rest_api_ok: bool, error_count: int = 0, 
                            warning_count: int = 0) -> bool:
        """Update Feeder health status"""
        now = utc_now_seconds()
        last_symbol_update = now  # Assume fresh data
        
        status = HealthStatus.GREEN
        if not ws_connected or not rest_api_ok:
            status = HealthStatus.YELLOW
        if error_count > 10 or warning_count > 50:
            status = HealthStatus.RED
        
        health_data = {
            "service": "feeder",
            "status": status.value,
            "last_update_ts": now,
            "updated_within_sec": 0.0,
            "symbols": symbols,
            "ws_connected": ws_connected,
            "rest_api_ok": rest_api_ok,
            "symbols_count": len(symbols),
            "last_symbol_update": last_symbol_update,
            "data_freshness_ok": True,
            "error_count": error_count,
            "warning_count": warning_count
        }
        
        return self._update_component_health("feeder", health_data)
    
    def update_ares_health(self, signal_count: int, active_strategies: List[str],
                          latency_ms_p50: float = 0.0) -> Tuple[bool, Optional[str]]:
        """Update ARES health status with readiness gate"""
        now = utc_now_seconds()
        
        # Check Feeder dependency
        feeder_health = self.get_component_status("feeder")
        feeder_ok = self._is_component_healthy(feeder_health, self.thresholds.feeder_freshness_sec)
        
        # Health gate logic
        health_gate_passed = True
        blocked_reason = None
        
        if not feeder_health:
            health_gate_passed = False
            blocked_reason = "feeder_health_missing"
        elif feeder_health.get("status") != "ok":
            health_gate_passed = False
            blocked_reason = f"feeder_status_{feeder_health.get('status')}"
        elif not feeder_ok:
            health_gate_passed = False
            blocked_reason = "feeder_data_stale"
        
        # Determine ARES status
        status = HealthStatus.GREEN
        if not health_gate_passed:
            status = HealthStatus.YELLOW
        
        health_data = {
            "service": "ares",
            "status": status.value,
            "last_update_ts": now,
            "updated_within_sec": 0.0,
            "signal_count": signal_count,
            "last_signal_time": now if signal_count > 0 else 0.0,
            "feeder_health_ok": feeder_ok,
            "default_signals_blocked": not health_gate_passed,
            "active_strategies": active_strategies,
            "latency_ms_p50": latency_ms_p50,
            "data_freshness_ok": feeder_ok,
            "health_gate_passed": health_gate_passed,
            "blocked_reason": blocked_reason
        }
        
        success = self._update_component_health("ares", health_data)
        
        # Log readiness decision
        if health_gate_passed:
            logger.info(f"ARES readiness: ALLOW - Feeder healthy, signals enabled")
        else:
            logger.warning(f"ARES readiness: BLOCK - {blocked_reason}")
        
        return success, blocked_reason
    
    def update_trader_health(self, orders_count: int, fills_count: int,
                            quarantined_symbols: List[str], active_positions: int,
                            account_balance_ok: bool = True) -> Tuple[bool, Optional[str]]:
        """Update Trader health status with readiness gate"""
        now = utc_now_seconds()
        
        # Check dependencies
        ares_health = self.get_component_status("ares")
        ares_ok = self._is_component_healthy(ares_health, self.thresholds.ares_freshness_sec)
        
        # Readiness gate logic
        readiness_gate_passed = True
        blocked_reason = None
        
        if not ares_health:
            readiness_gate_passed = False
            blocked_reason = "ares_health_missing"
        elif ares_health.get("status") != "ok":
            readiness_gate_passed = False
            blocked_reason = f"ares_status_{ares_health.get('status')}"
        elif not ares_ok:
            readiness_gate_passed = False
            blocked_reason = "ares_data_stale"
        elif not account_balance_ok:
            readiness_gate_passed = False
            blocked_reason = "account_balance_insufficient"
        
        # Determine Trader status
        status = HealthStatus.GREEN
        if not readiness_gate_passed:
            status = HealthStatus.YELLOW
        
        health_data = {
            "service": "trader",
            "status": status.value,
            "last_update_ts": now,
            "updated_within_sec": 0.0,
            "orders_count": orders_count,
            "fills_count": fills_count,
            "last_order_time": now if orders_count > 0 else 0.0,
            "account_balance_ok": account_balance_ok,
            "ares_health_ok": ares_ok,
            "quarantined_symbols": quarantined_symbols,
            "active_positions": active_positions,
            "readiness_gate_passed": readiness_gate_passed,
            "blocked_reason": blocked_reason,
            "balance_freshness_ok": account_balance_ok
        }
        
        success = self._update_component_health("trader", health_data)
        
        # Log readiness decision
        if readiness_gate_passed:
            logger.info(f"Trader readiness: ALLOW - Dependencies healthy, orders enabled")
        else:
            logger.warning(f"Trader readiness: BLOCK - {blocked_reason}")
        
        return success, blocked_reason
    
    def update_memory_health(self, integrity_ok: bool, events_count: int,
                            snapshots_count: int, merkle_root: Optional[str] = None,
                            integrity_errors: List[str] = None) -> bool:
        """Update Memory health status"""
        now = utc_now_seconds()
        
        if integrity_errors is None:
            integrity_errors = []
        
        status = HealthStatus.GREEN
        if not integrity_ok:
            status = HealthStatus.RED
        elif integrity_errors:
            status = HealthStatus.YELLOW
        
        health_data = {
            "service": "memory",
            "status": status.value,
            "last_update_ts": now,
            "updated_within_sec": 0.0,
            "integrity_ok": integrity_ok,
            "events_count": events_count,
            "snapshots_count": snapshots_count,
            "last_integrity_check": now,
            "merkle_root": merkle_root,
            "chain_length": events_count,
            "integrity_errors": integrity_errors,
            "quarantine_active": len(integrity_errors) > 0
        }
        
        return self._update_component_health("memory", health_data)
    
    def _update_component_health(self, component_name: str, health_data: Dict[str, Any]) -> bool:
        """Update component health data"""
        current_health = self._load_health_data()
        
        # Update freshness
        health_data["updated_within_sec"] = age_seconds(health_data["last_update_ts"])
        
        current_health["components"][component_name] = health_data
        return self._save_health_data(current_health)
    
    def get_component_status(self, component_name: str) -> Optional[Dict[str, Any]]:
        """Get component health status"""
        health_data = self._load_health_data()
        return health_data["components"].get(component_name)
    
    def _is_component_healthy(self, component_status: Optional[Dict[str, Any]], 
                            freshness_threshold: float) -> bool:
        """Check if component is healthy and fresh"""
        if not component_status:
            return False
        
        if component_status.get("status") != "ok":
            return False
        
        last_update_ts = component_status.get("last_update_ts", 0)
        if not last_update_ts or age_seconds(last_update_ts) > freshness_threshold:
            return False
        
        return True
    
    def get_overall_status(self) -> str:
        """Get overall system health status"""
        health_data = self._load_health_data()
        components = health_data["components"]
        
        if not components:
            return "YELLOW"
        
        # If any component is RED, overall is RED
        if any(c.get("status") == "error" for c in components.values()):
            return "RED"
        # If any component is YELLOW, overall is YELLOW
        if any(c.get("status") == "degraded" for c in components.values()):
            return "YELLOW"
        
        return "GREEN"
    
    def get_readiness_summary(self) -> Dict[str, Any]:
        """Get readiness summary for all components"""
        health_data = self._load_health_data()
        components = health_data["components"]
        
        summary = {
            "overall_status": self.get_overall_status(),
            "components": {},
            "blocked_services": [],
            "ready_services": []
        }
        
        for name, status in components.items():
            component_summary = {
                "status": status.get("status"),
                "fresh": self._is_component_healthy(status, self.thresholds.feeder_freshness_sec),
                "last_update": status.get("last_update_ts", 0),
                "blocked_reason": status.get("blocked_reason")
            }
            
            summary["components"][name] = component_summary
            
            if status.get("blocked_reason"):
                summary["blocked_services"].append(name)
            else:
                summary["ready_services"].append(name)
        
        return summary


class ReadinessGate:
    """Readiness gate for service dependencies"""
    
    def __init__(self, health_manager: HealthManager, service_name: str):
        self.health_manager = health_manager
        self.service_name = service_name
        self.logger = logging.getLogger(f"readiness.{service_name}")
    
    def check_feeder_readiness(self) -> Tuple[bool, str]:
        """Check if Feeder is ready"""
        feeder_health = self.health_manager.get_component_status("feeder")
        
        if not feeder_health:
            return False, "Feeder health missing"
        
        if feeder_health.get("status") != "ok":
            return False, f"Feeder status: {feeder_health.get('status')}"
        
        if not feeder_health.get("ws_connected", False):
            return False, "WebSocket disconnected"
        
        if not feeder_health.get("rest_api_ok", False):
            return False, "REST API unavailable"
        
        return True, "Feeder ready"
    
    def check_ares_readiness(self) -> Tuple[bool, str]:
        """Check if ARES is ready"""
        ares_health = self.health_manager.get_component_status("ares")
        
        if not ares_health:
            return False, "ARES health missing"
        
        if not ares_health.get("health_gate_passed", False):
            blocked_reason = ares_health.get("blocked_reason", "unknown")
            return False, f"ARES blocked: {blocked_reason}"
        
        return True, "ARES ready"
    
    def check_trader_readiness(self) -> Tuple[bool, str]:
        """Check if Trader is ready"""
        trader_health = self.health_manager.get_component_status("trader")
        
        if not trader_health:
            return False, "Trader health missing"
        
        if not trader_health.get("readiness_gate_passed", False):
            blocked_reason = trader_health.get("blocked_reason", "unknown")
            return False, f"Trader blocked: {blocked_reason}"
        
        if not trader_health.get("account_balance_ok", False):
            return False, "Account balance insufficient"
        
        return True, "Trader ready"
    
    def check_readiness(self) -> Dict[str, Any]:
        """Check service readiness and return status"""
        if self.service_name == "ares":
            ready, reason = self.check_ares_readiness()
        elif self.service_name == "trader":
            ready, reason = self.check_trader_readiness()
        else:
            ready, reason = self.check_feeder_readiness()
        
        return {
            "service": self.service_name,
            "ready": ready,
            "reason": reason,
            "timestamp": utc_now_seconds()
        }
    
    def wait_for_readiness(self, timeout_sec: float = 300.0) -> bool:
        """Wait for service readiness with exponential backoff"""
        start_time = time.time()
        backoff_sec = 1.0
        max_backoff = 30.0
        
        while time.time() - start_time < timeout_sec:
            if self.service_name == "ares":
                ready, reason = self.check_ares_readiness()
            elif self.service_name == "trader":
                ready, reason = self.check_trader_readiness()
            else:
                ready, reason = self.check_feeder_readiness()
            
            if ready:
                self.logger.info(f"{self.service_name} readiness: READY - {reason}")
                return True
            
            self.logger.warning(f"{self.service_name} readiness: WAITING - {reason}")
            time.sleep(backoff_sec)
            backoff_sec = min(backoff_sec * 1.5, max_backoff)
        
        self.logger.error(f"{self.service_name} readiness: TIMEOUT after {timeout_sec}s")
        return False


# Global health manager instance
health_manager = HealthManager()


def get_health_manager() -> HealthManager:
    """Get global health manager instance"""
    return health_manager


def create_readiness_gate(service_name: str) -> ReadinessGate:
    """Create readiness gate for service"""
    return ReadinessGate(health_manager, service_name)
