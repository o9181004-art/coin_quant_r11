"""
Path resolution utilities for Coin Quant R11

Centralized path resolution with environment variable support.
Eliminates CWD dependencies and provides canonical paths.
"""

import os
from pathlib import Path
from typing import Optional


def get_data_dir() -> Path:
    """
    Resolve data directory: COIN_QUANT_DATA_DIR → ./shared_data
    
    Returns:
        Path: Resolved data directory path
    """
    data_dir = os.environ.get("COIN_QUANT_DATA_DIR")
    if data_dir:
        return Path(data_dir).resolve()
    return (Path.cwd() / "shared_data").resolve()


def get_health_dir() -> Path:
    """
    Get health directory path.
    
    Returns:
        Path: Health directory path
    """
    return get_data_dir() / "health"


def get_memory_dir() -> Path:
    """
    Get memory directory path.
    
    Returns:
        Path: Memory directory path
    """
    return get_data_dir() / "memory"


def get_logs_dir() -> Path:
    """
    Get logs directory path.
    
    Returns:
        Path: Logs directory path
    """
    return get_data_dir() / "logs"


def ensure_directories() -> None:
    """
    Ensure all required directories exist.
    """
    directories = [
        get_data_dir(),
        get_health_dir(),
        get_memory_dir(),
        get_logs_dir(),
    ]
    
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)


# Canonical health file paths
def get_feeder_health_path() -> Path:
    """Get feeder health file path."""
    return get_health_dir() / "feeder.json"


def get_ares_health_path() -> Path:
    """Get ARES health file path."""
    return get_health_dir() / "ares.json"


def get_trader_health_path() -> Path:
    """Get trader health file path."""
    return get_health_dir() / "trader.json"


def get_memory_health_path() -> Path:
    """Get memory health file path."""
    return get_health_dir() / "memory.json"


# Canonical PID file paths
def get_feeder_pid_path() -> Path:
    """Get feeder PID file path."""
    return get_data_dir() / "feeder.pid"


def get_ares_pid_path() -> Path:
    """Get ARES PID file path."""
    return get_data_dir() / "ares.pid"


def get_trader_pid_path() -> Path:
    """Get trader PID file path."""
    return get_data_dir() / "trader.pid"


# Canonical data file paths
def get_account_snapshot_path() -> Path:
    """Get account snapshot file path."""
    return get_data_dir() / "account_snapshot.json"


def get_databus_snapshot_path() -> Path:
    """Get databus snapshot file path."""
    return get_data_dir() / "databus_snapshot.json"


def get_universe_cache_path() -> Path:
    """Get universe cache file path."""
    return get_data_dir() / "universe_cache.json"


# Memory layer paths
def get_event_chain_path() -> Path:
    """Get event chain file path."""
    return get_memory_dir() / "event_chain.ndjson"


def get_snapshot_store_path() -> Path:
    """Get snapshot store file path."""
    return get_memory_dir() / "snapshot_store.json"


def get_hashchain_path() -> Path:
    """Get hash chain file path."""
    return get_memory_dir() / "hashchain.json"


def get_approval_queue_path() -> Path:
    """Get approval queue file path."""
    return get_memory_dir() / "approval_queue.json"


# Convenience functions for backward compatibility
def ssot_dir() -> Path:
    """Convenience function for data directory"""
    return get_data_dir()

def ensure_all_dirs() -> None:
    """Convenience function for directory creation"""
    ensure_directories()
