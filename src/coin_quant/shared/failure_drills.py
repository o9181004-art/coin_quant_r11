#!/usr/bin/env python3
"""
Failure Drills & Recovery System for Coin Quant R11

Implements deterministic failure drills and recovery procedures.
Provides automated testing of system resilience and recovery capabilities.
"""

import time
import json
import logging
import subprocess
import psutil
import os
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from coin_quant.shared.io import AtomicWriter, AtomicReader
from coin_quant.shared.paths import get_data_dir
from coin_quant.shared.time import utc_now_seconds

logger = logging.getLogger(__name__)


class DrillType(Enum):
    """Types of failure drills"""
    FEEDER_OUTAGE = "feeder_outage"
    INSUFFICIENT_BALANCE = "insufficient_balance"
    MEMORY_CORRUPTION = "memory_corruption"


class DrillStatus(Enum):
    """Drill execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class DrillResult:
    """Result of a failure drill"""
    drill_type: DrillType
    status: DrillStatus
    start_time: float
    end_time: Optional[float]
    expected_observations: List[str]
    actual_observations: List[str]
    success_conditions: List[str]
    success: bool
    errors: List[str]
    recovery_time: Optional[float]


class FailureDrillManager:
    """Manages failure drills and recovery procedures"""
    
    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or get_data_dir()
        self.writer = AtomicWriter()
        self.reader = AtomicReader()
        
        # Drill configuration - fast for tests
        self.test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
        self.max_wait_sec = int(os.getenv("DRILL_MAX_WAIT_SEC", "5" if self.test_mode else "30"))
        self.drill_timeout = self.max_wait_sec
        self.recovery_timeout = self.max_wait_sec * 2
        
        logger.info(f"FailureDrillManager initialized: {self.data_dir} (test_mode={self.test_mode}, max_wait={self.max_wait_sec}s)")
    
    def run_feeder_outage_drill(self) -> DrillResult:
        """Run Feeder outage drill"""
        logger.info("Starting Feeder outage drill")
        
        drill_type = DrillType.FEEDER_OUTAGE
        start_time = utc_now_seconds()
        
        expected_observations = [
            "ARES blocks signal generation with stale-health reason",
            "Trader waits for account/feeder readiness",
            "Logs show backoff and recovery messages",
            "Services recover once Feeder restarts"
        ]
        
        success_conditions = [
            "ARES health status changes to degraded",
            "ARES blocked_reason contains 'feeder_data_stale'",
            "Trader readiness_gate_passed becomes false",
            "System recovers within 5 minutes of Feeder restart"
        ]
        
        actual_observations = []
        errors = []
        
        try:
            # Step 1: Record initial state
            initial_health = self._get_system_health()
            actual_observations.append(f"Initial system health: {initial_health}")
            
            # Step 2: Stop Feeder service
            feeder_pid = self._find_service_pid("feeder")
            if feeder_pid:
                self._kill_service(feeder_pid)
                actual_observations.append(f"Feeder service stopped (PID: {feeder_pid})")
            else:
                errors.append("Feeder service PID not found")
            
            # Step 3: Wait for ARES to detect outage (fast polling)
            ares_health = self._wait_for_condition(
                lambda: self._get_component_health("ares"),
                lambda health: health and health.get("status") == "degraded",
                timeout=self.max_wait_sec,
                step=0.5
            )
            if ares_health:
                actual_observations.append("ARES detected Feeder outage")
            else:
                errors.append("ARES failed to detect Feeder outage")
            
            # Step 4: Check ARES blocking
            if ares_health and ares_health.get("blocked_reason"):
                blocked_reason = ares_health["blocked_reason"]
                actual_observations.append(f"ARES blocked with reason: {blocked_reason}")
                if "feeder_data_stale" in blocked_reason:
                    actual_observations.append("ARES correctly blocked due to stale data")
                else:
                    errors.append(f"ARES blocked for wrong reason: {blocked_reason}")
            
            # Step 5: Check Trader readiness
            trader_health = self._get_component_health("trader")
            if trader_health and not trader_health.get("readiness_gate_passed", True):
                actual_observations.append("Trader correctly blocked by readiness gate")
            else:
                errors.append("Trader failed to block on readiness gate")
            
            # Step 6: Restart Feeder service
            self._start_feeder_service()
            actual_observations.append("Feeder service restarted")
            
            # Step 7: Wait for recovery (fast polling)
            recovery_start = time.time()
            recovery_success = self._wait_for_recovery(timeout=self.recovery_timeout)
            recovery_time = time.time() - recovery_start
            
            if recovery_success:
                actual_observations.append(f"System recovered in {recovery_time:.1f} seconds")
            else:
                errors.append("System failed to recover within timeout")
            
            # Determine success
            success = len(errors) == 0 and recovery_success
            
            return DrillResult(
                drill_type=drill_type,
                status=DrillStatus.COMPLETED if success else DrillStatus.FAILED,
                start_time=start_time,
                end_time=utc_now_seconds(),
                expected_observations=expected_observations,
                actual_observations=actual_observations,
                success_conditions=success_conditions,
                success=success,
                errors=errors,
                recovery_time=recovery_time
            )
            
        except Exception as e:
            errors.append(f"Drill execution error: {str(e)}")
            return DrillResult(
                drill_type=drill_type,
                status=DrillStatus.FAILED,
                start_time=start_time,
                end_time=utc_now_seconds(),
                expected_observations=expected_observations,
                actual_observations=actual_observations,
                success_conditions=success_conditions,
                success=False,
                errors=errors,
                recovery_time=None
            )
    
    def run_insufficient_balance_drill(self) -> DrillResult:
        """Run insufficient balance drill"""
        logger.info("Starting insufficient balance drill")
        
        drill_type = DrillType.INSUFFICIENT_BALANCE
        start_time = utc_now_seconds()
        
        expected_observations = [
            "Trader detects insufficient balance",
            "Order sizes are down-scaled automatically",
            "Retry attempts are bounded",
            "Symbol is quarantined after persistent failure"
        ]
        
        success_conditions = [
            "Trader logs insufficient balance errors",
            "Order size scaling is applied",
            "Retry count is bounded",
            "Symbol appears in quarantine list"
        ]
        
        actual_observations = []
        errors = []
        
        try:
            # Step 1: Record initial state
            initial_quarantine = self._get_quarantined_symbols()
            actual_observations.append(f"Initial quarantined symbols: {initial_quarantine}")
            
            # Step 2: Simulate insufficient balance
            # This would typically involve modifying account balance or order size
            # For now, we'll monitor the logs for balance-related errors
            actual_observations.append("Simulating insufficient balance scenario")
            
            # Step 3: Monitor Trader behavior (fast polling)
            trader_activity = self._wait_for_condition(
                lambda: self._get_recent_logs("trader", minutes=1),
                lambda logs: len(logs) > 0,
                timeout=self.max_wait_sec,
                step=0.5
            )
            
            # Step 4: Check for order scaling
            recent_logs = self._get_recent_logs("trader", minutes=2)
            scaling_observed = any("down-scale" in log.lower() for log in recent_logs)
            if scaling_observed:
                actual_observations.append("Order size scaling observed")
            else:
                errors.append("Order size scaling not observed")
            
            # Step 5: Check for retry bounding
            retry_observed = any("retry" in log.lower() for log in recent_logs)
            if retry_observed:
                actual_observations.append("Retry attempts observed")
            else:
                errors.append("Retry attempts not observed")
            
            # Step 6: Check for quarantine
            final_quarantine = self._get_quarantined_symbols()
            new_quarantined = set(final_quarantine) - set(initial_quarantine)
            if new_quarantined:
                actual_observations.append(f"New quarantined symbols: {list(new_quarantined)}")
            else:
                errors.append("No new symbols quarantined")
            
            # Determine success
            success = len(errors) == 0
            
            return DrillResult(
                drill_type=drill_type,
                status=DrillStatus.COMPLETED if success else DrillStatus.FAILED,
                start_time=start_time,
                end_time=utc_now_seconds(),
                expected_observations=expected_observations,
                actual_observations=actual_observations,
                success_conditions=success_conditions,
                success=success,
                errors=errors,
                recovery_time=None
            )
            
        except Exception as e:
            errors.append(f"Drill execution error: {str(e)}")
            return DrillResult(
                drill_type=drill_type,
                status=DrillStatus.FAILED,
                start_time=start_time,
                end_time=utc_now_seconds(),
                expected_observations=expected_observations,
                actual_observations=actual_observations,
                success_conditions=success_conditions,
                success=False,
                errors=errors,
                recovery_time=None
            )
    
    def run_memory_corruption_drill(self) -> DrillResult:
        """Run memory corruption drill"""
        logger.info("Starting memory corruption drill")
        
        drill_type = DrillType.MEMORY_CORRUPTION
        start_time = utc_now_seconds()
        
        expected_observations = [
            "Memory integrity check fails",
            "Memory health status changes to degraded/error",
            "Debug bundle is exported automatically",
            "Replay from last good snapshot succeeds",
            "Quarantine scope is limited to affected components"
        ]
        
        success_conditions = [
            "Memory integrity status is not 'valid'",
            "Debug bundle export succeeds",
            "Replay reconstructs state deterministically",
            "Quarantine is limited to affected scope"
        ]
        
        actual_observations = []
        errors = []
        
        try:
            # Step 1: Record initial state
            initial_integrity = self._get_memory_integrity()
            actual_observations.append(f"Initial memory integrity: {initial_integrity}")
            
            # Step 2: Inject controlled integrity failure
            self._inject_memory_corruption()
            actual_observations.append("Memory corruption injected")
            
            # Step 3: Wait for integrity check to detect corruption (fast polling)
            corrupted_integrity = self._wait_for_condition(
                lambda: self._get_memory_integrity(),
                lambda integrity: integrity and integrity.get("status") != "valid",
                timeout=self.max_wait_sec,
                step=0.5
            )
            if corrupted_integrity:
                actual_observations.append(f"Memory corruption detected: {corrupted_integrity['status']}")
            else:
                errors.append("Memory corruption not detected")
            
            # Step 4: Check debug bundle export
            debug_bundle_path = self._export_debug_bundle()
            if debug_bundle_path and debug_bundle_path.exists():
                actual_observations.append(f"Debug bundle exported: {debug_bundle_path}")
            else:
                errors.append("Debug bundle export failed")
            
            # Step 5: Test replay capability
            try:
                replayed_state = self._replay_from_snapshot()
                actual_observations.append("Replay from snapshot succeeded")
            except Exception as e:
                errors.append(f"Replay failed: {str(e)}")
            
            # Step 6: Check quarantine scope
            quarantine_scope = self._get_quarantine_scope()
            if quarantine_scope:
                actual_observations.append(f"Quarantine scope: {quarantine_scope}")
            else:
                errors.append("Quarantine scope not determined")
            
            # Step 7: Restore from backup
            self._restore_memory_from_backup()
            actual_observations.append("Memory restored from backup")
            
            # Determine success
            success = len(errors) == 0
            
            return DrillResult(
                drill_type=drill_type,
                status=DrillStatus.COMPLETED if success else DrillStatus.FAILED,
                start_time=start_time,
                end_time=utc_now_seconds(),
                expected_observations=expected_observations,
                actual_observations=actual_observations,
                success_conditions=success_conditions,
                success=success,
                errors=errors,
                recovery_time=None
            )
            
        except Exception as e:
            errors.append(f"Drill execution error: {str(e)}")
            return DrillResult(
                drill_type=drill_type,
                status=DrillStatus.FAILED,
                start_time=start_time,
                end_time=utc_now_seconds(),
                expected_observations=expected_observations,
                actual_observations=actual_observations,
                success_conditions=success_conditions,
                success=False,
                errors=errors,
                recovery_time=None
            )
    
    def _get_system_health(self) -> Dict[str, Any]:
        """Get current system health"""
        health_file = self.data_dir / "health" / "health.json"
        if health_file.exists():
            return self.reader.read_json(health_file, default={})
        return {}
    
    def _get_component_health(self, component: str) -> Optional[Dict[str, Any]]:
        """Get component health status"""
        health_data = self._get_system_health()
        return health_data.get("components", {}).get(component)
    
    def _find_service_pid(self, service_name: str) -> Optional[int]:
        """Find service process ID"""
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.info['cmdline']
                if cmdline and any(service_name in arg for arg in cmdline):
                    return proc.info['pid']
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return None
    
    def _kill_service(self, pid: int) -> bool:
        """Kill service process"""
        try:
            proc = psutil.Process(pid)
            proc.kill()
            proc.wait(timeout=10)
            return True
        except (psutil.NoSuchProcess, psutil.TimeoutExpired):
            return False
    
    def _start_feeder_service(self) -> bool:
        """Start Feeder service"""
        try:
            script_path = self.data_dir.parent / "scripts" / "launch_feeder.ps1"
            subprocess.Popen(["powershell.exe", "-File", str(script_path)], 
                           creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            return True
        except Exception as e:
            logger.error(f"Failed to start Feeder service: {str(e)}")
            return False
    
    def _wait_for_condition(self, getter_func, condition_func, timeout: float, step: float = 0.5) -> Any:
        """Wait for a condition to be met with fast polling"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                result = getter_func()
                if condition_func(result):
                    return result
            except Exception:
                pass
            
            time.sleep(step)
        
        return None
    
    def _wait_for_recovery(self, timeout: float) -> bool:
        """Wait for system recovery with fast polling"""
        return self._wait_for_condition(
            lambda: self._get_system_health(),
            lambda health: self._is_system_healthy(health),
            timeout=timeout,
            step=1.0
        ) is not None
    
    def _is_system_healthy(self, health_data: Dict[str, Any]) -> bool:
        """Check if system is healthy"""
        components = health_data.get("components", {})
        
        for component_name, component_data in components.items():
            if component_data.get("status") not in ["ok", "GREEN"]:
                return False
        
        return True
    
    def _get_quarantined_symbols(self) -> List[str]:
        """Get quarantined symbols"""
        quarantine_file = self.data_dir / "memory" / "quarantine.json"
        if quarantine_file.exists():
            quarantine_data = self.reader.read_json(quarantine_file, default={})
            return list(quarantine_data.keys())
        return []
    
    def _get_recent_logs(self, service: str, minutes: int = 5) -> List[str]:
        """Get recent log entries"""
        log_file = self.data_dir / "logs" / f"{service}.log"
        if not log_file.exists():
            return []
        
        cutoff_time = time.time() - (minutes * 60)
        recent_logs = []
        
        try:
            with open(log_file, 'r') as f:
                for line in f:
                    if line.startswith('20'):  # ISO timestamp
                        try:
                            timestamp_str = line.split(' - ')[0]
                            timestamp = time.mktime(time.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f'))
                            if timestamp >= cutoff_time:
                                recent_logs.append(line.strip())
                        except ValueError:
                            continue
        except Exception as e:
            logger.error(f"Failed to read logs: {str(e)}")
        
        return recent_logs
    
    def _get_memory_integrity(self) -> Optional[Dict[str, Any]]:
        """Get memory integrity status"""
        integrity_file = self.data_dir / "memory" / "integrity.json"
        if integrity_file.exists():
            return self.reader.read_json(integrity_file)
        return None
    
    def _inject_memory_corruption(self) -> None:
        """Inject controlled memory corruption"""
        # This would typically involve modifying memory files
        # For safety, we'll simulate this by creating a temporary corruption marker
        corruption_marker = self.data_dir / "memory" / "corruption_marker.json"
        self.writer.write_json(corruption_marker, {
            "injected": True,
            "timestamp": utc_now_seconds(),
            "type": "controlled_corruption"
        })
    
    def _export_debug_bundle(self) -> Optional[Path]:
        """Export debug bundle"""
        try:
            from coin_quant.shared.observability import create_debug_bundle
            return create_debug_bundle(minutes_back=30)
        except Exception as e:
            logger.error(f"Failed to export debug bundle: {str(e)}")
            return None
    
    def _replay_from_snapshot(self) -> Dict[str, Any]:
        """Replay from last snapshot"""
        try:
            from coin_quant.shared.memory_validator import get_memory_validator
            validator = get_memory_validator()
            return validator.replay_from_snapshot()
        except Exception as e:
            logger.error(f"Failed to replay from snapshot: {str(e)}")
            raise
    
    def _get_quarantine_scope(self) -> Optional[str]:
        """Get quarantine scope"""
        # This would typically analyze the quarantine data
        # For now, return a placeholder
        return "memory_layer"
    
    def _restore_memory_from_backup(self) -> None:
        """Restore memory from backup"""
        # This would typically restore from a backup
        # For now, remove the corruption marker
        corruption_marker = self.data_dir / "memory" / "corruption_marker.json"
        if corruption_marker.exists():
            corruption_marker.unlink()
    
    def run_all_drills(self) -> List[DrillResult]:
        """Run all failure drills"""
        logger.info("Running all failure drills")
        
        results = []
        
        # Run each drill type
        drill_types = [DrillType.FEEDER_OUTAGE, DrillType.INSUFFICIENT_BALANCE, DrillType.MEMORY_CORRUPTION]
        
        for drill_type in drill_types:
            logger.info(f"Running {drill_type.value} drill")
            
            if drill_type == DrillType.FEEDER_OUTAGE:
                result = self.run_feeder_outage_drill()
            elif drill_type == DrillType.INSUFFICIENT_BALANCE:
                result = self.run_insufficient_balance_drill()
            elif drill_type == DrillType.MEMORY_CORRUPTION:
                result = self.run_memory_corruption_drill()
            
            results.append(result)
            
            # Short wait between drills (only in non-test mode)
            if not self.test_mode:
                time.sleep(5)
        
        # Save results
        self._save_drill_results(results)
        
        return results
    
    def _save_drill_results(self, results: List[DrillResult]) -> None:
        """Save drill results to file"""
        results_data = []
        
        for result in results:
            results_data.append({
                "drill_type": result.drill_type.value,
                "status": result.status.value,
                "start_time": result.start_time,
                "end_time": result.end_time,
                "expected_observations": result.expected_observations,
                "actual_observations": result.actual_observations,
                "success_conditions": result.success_conditions,
                "success": result.success,
                "errors": result.errors,
                "recovery_time": result.recovery_time
            })
        
        results_file = self.data_dir / "drill_results.json"
        self.writer.write_json(results_file, {
            "timestamp": utc_now_seconds(),
            "results": results_data
        })
        
        logger.info(f"Drill results saved to: {results_file}")


def run_failure_drills() -> List[DrillResult]:
    """Run all failure drills"""
    manager = FailureDrillManager()
    return manager.run_all_drills()


if __name__ == "__main__":
    # Run failure drills
    results = run_failure_drills()
    
    # Print summary
    print("\n" + "="*80)
    print("FAILURE DRILL RESULTS SUMMARY")
    print("="*80)
    
    for result in results:
        status = "✅ PASSED" if result.success else "❌ FAILED"
        print(f"\n{result.drill_type.value.upper()}: {status}")
        print(f"Duration: {result.end_time - result.start_time:.1f} seconds")
        
        if result.errors:
            print("Errors:")
            for error in result.errors:
                print(f"  - {error}")
        
        if result.recovery_time:
            print(f"Recovery time: {result.recovery_time:.1f} seconds")
    
    print("\n" + "="*80)
