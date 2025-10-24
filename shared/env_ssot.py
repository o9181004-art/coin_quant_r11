#!/usr/bin/env python3
"""
Environment Single Source of Truth (SSOT)
Deterministic ENV_HASH calculation and SSOT management
"""

import hashlib
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .path_registry import get_absolute_path


def get_git_hash() -> str:
    """Get short git hash if available"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=get_absolute_path("repo_root"),
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"


def calculate_env_hash() -> str:
    """
    Calculate deterministic ENV_HASH using the same logic as shared.env_loader
    """
    # Import here to avoid circular imports
    from .env_loader import EnvironmentLoader

    # Create a temporary instance to get the hash
    temp_loader = EnvironmentLoader()
    return temp_loader.get_env_hash()


def get_effective_mode() -> str:
    """Determine effective mode (TESTNET or MAINNET)"""
    # Check environment variables
    if os.getenv("BINANCE_USE_TESTNET", "").lower() == "true":
        return "TESTNET"
    if os.getenv("ENV_MODE", "").upper() == "TESTNET":
        return "TESTNET"
    if os.getenv("ENV_MODE", "").upper() == "MAINNET":
        return "MAINNET"

    # Check config.env
    config_env_path = get_absolute_path("config") / "config.env"
    if config_env_path.exists():
        try:
            with open(config_env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        key, value = line.split("=", 1)
                        key = key.strip()
                        if key in ["BINANCE_USE_TESTNET", "ENV_MODE"]:
                            if (
                                key == "BINANCE_USE_TESTNET"
                                and value.strip().lower() == "true"
                            ):
                                return "TESTNET"
                            elif (
                                key == "ENV_MODE" and value.strip().upper() == "TESTNET"
                            ):
                                return "TESTNET"
                            elif (
                                key == "ENV_MODE" and value.strip().upper() == "MAINNET"
                            ):
                                return "MAINNET"
        except Exception:
            pass

    # Default to TESTNET for safety
    return "TESTNET"


def get_effective_base_url() -> str:
    """Get effective base URL for REST/WS endpoints"""
    # Check environment variables
    base_url = os.getenv("BINANCE_BASE_URL", "")
    if base_url:
        return base_url

    # Check config.env
    config_env_path = get_absolute_path("config") / "config.env"
    if config_env_path.exists():
        try:
            with open(config_env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        key, value = line.split("=", 1)
                        key = key.strip()
                        if key == "BINANCE_BASE_URL":
                            return value.strip()
        except Exception:
            pass

    # Default based on mode
    mode = get_effective_mode()
    if mode == "TESTNET":
        return "https://testnet.binance.vision"
    else:
        return "https://api.binance.com"


def get_effective_symbols() -> List[str]:
    """Get effective symbols list (UPPERCASE)"""
    # Check environment variables
    symbols_str = os.getenv("SYMBOLS", "")
    if symbols_str:
        symbols = [s.strip().upper() for s in symbols_str.split(",") if s.strip()]
        if symbols:
            return symbols

    # Check config.env
    config_env_path = get_absolute_path("config") / "config.env"
    if config_env_path.exists():
        try:
            with open(config_env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        key, value = line.split("=", 1)
                        key = key.strip()
                        if key == "SYMBOLS":
                            symbols = [
                                s.strip().upper() for s in value.split(",") if s.strip()
                            ]
                            if symbols:
                                return symbols
        except Exception:
            pass

    # Default symbols
    return ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


def create_ssot_snapshot(writer: str = "feeder") -> Dict[str, Any]:
    """Create SSOT snapshot with current environment state"""
    current_time = datetime.now(timezone.utc)

    # Import get_env_hash from env_loader to ensure consistency
    from .env_loader import get_env_hash

    return {
        "mode": get_effective_mode(),
        "base_url": get_effective_base_url(),
        "symbols": get_effective_symbols(),
        "git_hash": get_git_hash(),
        "env_hash": get_env_hash(),
        "writer": writer,
        "updated_at": current_time.isoformat(),
        "timestamp": int(current_time.timestamp()),
    }


def write_ssot_snapshot(snapshot: Dict[str, Any]) -> bool:
    """Write SSOT snapshot to file (atomic, UTF-8, no BOM)"""
    try:
        from shared.json_io import dump_json_atomic
        from shared.symbol_writer_guard import ensure_upper

        ssot_dir = get_absolute_path("shared_data") / "ssot"
        ssot_dir.mkdir(parents=True, exist_ok=True)

        ssot_file = ssot_dir / "env.json"

        # GUARD: Ensure all symbols in snapshot are UPPERCASE
        if "symbols" in snapshot and isinstance(snapshot["symbols"], list):
            uppercase_symbols = []
            for sym in snapshot["symbols"]:
                if isinstance(sym, str):
                    try:
                        upper_sym = ensure_upper(
                            sym, source="SSOT.write", abort_on_empty=False
                        )
                        if upper_sym:
                            uppercase_symbols.append(upper_sym)
                    except ValueError:
                        continue

            snapshot["symbols"] = sorted(list(set(uppercase_symbols)))

        # Atomic write (UTF-8, no BOM)
        return dump_json_atomic(ssot_file, snapshot)

    except Exception as e:
        print(f"Failed to write SSOT snapshot: {e}")
        return False


def read_ssot_snapshot() -> Optional[Dict[str, Any]]:
    """Read SSOT snapshot from file - BOM-resilient"""
    try:
        ssot_file = get_absolute_path("shared_data") / "ssot" / "env.json"

        if not ssot_file.exists():
            return None

        # BOM-resilient read: try utf-8-sig first, then utf-8
        for encoding in ["utf-8-sig", "utf-8"]:
            try:
                with open(ssot_file, "r", encoding=encoding) as f:
                    data = json.load(f)

                # Validate symbols if present
                if "symbols" in data and isinstance(data["symbols"], list):
                    from shared.symbol_writer_guard import ensure_upper

                    # Ensure all symbols are UPPERCASE
                    uppercase_symbols = []
                    for sym in data["symbols"]:
                        if isinstance(sym, str):
                            try:
                                upper_sym = ensure_upper(
                                    sym, source="SSOT.read", abort_on_empty=False
                                )
                                if upper_sym:
                                    uppercase_symbols.append(upper_sym)
                            except ValueError:
                                continue

                    data["symbols"] = sorted(list(set(uppercase_symbols)))

                return data

            except UnicodeDecodeError:
                continue
            except json.JSONDecodeError as e:
                if "BOM" in str(e):
                    continue
                print(f"Failed to decode SSOT JSON: {e}")
                return None
            except Exception:
                raise

        return None

    except Exception as e:
        print(f"Failed to read SSOT snapshot: {e}")
        return None


def ensure_ssot_exists(writer: str = "feeder") -> bool:
    """Ensure SSOT file exists, create if missing"""
    snapshot = read_ssot_snapshot()

    if snapshot is None:
        # Create new SSOT snapshot
        snapshot = create_ssot_snapshot(writer)
        return write_ssot_snapshot(snapshot)

    return True


def validate_env_hash_consistency() -> bool:
    """Validate that all services have consistent ENV_HASH"""
    ssot_snapshot = read_ssot_snapshot()
    if not ssot_snapshot:
        return False

    expected_hash = ssot_snapshot.get("env_hash")
    current_hash = calculate_env_hash()

    return expected_hash == current_hash


def get_env_hash_diff() -> List[str]:
    """Get list of keys that differ between current and SSOT"""
    ssot_snapshot = read_ssot_snapshot()
    if not ssot_snapshot:
        return ["SSOT file missing"]

    current_snapshot = create_ssot_snapshot()
    diff_keys = []

    for key in ["mode", "base_url", "symbols"]:
        if ssot_snapshot.get(key) != current_snapshot.get(key):
            diff_keys.append(key)

    return diff_keys


if __name__ == "__main__":
    # Test SSOT functionality
    print("SSOT Test:")

    # Create and write SSOT
    snapshot = create_ssot_snapshot("test")
    print(f"Created snapshot: {snapshot}")

    success = write_ssot_snapshot(snapshot)
    print(f"Write success: {success}")

    # Read back
    read_snapshot = read_ssot_snapshot()
    print(f"Read snapshot: {read_snapshot}")

    # Validate hash
    consistent = validate_env_hash_consistency()
    print(f"Hash consistent: {consistent}")

    # Get diff
    diff = get_env_hash_diff()
    print(f"Hash diff: {diff}")
