#!/usr/bin/env python3
"""
Health Monitor - Enhanced health monitoring with stale-read guards
Implements 2-probe requirement and cooldown logic for restart alerts
"""

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psutil

from shared.alert_cooldown import get_alert_manager
from shared.health_writer import HealthReader, get_health_reader

logger = logging.getLogger(__name__)

# Configuration
HEALTH_FRESHNESS_S = 120
PROBE_COOLDOWN_MINUTES = 10


class HealthMonitor:
    """Enhanced health monitoring with stale-read guards"""
    
    def __init__(self, repo_root: Optional[Path] = None):
        if repo_root is None:
            repo_root = Path(__file__).parent.parent.absolute()
        
        self.repo_root = repo_root
        self.health_reader = get_health_reader(repo_root)
        self.alert_manager = get_alert_manager(repo_root)
        
        # Process tracking
        self._process_cache: Dict[str, int] = {}
        self._last_process_check = 0.0
        
        logger.info("HealthMonitor initialized")
    
    def _get_process_pid(self, process_name: str) -> Optional[int]:
        """Get PID for a process name (with caching)"""
        now = time.time()
        
        # Use cache if recent (within 5 seconds)
        if (now - self._last_process_check) < 5.0 and process_name in self._process_cache:
            cached_pid = self._process_cache[process_name]
            if cached_pid and psutil.pid_exists(cached_pid):
                return cached_pid
            else:
                # Cached PID is invalid, remove from cache
                del self._process_cache[process_name]
        
        # Find process
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if process_name in proc.info['name'] or (
                    proc.info['cmdline'] and 
                    any(process_name in arg for arg in proc.info['cmdline'])
                ):
                    pid = proc.info['pid']
                    self._process_cache[process_name] = pid
                    self._last_process_check = now
                    return pid
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        # Process not found
        self._process_cache[process_name] = 0
        self._last_process_check = now
        return None
    
    def _is_process_alive(self, process_name: str) -> bool:
        """Check if process is alive"""
        pid = self._get_process_pid(process_name)
        if pid is None or pid == 0:
            return False
        
        try:
            return psutil.pid_exists(pid)
        except Exception:
            return False
    
    def _check_health_freshness(self, health_data: Dict[str, Any]) -> Tuple[bool, float]:
        """Check if health data is fresh"""
        if not health_data or "ts" not in health_data:
            return False, 0.0
        
        age_s = (time.time() * 1000 - health_data["ts"]) / 1000.0
        is_fresh = age_s <= HEALTH_FRESHNESS_S
        
        return is_fresh, age_s
    
    def _check_feeder_health(self, health_data: Dict[str, Any]) -> Dict[str, Any]:
        """Check Feeder health with 2-probe requirement"""
        result = {
            "process_alive": False,
            "ws_fresh": False,
            "overall_healthy": False,
            "age_s": 0.0,
            "should_alert": False
        }
        
        if not health_data:
            return result
        
        # Check process
        result["process_alive"] = self._is_process_alive("feeder")
        
        # Check WebSocket freshness
        ws_fresh_s = health_data.get("feeder", {}).get("ws_fresh_s", 0)
        result["ws_fresh"] = ws_fresh_s <= 30  # 30 second threshold
        
        # Check overall health data freshness
        is_fresh, age_s = self._check_health_freshness(health_data)
        result["age_s"] = age_s
        
        # 2-probe requirement: both process dead AND ws stale
        result["overall_healthy"] = result["process_alive"] and result["ws_fresh"] and is_fresh
        
        # Alert logic: process dead AND (ws stale OR health stale)
        should_alert = not result["process_alive"] and (not result["ws_fresh"] or not is_fresh)
        
        if should_alert:
            # Check cooldown
            can_alert = self.alert_manager.can_send_alert("restart", "feeder")
            result["should_alert"] = can_alert
            
            if can_alert:
                self.alert_manager.record_alert_sent("restart", "feeder")
                logger.warning(
                    f"feeder_health_alert process_alive={result['process_alive']} "
                    f"ws_fresh={result['ws_fresh']} health_age_s={age_s:.1f}"
                )
            else:
                remaining_min = self.alert_manager.get_remaining_cooldown("restart", "feeder")
                logger.debug(f"feeder_alert_cooldown remaining_min={remaining_min:.1f}")
        
        return result
    
    def _check_trader_health(self, health_data: Dict[str, Any]) -> Dict[str, Any]:
        """Check Trader health with 2-probe requirement"""
        result = {
            "process_alive": False,
            "positions_fresh": False,
            "overall_healthy": False,
            "age_s": 0.0,
            "should_alert": False
        }
        
        if not health_data:
            return result
        
        # Check process
        result["process_alive"] = self._is_process_alive("trader")
        
        # Check positions freshness
        positions_fresh_s = health_data.get("trader", {}).get("positions_fresh_s", 0)
        result["positions_fresh"] = positions_fresh_s <= 60  # 60 second threshold
        
        # Check overall health data freshness
        is_fresh, age_s = self._check_health_freshness(health_data)
        result["age_s"] = age_s
        
        # 2-probe requirement: both process alive AND positions fresh
        result["overall_healthy"] = result["process_alive"] and result["positions_fresh"] and is_fresh
        
        # Alert logic: process dead AND (positions stale OR health stale)
        should_alert = not result["process_alive"] and (not result["positions_fresh"] or not is_fresh)
        
        if should_alert:
            # Check cooldown
            can_alert = self.alert_manager.can_send_alert("restart", "trader")
            result["should_alert"] = can_alert
            
            if can_alert:
                self.alert_manager.record_alert_sent("restart", "trader")
                logger.warning(
                    f"trader_health_alert process_alive={result['process_alive']} "
                    f"positions_fresh={result['positions_fresh']} health_age_s={age_s:.1f}"
                )
            else:
                remaining_min = self.alert_manager.get_remaining_cooldown("restart", "trader")
                logger.debug(f"trader_alert_cooldown remaining_min={remaining_min:.1f}")
        
        return result
    
    def _check_ares_health(self, health_data: Dict[str, Any]) -> Dict[str, Any]:
        """Check ARES health"""
        result = {
            "process_alive": False,
            "signals_fresh": False,
            "overall_healthy": False,
            "age_s": 0.0,
            "should_alert": False
        }
        
        if not health_data:
            return result
        
        # Check process
        result["process_alive"] = self._is_process_alive("ares")
        
        # Check signals freshness
        signals_fresh_s = health_data.get("ares", {}).get("signals_fresh_s", 0)
        result["signals_fresh"] = signals_fresh_s <= 75  # 75 second threshold
        
        # Check overall health data freshness
        is_fresh, age_s = self._check_health_freshness(health_data)
        result["age_s"] = age_s
        
        # Overall health
        result["overall_healthy"] = result["process_alive"] and result["signals_fresh"] and is_fresh
        
        # Alert logic: process dead AND (signals stale OR health stale)
        should_alert = not result["process_alive"] and (not result["signals_fresh"] or not is_fresh)
        
        if should_alert:
            # Check cooldown
            can_alert = self.alert_manager.can_send_alert("restart", "ares")
            result["should_alert"] = can_alert
            
            if can_alert:
                self.alert_manager.record_alert_sent("restart", "ares")
                logger.warning(
                    f"ares_health_alert process_alive={result['process_alive']} "
                    f"signals_fresh={result['signals_fresh']} health_age_s={age_s:.1f}"
                )
            else:
                remaining_min = self.alert_manager.get_remaining_cooldown("restart", "ares")
                logger.debug(f"ares_alert_cooldown remaining_min={remaining_min:.1f}")
        
        return result
    
    def check_all_health(self) -> Dict[str, Any]:
        """Check health of all services"""
        health_data = self.health_reader.read_health()
        
        result = {
            "timestamp": time.time(),
            "health_data_fresh": False,
            "services": {
                "feeder": self._check_feeder_health(health_data),
                "trader": self._check_trader_health(health_data),
                "ares": self._check_ares_health(health_data)
            },
            "overall_healthy": True,
            "alerts": []
        }
        
        # Check if health data itself is fresh
        if health_data:
            is_fresh, age_s = self._check_health_freshness(health_data)
            result["health_data_fresh"] = is_fresh
            result["health_data_age_s"] = age_s
        
        # Determine overall health
        for service_name, service_health in result["services"].items():
            if not service_health["overall_healthy"]:
                result["overall_healthy"] = False
            
            if service_health["should_alert"]:
                result["alerts"].append({
                    "type": "restart",
                    "service": service_name,
                    "reason": f"process_alive={service_health['process_alive']} "
                             f"fresh={service_health.get('ws_fresh', service_health.get('positions_fresh', service_health.get('signals_fresh', False)))}"
                })
        
        return result
    
    def get_service_status(self, service_name: str) -> Dict[str, Any]:
        """Get status of a specific service"""
        health_data = self.health_reader.read_health()
        
        if service_name == "feeder":
            return self._check_feeder_health(health_data)
        elif service_name == "trader":
            return self._check_trader_health(health_data)
        elif service_name == "ares":
            return self._check_ares_health(health_data)
        else:
            return {
                "process_alive": False,
                "overall_healthy": False,
                "age_s": 0.0,
                "should_alert": False
            }


# Global instance
_health_monitor: Optional[HealthMonitor] = None


def get_health_monitor(repo_root: Optional[Path] = None) -> HealthMonitor:
    """Get singleton health monitor"""
    global _health_monitor
    if _health_monitor is None:
        _health_monitor = HealthMonitor(repo_root)
    return _health_monitor


def check_all_health(repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """Check health of all services"""
    monitor = get_health_monitor(repo_root)
    return monitor.check_all_health()


def get_service_status(service_name: str, repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """Get status of a specific service"""
    monitor = get_health_monitor(repo_root)
    return monitor.get_service_status(service_name)
