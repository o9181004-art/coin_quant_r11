#!/usr/bin/env python3
"""
Path Registry - Single Source of Truth for all repository paths
Enforces CQ_ROOT validation and eliminates path drift
"""
import os
import sys
from pathlib import Path
from typing import Dict, Optional


class CQ_ROOT_VIOLATION(Exception):
    """CQ_ROOT validation violation exception"""

    pass


class PathRegistry:
    """Centralized path registry with CQ_ROOT enforcement"""

    _instance: Optional["PathRegistry"] = None
    _cq_root: Optional[Path] = None
    _paths: Dict[str, Path] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def current(cls) -> "PathRegistry":
        """Get current instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        if self._cq_root is not None:
            return  # Already initialized

        self._cq_root = self._find_cq_root()
        self._validate_cq_root()
        self._initialize_paths()

    def _find_cq_root(self) -> Path:
        """Find CQ_ROOT using env var or walking up from current file"""
        # 1. Check CQ_ROOT environment variable
        env_root = os.getenv("CQ_ROOT")
        if env_root:
            return Path(env_root).resolve()

        # 2. Walk up from current file looking for coin_quant signature
        current = Path(__file__).resolve()
        while current != current.parent:
            # Look for coin_quant signature files
            if (
                (current / "run_dashboard.ps1").exists()
                and (current / "shared").exists()
                and current.name == "coin_quant"
            ):
                return current
            current = current.parent

        # 3. Fallback to current working directory if it contains coin_quant structure
        cwd = Path.cwd()
        if (cwd / "run_dashboard.ps1").exists() and (cwd / "shared").exists():
            return cwd

        # 4. Last resort: assume current working directory
        return cwd

    def _validate_cq_root(self):
        """Validate CQ_ROOT is properly structured"""
        if not self._cq_root.exists():
            raise CQ_ROOT_VIOLATION(f"CQ_ROOT not found: {self._cq_root}")

        if not self._cq_root.is_dir():
            raise CQ_ROOT_VIOLATION(f"CQ_ROOT is not a directory: {self._cq_root}")

        # Validate it's actually coin_quant
        required_files = ["run_dashboard.ps1", "shared"]
        for req in required_files:
            if not (self._cq_root / req).exists():
                raise CQ_ROOT_VIOLATION(
                    f"Missing coin_quant signature: {req} in {self._cq_root}"
                )

    def _initialize_paths(self):
        """Initialize all canonical paths"""
        shared_data = self._cq_root / "shared_data"

        self._paths = {
            # Core paths
            "CQ_ROOT": self._cq_root,
            "SHARED_DATA": shared_data,
            # Health system
            "HEALTH": shared_data / "health.json",
            "HEALTH_DIR": shared_data / "health",
            "HEALTH_UDS": shared_data / "health" / "uds.json",
            "UDS_HEARTBEAT": shared_data / "health" / "uds.json",  # Alias for clarity
            "HEALTH_FEEDER": shared_data / "health" / "feeder.json",
            "HEALTH_TRADER": shared_data / "health" / "trader.json",
            "HEALTH_ARES": shared_data / "health" / "ares.json",
            # Data streams
            "UDS_SNAPSHOT": shared_data / "databus_snapshot.json",
            "DATABUS_SNAPSHOT": shared_data / "databus_snapshot.json",
            # Account & positions
            "ACCOUNT_SNAPSHOT": shared_data / "accounts" / "account_snapshot.json",
            "POSITIONS_SNAPSHOT": shared_data / "positions.json",
            # Legacy compatibility
            "ACCOUNT_SNAPSHOT_LEGACY": shared_data / "account_snapshot.json",
            # Other critical paths
            "ARES_CANDIDATES": shared_data / "ares" / "candidates.ndjson",
            "EXCHANGE_FILTERS": shared_data / "exchange_filters.json",
            "STATE_BUS": shared_data / "state_bus.json",
            "LOGS_DIR": self._cq_root / "logs",
            "RUNTIME_DIR": self._cq_root / "runtime",
        }

    @property
    def cq_root(self) -> Path:
        """Get CQ_ROOT"""
        return self._cq_root

    @property
    def repo_root(self) -> Path:
        """Alias for CQ_ROOT (backward compatibility)"""
        return self._cq_root

    def get_path(self, key: str) -> Path:
        """Get canonical path by key"""
        if key not in self._paths:
            raise ValueError(
                f"Unknown path key: {key}. Available: {list(self._paths.keys())}"
            )

        return self._paths[key]

    def get_all_paths(self) -> Dict[str, Path]:
        """Get all canonical paths"""
        return self._paths.copy()

    def validate_path(self, path: Path) -> bool:
        """Validate path is within CQ_ROOT"""
        try:
            path.resolve().relative_to(self._cq_root)
            return True
        except ValueError:
            return False

    def log_paths(self, service_name: str = None):
        """Log all canonical paths for debugging"""
        import logging

        logger = logging.getLogger("PathRegistry")

        banner = ["=" * 60]
        if service_name:
            banner.append(f"PathRegistry - Service: {service_name}")
        else:
            banner.append("PathRegistry - Canonical Paths")
        banner.append("=" * 60)

        for key, path in self._paths.items():
            exists = "✓" if path.exists() else "✗"
            banner.append(f"{key:25s}: {exists} {path}")

        banner.append("=" * 60)

        banner_text = "\n".join(banner)
        print(banner_text, flush=True)
        logger.info(f"PathRegistry banner:\n{banner_text}")

        return banner_text


# Global instance
_registry = PathRegistry.current()


# Convenience functions
def get_cq_root() -> Path:
    """Get CQ_ROOT"""
    return _registry.cq_root


def get_path(key: str) -> Path:
    """Get canonical path by key"""
    return _registry.get_path(key)


def get_all_paths() -> Dict[str, Path]:
    """Get all canonical paths"""
    return _registry.get_all_paths()


def log_paths(service_name: str = None):
    """Log all canonical paths"""
    return _registry.log_paths(service_name)


# Specific path getters
def get_health_uds_path() -> Path:
    """Get UDS health heartbeat path"""
    return get_path("HEALTH_UDS")


def get_databus_snapshot_path() -> Path:
    """Get databus snapshot path"""
    return get_path("DATABUS_SNAPSHOT")


def get_account_snapshot_path() -> Path:
    """Get account snapshot path (with legacy fallback)"""
    # Try new location first
    new_path = get_path("ACCOUNT_SNAPSHOT")
    if new_path.exists():
        return new_path

    # Fallback to legacy location
    return get_path("ACCOUNT_SNAPSHOT_LEGACY")


def get_uds_heartbeat_path() -> Path:
    """Get UDS heartbeat path"""
    return get_path("UDS_HEARTBEAT")


def get_uds_snapshot_path() -> Path:
    """Get UDS databus snapshot path"""
    return get_path("DATABUS_SNAPSHOT")


def validate_cq_root():
    """Validate current working directory is within CQ_ROOT"""
    cwd = Path.cwd()
    cq_root = get_cq_root()

    try:
        cwd.resolve().relative_to(cq_root)
        return True
    except ValueError:
        print(f"WARNING: CWD {cwd} is not within CQ_ROOT {cq_root}", flush=True)
        return False


# ========== get_absolute_path (restored) ==========


def _project_root() -> Path:
    """
    Get project root directory.
    Uses CQ_ROOT env var if set, otherwise infers from current file location.
    """
    # CQ_ROOT 우선, 없으면 repo root 추정
    env_root = os.getenv("CQ_ROOT")
    if env_root:
        return Path(env_root).resolve()
    # .../shared/path_registry.py -> repo_root = parents[1]
    return Path(__file__).resolve().parents[1]


def get_absolute_path(*segments) -> Path:
    """
    Join repo root (or CQ_ROOT) with given path segments and return a Path object.
    Supports the / operator for further path construction.
    Windows-safe path joins.

    Args:
        *segments: Path segments to join (e.g., 'shared_data', 'health', 'uds.json')

    Returns:
        Path: Path object (supports / operator, use str(path) for string)

    Examples:
        >>> get_absolute_path('shared_data', 'health', 'uds.json')
        WindowsPath('C:/Users/.../coin_quant/shared_data/health/uds.json')

        >>> get_absolute_path('shared_data') / 'env_ssot.json'
        WindowsPath('C:/Users/.../coin_quant/shared_data/env_ssot.json')
    """
    root = _project_root()
    return root.joinpath(*segments)


def resolve_path(*segments) -> Path:
    """
    Resolve Path object from CQ_ROOT with given segments.

    Args:
        *segments: Path segments to join

    Returns:
        Path: Path object (alias for get_absolute_path, now redundant)
    """
    # Now that get_absolute_path returns Path, this is just an alias
    return get_absolute_path(*segments)


# Export public API
__all__ = [
    "PathRegistry",
    "CQ_ROOT_VIOLATION",
    "get_cq_root",
    "get_path",
    "get_all_paths",
    "log_paths",
    "get_absolute_path",
    "resolve_path",
    "get_health_uds_path",
    "get_databus_snapshot_path",
    "get_account_snapshot_path",
    "get_uds_heartbeat_path",
    "get_uds_snapshot_path",
    "validate_cq_root",
    "atomic_write",  # Re-exported from atomic_io
]


# Self-test (guarded import-time check)
if __name__ != "__main__":
    try:
        # Verify get_absolute_path works and returns Path objects
        test_path = get_absolute_path("shared_data", "health", "uds.json")

        # Verify it's a Path object
        assert isinstance(
            test_path, Path
        ), f"get_absolute_path should return Path, got {type(test_path)}"

        # Check that the directory prefix exists (parent of parent = shared_data)
        shared_data_dir = test_path.parent.parent
        if not shared_data_dir.exists():
            # Only warn, don't fail - directory might not exist yet
            import logging

            logger = logging.getLogger("PathRegistry")
            logger.debug(
                f"PathRegistry self-test: shared_data directory not found at {shared_data_dir} (may be created later)"
            )
    except Exception as e:
        # Silent fail on self-test - don't break module import
        pass

try:
    from .atomic_io import atomic_write  # re-export for legacy imports
except Exception as _e:
    import logging as _logging

    _logging.getLogger(__name__).warning("atomic_write unavailable: %s", _e)
    atomic_write = None  # type: ignore
