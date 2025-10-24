"""
Inter-Service Integration Contracts
Defines explicit rules for system health and GREEN status
"""
import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .heartbeat_contracts import (get_heartbeat_age, load_heartbeat,
                                  validate_env_hash_consistency)
from .path_registry import get_absolute_path


@dataclass
class ContractViolation:
    """Contract violation details"""
    contract_name: str
    violation_type: str
    message: str
    severity: str  # "error", "warning", "info"
    timestamp: float = 0.0


@dataclass
class IntegrationContracts:
    """Integration contracts validation result"""
    symbol_set_handshake: bool = True
    freshness_chain: bool = True
    dependency_readiness: bool = True
    environment_consistency: bool = True
    writer_roles: bool = True
    violations: List[ContractViolation] = None
    timestamp: float = 0.0
    
    def __post_init__(self):
        if self.violations is None:
            self.violations = []
    
    @property
    def all_contracts_pass(self) -> bool:
        """Check if all contracts pass"""
        return (
            self.symbol_set_handshake and
            self.freshness_chain and
            self.dependency_readiness and
            self.environment_consistency and
            self.writer_roles
        )


class IntegrationContractValidator:
    """Validator for inter-service integration contracts"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.current_time = time.time()
    
    def validate_all_contracts(self) -> IntegrationContracts:
        """Validate all integration contracts"""
        contracts = IntegrationContracts()
        contracts.timestamp = self.current_time
        
        # Validate each contract
        contracts.symbol_set_handshake = self._validate_symbol_set_handshake(contracts)
        contracts.freshness_chain = self._validate_freshness_chain(contracts)
        contracts.dependency_readiness = self._validate_dependency_readiness(contracts)
        contracts.environment_consistency = self._validate_environment_consistency(contracts)
        contracts.writer_roles = self._validate_writer_roles(contracts)
        
        return contracts
    
    def _validate_symbol_set_handshake(self, contracts: IntegrationContracts) -> bool:
        """Validate symbol set handshake between services"""
        try:
            # Load heartbeats
            feeder_hb = load_heartbeat("feeder")
            ares_hb = load_heartbeat("ares")
            trader_hb = load_heartbeat("trader")
            
            if not feeder_hb or not ares_hb or not trader_hb:
                contracts.violations.append(ContractViolation(
                    contract_name="symbol_set_handshake",
                    violation_type="missing_heartbeat",
                    message="Missing heartbeats for symbol validation",
                    severity="error"
                ))
                return False
            
            # Get symbol sets
            feeder_symbols = set(feeder_hb.data.get("symbols", []))
            ares_symbols = set()
            for candidate in ares_hb.data.get("candidates", []):
                if "symbol" in candidate:
                    ares_symbols.add(candidate["symbol"])
            
            # Check symbol subset relationship
            if not ares_symbols.issubset(feeder_symbols):
                missing_symbols = ares_symbols - feeder_symbols
                contracts.violations.append(ContractViolation(
                    contract_name="symbol_set_handshake",
                    violation_type="symbol_mismatch",
                    message=f"ARES symbols not subset of Feeder: {missing_symbols}",
                    severity="error"
                ))
                return False
            
            # Check symbol casing (all should be uppercase)
            for symbol in feeder_symbols:
                if symbol != symbol.upper():
                    contracts.violations.append(ContractViolation(
                        contract_name="symbol_set_handshake",
                        violation_type="casing_violation",
                        message=f"Feeder symbol not uppercase: {symbol}",
                        severity="error"
                    ))
                    return False
            
            return True
            
        except Exception as e:
            contracts.violations.append(ContractViolation(
                contract_name="symbol_set_handshake",
                violation_type="validation_error",
                message=f"Symbol handshake validation failed: {e}",
                severity="error"
            ))
            return False
    
    def _validate_freshness_chain(self, contracts: IntegrationContracts) -> bool:
        """Validate freshness chain for critical data"""
        try:
            # Check state_bus freshness (≤30s)
            state_bus_file = get_absolute_path('state_bus')
            if state_bus_file.exists():
                state_bus_age = self.current_time - state_bus_file.stat().st_mtime
                if state_bus_age > 30:
                    contracts.violations.append(ContractViolation(
                        contract_name="freshness_chain",
                        violation_type="stale_state_bus",
                        message=f"State bus stale: {state_bus_age:.1f}s > 30s",
                        severity="error"
                    ))
                    return False
            
            # Check positions freshness (≤60s)
            positions_file = get_absolute_path('positions_snapshot')
            if positions_file.exists():
                positions_age = self.current_time - positions_file.stat().st_mtime
                if positions_age > 60:
                    contracts.violations.append(ContractViolation(
                        contract_name="freshness_chain",
                        violation_type="stale_positions",
                        message=f"Positions stale: {positions_age:.1f}s > 60s",
                        severity="error"
                    ))
                    return False
            
            # Check candidates freshness (≤150s for real signals, ≤75s for heartbeats)
            ares_hb = load_heartbeat("ares")
            if ares_hb:
                candidates_age = self.current_time - ares_hb.data.get("last_signal_update", 0)
                is_real_signal = ares_hb.data.get("is_real_signal", False)
                max_age = 150 if is_real_signal else 75
                
                if candidates_age > max_age:
                    contracts.violations.append(ContractViolation(
                        contract_name="freshness_chain",
                        violation_type="stale_candidates",
                        message=f"Candidates stale: {candidates_age:.1f}s > {max_age}s",
                        severity="error"
                    ))
                    return False
            
            # Check trader health freshness (≤15s)
            trader_hb = load_heartbeat("trader")
            if trader_hb:
                trader_age = self.current_time - trader_hb.timestamp
                if trader_age > 15:
                    contracts.violations.append(ContractViolation(
                        contract_name="freshness_chain",
                        violation_type="stale_trader",
                        message=f"Trader heartbeat stale: {trader_age:.1f}s > 15s",
                        severity="error"
                    ))
                    return False
            
            return True
            
        except Exception as e:
            contracts.violations.append(ContractViolation(
                contract_name="freshness_chain",
                violation_type="validation_error",
                message=f"Freshness chain validation failed: {e}",
                severity="error"
            ))
            return False
    
    def _validate_dependency_readiness(self, contracts: IntegrationContracts) -> bool:
        """Validate dependency readiness"""
        try:
            # Check trader readiness
            trader_hb = load_heartbeat("trader")
            if not trader_hb:
                contracts.violations.append(ContractViolation(
                    contract_name="dependency_readiness",
                    violation_type="missing_trader",
                    message="Trader heartbeat missing",
                    severity="error"
                ))
                return False
            
            # Check exchange info loaded
            if not trader_hb.data.get("exchange_info_loaded", False):
                contracts.violations.append(ContractViolation(
                    contract_name="dependency_readiness",
                    violation_type="exchange_info_not_loaded",
                    message="Trader exchange info not loaded",
                    severity="error"
                ))
                return False
            
            # Check last REST OK timestamp
            last_rest_ok = trader_hb.data.get("last_rest_ok_ts", 0)
            if self.current_time - last_rest_ok > 60:
                contracts.violations.append(ContractViolation(
                    contract_name="dependency_readiness",
                    violation_type="stale_rest_connection",
                    message=f"Trader REST connection stale: {self.current_time - last_rest_ok:.1f}s > 60s",
                    severity="error"
                ))
                return False
            
            # Check balances freshness
            balances_fresh_ts = trader_hb.data.get("balances_fresh_ts", 0)
            if self.current_time - balances_fresh_ts > 300:  # 5 minutes
                contracts.violations.append(ContractViolation(
                    contract_name="dependency_readiness",
                    violation_type="stale_balances",
                    message=f"Trader balances stale: {self.current_time - balances_fresh_ts:.1f}s > 300s",
                    severity="error"
                ))
                return False
            
            # Check circuit breaker
            if trader_hb.data.get("circuit_breaker_active", False):
                contracts.violations.append(ContractViolation(
                    contract_name="dependency_readiness",
                    violation_type="circuit_breaker_active",
                    message="Trader circuit breaker is active",
                    severity="error"
                ))
                return False
            
            return True
            
        except Exception as e:
            contracts.violations.append(ContractViolation(
                contract_name="dependency_readiness",
                violation_type="validation_error",
                message=f"Dependency readiness validation failed: {e}",
                severity="error"
            ))
            return False
    
    def _validate_environment_consistency(self, contracts: IntegrationContracts) -> bool:
        """Validate environment consistency across services"""
        try:
            if not validate_env_hash_consistency():
                contracts.violations.append(ContractViolation(
                    contract_name="environment_consistency",
                    violation_type="env_hash_mismatch",
                    message="ENV_HASH mismatch across services",
                    severity="error"
                ))
                return False
            
            return True
            
        except Exception as e:
            contracts.violations.append(ContractViolation(
                contract_name="environment_consistency",
                violation_type="validation_error",
                message=f"Environment consistency validation failed: {e}",
                severity="error"
            ))
            return False
    
    def _validate_writer_roles(self, contracts: IntegrationContracts) -> bool:
        """Validate single-writer policy"""
        try:
            # Check that critical files exist and are being written
            critical_files = [
                ("state_bus", "feeder"),
                ("positions_snapshot", "positions"),
                ("candidates_ndjson", "ares")
            ]
            
            for file_key, expected_writer in critical_files:
                file_path = get_absolute_path(file_key)
                if not file_path.exists():
                    contracts.violations.append(ContractViolation(
                        contract_name="writer_roles",
                        violation_type="missing_file",
                        message=f"Critical file missing: {file_key} (expected writer: {expected_writer})",
                        severity="error"
                    ))
                    return False
                
                # Check file age (should be recent)
                file_age = self.current_time - file_path.stat().st_mtime
                if file_age > 300:  # 5 minutes
                    contracts.violations.append(ContractViolation(
                        contract_name="writer_roles",
                        violation_type="stale_file",
                        message=f"File stale: {file_key} age {file_age:.1f}s > 300s",
                        severity="error"
                    ))
                    return False
            
            return True
            
        except Exception as e:
            contracts.violations.append(ContractViolation(
                contract_name="writer_roles",
                violation_type="validation_error",
                message=f"Writer roles validation failed: {e}",
                severity="error"
            ))
            return False


def validate_integration_contracts() -> IntegrationContracts:
    """Validate all integration contracts"""
    validator = IntegrationContractValidator()
    return validator.validate_all_contracts()


def get_contract_status_summary(contracts: IntegrationContracts) -> str:
    """Get human-readable contract status summary"""
    if contracts.all_contracts_pass:
        return "✅ All integration contracts pass"
    
    violations = contracts.violations
    error_count = sum(1 for v in violations if v.severity == "error")
    warning_count = sum(1 for v in violations if v.severity == "warning")
    
    summary = f"❌ {error_count} errors, {warning_count} warnings"
    
    if error_count > 0:
        summary += "\nErrors:"
        for v in violations:
            if v.severity == "error":
                summary += f"\n  • {v.contract_name}: {v.message}"
    
    return summary


if __name__ == '__main__':
    # Test integration contracts
    print("Integration Contracts Test:")
    
    contracts = validate_integration_contracts()
    print(f"All contracts pass: {contracts.all_contracts_pass}")
    print(f"Summary: {get_contract_status_summary(contracts)}")
    
    if contracts.violations:
        print("\nViolations:")
        for violation in contracts.violations:
            print(f"  {violation.severity.upper()}: {violation.contract_name} - {violation.message}")