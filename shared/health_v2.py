"""
HealthV2 - GREEN-by-Design Gating System
Comprehensive health validation with 7 core probes
"""
import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .env_loader import get_env_hash
from .env_ssot import read_ssot_snapshot
from .heartbeat_contracts import (get_heartbeat_age, load_heartbeat,
                                  validate_heartbeat_freshness)
from .integration_contracts import (IntegrationContracts,
                                    validate_integration_contracts)
from .path_registry import get_absolute_path


@dataclass
class ProbeResult:
    """Individual probe result"""
    probe_name: str
    status: bool
    message: str
    age_seconds: float = 0.0
    threshold_seconds: float = 0.0
    timestamp: float = 0.0


@dataclass
class HealthV2Status:
    """HealthV2 overall status"""
    ws_stream_databus: bool = False
    positions_snapshot: bool = False
    ares_signal_flow: bool = False
    trader_readiness: bool = False
    env_drift: bool = False
    integration_contracts: bool = False
    autoheal_recovery: bool = False
    global_status: str = "RED"
    safe_to_trade: bool = False
    probe_results: List[ProbeResult] = None
    violations: List[str] = None
    timestamp: float = 0.0
    total_probes: int = 7
    green_count: int = 0
    
    def __post_init__(self):
        if self.probe_results is None:
            self.probe_results = []
        if self.violations is None:
            self.violations = []
    
    @property
    def is_green(self) -> bool:
        """Check if all probes are GREEN"""
        return (
            self.ws_stream_databus and
            self.positions_snapshot and
            self.ares_signal_flow and
            self.trader_readiness and
            self.env_drift and
            self.integration_contracts and
            self.autoheal_recovery
        )
    


class HealthV2Validator:
    """HealthV2 validator with 7 core probes"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.current_time = time.time()
    
    def validate_all_probes(self) -> HealthV2Status:
        """Validate all 7 core probes"""
        status = HealthV2Status()
        status.timestamp = self.current_time
        
        # Validate each probe
        status.ws_stream_databus = self._validate_ws_stream_databus(status)
        status.positions_snapshot = self._validate_positions_snapshot(status)
        status.ares_signal_flow = self._validate_ares_signal_flow(status)
        status.trader_readiness = self._validate_trader_readiness(status)
        status.env_drift = self._validate_env_drift(status)
        status.integration_contracts = self._validate_integration_contracts(status)
        status.autoheal_recovery = self._validate_autoheal_recovery(status)
        
        # Calculate green count
        status.green_count = sum([
            status.ws_stream_databus,
            status.positions_snapshot,
            status.ares_signal_flow,
            status.trader_readiness,
            status.env_drift,
            status.integration_contracts,
            status.autoheal_recovery
        ])
        
        # Determine global status
        if status.is_green:
            status.global_status = "GREEN"
            status.safe_to_trade = True
        else:
            status.global_status = "RED"
            status.safe_to_trade = False
        
        return status
    
    def _validate_ws_stream_databus(self, status: HealthV2Status) -> bool:
        """Validate WebSocket stream and databus"""
        try:
            # Check state_bus file exists and is fresh
            state_bus_file = get_absolute_path('state_bus')
            if not state_bus_file.exists():
                status.probe_results.append(ProbeResult(
                    probe_name="ws_stream_databus",
                    status=False,
                    message="State bus file missing",
                    age_seconds=float('inf'),
                    threshold_seconds=30.0
                ))
                return False
            
            # Check file age
            file_age = self.current_time - state_bus_file.stat().st_mtime
            if file_age > 30:
                status.probe_results.append(ProbeResult(
                    probe_name="ws_stream_databus",
                    status=False,
                    message=f"State bus stale: {file_age:.1f}s > 30s",
                    age_seconds=file_age,
                    threshold_seconds=30.0
                ))
                return False
            
            # Check file content
            try:
                with open(state_bus_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Check for required fields
                if 'symbols' not in data and 'prices' not in data:
                    status.probe_results.append(ProbeResult(
                        probe_name="ws_stream_databus",
                        status=False,
                        message="State bus missing required fields",
                        age_seconds=file_age,
                        threshold_seconds=30.0
                    ))
                    return False
                
                # Check symbol casing (all should be uppercase)
                # Support both old format (symbols at root) and new format (symbols in prices)
                symbols = data.get('symbols', [])
                if not symbols and 'prices' in data and 'symbols' in data['prices']:
                    symbols = data['prices']['symbols']
                for symbol in symbols:
                    if symbol != symbol.upper():
                        status.probe_results.append(ProbeResult(
                            probe_name="ws_stream_databus",
                            status=False,
                            message=f"Symbol not uppercase: {symbol}",
                            age_seconds=file_age,
                            threshold_seconds=30.0
                        ))
                        return False
                
                # Check for BTCUSDT presence
                if 'BTCUSDT' not in symbols:
                    status.probe_results.append(ProbeResult(
                        probe_name="ws_stream_databus",
                        status=False,
                        message="BTCUSDT not in symbols",
                        age_seconds=file_age,
                        threshold_seconds=30.0
                    ))
                    return False
                
            except json.JSONDecodeError:
                status.probe_results.append(ProbeResult(
                    probe_name="ws_stream_databus",
                    status=False,
                    message="State bus invalid JSON",
                    age_seconds=file_age,
                    threshold_seconds=30.0
                ))
                return False
            
            status.probe_results.append(ProbeResult(
                probe_name="ws_stream_databus",
                status=True,
                message="WebSocket stream and databus healthy",
                age_seconds=file_age,
                threshold_seconds=30.0
            ))
            return True
            
        except Exception as e:
            status.probe_results.append(ProbeResult(
                probe_name="ws_stream_databus",
                status=False,
                message=f"Validation error: {e}",
                age_seconds=float('inf'),
                threshold_seconds=30.0
            ))
            return False
    
    def _validate_positions_snapshot(self, status: HealthV2Status) -> bool:
        """Validate positions snapshot"""
        try:
            # Check positions file exists and is fresh
            positions_file = get_absolute_path('positions_snapshot')
            if not positions_file.exists():
                status.probe_results.append(ProbeResult(
                    probe_name="positions_snapshot",
                    status=False,
                    message="Positions snapshot missing",
                    age_seconds=float('inf'),
                    threshold_seconds=60.0
                ))
                return False
            
            # Check file age
            file_age = self.current_time - positions_file.stat().st_mtime
            if file_age > 60:
                status.probe_results.append(ProbeResult(
                    probe_name="positions_snapshot",
                    status=False,
                    message=f"Positions snapshot stale: {file_age:.1f}s > 60s",
                    age_seconds=file_age,
                    threshold_seconds=60.0
                ))
                return False
            
            # Check file content
            try:
                with open(positions_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Check for required fields
                if 'positions' not in data or 'timestamp' not in data:
                    status.probe_results.append(ProbeResult(
                        probe_name="positions_snapshot",
                        status=False,
                        message="Positions snapshot missing required fields",
                        age_seconds=file_age,
                        threshold_seconds=60.0
                    ))
                    return False
                
                # Check canonical schema
                positions = data.get('positions', [])
                for position in positions:
                    if not isinstance(position, dict):
                        status.probe_results.append(ProbeResult(
                            probe_name="positions_snapshot",
                            status=False,
                            message="Invalid position format",
                            age_seconds=file_age,
                            threshold_seconds=60.0
                        ))
                        return False
                    
                    # Check for required fields
                    required_fields = ['symbol', 'side', 'quantity']
                    for field in required_fields:
                        if field not in position:
                            status.probe_results.append(ProbeResult(
                                probe_name="positions_snapshot",
                                status=False,
                                message=f"Position missing {field}",
                                age_seconds=file_age,
                                threshold_seconds=60.0
                            ))
                            return False
                    
                    # Check symbol casing
                    if position['symbol'] != position['symbol'].upper():
                        status.probe_results.append(ProbeResult(
                            probe_name="positions_snapshot",
                            status=False,
                            message=f"Position symbol not uppercase: {position['symbol']}",
                            age_seconds=file_age,
                            threshold_seconds=60.0
                        ))
                        return False
                
            except json.JSONDecodeError:
                status.probe_results.append(ProbeResult(
                    probe_name="positions_snapshot",
                    status=False,
                    message="Positions snapshot invalid JSON",
                    age_seconds=file_age,
                    threshold_seconds=60.0
                ))
                return False
            
            status.probe_results.append(ProbeResult(
                probe_name="positions_snapshot",
                status=True,
                message="Positions snapshot healthy",
                age_seconds=file_age,
                threshold_seconds=60.0
            ))
            return True
            
        except Exception as e:
            status.probe_results.append(ProbeResult(
                probe_name="positions_snapshot",
                status=False,
                message=f"Validation error: {e}",
                age_seconds=float('inf'),
                threshold_seconds=60.0
            ))
            return False
    
    def _validate_ares_signal_flow(self, status: HealthV2Status) -> bool:
        """Validate ARES signal flow"""
        try:
            # Check ARES heartbeat
            ares_hb = load_heartbeat("ares")
            if not ares_hb:
                status.probe_results.append(ProbeResult(
                    probe_name="ares_signal_flow",
                    status=False,
                    message="ARES heartbeat missing",
                    age_seconds=float('inf'),
                    threshold_seconds=75.0
                ))
                return False
            
            # Check heartbeat age
            heartbeat_age = self.current_time - ares_hb.timestamp
            is_real_signal = ares_hb.data.get("is_real_signal", False)
            max_age = 150 if is_real_signal else 75
            
            if heartbeat_age > max_age:
                status.probe_results.append(ProbeResult(
                    probe_name="ares_signal_flow",
                    status=False,
                    message=f"ARES heartbeat stale: {heartbeat_age:.1f}s > {max_age}s",
                    age_seconds=heartbeat_age,
                    threshold_seconds=max_age
                ))
                return False
            
            # Check candidates data
            candidates = ares_hb.data.get("candidates", [])
            is_real_signal = ares_hb.data.get("is_real_signal", False)
            
            # If no real signals and TEST_ALLOW_DEFAULT_SIGNAL is false, this is expected
            if not candidates and not is_real_signal:
                # Check if default signals are disabled
                test_allow_default = os.getenv("TEST_ALLOW_DEFAULT_SIGNAL", "false").lower() == "true"
                if not test_allow_default:
                    # This is expected behavior - no candidates when default signals are disabled
                    status.probe_results.append(ProbeResult(
                        probe_name="ares_signal_flow",
                        status=True,
                        message="ARES running (no default signals)",
                        age_seconds=heartbeat_age,
                        threshold_seconds=max_age
                    ))
                    return True
            
            if not candidates:
                status.probe_results.append(ProbeResult(
                    probe_name="ares_signal_flow",
                    status=False,
                    message="ARES no candidates",
                    age_seconds=heartbeat_age,
                    threshold_seconds=max_age
                ))
                return False
            
            # Check symbol casing
            for candidate in candidates:
                if 'symbol' in candidate and candidate['symbol'] != candidate['symbol'].upper():
                    status.probe_results.append(ProbeResult(
                        probe_name="ares_signal_flow",
                        status=False,
                        message=f"ARES candidate symbol not uppercase: {candidate['symbol']}",
                        age_seconds=heartbeat_age,
                        threshold_seconds=max_age
                    ))
                    return False
            
            status.probe_results.append(ProbeResult(
                probe_name="ares_signal_flow",
                status=True,
                message="ARES signal flow healthy",
                age_seconds=heartbeat_age,
                threshold_seconds=max_age
            ))
            return True
            
        except Exception as e:
            status.probe_results.append(ProbeResult(
                probe_name="ares_signal_flow",
                status=False,
                message=f"Validation error: {e}",
                age_seconds=float('inf'),
                threshold_seconds=75.0
            ))
            return False
    
    def _validate_trader_readiness(self, status: HealthV2Status) -> bool:
        """Validate trader readiness"""
        try:
            # Check trader heartbeat
            trader_hb = load_heartbeat("trader")
            if not trader_hb:
                status.probe_results.append(ProbeResult(
                    probe_name="trader_readiness",
                    status=False,
                    message="Trader heartbeat missing",
                    age_seconds=float('inf'),
                    threshold_seconds=15.0
                ))
                return False
            
            # Check heartbeat age
            heartbeat_age = self.current_time - trader_hb.timestamp
            if heartbeat_age > 15:
                status.probe_results.append(ProbeResult(
                    probe_name="trader_readiness",
                    status=False,
                    message=f"Trader heartbeat stale: {heartbeat_age:.1f}s > 15s",
                    age_seconds=heartbeat_age,
                    threshold_seconds=15.0
                ))
                return False
            
            # Check readiness conditions
            if not trader_hb.data.get("exchange_info_loaded", False):
                status.probe_results.append(ProbeResult(
                    probe_name="trader_readiness",
                    status=False,
                    message="Trader exchange info not loaded",
                    age_seconds=heartbeat_age,
                    threshold_seconds=15.0
                ))
                return False
            
            last_rest_ok = trader_hb.data.get("last_rest_ok_ts", 0)
            if self.current_time - last_rest_ok > 60:
                status.probe_results.append(ProbeResult(
                    probe_name="trader_readiness",
                    status=False,
                    message=f"Trader REST connection stale: {self.current_time - last_rest_ok:.1f}s > 60s",
                    age_seconds=heartbeat_age,
                    threshold_seconds=15.0
                ))
                return False
            
            balances_fresh_ts = trader_hb.data.get("balances_fresh_ts", 0)
            if self.current_time - balances_fresh_ts > 300:
                status.probe_results.append(ProbeResult(
                    probe_name="trader_readiness",
                    status=False,
                    message=f"Trader balances stale: {self.current_time - balances_fresh_ts:.1f}s > 300s",
                    age_seconds=heartbeat_age,
                    threshold_seconds=15.0
                ))
                return False
            
            if trader_hb.data.get("circuit_breaker_active", False):
                status.probe_results.append(ProbeResult(
                    probe_name="trader_readiness",
                    status=False,
                    message="Trader circuit breaker active",
                    age_seconds=heartbeat_age,
                    threshold_seconds=15.0
                ))
                return False
            
            status.probe_results.append(ProbeResult(
                probe_name="trader_readiness",
                status=True,
                message="Trader readiness healthy",
                age_seconds=heartbeat_age,
                threshold_seconds=15.0
            ))
            return True
            
        except Exception as e:
            status.probe_results.append(ProbeResult(
                probe_name="trader_readiness",
                status=False,
                message=f"Validation error: {e}",
                age_seconds=float('inf'),
                threshold_seconds=15.0
            ))
            return False
    
    def _validate_env_drift(self, status: HealthV2Status) -> bool:
        """Validate environment drift using SSOT"""
        try:
            # Read SSOT snapshot
            ssot = read_ssot_snapshot()
            if not ssot:
                status.probe_results.append(ProbeResult(
                    probe_name="env_drift",
                    status=False,
                    message="SSOT snapshot missing",
                    age_seconds=float('inf'),
                    threshold_seconds=0.0
                ))
                return False
            
            # Get current environment hash
            current_env_hash = get_env_hash()
            ssot_env_hash = ssot.get('env_hash', '')
            
            # Check hash consistency
            if current_env_hash != ssot_env_hash:
                status.probe_results.append(ProbeResult(
                    probe_name="env_drift",
                    status=False,
                    message=f"ENV_HASH mismatch: current={current_env_hash[:8]}, ssot={ssot_env_hash[:8]}",
                    age_seconds=0.0,
                    threshold_seconds=0.0
                ))
                return False
            
            # Check SSOT age
            ssot_updated_at = ssot.get('updated_at', '')
            if ssot_updated_at:
                try:
                    from datetime import datetime
                    ssot_time = datetime.fromisoformat(ssot_updated_at.replace('Z', '+00:00'))
                    ssot_age = (datetime.now(ssot_time.tzinfo) - ssot_time).total_seconds()
                    
                    if ssot_age > 300:  # 5 minutes
                        status.probe_results.append(ProbeResult(
                            probe_name="env_drift",
                            status=False,
                            message=f"SSOT stale: {ssot_age:.1f}s > 300s",
                            age_seconds=ssot_age,
                            threshold_seconds=300.0
                        ))
                        return False
                except Exception as e:
                    self.logger.warning(f"Failed to parse SSOT timestamp: {e}")
            
            status.probe_results.append(ProbeResult(
                probe_name="env_drift",
                status=True,
                message=f"Environment consistent (hash: {current_env_hash[:8]})",
                age_seconds=0.0,
                threshold_seconds=0.0
            ))
            return True
            
        except Exception as e:
            status.probe_results.append(ProbeResult(
                probe_name="env_drift",
                status=False,
                message=f"Validation error: {e}",
                age_seconds=0.0,
                threshold_seconds=0.0
            ))
            return False
    
    def _validate_integration_contracts(self, status: HealthV2Status) -> bool:
        """Validate integration contracts - allow empty but fresh artifacts"""
        try:
            # Check required artifacts exist and are fresh
            required_artifacts = [
                ("candidates_ndjson", "ares", 120),  # 2 minutes
                ("positions_snapshot", "positions", 120)  # 2 minutes
            ]
            
            missing_artifacts = []
            stale_artifacts = []
            
            for artifact_name, expected_writer, max_age in required_artifacts:
                artifact_path = get_absolute_path(artifact_name)
                
                if not artifact_path.exists():
                    missing_artifacts.append(artifact_name)
                    continue
                
                # Check file age
                file_age = self.current_time - artifact_path.stat().st_mtime
                if file_age > max_age:
                    stale_artifacts.append(f"{artifact_name} ({file_age:.1f}s)")
                    continue
                
                # For candidates_ndjson, check if it has valid JSON header
                if artifact_name == "candidates_ndjson":
                    try:
                        with open(artifact_path, 'r', encoding='utf-8') as f:
                            first_line = f.readline().strip()
                            if first_line:
                                header = json.loads(first_line)
                                if header.get('writer') != expected_writer:
                                    stale_artifacts.append(f"{artifact_name} (wrong writer: {header.get('writer')})")
                                    continue
                    except Exception as e:
                        stale_artifacts.append(f"{artifact_name} (invalid JSON: {e})")
                        continue
            
            # Report issues
            if missing_artifacts or stale_artifacts:
                issues = []
                if missing_artifacts:
                    issues.append(f"missing: {', '.join(missing_artifacts)}")
                if stale_artifacts:
                    issues.append(f"stale: {', '.join(stale_artifacts)}")
                
                status.probe_results.append(ProbeResult(
                    probe_name="integration_contracts",
                    status=False,
                    message=f"Integration contracts failed: {'; '.join(issues)}",
                    age_seconds=0.0,
                    threshold_seconds=0.0
                ))
                return False
            
            status.probe_results.append(ProbeResult(
                probe_name="integration_contracts",
                status=True,
                message="Integration contracts healthy (all artifacts fresh)",
                age_seconds=0.0,
                threshold_seconds=0.0
            ))
            return True
            
        except Exception as e:
            status.probe_results.append(ProbeResult(
                probe_name="integration_contracts",
                status=False,
                message=f"Validation error: {e}",
                age_seconds=0.0,
                threshold_seconds=0.0
            ))
            return False
    
    def _validate_autoheal_recovery(self, status: HealthV2Status) -> bool:
        """Validate autoheal recovery"""
        try:
            # Check if autoheal is enabled
            autoheal_enabled = os.getenv("AUTOHEAL_ENABLED", "false").lower() == "true"
            
            if not autoheal_enabled:
                status.probe_results.append(ProbeResult(
                    probe_name="autoheal_recovery",
                    status=True,  # SKIPPED counts as success
                    message="SKIPPED (AUTOHEAL_ENABLED=false)",
                    age_seconds=0.0,
                    threshold_seconds=0.0
                ))
                return True
            
            # Check autoheal heartbeat
            autoheal_hb = load_heartbeat("autoheal")
            if not autoheal_hb:
                status.probe_results.append(ProbeResult(
                    probe_name="autoheal_recovery",
                    status=False,
                    message="Autoheal heartbeat missing",
                    age_seconds=float('inf'),
                    threshold_seconds=30.0
                ))
                return False
            
            # Check heartbeat age
            heartbeat_age = self.current_time - autoheal_hb.timestamp
            if heartbeat_age > 30:  # 30 seconds threshold
                status.probe_results.append(ProbeResult(
                    probe_name="autoheal_recovery",
                    status=False,
                    message=f"Autoheal heartbeat stale: {heartbeat_age:.1f}s > 30s",
                    age_seconds=heartbeat_age,
                    threshold_seconds=30.0
                ))
                return False
            
            # Check for repeated failures
            failure_count = autoheal_hb.data.get("failure_count", 0)
            if failure_count > 3:
                status.probe_results.append(ProbeResult(
                    probe_name="autoheal_recovery",
                    status=False,
                    message=f"Autoheal repeated failures: {failure_count} > 3",
                    age_seconds=heartbeat_age,
                    threshold_seconds=30.0
                ))
                return False
            
            status.probe_results.append(ProbeResult(
                probe_name="autoheal_recovery",
                status=True,
                message=f"Autoheal recovery healthy ({heartbeat_age:.1f}s)",
                age_seconds=heartbeat_age,
                threshold_seconds=30.0
            ))
            return True
            
        except Exception as e:
            status.probe_results.append(ProbeResult(
                probe_name="autoheal_recovery",
                status=False,
                message=f"Validation error: {e}",
                age_seconds=float('inf'),
                threshold_seconds=60.0
            ))
            return False


def validate_health_v2() -> HealthV2Status:
    """Validate HealthV2 status"""
    validator = HealthV2Validator()
    return validator.validate_all_probes()


def get_health_v2_summary(status: HealthV2Status) -> str:
    """Get human-readable HealthV2 summary"""
    if status.is_green:
        return f"🟢 GREEN ({status.green_count}/7) - Safe to trade"
    else:
        failed_probes = [p.probe_name for p in status.probe_results if not p.status]
        return f"🔴 RED ({status.green_count}/7) - Failed: {', '.join(failed_probes)}"


def is_system_ready_for_auto_trading() -> bool:
    """Check if system is ready for auto trading"""
    status = validate_health_v2()
    return status.safe_to_trade


if __name__ == '__main__':
    # Test HealthV2
    print("HealthV2 Test:")
    
    status = validate_health_v2()
    print(f"Global status: {status.global_status}")
    print(f"Safe to trade: {status.safe_to_trade}")
    print(f"Summary: {get_health_v2_summary(status)}")
    
    print("\nProbe results:")
    for probe in status.probe_results:
        status_icon = "✅" if probe.status else "❌"
        print(f"  {status_icon} {probe.probe_name}: {probe.message}")
        if probe.age_seconds > 0:
            print(f"    Age: {probe.age_seconds:.1f}s (threshold: {probe.threshold_seconds:.1f}s)")