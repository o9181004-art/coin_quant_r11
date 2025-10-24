"""
Heartbeat System - Service readiness contracts and health monitoring
Provides standardized heartbeats for all services with drift detection
"""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .env_loader import get_env_hash
from .path_registry import get_absolute_path
from .io_safe import atomic_write, append_ndjson_safe


class HeartbeatManager:
    """Centralized heartbeat management for all services"""
    
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.env_hash = get_env_hash()
        self.start_time = int(time.time())
        self.entrypoint_ok = False
    
    def log_entrypoint_ok(self):
        """Log successful service entrypoint"""
        self.entrypoint_ok = True
        print(f"ENTRYPOINT_OK module={self.service_name}")
    
    def write_heartbeat(self, data: Dict[str, Any]):
        """Write service heartbeat with standard format"""
        # Add standard fields
        heartbeat = {
            "timestamp": int(time.time()),
            "service": self.service_name,
            "env_hash": self.env_hash,
            "entrypoint_ok": self.entrypoint_ok,
            "uptime_seconds": int(time.time()) - self.start_time,
            **data
        }
        
        # Write to service-specific heartbeat file
        heartbeat_file = get_absolute_path('shared_data_health') / f"{self.service_name}.json"
        get_absolute_path('shared_data_health').mkdir(parents=True, exist_ok=True)
        
        atomic_write(heartbeat_file, json.dumps(heartbeat, separators=(',', ':')))


class FeederHeartbeat(HeartbeatManager):
    """Feeder service heartbeat"""
    
    def __init__(self):
        super().__init__("feeder")
        self.last_prices_update = 0
        self.symbols = set()
    
    def update_prices(self, symbols: List[str]):
        """Update price data heartbeat"""
        self.symbols = set(symbol.upper() for symbol in symbols)  # Always UPPERCASE
        self.last_prices_update = int(time.time())
        
        self.write_heartbeat({
            "state": "state_bus",
            "last_ts": self.last_prices_update,
            "prices": {
                "symbols": list(self.symbols),
                "symbol_count": len(self.symbols)
            }
        })


class TraderHeartbeat(HeartbeatManager):
    """Trader service heartbeat"""
    
    def __init__(self):
        super().__init__("trader")
        self.exchange_info_loaded = False
        self.last_rest_ok_ts = 0
        self.balances_fresh_ts = 0
        self.circuit_breaker_active = False
    
    def update_health(self, 
                     exchange_info_loaded: bool = None,
                     last_rest_ok_ts: int = None,
                     balances_fresh_ts: int = None,
                     circuit_breaker_active: bool = None):
        """Update trader health status"""
        
        if exchange_info_loaded is not None:
            self.exchange_info_loaded = exchange_info_loaded
        if last_rest_ok_ts is not None:
            self.last_rest_ok_ts = last_rest_ok_ts
        if balances_fresh_ts is not None:
            self.balances_fresh_ts = balances_fresh_ts
        if circuit_breaker_active is not None:
            self.circuit_breaker_active = circuit_breaker_active
        
        self.write_heartbeat({
            "state": "health",
            "timestamp": int(time.time()),
            "entrypoint_ok": self.entrypoint_ok,
            "exchange_info_loaded": self.exchange_info_loaded,
            "last_rest_ok_ts": self.last_rest_ok_ts,
            "balances": {
                "fresh_ts": self.balances_fresh_ts
            },
            "circuit_breaker": {
                "active": self.circuit_breaker_active
            }
        })


class PositionsHeartbeat(HeartbeatManager):
    """Positions data heartbeat with canonical schema"""
    
    def __init__(self):
        super().__init__("positions")
    
    def update_positions(self, positions: Dict[str, Any]):
        """Update positions with canonical schema"""
        # Canonical positions schema
        canonical_positions = {
            "timestamp": int(time.time()),
            "positions": positions or {},  # Ensure positions dict exists
            "positions_count": len(positions) if positions else 0
        }
        
        # Write to positions.json
        positions_file = get_absolute_path('shared_data') / "positions.json"
        atomic_write(positions_file, json.dumps(canonical_positions, separators=(',', ':')))
        
        # Also write heartbeat
        self.write_heartbeat({
            "state": "positions",
            "positions_count": canonical_positions["positions_count"],
            "last_update": canonical_positions["timestamp"]
        })


class AresHeartbeat(HeartbeatManager):
    """ARES signal heartbeat"""
    
    def __init__(self):
        super().__init__("ares")
        self.last_signal_ts = 0
        self.last_heartbeat_ts = 0
        self.symbols = set()
    
    def update_candidates(self, candidates: List[Dict[str, Any]]):
        """Update ARES candidates (heartbeat or real signals)"""
        now = int(time.time())
        
        # Ensure all symbols are UPPERCASE
        for candidate in candidates:
            if 'symbol' in candidate:
                candidate['symbol'] = candidate['symbol'].upper()
                self.symbols.add(candidate['symbol'])
        
        # Determine if this is a real signal run or heartbeat
        is_real_signal = len(candidates) > 0
        
        if is_real_signal:
            self.last_signal_ts = now
            # Real signal run - append to candidates.ndjson
            candidates_file = get_absolute_path('shared_data') / "candidates.ndjson"
            for candidate in candidates:
                append_ndjson_safe(candidates_file, candidate)
        else:
            self.last_heartbeat_ts = now
            # Heartbeat only - just update timestamp
        
        # Write heartbeat
        self.write_heartbeat({
            "state": "candidates",
            "last_signal_ts": self.last_signal_ts,
            "last_heartbeat_ts": self.last_heartbeat_ts,
            "symbols": list(self.symbols),
            "candidate_count": len(candidates)
        })


class HealthV2:
    """Health v2 with integration contracts and drift detection"""
    
    def __init__(self):
        self.health_file = get_absolute_path('shared_data_health') / "health.json"
        get_absolute_path('shared_data_health').mkdir(parents=True, exist_ok=True)
    
    def check_env_drift(self) -> Dict[str, Any]:
        """Check for environment drift across services"""
        now = int(time.time())
        env_hashes = {}
        
        # Collect env hashes from all services
        for service in ['feeder', 'trader', 'positions', 'ares']:
            heartbeat_file = get_absolute_path('shared_data_health') / f"{service}.json"
            if heartbeat_file.exists():
                try:
                    with open(heartbeat_file, 'r') as f:
                        data = json.load(f)
                        env_hashes[service] = data.get('env_hash')
                except Exception:
                    pass
        
        # Check if all hashes are the same
        unique_hashes = set(env_hashes.values())
        is_drift = len(unique_hashes) > 1
        
        return {
            "status": "OK" if not is_drift else "DRIFT",
            "reason": f"ENV_HASH mismatch: {env_hashes}" if is_drift else None,
            "env_hashes": env_hashes
        }
    
    def check_integration_contracts(self) -> Dict[str, Any]:
        """Check inter-service integration contracts"""
        now = int(time.time())
        violations = []
        
        try:
            # Load service heartbeats
            feeder_data = self._load_heartbeat('feeder')
            ares_data = self._load_heartbeat('ares')
            positions_data = self._load_heartbeat('positions')
            
            # Symbol set handshake check
            feeder_symbols = set(feeder_data.get('prices_symbols', []))
            ares_symbols = set(ares_data.get('symbols', []))
            positions_symbols = set()
            
            # Load positions symbols
            positions_file = get_absolute_path('positions_snapshot')
            if positions_file.exists():
                with open(positions_file, 'r') as f:
                    pos_data = json.load(f)
                    positions_symbols = set(pos_data.get('positions', {}).keys())
            
            # Check subset relationships
            if ares_symbols and not ares_symbols.issubset(feeder_symbols):
                violations.append(f"ARES symbols {ares_symbols} not subset of Feeder symbols {feeder_symbols}")
            
            if positions_symbols and not positions_symbols.issubset(feeder_symbols):
                violations.append(f"Positions symbols {positions_symbols} not subset of Feeder symbols {feeder_symbols}")
            
            # Check symbol casing
            for symbol_set, name in [(feeder_symbols, 'Feeder'), (ares_symbols, 'ARES'), (positions_symbols, 'Positions')]:
                for symbol in symbol_set:
                    if symbol != symbol.upper():
                        violations.append(f"{name} symbol {symbol} not UPPERCASE")
            
            return {
                "status": "OK" if not violations else "VIOLATION",
                "reason": f"CASING_OR_SYMBOL_SET_VIOLATION: {violations}" if violations else None,
                "violations": violations
            }
            
        except Exception as e:
            return {
                "status": "ERROR",
                "reason": f"Integration contract check failed: {e}",
                "violations": []
            }
    
    def check_freshness_chain(self) -> Dict[str, Any]:
        """Check freshness chain across services"""
        now = int(time.time())
        
        try:
            # Load heartbeats
            feeder_data = self._load_heartbeat('feeder')
            trader_data = self._load_heartbeat('trader')
            ares_data = self._load_heartbeat('ares')
            positions_data = self._load_heartbeat('positions')
            
            freshness_issues = []
            
            # Check state_bus freshness (≤60s)
            try:
                state_bus_file = get_absolute_path('state_bus')
                if state_bus_file.exists():
                    with open(state_bus_file, 'r') as f:
                        state_bus_data = json.load(f)
                    state_bus_age = now - state_bus_data.get('last_updated', 0)
                    if state_bus_age > 60:
                        freshness_issues.append(f"state_bus stale {state_bus_age}s")
                else:
                    freshness_issues.append("state_bus file missing")
            except Exception as e:
                freshness_issues.append(f"state_bus read error: {str(e)[:50]}")
            
            # Check positions freshness (≤120s)
            positions_age = now - positions_data.get('last_update', 0)
            if positions_age > 120:
                freshness_issues.append(f"positions stale {positions_age}s")
            
            # Check ARES freshness (≤120s)
            ares_age = now - max(ares_data.get('last_signal_ts', 0), ares_data.get('last_heartbeat_ts', 0))
            if ares_age > 120:
                freshness_issues.append(f"ares_signal_flow stale {ares_age}s")
            
            # Check trader health freshness (≤120s)
            trader_age = now - trader_data.get('timestamp', 0)
            if trader_age > 120:
                freshness_issues.append(f"trader_health stale {trader_age}s")
            
            return {
                "status": "OK" if not freshness_issues else "STALE",
                "reason": f"Freshness violations: {freshness_issues}" if freshness_issues else None,
                "issues": freshness_issues
            }
            
        except Exception as e:
            return {
                "status": "ERROR",
                "reason": f"Freshness check failed: {e}",
                "issues": []
            }
    
    def check_trader_readiness(self) -> Dict[str, Any]:
        """Check trader readiness conditions"""
        now = int(time.time())
        
        try:
            trader_data = self._load_heartbeat('trader')
            
            readiness_issues = []
            
            # Check exchange_info_loaded
            if not trader_data.get('exchange_info_loaded', False):
                readiness_issues.append("exchange_info_loaded=false")
            
            # Check last_rest_ok_ts age (≤60s)
            rest_age = now - trader_data.get('last_rest_ok_ts', 0)
            if rest_age > 60:
                readiness_issues.append(f"last_rest_ok_ts stale {rest_age}s")
            
            # Check balances freshness (≤120s)
            balances_age = now - trader_data.get('balances', {}).get('fresh_ts', 0)
            if balances_age > 120:
                readiness_issues.append(f"balances stale {balances_age}s")
            
            # Check circuit breaker
            if trader_data.get('circuit_breaker', {}).get('active', False):
                readiness_issues.append("circuit_breaker active")
            
            return {
                "status": "OK" if not readiness_issues else "NOT_READY",
                "reason": f"Trader readiness issues: {readiness_issues}" if readiness_issues else None,
                "issues": readiness_issues
            }
            
        except Exception as e:
            return {
                "status": "ERROR",
                "reason": f"Trader readiness check failed: {e}",
                "issues": []
            }
    
    def _load_heartbeat(self, service: str) -> Dict[str, Any]:
        """Load service heartbeat data"""
        heartbeat_file = get_absolute_path('shared_data_health') / f"{service}.json"
        if not heartbeat_file.exists():
            return {}
        
        try:
            with open(heartbeat_file, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    
    def check_ui_status(self) -> Dict[str, Any]:
        """Check UI status - WARN only, does not affect trading gates"""
        try:
            # Check for UI build errors
            ui_error_log = get_absolute_path('logs') / "ui_build_errors.log"
            ui_has_errors = False
            ui_error_details = []
            
            if ui_error_log.exists():
                try:
                    with open(ui_error_log, 'r', encoding='utf-8') as f:
                        content = f.read()
                        if content.strip():
                            ui_has_errors = True
                            # Get last few lines
                            lines = content.strip().split('\n')
                            ui_error_details = lines[-3:] if len(lines) >= 3 else lines
                except Exception:
                    pass
            
            # Check for LKG UI status
            lkg_log = get_absolute_path('logs') / "lkg_ui.log"
            lkg_has_issues = False
            lkg_details = []
            
            if lkg_log.exists():
                try:
                    with open(lkg_log, 'r', encoding='utf-8') as f:
                        content = f.read()
                        if "ERROR" in content or "FAILED" in content:
                            lkg_has_issues = True
                            lines = content.strip().split('\n')
                            lkg_details = [line for line in lines if "ERROR" in line or "FAILED" in line][-2:]
                except Exception:
                    pass
            
            # UI issues are warnings only - do not affect trading gates
            ui_issues = []
            if ui_has_errors:
                ui_issues.append(f"UI build errors: {ui_error_details}")
            if lkg_has_issues:
                ui_issues.append(f"LKG UI issues: {lkg_details}")
            
            return {
                "status": "WARN" if ui_issues else "OK",
                "reason": f"UI issues (non-critical): {ui_issues}" if ui_issues else None,
                "issues": ui_issues,
                "trading_affected": False  # UI issues never affect trading
            }
            
        except Exception as e:
            return {
                "status": "WARN",
                "reason": f"UI status check failed: {e}",
                "issues": [f"UI check error: {e}"],
                "trading_affected": False
            }
    
    def check_health_emitter_status(self) -> Dict[str, Any]:
        """Check health emitter status - WARN only, does not affect trading gates"""
        try:
            # Use EnvironmentManager.get_health_path() for single source of path
            from .environment_manager import get_health_path
            health_file = get_health_path()
            
            if not health_file.exists():
                return {
                    "status": "WARN",
                    "reason": "Health emitter file not found",
                    "issues": ["health.json missing"],
                    "trading_affected": False  # Health emitter issues never affect trading
                }
            
            # Check file age
            current_time = time.time()
            file_age = current_time - health_file.stat().st_mtime
            health_ttl_sec = 5  # HEALTH_TTL_SEC=5 by default
            
            if file_age > health_ttl_sec:
                return {
                    "status": "WARN",
                    "reason": f"Health emitter stale: {file_age:.1f}s > {health_ttl_sec}s",
                    "issues": [f"STALE: {file_age:.1f}s"],
                    "trading_affected": False  # Health emitter issues never affect trading
                }
            
            # Try to parse the file
            try:
                # Tolerant reading: try utf-8 first, then utf-8-sig on failure
                try:
                    with open(health_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                        content = content.rstrip('\n\r')
                        data = json.loads(content)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    # Retry with utf-8-sig (BOM handling)
                    with open(health_file, 'r', encoding='utf-8-sig') as f:
                        content = f.read()
                        content = content.rstrip('\n\r')
                        data = json.loads(content)
                
                # Check if it's from health_emitter
                producer = data.get("producer", "unknown")
                if producer != "health_emitter":
                    return {
                        "status": "WARN",
                        "reason": f"Health emitter producer mismatch: {producer}",
                        "issues": [f"PARSE_ERROR: wrong producer"],
                        "trading_affected": False
                    }
                
                return {
                    "status": "OK",
                    "reason": None,
                    "issues": [],
                    "trading_affected": False
                }
                
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                return {
                    "status": "WARN",
                    "reason": f"Health emitter parse error: {e}",
                    "issues": [f"PARSE_ERROR: {str(e)[:50]}"],
                    "trading_affected": False  # Health emitter issues never affect trading
                }
            
        except Exception as e:
            return {
                "status": "WARN",
                "reason": f"Health emitter check failed: {e}",
                "issues": [f"Health emitter error: {e}"],
                "trading_affected": False
            }

    def check_command_queue_drain(self) -> Dict[str, Any]:
        """Check command queue drain status - RED if Pending>0 for >15s"""
        try:
            queue_path = get_absolute_path('shared_data_ops') / "command_queue.jsonl"
            
            if not queue_path.exists():
                return {
                    "status": "OK",
                    "reason": None,
                    "pending_count": 0,
                    "oldest_pending_age": 0,
                    "trading_affected": False
                }
            
            # Read queue file
            pending_commands = []
            current_time = time.time()
            
            with open(queue_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            command = json.loads(line)
                            command_ts = command.get("timestamp", 0)
                            age = current_time - command_ts
                            pending_commands.append({
                                "command": command,
                                "age": age
                            })
                        except json.JSONDecodeError:
                            continue
            
            if not pending_commands:
                return {
                    "status": "OK",
                    "reason": None,
                    "pending_count": 0,
                    "oldest_pending_age": 0,
                    "trading_affected": False
                }
            
            # Check for old pending commands
            oldest_age = max(cmd["age"] for cmd in pending_commands)
            pending_count = len(pending_commands)
            
            # RED if pending > 0 for > 15 seconds
            if pending_count > 0 and oldest_age > 15:
                return {
                    "status": "RED",
                    "reason": f"Command queue drain failure: {pending_count} commands pending for {oldest_age:.1f}s",
                    "pending_count": pending_count,
                    "oldest_pending_age": oldest_age,
                    "trading_affected": True  # Command queue issues can affect trading
                }
            elif pending_count > 0:
                return {
                    "status": "WARN",
                    "reason": f"Command queue has {pending_count} pending commands (oldest: {oldest_age:.1f}s)",
                    "pending_count": pending_count,
                    "oldest_pending_age": oldest_age,
                    "trading_affected": False
                }
            else:
                return {
                    "status": "OK",
                    "reason": None,
                    "pending_count": 0,
                    "oldest_pending_age": 0,
                    "trading_affected": False
                }
                
        except Exception as e:
            return {
                "status": "ERROR",
                "reason": f"Command queue check failed: {e}",
                "pending_count": -1,
                "oldest_pending_age": -1,
                "trading_affected": True
            }

    def compute_global_health(self) -> Dict[str, Any]:
        """Compute global health status"""
        now = int(time.time())
        
        # Run all health checks
        env_drift = self.check_env_drift()
        integration = self.check_integration_contracts()
        freshness = self.check_freshness_chain()
        trader_readiness = self.check_trader_readiness()
        ui_status = self.check_ui_status()  # WARN only
        health_emitter_status = self.check_health_emitter_status()  # WARN only
        command_queue = self.check_command_queue_drain()  # RED if pending > 15s
        
        # Determine global status - UI and health_emitter issues are warnings only
        critical_checks = [env_drift, integration, freshness, trader_readiness, command_queue]
        failed_critical_checks = [check for check in critical_checks if check['status'] != 'OK']
        
        global_status = "RED" if failed_critical_checks else "GREEN"
        
        # Compile reasons (exclude UI warnings from critical status)
        reasons = []
        for check in failed_critical_checks:
            if check.get('reason'):
                reasons.append(check['reason'])
        
        global_reason = "; ".join(reasons) if reasons else None
        
        health_data = {
            "timestamp": now,
            "global_status": global_status,
            "global_reason": global_reason,
            "checks": {
                "env_drift": env_drift,
                "integration_contracts": integration,
                "freshness_chain": freshness,
                "trader_readiness": trader_readiness,
                "command_queue_drain": command_queue,  # RED if pending > 15s
                "ui_status": ui_status,  # WARN only, does not affect global status
                "health_emitter_status": health_emitter_status  # WARN only, does not affect global status
            }
        }
        
        # Write health data
        atomic_write(self.health_file, json.dumps(health_data, separators=(',', ':')))
        
        return health_data


# Global instances for easy access
def get_feeder_heartbeat() -> FeederHeartbeat:
    """Get global Feeder heartbeat manager"""
    if not hasattr(get_feeder_heartbeat, '_instance'):
        get_feeder_heartbeat._instance = FeederHeartbeat()
    return get_feeder_heartbeat._instance


def get_trader_heartbeat() -> TraderHeartbeat:
    """Get global Trader heartbeat manager"""
    if not hasattr(get_trader_heartbeat, '_instance'):
        get_trader_heartbeat._instance = TraderHeartbeat()
    return get_trader_heartbeat._instance


def get_positions_heartbeat() -> PositionsHeartbeat:
    """Get global Positions heartbeat manager"""
    if not hasattr(get_positions_heartbeat, '_instance'):
        get_positions_heartbeat._instance = PositionsHeartbeat()
    return get_positions_heartbeat._instance


def get_ares_heartbeat() -> AresHeartbeat:
    """Get global ARES heartbeat manager"""
    if not hasattr(get_ares_heartbeat, '_instance'):
        get_ares_heartbeat._instance = AresHeartbeat()
    return get_ares_heartbeat._instance


def get_health_v2() -> HealthV2:
    """Get global Health v2 manager"""
    if not hasattr(get_health_v2, '_instance'):
        get_health_v2._instance = HealthV2()
    return get_health_v2._instance


if __name__ == '__main__':
    # Test heartbeat system
    print("Heartbeat System Test:")
    
    # Test feeder heartbeat
    feeder = get_feeder_heartbeat()
    feeder.log_entrypoint_ok()
    feeder.update_prices(['BTCUSDT', 'ETHUSDT'])
    
    # Test trader heartbeat
    trader = get_trader_heartbeat()
    trader.log_entrypoint_ok()
    trader.update_health(exchange_info_loaded=True, last_rest_ok_ts=int(time.time()))
    
    # Test health v2
    health = get_health_v2()
    health_status = health.compute_global_health()
    print(f"Global health: {health_status['global_status']}")
    if health_status['global_reason']:
        print(f"Reason: {health_status['global_reason']}")
        print(f"Reason: {health_status['global_reason']}")
