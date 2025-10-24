"""
Heartbeat Contracts
Standardized service heartbeats with ENV_HASH and freshness validation
"""

import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .env_loader import get_env_hash
from .io_safe import append_ndjson_safe, atomic_write
from .path_registry import get_absolute_path


@dataclass
class HeartbeatData:
    """Standardized heartbeat data structure"""

    timestamp: int
    service: str
    env_hash: str
    entrypoint_ok: bool
    uptime_seconds: int
    data: Dict[str, Any]
    # Legacy fields for backward compatibility
    pid: Optional[int] = None
    started_at: Optional[float] = None
    version: Optional[str] = None
    args: Optional[List[str]] = None
    status: Optional[str] = None


class HeartbeatManager:
    """Base class for service heartbeat management"""

    def __init__(self, service_name: str):
        self.service_name = service_name
        self.env_hash = get_env_hash()
        self.start_time = int(time.time())
        self.entrypoint_ok = False
        self.logger = logging.getLogger(f"{__name__}.{service_name}")

    def log_entrypoint_ok(self):
        """Log successful entrypoint initialization"""
        self.entrypoint_ok = True
        print(f"ENTRYPOINT_OK module={self.service_name}")

    def write_heartbeat(self, data: Dict[str, Any]):
        """Write heartbeat to file"""
        try:
            heartbeat_file = (
                get_absolute_path("shared_data_health") / f"{self.service_name}.json"
            )

            heartbeat_data = HeartbeatData(
                timestamp=int(time.time()),
                service=self.service_name,
                env_hash=self.env_hash,
                entrypoint_ok=self.entrypoint_ok,
                uptime_seconds=int(time.time()) - self.start_time,
                data=data,
            )

            atomic_write(heartbeat_file, json.dumps(asdict(heartbeat_data), indent=2))

        except Exception as e:
            self.logger.error(f"Failed to write heartbeat: {e}")


class FeederHeartbeat(HeartbeatManager):
    """Feeder service heartbeat"""

    def __init__(self):
        super().__init__("feeder")

    def update_heartbeat(self, prices_data: Dict[str, Any], symbols: List[str]):
        """Update feeder heartbeat with price data"""
        # Ensure all symbols are uppercase
        uppercase_symbols = [s.upper() for s in symbols]

        data = {
            "prices_data": prices_data,
            "symbols": uppercase_symbols,
            "symbol_count": len(uppercase_symbols),
            "last_price_update": int(time.time()),
        }

        self.write_heartbeat(data)


class TraderHeartbeat(HeartbeatManager):
    """Trader service heartbeat"""

    def __init__(self):
        super().__init__("trader")

    def update_health(
        self,
        exchange_info_loaded: bool,
        last_rest_ok_ts: float,
        balances_fresh_ts: float,
        circuit_breaker_active: bool,
    ):
        """Update trader heartbeat with health data"""
        data = {
            "exchange_info_loaded": exchange_info_loaded,
            "last_rest_ok_ts": last_rest_ok_ts,
            "balances_fresh_ts": balances_fresh_ts,
            "circuit_breaker_active": circuit_breaker_active,
            "health_status": (
                "ok"
                if exchange_info_loaded and not circuit_breaker_active
                else "degraded"
            ),
        }

        self.write_heartbeat(data)


class AresHeartbeat(HeartbeatManager):
    """ARES service heartbeat"""

    def __init__(self):
        super().__init__("ares")

    def update_heartbeat(self, candidates: List[Dict[str, Any]], is_real_signal: bool):
        """Update ARES heartbeat with signal data"""
        # Ensure all symbols are uppercase
        uppercase_candidates = []
        for candidate in candidates:
            if "symbol" in candidate:
                candidate["symbol"] = candidate["symbol"].upper()
            uppercase_candidates.append(candidate)

        data = {
            "candidates": uppercase_candidates,
            "candidate_count": len(uppercase_candidates),
            "is_real_signal": is_real_signal,
            "last_signal_update": int(time.time()),
        }

        self.write_heartbeat(data)

        # Also write to NDJSON file for historical tracking
        self._write_candidates_ndjson(uppercase_candidates, is_real_signal)

    def _write_candidates_ndjson(
        self, candidates: List[Dict[str, Any]], is_real_signal: bool
    ):
        """Write candidates to NDJSON file"""
        try:
            candidates_file = get_absolute_path("shared_data") / "candidates.ndjson"

            for candidate in candidates:
                ndjson_data = {
                    "timestamp": int(time.time()),
                    "service": "ares",
                    "env_hash": self.env_hash,
                    "is_real_signal": is_real_signal,
                    "candidate": candidate,
                }

                append_ndjson_safe(candidates_file, ndjson_data)

        except Exception as e:
            self.logger.error(f"Failed to write candidates NDJSON: {e}")


class AutohealHeartbeat(HeartbeatManager):
    """Autoheal service heartbeat"""

    def __init__(self):
        super().__init__("autoheal")

    def update_heartbeat(
        self,
        failure_count: int = 0,
        circuit_breaker_active: bool = False,
        last_action_time: float = 0,
        status: str = "MONITORING",
        **kwargs,
    ):
        """Update autoheal heartbeat"""
        try:
            current_time = time.time()

            # Prepare heartbeat data
            heartbeat_data = HeartbeatData(
                service="autoheal",
                env_hash=get_env_hash(),
                entrypoint_ok=True,
                uptime_seconds=current_time - self.start_time,
                data={
                    "failure_count": failure_count,
                    "circuit_breaker_active": circuit_breaker_active,
                    "last_action_time": last_action_time,
                    "status": status,
                    "pid": os.getpid(),
                    "version": "1.0.0",
                },
            )

            # Write heartbeat file
            self.write_heartbeat(heartbeat_data.data)

        except Exception as e:
            self.logger.error(f"Autoheal heartbeat update failed: {e}")


class PositionsHeartbeat(HeartbeatManager):
    """Positions service heartbeat"""

    def __init__(self):
        super().__init__("positions")

    def update_positions(self, positions: Dict[str, Any], **kwargs):
        """Update positions heartbeat with optional extra metrics"""
        # Type safety guard
        if not isinstance(positions, dict):
            self.logger.warning("positions payload is not dict; skipping heartbeat")
            return

        # Ensure all symbols are uppercase
        uppercase_positions = []
        if isinstance(positions, dict):
            for symbol, position_data in positions.items():
                if isinstance(position_data, dict):
                    position_data["symbol"] = symbol.upper()
                    uppercase_positions.append(position_data)
                else:
                    # Handle simple position data
                    uppercase_positions.append(
                        {"symbol": symbol.upper(), "data": position_data}
                    )

        data = {
            "positions": uppercase_positions,
            "position_count": len(uppercase_positions),
            "last_position_update": int(time.time()),
        }

        # Add optional metrics from kwargs
        if "total_pnl" in kwargs:
            data["total_pnl"] = kwargs["total_pnl"]
        if "total_balance" in kwargs:
            data["total_balance"] = kwargs["total_balance"]

        self.write_heartbeat(data)

        # Also write to positions snapshot file
        self._write_positions_snapshot(uppercase_positions)

    def _write_positions_snapshot(self, positions: List[Dict[str, Any]]):
        """Write positions snapshot to file"""
        try:
            positions_file = get_absolute_path("positions_snapshot")

            snapshot_data = {
                "timestamp": int(time.time()),
                "service": "positions",
                "env_hash": self.env_hash,
                "positions": positions,
                "position_count": len(positions),
            }

            atomic_write(positions_file, json.dumps(snapshot_data, indent=2))

        except Exception as e:
            self.logger.error(f"Failed to write positions snapshot: {e}")


def load_heartbeat(service_name: str) -> Optional[HeartbeatData]:
    """Load heartbeat data for a service"""
    try:
        # Try new location first
        heartbeat_file = (
            get_absolute_path("shared_data_health") / f"{service_name}.json"
        )

        # If not found, try legacy location
        if not heartbeat_file.exists():
            heartbeat_file = (
                get_absolute_path("shared_data") / f"{service_name}.heartbeat.json"
            )

        if not heartbeat_file.exists():
            return None

        with open(heartbeat_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Convert legacy format to HeartbeatData format
        if "pid" in data and "service" not in data:
            # Legacy format - convert to new format
            return HeartbeatData(
                timestamp=int(data.get("timestamp", time.time())),
                service=service_name,
                env_hash=data.get("env_hash", "unknown"),
                entrypoint_ok=data.get("status") == "running",
                uptime_seconds=int(time.time() - data.get("started_at", time.time())),
                data={},
                pid=data.get("pid"),
                started_at=data.get("started_at"),
                version=data.get("version"),
                args=data.get("args"),
                status=data.get("status"),
            )
        else:
            # New format - ensure all required fields are present
            filtered_data = {}
            valid_fields = {
                "timestamp",
                "service",
                "env_hash",
                "entrypoint_ok",
                "uptime_seconds",
                "data",
                "pid",
                "started_at",
                "version",
                "args",
                "status",
            }

            # Ensure required fields have default values
            filtered_data["timestamp"] = data.get("timestamp", int(time.time()))
            filtered_data["service"] = data.get("service", service_name)
            filtered_data["env_hash"] = data.get("env_hash", "unknown")
            filtered_data["entrypoint_ok"] = data.get("entrypoint_ok", True)
            filtered_data["uptime_seconds"] = data.get("uptime_seconds", 0)
            filtered_data["data"] = data.get("data", {})

            # Add optional fields if present
            for key, value in data.items():
                if key in valid_fields and key not in filtered_data:
                    filtered_data[key] = value
                elif key not in valid_fields:
                    # Store unknown fields in data dict
                    filtered_data["data"][key] = value

            return HeartbeatData(**filtered_data)

    except Exception as e:
        logging.getLogger(__name__).error(
            f"Failed to load heartbeat for {service_name}: {e}"
        )
        return None


def get_heartbeat_age(service_name: str) -> float:
    """Get heartbeat age in seconds"""
    heartbeat = load_heartbeat(service_name)
    if heartbeat is None:
        return float("inf")

    return time.time() - heartbeat.timestamp


def validate_heartbeat_freshness(service_name: str, max_age_seconds: int = 120) -> bool:
    """Validate heartbeat freshness"""
    age = get_heartbeat_age(service_name)
    return age <= max_age_seconds


def validate_env_hash_consistency() -> bool:
    """Validate ENV_HASH consistency across all heartbeats"""
    try:
        current_env_hash = get_env_hash()
        services = ["feeder", "trader", "ares", "positions"]

        for service_name in services:
            heartbeat = load_heartbeat(service_name)
            if heartbeat is None:
                continue

            if heartbeat.env_hash != current_env_hash:
                return False

        return True

    except Exception as e:
        logging.getLogger(__name__).error(
            f"Failed to validate ENV_HASH consistency: {e}"
        )
        return False


def get_all_heartbeats() -> Dict[str, HeartbeatData]:
    """Get all service heartbeats"""
    heartbeats = {}
    services = ["feeder", "trader", "ares", "positions"]

    for service_name in services:
        heartbeat = load_heartbeat(service_name)
        if heartbeat is not None:
            heartbeats[service_name] = heartbeat

    return heartbeats


if __name__ == "__main__":
    # Test heartbeat contracts
    print("Heartbeat Contracts Test:")

    # Test feeder heartbeat
    feeder_hb = FeederHeartbeat()
    feeder_hb.log_entrypoint_ok()
    feeder_hb.update_heartbeat(
        prices_data={"BTCUSDT": 50000.0, "ETHUSDT": 3000.0},
        symbols=["BTCUSDT", "ETHUSDT"],
    )

    # Test trader heartbeat
    trader_hb = TraderHeartbeat()
    trader_hb.log_entrypoint_ok()
    trader_hb.update_health(
        exchange_info_loaded=True,
        last_rest_ok_ts=time.time(),
        balances_fresh_ts=time.time(),
        circuit_breaker_active=False,
    )

    # Test ARES heartbeat
    ares_hb = AresHeartbeat()
    ares_hb.log_entrypoint_ok()
    ares_hb.update_heartbeat(
        candidates=[{"symbol": "BTCUSDT", "score": 0.8}], is_real_signal=True
    )

    # Test positions heartbeat
    positions_hb = PositionsHeartbeat()
    positions_hb.log_entrypoint_ok()
    positions_hb.update_positions(
        [{"symbol": "BTCUSDT", "side": "BUY", "quantity": 0.001}]
    )

    print("Heartbeat tests completed")

    # Test validation functions
    print(f"ENV_HASH consistency: {validate_env_hash_consistency()}")
    print(f"Feeder heartbeat age: {get_heartbeat_age('feeder')}")
    print(f"Feeder heartbeat fresh: {validate_heartbeat_freshness('feeder')}")
