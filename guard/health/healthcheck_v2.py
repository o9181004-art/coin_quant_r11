#!/usr/bin/env python3
"""
Health Check v2 - Contract Alignment & Resilience
Reads STATE_BUS and validates all contracts with epoch seconds timestamps
"""

import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from shared.io.jsonio import (ensure_epoch_seconds, get_last_ndjson_line,
                              read_json_nobom)
from shared.paths import (CANDIDATES, EXCHANGE_FILTERS, HEALTH_V2, POSITIONS,
                          STATE_BUS, ensure_all_dirs)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class ProbeResult:
    """Probe result"""
    ok: bool
    details: Dict[str, Any]
    error: str = ""
    latency_ms: float = 0.0


@dataclass
class HealthCheckResult:
    """Overall health check result"""
    timestamp: float
    dor: bool  # Definition of Ready
    failing_components: List[str]
    probes: Dict[str, ProbeResult]
    summary: Dict[str, Any]


class HealthCheckV2:
    """Health Check v2 - Functional probes"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Ensure directories exist
        ensure_all_dirs()

        # Load config
        self.use_testnet = os.getenv("BINANCE_USE_TESTNET", "true").lower() == "true"

        # Thresholds (Definition of Ready)
        self.DOR_THRESHOLDS = {
            "ws_fresh_sec": 60,
            "databus_age_sec": 60,
            "ares_candidate_age_sec": 120,
            "position_snapshot_age_sec": 120,
        }

    def probe_ws_stream(self) -> ProbeResult:
        """
        Probe WebSocket stream freshness
        - Ensure prices.symbols includes BTCUSDT and prices.age_s<=60
        """
        start_time = time.time()

        try:
            # Read STATE_BUS
            state_bus = read_json_nobom(STATE_BUS, {})
            
            if not state_bus:
                return ProbeResult(
                    ok=False,
                    details={"reason": "STATE_BUS not found or empty"},
                    error="STATE_BUS missing",
                    latency_ms=(time.time() - start_time) * 1000
                )

            # Check prices section
            prices = state_bus.get("prices", {})
            if not prices:
                return ProbeResult(
                    ok=False,
                    details={"reason": "prices section missing"},
                    error="Prices section missing",
                    latency_ms=(time.time() - start_time) * 1000
                )

            # Check symbols include BTCUSDT and are uppercase
            symbols = prices.get("symbols", [])
            if "BTCUSDT" not in symbols:
                return ProbeResult(
                    ok=False,
                    details={
                        "reason": "BTCUSDT not in symbols",
                        "symbols": symbols
                    },
                    error="BTCUSDT not in symbols",
                    latency_ms=(time.time() - start_time) * 1000
                )
            
            # Check all symbols are uppercase
            for symbol in symbols:
                if symbol != symbol.upper():
                    return ProbeResult(
                        ok=False,
                        details={
                            "reason": f"Symbol {symbol} is not uppercase",
                            "symbols": symbols
                        },
                        error=f"Symbol {symbol} not uppercase",
                        latency_ms=(time.time() - start_time) * 1000
                    )

            # Check age
            age_s = prices.get("age_s", 999)
            if age_s > 60:
                return ProbeResult(
                    ok=False,
                    details={
                        "age_s": age_s,
                        "threshold_s": 60,
                        "reason": "prices too old"
                    },
                    error=f"Prices age {age_s}s > 60s",
                    latency_ms=(time.time() - start_time) * 1000
                )

            # Success
            return ProbeResult(
                ok=True,
                details={
                    "symbols": symbols,
                    "age_s": age_s,
                    "last_ts": prices.get("last_ts", 0)
                },
                latency_ms=(time.time() - start_time) * 1000
            )

        except Exception as e:
            self.logger.error(f"WS stream probe failed: {e}")
            return ProbeResult(
                ok=False,
                details={"exception": str(e)},
                error=f"Exception: {e}",
                latency_ms=(time.time() - start_time) * 1000
            )

    def probe_databus_snapshot(self) -> ProbeResult:
        """
        Probe databus snapshot freshness
        - Use prices.last_ts; compute age; flag unit-mismatch if age>1e7
        """
        start_time = time.time()

        try:
            # Read STATE_BUS
            state_bus = read_json_nobom(STATE_BUS, {})
            
            if not state_bus:
                return ProbeResult(
                    ok=False,
                    details={"reason": "STATE_BUS not found or empty"},
                    error="STATE_BUS missing",
                    latency_ms=(time.time() - start_time) * 1000
                )

            # Check prices section
            prices = state_bus.get("prices", {})
            if not prices:
                return ProbeResult(
                    ok=False,
                    details={"reason": "prices section missing"},
                    error="Prices section missing",
                    latency_ms=(time.time() - start_time) * 1000
                )

            # Get last_ts and compute age
            last_ts = prices.get("last_ts", 0)
            current_time = int(time.time())
            
            # Ensure epoch seconds
            last_ts = ensure_epoch_seconds(last_ts)
            age_s = current_time - last_ts

            # Flag unit mismatch if age > 1e7 (milliseconds instead of seconds)
            if age_s > 1e7:
                return ProbeResult(
                    ok=False,
                    details={
                        "last_ts": last_ts,
                        "age_s": age_s,
                        "reason": "unit_mismatch"
                    },
                    error=f"Unit mismatch: age {age_s} > 1e7 (likely milliseconds)",
                    latency_ms=(time.time() - start_time) * 1000
                )

            # Check if age is acceptable (< 60s)
            age_ok = age_s < 60

            return ProbeResult(
                ok=age_ok,
                details={
                    "last_ts": last_ts,
                    "age_s": age_s,
                    "threshold_s": 60
                },
                error="" if age_ok else f"Databus age {age_s}s > 60s",
                latency_ms=(time.time() - start_time) * 1000
            )

        except Exception as e:
            self.logger.error(f"Databus snapshot probe failed: {e}")
            return ProbeResult(
                ok=False,
                details={"exception": str(e)},
                error=f"Exception: {e}",
                latency_ms=(time.time() - start_time) * 1000
            )


    def probe_ares_signal_flow(self) -> ProbeResult:
        """
        Probe ARES signal flow
        - Read last NDJSON line from CANDIDATES; require timestamp present and now - timestamp <= 120
        """
        start_time = time.time()

        try:
            # Check candidates file
            if not CANDIDATES.exists():
                return ProbeResult(
                    ok=False,
                    details={"reason": "CANDIDATES file not found"},
                    error="Candidates file missing",
                    latency_ms=(time.time() - start_time) * 1000
                )

            # Read last line
            last_candidate = get_last_ndjson_line(CANDIDATES)
            
            if not last_candidate:
                return ProbeResult(
                    ok=False,
                    details={"reason": "Empty candidates file"},
                    error="No candidates found",
                    latency_ms=(time.time() - start_time) * 1000
                )

            # Check timestamp
            timestamp = last_candidate.get("timestamp", 0)
            if timestamp == 0:
                return ProbeResult(
                    ok=False,
                    details={"reason": "No timestamp in candidate"},
                    error="Candidate missing timestamp",
                    latency_ms=(time.time() - start_time) * 1000
                )

            # Ensure epoch seconds
            timestamp = ensure_epoch_seconds(timestamp)
            current_time = int(time.time())
            age_s = current_time - timestamp

            # Check if age is acceptable (< 120s)
            age_ok = age_s < 120
            
            # Check symbol is uppercase
            symbol = last_candidate.get("symbol", "unknown")
            symbol_ok = symbol == symbol.upper()
            
            # Overall success requires both age and symbol checks
            overall_ok = age_ok and symbol_ok

            return ProbeResult(
                ok=overall_ok,
                details={
                    "age_s": age_s,
                    "threshold_s": 120,
                    "symbol": symbol,
                    "symbol_uppercase": symbol_ok,
                    "side": last_candidate.get("side", "unknown"),
                    "trace_id": last_candidate.get("trace_id", "unknown")
                },
                error="" if overall_ok else f"Candidate age {age_s}s > 120s" if not age_ok else f"Symbol {symbol} not uppercase",
                latency_ms=(time.time() - start_time) * 1000
            )

        except Exception as e:
            self.logger.error(f"ARES signal flow probe failed: {e}")
            return ProbeResult(
                ok=False,
                details={"exception": str(e)},
                error=f"Exception: {e}",
                latency_ms=(time.time() - start_time) * 1000
            )

    def probe_trader_gateway(self) -> ProbeResult:
        """
        Probe trader gateway
        - Assert EXCHANGE_FILTERS["BTCUSDT"] exists with stepSize/tickSize/minNotional
        """
        start_time = time.time()

        try:
            # Check if filters are loaded
            if not EXCHANGE_FILTERS.exists():
                return ProbeResult(
                    ok=False,
                    details={"reason": "EXCHANGE_FILTERS not found"},
                    error="Exchange filters not loaded",
                    latency_ms=(time.time() - start_time) * 1000
                )

            filters = read_json_nobom(EXCHANGE_FILTERS, {})

            # Check if BTCUSDT filters exist
            if "BTCUSDT" not in filters:
                return ProbeResult(
                    ok=False,
                    details={"reason": "BTCUSDT filters not found"},
                    error="BTCUSDT filters missing",
                    latency_ms=(time.time() - start_time) * 1000
                )

            btc_filters = filters["BTCUSDT"]

            # Validate filter structure
            required_keys = ["step_size", "tick_size", "min_notional"]
            missing_keys = [k for k in required_keys if k not in btc_filters]

            if missing_keys:
                return ProbeResult(
                    ok=False,
                    details={
                        "reason": "Incomplete filters",
                        "missing_keys": missing_keys
                    },
                    error=f"Missing filter keys: {missing_keys}",
                    latency_ms=(time.time() - start_time) * 1000
                )

            # Success
            return ProbeResult(
                ok=True,
                details={
                    "filters_loaded": True,
                    "symbols_count": len([k for k in filters.keys() if k != "meta"]),
                    "btc_min_notional": btc_filters.get("min_notional", 0),
                    "btc_step_size": btc_filters.get("step_size", 0),
                    "btc_tick_size": btc_filters.get("tick_size", 0)
                },
                latency_ms=(time.time() - start_time) * 1000
            )

        except Exception as e:
            self.logger.error(f"Trader gateway probe failed: {e}")
            return ProbeResult(
                ok=False,
                details={"exception": str(e)},
                error=f"Exception: {e}",
                latency_ms=(time.time() - start_time) * 1000
            )

    def probe_position_snapshot(self) -> ProbeResult:
        """
        Probe position snapshot
        - now - POSITIONS.timestamp <= 120
        """
        start_time = time.time()

        try:
            # Check positions file
            if not POSITIONS.exists():
                return ProbeResult(
                    ok=False,
                    details={"reason": "POSITIONS file not found"},
                    error="Positions file missing",
                    latency_ms=(time.time() - start_time) * 1000
                )

            # Read positions
            positions = read_json_nobom(POSITIONS, {})
            
            if not positions:
                return ProbeResult(
                    ok=False,
                    details={"reason": "POSITIONS file empty"},
                    error="Positions file empty",
                    latency_ms=(time.time() - start_time) * 1000
                )

            # Check timestamp (backward compatibility)
            timestamp = positions.get("timestamp", 0)
            if timestamp == 0:
                # Try legacy "ts" field
                timestamp = positions.get("ts", 0)
                if timestamp == 0:
                    return ProbeResult(
                        ok=False,
                        details={"reason": "No timestamp in positions"},
                        error="Positions missing timestamp",
                        latency_ms=(time.time() - start_time) * 1000
                    )

            # Ensure epoch seconds
            timestamp = ensure_epoch_seconds(timestamp)
            current_time = int(time.time())
            age_s = current_time - timestamp

            # Check if age is acceptable (< 120s)
            age_ok = age_s < 120

            return ProbeResult(
                ok=age_ok,
                details={
                    "age_s": age_s,
                    "threshold_s": 120,
                    "positions_count": positions.get("positions_count", 0),
                    "timestamp": timestamp
                },
                error="" if age_ok else f"Position snapshot age {age_s}s > 120s",
                latency_ms=(time.time() - start_time) * 1000
            )

        except Exception as e:
            self.logger.error(f"Position snapshot probe failed: {e}")
            return ProbeResult(
                ok=False,
                details={"exception": str(e)},
                error=f"Exception: {e}",
                latency_ms=(time.time() - start_time) * 1000
            )

    def probe_trader_readiness(self) -> ProbeResult:
        """Probe trader readiness - exchange_info_loaded, last_rest_ok_ts, balances, circuit_breaker"""
        start_time = time.time()
        
        try:
            # Read trader health file
            trader_health_file = Path("shared_data/health/trader.json")
            if not trader_health_file.exists():
                return ProbeResult(
                    ok=False,
                    details={"reason": "trader.json not found"},
                    error="Trader health file missing",
                    latency_ms=(time.time() - start_time) * 1000
                )
            
            trader_health = read_json_nobom(trader_health_file, {})
            current_time = int(time.time())
            
            # Check exchange_info_loaded
            exchange_info_loaded = trader_health.get("exchange_info_loaded", False)
            if not exchange_info_loaded:
                return ProbeResult(
                    ok=False,
                    details={"reason": "exchange_info_loaded=false"},
                    error="Exchange info not loaded",
                    latency_ms=(time.time() - start_time) * 1000
                )
            
            # Check last_rest_ok_ts age <= 60s
            last_rest_ok_ts = trader_health.get("last_rest_ok_ts", 0)
            rest_age_s = current_time - last_rest_ok_ts
            if rest_age_s > 60:
                return ProbeResult(
                    ok=False,
                    details={
                        "reason": f"last_rest_ok_ts age {rest_age_s}s > 60s",
                        "rest_age_s": rest_age_s,
                        "threshold_s": 60
                    },
                    error=f"REST API stale: {rest_age_s}s > 60s",
                    latency_ms=(time.time() - start_time) * 1000
                )
            
            # Check balances.fresh_ts <= 120s
            balances = trader_health.get("balances", {})
            fresh_ts = balances.get("fresh_ts", 0)
            balances_age_s = current_time - fresh_ts
            if balances_age_s > 120:
                return ProbeResult(
                    ok=False,
                    details={
                        "reason": f"balances.fresh_ts age {balances_age_s}s > 120s",
                        "balances_age_s": balances_age_s,
                        "threshold_s": 120
                    },
                    error=f"Balances stale: {balances_age_s}s > 120s",
                    latency_ms=(time.time() - start_time) * 1000
                )
            
            # Check circuit_breaker.active == false
            circuit_breaker = trader_health.get("circuit_breaker", {})
            if circuit_breaker.get("active", False):
                return ProbeResult(
                    ok=False,
                    details={
                        "reason": "circuit_breaker.active=true",
                        "since": circuit_breaker.get("since", 0)
                    },
                    error="Circuit breaker active",
                    latency_ms=(time.time() - start_time) * 1000
                )
            
            # All checks passed
            return ProbeResult(
                ok=True,
                details={
                    "exchange_info_loaded": exchange_info_loaded,
                    "rest_age_s": rest_age_s,
                    "balances_age_s": balances_age_s,
                    "circuit_breaker_active": False
                },
                error="",
                latency_ms=(time.time() - start_time) * 1000
            )
            
        except Exception as e:
            return ProbeResult(
                ok=False,
                details={"error": str(e)},
                error=f"Trader readiness probe error: {e}",
                latency_ms=(time.time() - start_time) * 1000
            )

    def probe_autoheal_recovery(self) -> ProbeResult:
        """Probe Auto-Heal recovery status"""
        start_time = time.time()
        
        try:
            # Import here to avoid circular imports
            from guard.autoheal.autoheal_v2 import get_autoheal_v2
            from shared.control_plane import get_control_plane
            
            control_plane = get_control_plane()
            autoheal = get_autoheal_v2()
            
            # Check if auto trading is enabled
            auto_trading_enabled = control_plane.is_auto_trading_enabled()
            reason = control_plane.get_reason()
            
            # Get autoheal state
            autoheal_state = autoheal.get_state()
            state = autoheal_state.get("state", "unknown")
            attempts = autoheal_state.get("attempts_window", {}).get("attempts", 0)
            failed = autoheal_state.get("attempts_window", {}).get("failed", 0)
            last_error = autoheal_state.get("last_error", "")
            
            # Check if trader is running
            trader_running = autoheal._is_trader_running()
            
            # Determine probe result
            if not auto_trading_enabled:
                # Auto trading disabled - check if blocked by control
                if state == "blocked":
                    return ProbeResult(
                        ok=True,  # AMBER - not an error, user-blocked
                        details={
                            "state": state,
                            "reason": reason,
                            "auto_trading_enabled": auto_trading_enabled,
                            "trader_running": trader_running
                        },
                        error="",  # Not an error
                        latency_ms=(time.time() - start_time) * 1000
                    )
                else:
                    return ProbeResult(
                        ok=True,  # OK - auto trading disabled
                        details={
                            "state": state,
                            "reason": reason,
                            "auto_trading_enabled": auto_trading_enabled,
                            "trader_running": trader_running
                        },
                        error="",
                        latency_ms=(time.time() - start_time) * 1000
                    )
            
            # Auto trading enabled - check recovery status
            if not trader_running:
                if state == "recovering":
                    return ProbeResult(
                        ok=True,  # AMBER - recovering
                        details={
                            "state": state,
                            "attempts": attempts,
                            "failed": failed,
                            "auto_trading_enabled": auto_trading_enabled,
                            "trader_running": trader_running
                        },
                        error="",  # Not an error yet
                        latency_ms=(time.time() - start_time) * 1000
                    )
                elif state == "failed" and failed >= 3:
                    return ProbeResult(
                        ok=False,  # RED - failed recovery
                        details={
                            "state": state,
                            "attempts": attempts,
                            "failed": failed,
                            "last_error": last_error,
                            "auto_trading_enabled": auto_trading_enabled,
                            "trader_running": trader_running
                        },
                        error=f"auto-heal failed to recover trader: attempts={failed}/10m, error={last_error}",
                        latency_ms=(time.time() - start_time) * 1000
                    )
                else:
                    return ProbeResult(
                        ok=True,  # OK - trader down but not failed yet
                        details={
                            "state": state,
                            "attempts": attempts,
                            "failed": failed,
                            "auto_trading_enabled": auto_trading_enabled,
                            "trader_running": trader_running
                        },
                        error="",
                        latency_ms=(time.time() - start_time) * 1000
                    )
            else:
                # Trader running - OK
                return ProbeResult(
                    ok=True,
                    details={
                        "state": state,
                        "attempts": attempts,
                        "failed": failed,
                        "auto_trading_enabled": auto_trading_enabled,
                        "trader_running": trader_running
                    },
                    error="",
                    latency_ms=(time.time() - start_time) * 1000
                )
                
        except Exception as e:
            return ProbeResult(
                ok=False,
                details={"error": str(e)},
                error=f"autoheal recovery probe error: {e}",
                latency_ms=(time.time() - start_time) * 1000
            )

    def run_all_probes(self) -> HealthCheckResult:
        """Run all probes and determine DOR"""
        self.logger.info("=" * 70)
        self.logger.info("Running Health Check v2 - Contract Alignment & Resilience")
        self.logger.info("=" * 70)

        timestamp = time.time()
        probes = {}

        # Run all probes
        self.logger.info("\n[1/7] Probing WS Stream...")
        probes["ws_stream"] = self.probe_ws_stream()
        self.logger.info(f"  Result: {'✅ OK' if probes['ws_stream'].ok else '❌ FAIL'} - {probes['ws_stream'].error or 'Healthy'}")

        self.logger.info("\n[2/7] Probing Databus Snapshot...")
        probes["databus_snapshot"] = self.probe_databus_snapshot()
        self.logger.info(f"  Result: {'✅ OK' if probes['databus_snapshot'].ok else '❌ FAIL'} - {probes['databus_snapshot'].error or 'Healthy'}")

        self.logger.info("\n[3/7] Probing ARES Signal Flow...")
        probes["ares_signal_flow"] = self.probe_ares_signal_flow()
        self.logger.info(f"  Result: {'✅ OK' if probes['ares_signal_flow'].ok else '❌ FAIL'} - {probes['ares_signal_flow'].error or 'Healthy'}")

        self.logger.info("\n[4/7] Probing Trader Gateway...")
        probes["trader_gateway"] = self.probe_trader_gateway()
        self.logger.info(f"  Result: {'✅ OK' if probes['trader_gateway'].ok else '❌ FAIL'} - {probes['trader_gateway'].error or 'Healthy'}")

        self.logger.info("\n[5/7] Probing Position Snapshot...")
        probes["position_snapshot"] = self.probe_position_snapshot()
        self.logger.info(f"  Result: {'✅ OK' if probes['position_snapshot'].ok else '❌ FAIL'} - {probes['position_snapshot'].error or 'Healthy'}")

        self.logger.info("\n[6/7] Probing Trader Readiness...")
        probes["trader_readiness"] = self.probe_trader_readiness()
        self.logger.info(f"  Result: {'✅ OK' if probes['trader_readiness'].ok else '❌ FAIL'} - {probes['trader_readiness'].error or 'Healthy'}")

        self.logger.info("\n[7/7] Probing Auto-Heal Recovery...")
        probes["autoheal_recovery"] = self.probe_autoheal_recovery()
        self.logger.info(f"  Result: {'✅ OK' if probes['autoheal_recovery'].ok else '❌ FAIL'} - {probes['autoheal_recovery'].error or 'Healthy'}")

        # Determine DOR (Definition of Ready)
        failing_components = []

        if not probes["ws_stream"].ok:
            failing_components.append("Feeder")

        if not probes["databus_snapshot"].ok:
            failing_components.append("DataBus")

        if not probes["ares_signal_flow"].ok:
            failing_components.append("ARES")

        if not probes["trader_gateway"].ok:
            failing_components.append("Trader")

        if not probes["position_snapshot"].ok:
            failing_components.append("PositionTracker")

        if not probes["trader_readiness"].ok:
            failing_components.append("Trader Readiness")

        if not probes["autoheal_recovery"].ok:
            failing_components.append("Auto-Heal Recovery")

        # DOR is true only if all probes pass
        dor = len(failing_components) == 0

        # Summary
        summary = {
            "total_probes": len(probes),
            "passed_probes": sum(1 for p in probes.values() if p.ok),
            "failed_probes": sum(1 for p in probes.values() if not p.ok),
            "dor": dor,
            "failing_components": failing_components,
            "environment": "testnet" if self.use_testnet else "mainnet"
        }

        result = HealthCheckResult(
            timestamp=timestamp,
            dor=dor,
            failing_components=failing_components,
            probes=probes,
            summary=summary
        )

        # Log summary
        self.logger.info("\n" + "=" * 70)
        self.logger.info("Health Check Summary")
        self.logger.info("=" * 70)
        self.logger.info(f"DOR (Definition of Ready): {'✅ TRUE' if dor else '❌ FALSE'}")
        self.logger.info(f"Passed: {summary['passed_probes']}/{summary['total_probes']}")

        if failing_components:
            self.logger.warning(f"Failing Components: {', '.join(failing_components)}")
        else:
            self.logger.info("All components healthy! 🎉")

        self.logger.info("=" * 70)

        return result

    def save_results(self, result: HealthCheckResult):
        """Save results to JSON files"""
        try:
            from shared.io.jsonio import write_json_atomic_nobom

            # Convert to dict
            result_dict = {
                "timestamp": result.timestamp,
                "dor": result.dor,
                "failing_components": result.failing_components,
                "probes": {
                    name: asdict(probe) for name, probe in result.probes.items()
                },
                "summary": result.summary
            }

            # Write atomically with no BOM
            write_json_atomic_nobom(HEALTH_V2, result_dict)
            self.logger.info(f"\n✅ Results saved to: {HEALTH_V2}")

        except Exception as e:
            self.logger.error(f"Failed to save results: {e}")


def main():
    """Main entry point"""
    checker = HealthCheckV2()
    result = checker.run_all_probes()
    checker.save_results(result)

    # Exit with appropriate code
    if result.dor:
        print("\n✅ System is READY for unattended auto-trading")
        return 0
    else:
        print(f"\n❌ System is NOT READY - Failing: {', '.join(result.failing_components)}")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
