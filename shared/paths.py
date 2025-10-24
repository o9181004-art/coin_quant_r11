from __future__ import annotations
import os
from pathlib import Path

def ensure_all_dirs() -> None:
    """Ensure all required directories exist"""
    directories = [
        ssot_dir(),
        ssot_dir() / "pids",
        ssot_dir() / "health",
        ssot_dir() / "ares",
        ssot_dir() / "logs"
    ]
    
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)

def ssot_dir() -> Path:
    """Resolve SSOT: Env(SHARED_DATA) → <repo>/shared_data"""
    sd = os.environ.get("SHARED_DATA")
    if sd:
        return Path(sd).resolve()
    return (Path.cwd() / "shared_data").resolve()

# Canonical targets (used by snapshotters / services)
ACCOUNT_SNAPSHOT_PATH: Path = ssot_dir() / "account_info.json"
HEALTH_PATH: Path = ssot_dir() / "health.json"
ARES_STATUS_PATH: Path = ssot_dir() / "ares" / "ares_status.json"
TRADER_HEARTBEAT_PATH: Path = ssot_dir() / "health" / "trader.heartbeat.json"
