#!/usr/bin/env python3
"""
Auto-Heal v2 - Control-aware recovery with target success validation
Honors control plane state and validates target service recovery
"""

import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional

from shared.control_plane import get_control_plane
from shared.io.jsonio import now_epoch_s, write_json_atomic_nobom
from shared.paths import ensure_all_dirs


class AutoHealV2:
    """Auto-Heal v2 with control plane awareness"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.control_plane = get_control_plane()
        self.autoheal_file = Path("shared_data/health/autoheal.json")
        self.trader_health_file = Path("shared_data/health/trader.json")
        ensure_all_dirs()
        
        # Configuration
        self.max_attempts_per_window = 3
        self.window_seconds = 600  # 10 minutes
        self.recovery_timeout = 10  # seconds
        
        # Module targets
        self.service_map = {
            "feeder": "guard.feeder",
            "trader": "guard.trader", 
            "ares": "guard.optimizer.ares_service",
            "state_bus_writer": "guard.feeder.state_bus_writer",
            "filters_manager": "guard.trader.filters_manager"
        }
    
    def get_state(self) -> Dict[str, Any]:
        """Get current autoheal state"""
        try:
            if not self.autoheal_file.exists():
                return self._create_initial_state()
            
            with open(self.autoheal_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return self._create_initial_state()
    
    def _create_initial_state(self) -> Dict[str, Any]:
        """Create initial autoheal state"""
        return {
            "timestamp": now_epoch_s(),
            "state": "idle",
            "target": "none",
            "attempts_window": {
                "window_s": self.window_seconds,
                "attempts": 0,
                "success": 0,
                "failed": 0
            },
            "last_action": "none",
            "last_error": "",
            "last_error_ts": 0
        }
    
    def _update_state(self, state: str, target: str = "none", 
                     last_action: str = "none", error: str = ""):
        """Update autoheal state"""
        try:
            current_time = now_epoch_s()
            current_state = self.get_state()
            
            # Update state
            current_state.update({
                "timestamp": current_time,
                "state": state,
                "target": target,
                "last_action": last_action,
                "last_error": error,
                "last_error_ts": current_time if error else current_state.get("last_error_ts", 0)
            })
            
            # Update attempts window
            if state == "recovering":
                current_state["attempts_window"]["attempts"] += 1
            elif state == "idle" and target == "none":
                # Reset window if idle
                current_state["attempts_window"]["attempts"] = 0
                current_state["attempts_window"]["success"] = 0
                current_state["attempts_window"]["failed"] = 0
            
            write_json_atomic_nobom(self.autoheal_file, current_state)
        except Exception as e:
            self.logger.error(f"Failed to update autoheal state: {e}")
    
    def _is_trader_running(self) -> bool:
        """Check if trader is running"""
        try:
            # Check if trader health file exists and is recent
            if not self.trader_health_file.exists():
                return False
            
            with open(self.trader_health_file, 'r', encoding='utf-8') as f:
                trader_health = json.load(f)
            
            # Check if entrypoint is OK and recent
            if not trader_health.get("entrypoint_ok", False):
                return False
            
            # Check if timestamp is recent (within 30 seconds)
            last_update = trader_health.get("timestamp", 0)
            current_time = now_epoch_s()
            return (current_time - last_update) <= 30
            
        except Exception:
            return False
    
    def _cleanup_stale_artifacts(self, service: str):
        """Clean up stale artifacts for service"""
        try:
            if service == "trader":
                # Remove stale lock files
                lock_files = [
                    Path("logs/trader.lock"),
                    Path("shared_data/trader.pid")
                ]
                
                for lock_file in lock_files:
                    if lock_file.exists():
                        # Check if PID is alive
                        try:
                            if lock_file.name.endswith('.pid'):
                                with open(lock_file, 'r') as f:
                                    pid = int(f.read().strip())
                                # Check if process is alive (simplified)
                                import psutil
                                if not psutil.pid_exists(pid):
                                    lock_file.unlink()
                                    self.logger.info(f"Removed stale PID file: {lock_file}")
                        except Exception:
                            # Remove if we can't check
                            lock_file.unlink()
                            self.logger.info(f"Removed stale file: {lock_file}")
        except Exception as e:
            self.logger.warning(f"Failed to cleanup stale artifacts: {e}")
    
    def _start_service(self, service: str) -> bool:
        """Start a service using module entrypoint"""
        try:
            if service not in self.service_map:
                self.logger.error(f"Unknown service: {service}")
                return False
            
            module_target = self.service_map[service]
            repo_root = Path.cwd()
            
            # Cleanup stale artifacts
            self._cleanup_stale_artifacts(service)
            
            # Prepare environment
            env = dict(os.environ)
            env["PYTHONPATH"] = str(repo_root)
            
            # Start service
            self.logger.info(f"Starting {service} with module: {module_target}")
            process = subprocess.Popen(
                ["python", "-m", module_target],
                cwd=repo_root,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Wait for startup
            start_time = now_epoch_s()
            success = False
            
            for _ in range(self.recovery_timeout):
                time.sleep(1)
                
                # Check if process is alive
                if process.poll() is not None:
                    self.logger.error(f"Service {service} exited early")
                    break
                
                # Check for ENTRYPOINT_OK in logs (simplified)
                if service == "trader":
                    if self._is_trader_running():
                        success = True
                        break
                else:
                    # For other services, just check if process is alive
                    success = True
                    break
            
            if success:
                self.logger.info(f"Service {service} started successfully")
                return True
            else:
                self.logger.error(f"Service {service} failed to start within timeout")
                process.terminate()
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to start service {service}: {e}")
            return False
    
    def _validate_recovery(self, service: str) -> bool:
        """Validate that service recovery was successful"""
        try:
            if service == "trader":
                return self._is_trader_running()
            else:
                # For other services, basic validation
                return True
        except Exception:
            return False
    
    def attempt_recovery(self, service: str) -> bool:
        """Attempt to recover a service"""
        try:
            # Check if autoheal is disabled
            autoheal_enabled = os.getenv("AUTOHEAL_ENABLED", "1").lower() in ("1", "true", "yes")
            if not autoheal_enabled:
                self.logger.warning("Auto-Heal disabled (AUTOHEAL_ENABLED=false). Skipping recovery attempt.")
                return False
            
            # Check control plane
            if not self.control_plane.is_auto_trading_enabled():
                reason = self.control_plane.get_reason()
                self._update_state("blocked", service, "blocked_by_control", 
                                 f"blocked by control: {reason}")
                self.logger.info(f"Recovery blocked by control plane: {reason}")
                return False
            
            # Check attempts window
            current_state = self.get_state()
            attempts = current_state["attempts_window"]["attempts"]
            
            if attempts >= self.max_attempts_per_window:
                self._update_state("failed", service, "max_attempts_exceeded",
                                 f"max attempts ({self.max_attempts_per_window}) exceeded in {self.window_seconds}s")
                self.logger.error(f"Max recovery attempts exceeded for {service}")
                return False
            
            # Attempt recovery
            self._update_state("recovering", service, "restart_attempt")
            self.logger.info(f"Attempting recovery for {service}")
            
            success = self._start_service(service)
            
            if success:
                # Validate recovery
                if self._validate_recovery(service):
                    self._update_state("idle", "none", "recovery_success")
                    current_state["attempts_window"]["success"] += 1
                    self.logger.info(f"Recovery successful for {service}")
                    return True
                else:
                    self._update_state("failed", service, "validation_failed",
                                     "recovery validation failed")
                    current_state["attempts_window"]["failed"] += 1
                    return False
            else:
                self._update_state("failed", service, "start_failed",
                                 "service start failed")
                current_state["attempts_window"]["failed"] += 1
                return False
                
        except Exception as e:
            self.logger.error(f"Recovery attempt failed for {service}: {e}")
            self._update_state("failed", service, "exception", str(e))
            return False
    
    def check_and_recover(self, service: str) -> bool:
        """Check service health and attempt recovery if needed"""
        try:
            if service == "trader":
                if not self._is_trader_running():
                    return self.attempt_recovery(service)
                else:
                    # Service is healthy, reset state if needed
                    current_state = self.get_state()
                    if current_state["state"] in ["recovering", "failed"]:
                        self._update_state("idle", "none", "service_healthy")
                    return True
            else:
                # For other services, basic check
                return True
                
        except Exception as e:
            self.logger.error(f"Health check failed for {service}: {e}")
            return False


# Global instance
_autoheal_v2 = None

def get_autoheal_v2() -> AutoHealV2:
    """Get global autoheal v2 instance"""
    global _autoheal_v2
    if _autoheal_v2 is None:
        _autoheal_v2 = AutoHealV2()
    return _autoheal_v2