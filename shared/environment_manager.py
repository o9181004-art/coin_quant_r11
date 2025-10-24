#!/usr/bin/env python3
"""
Environment Manager - Unified SSOT with Drift Detection & Reconciliation
Implements deterministic ENV_HASH, material key filtering, and one-click reconcile

=============================================================================
API INVENTORY (Canonical Functions)
=============================================================================
Core Getters (pure, no side-effects):
  - get_ssot_path()          → Path to env_ssot.json
  - get_health_path()        → Path to health.json
  - get_env_hash()           → Current environment hash
  - get_material_env()       → Material environment dict
  - get_mode_status()        → Trading mode status
  
Drift Detection:
  - detect_env_drift()       → Optional[DriftDiff]
  - get_drift_status()       → Drift status for UI
  - get_masked_diff()        → Masked drift diff (secrets hidden)
  
Reconciliation:
  - reconcile_to_runtime()   → Save runtime → SSOT
  - reconcile_to_ssot()      → Load SSOT → runtime
  
Utilities:
  - material_keys()          → Material key patterns
  - excluded_volatile_keys() → Volatile key patterns
  - refresh_environment()    → Reload from OS env
  - self_test()              → Consistency check
=============================================================================
"""

import hashlib
import json
import os
import time
import warnings
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


# ============================================================================
# Path Resolution (Single Source)
# ============================================================================

# Try to import from path_registry, otherwise use fallback
_PATH_REGISTRY_AVAILABLE = False
try:
    from .path_registry import get_absolute_path as _imported_get_abs
    _PATH_REGISTRY_AVAILABLE = True
except (ImportError, AttributeError, ModuleNotFoundError):
    # Module not found or attribute missing - try resolve_path alias
    try:
        from .path_registry import resolve_path as _imported_get_abs
        _PATH_REGISTRY_AVAILABLE = True
    except (ImportError, AttributeError, ModuleNotFoundError):
        # Path registry not available - will use fallback implementation
        _imported_get_abs = None


def get_absolute_path(*segments) -> Path:
    """
    Smart path resolver with fallback chain (returns Path object).
    
    Resolution Strategy:
      1. If path_registry available: use get_absolute_path() or resolve_path()
      2. Otherwise: use CQ_ROOT env var
      3. Final fallback: derive from __file__ location
    
    Returns:
        Path object (never str)
    """
    if _PATH_REGISTRY_AVAILABLE and _imported_get_abs:
        result = _imported_get_abs(*segments)
        return result if isinstance(result, Path) else Path(result)
    
    # Fallback: use CQ_ROOT or derive from __file__
    root = os.getenv("CQ_ROOT")
    if not root:
        root = str(Path(__file__).resolve().parents[1])
    
    return Path(root).joinpath(*segments)


class DriftSeverity(Enum):
    """Drift severity levels"""
    NONE = "none"
    SOFT = "soft"  # Non-critical changes
    HARD = "hard"  # Safety-critical changes


@dataclass
class EnvironmentSnapshot:
    """Environment snapshot for SSOT storage"""
    material_env: Dict[str, str]
    env_hash: str
    updated_at: float
    source: str
    file_sources: List[str]


@dataclass
class DriftDiff:
    """Environment drift difference"""
    added: Dict[str, str]
    removed: Dict[str, str]
    changed: Dict[str, Tuple[str, str]]
    severity: DriftSeverity


class EnvironmentManager:
    """Unified environment manager with SSOT and drift detection"""
    
    # Volatile keys to exclude from hash computation
    VOLATILE_KEYS = {
        'PATH', 'PWD', 'HOME', 'VIRTUAL_ENV', 'PYTHONPATH', 'TEMP', 'TMP',
        'SESSION_TOKEN', 'TIMESTAMP', 'PID', 'USER', 'USERNAME', 'COMPUTERNAME',
        'PROCESSOR_ARCHITECTURE', 'NUMBER_OF_PROCESSORS', 'OS', 'PATHEXT'
    }
    
    # Material keys that affect system behavior
    MATERIAL_KEY_PATTERNS = {
        'BINANCE_', 'KIS_', 'TESTNET', 'LIVE_MODE', 'RUN_MODE',
        'TRADER_', 'FEEDER_', 'ARES_', 'AUTO_', 'RISK_', 'CACHE_',
        'WEBSOCKET_', 'REST_', 'API_', 'SYMBOL_', 'DATA_PATH',
        'ENABLE_', 'DISABLE_', 'MODE_', 'CONFIG_', 'ENDPOINT_',
        'TTL_', 'TIMEOUT_', 'RETRY_', 'LIMIT_', 'THRESHOLD_',
        'TRADING_', 'LIVE_'
    }
    
    # Safety-critical keys that block trading on drift
    SAFETY_CRITICAL_KEYS = {
        'BINANCE_API_KEY', 'BINANCE_API_SECRET', 'KIS_APPKEY', 'KIS_APPSECRET',
        'TESTNET', 'LIVE_MODE', 'TRADING_MODE', 'LIVE_TRADING_ENABLED', 'RISK_LIMIT', 'MAX_POSITION_SIZE',
        'API_ENDPOINT', 'WEBSOCKET_ENDPOINT'
    }
    
    def __init__(self):
        self.ssot_file = self.get_ssot_path()
        self.ssot_file.parent.mkdir(parents=True, exist_ok=True)
        
        self._material_env: Dict[str, str] = {}
        self._env_hash: Optional[str] = None
        self._ssot_snapshot: Optional[EnvironmentSnapshot] = None
        self._loaded_sources: List[str] = []
        
        self._load_environment()
        self._load_ssot()
        self._compute_hash()
        
        # Log SSOT path for debugging
        self._log_ssot_path()
    
    @staticmethod
    def get_ssot_path() -> Path:
        """Get the canonical SSOT file path using PathRegistry"""
        return get_absolute_path('shared_data') / 'env_ssot.json'
    
    @staticmethod
    def get_health_path() -> Path:
        """Get the canonical health file path using PathRegistry"""
        return get_absolute_path('shared_data') / 'health.json'
    
    def _load_environment(self):
        """Load environment with unified precedence: .env.local → .env → OS env"""
        self._material_env = {}
        loaded_sources = []
        
        # Priority order: .env.local → .env → config.env → OS env
        config_files = [
            get_absolute_path('config') / '.env.local',
            get_absolute_path('config') / '.env',
            get_absolute_path('config') / 'config.env',
            Path.cwd() / '.env.local',
            Path.cwd() / '.env',
            get_absolute_path('repo_root') / 'config.env'
        ]
        
        # Load config files (later files override earlier ones)
        for config_file in config_files:
            if config_file.exists():
                try:
                    self._load_env_file(config_file)
                    loaded_sources.append(str(config_file))
                except (FileNotFoundError, PermissionError, OSError) as e:
                    print(f"[ENV_LOAD_FAIL] path={config_file}, error={type(e).__name__}: {e}")
                except (UnicodeDecodeError, ValueError) as e:
                    print(f"[ENV_PARSE_FAIL] path={config_file}, error={type(e).__name__}: {e}")
        
        # Override with OS environment variables
        for key, value in os.environ.items():
            if self._is_material_key(key):
                self._material_env[key] = value
        
        # Store source information
        self._loaded_sources = loaded_sources
    
    def refresh_environment(self):
        """Refresh environment from current OS environment"""
        # Update material environment from current OS environment
        for key, value in os.environ.items():
            if self._is_material_key(key):
                self._material_env[key] = value
        
        # Remove keys that are no longer in OS environment
        keys_to_remove = []
        for key in self._material_env.keys():
            if key not in os.environ:
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del self._material_env[key]
        
        # Recompute hash
        self._compute_hash()
        print(f"INFO: Environment refreshed, new hash: {self._env_hash}")
    
    def setup_environment(self):
        """Load environment and set OS environment variables"""
        # Load environment from files
        self._load_environment()
        
        # Set OS environment variables from loaded material environment
        for key, value in self._material_env.items():
            os.environ[key] = value
        
        # Recompute hash
        self._compute_hash()
        print(f"INFO: Environment setup complete, hash: {self._env_hash}")
    
    def _load_env_file(self, file_path: Path):
        """Load environment variables from a file"""
        with open(file_path, 'r', encoding='utf-8') as f:
            for _, line in enumerate(f, 1):  # line_num not used, use _ instead
                line = line.strip()
                
                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue
                
                # Parse KEY=VALUE
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # Remove quotes if present
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]
                    
                    # Only store material keys
                    if self._is_material_key(key):
                        self._material_env[key] = value
    
    def _is_material_key(self, key: str) -> bool:
        """Check if a key is material (affects system behavior)"""
        # Exclude volatile keys
        if key in self.VOLATILE_KEYS:
            return False
        
        # Check material key patterns
        for pattern in self.MATERIAL_KEY_PATTERNS:
            if key.startswith(pattern):
                return True
        
        return False
    
    def _compute_hash(self):
        """Compute stable SHA-256 hash of material environment"""
        # Sort keys for consistent hash
        sorted_items = sorted(self._material_env.items())
        
        # Create normalized JSON string
        normalized_dict = {k: v for k, v in sorted_items}
        json_string = json.dumps(normalized_dict, sort_keys=True, separators=(',', ':'))
        
        # Compute SHA-256 hash and take first 7 characters
        full_hash = hashlib.sha256(json_string.encode('utf-8')).hexdigest()
        self._env_hash = full_hash[:7]
    
    def _log_ssot_path(self):
        """Log SSOT path for debugging"""
        print(f"🔧 EnvironmentManager SSOT path: {self.ssot_file.absolute()}")
    
    def material_keys(self) -> Set[str]:
        """Get set of material key patterns for consistency checking"""
        return self.MATERIAL_KEY_PATTERNS.copy()
    
    def excluded_volatile_keys(self) -> Set[str]:
        """Get set of volatile keys for consistency checking"""
        return self.VOLATILE_KEYS.copy()
    
    def _load_ssot(self):
        """Load SSOT snapshot from file"""
        # Log absolute SSOT path
        print(f"INFO: ssot_path={self.ssot_file.absolute()}")
        
        if self.ssot_file.exists():
            try:
                with open(self.ssot_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                self._ssot_snapshot = EnvironmentSnapshot(
                    material_env=data.get('material_env', {}),
                    env_hash=data.get('env_hash', ''),
                    updated_at=data.get('updated_at', 0),
                    source=data.get('source', 'unknown'),
                    file_sources=data.get('file_sources', [])
                )
            except FileNotFoundError:
                # SSOT file not found - normal for first run
                self._ssot_snapshot = None
            except (PermissionError, OSError) as e:
                print(f"[SSOT_LOAD_FAIL] path={self.ssot_file}, error={type(e).__name__}: {e}")
                self._ssot_snapshot = None
            except json.JSONDecodeError as e:
                print(f"[SSOT_PARSE_FAIL] path={self.ssot_file}, line={e.lineno}, col={e.colno}: {e.msg}")
                self._ssot_snapshot = None
            except (KeyError, ValueError, TypeError) as e:
                print(f"[SSOT_SCHEMA_FAIL] path={self.ssot_file}, error={type(e).__name__}: {e}")
                self._ssot_snapshot = None
        else:
            self._ssot_snapshot = None
    
    def _save_ssot(self, source: str = 'runtime'):
        """Save current environment as SSOT"""
        snapshot = EnvironmentSnapshot(
            material_env=self._material_env.copy(),
            env_hash=self._env_hash,
            updated_at=time.time(),
            source=source,
            file_sources=self._loaded_sources
        )
        
        temp_file = None
        try:
            # Log absolute SSOT path
            print(f"INFO: ssot_path={self.ssot_file.absolute()}")
            
            # Atomic write
            temp_file = self.ssot_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(asdict(snapshot), f, indent=2)
            
            os.replace(temp_file, self.ssot_file)
            self._ssot_snapshot = snapshot
            
            # Log reconciliation
            self._log_reconcile(source, "SSOT updated")
            
        except (PermissionError, OSError) as e:
            print(f"[SSOT_WRITE_FAIL] path={self.ssot_file}, op=write, error={type(e).__name__}: {e}")
            if temp_file and temp_file.exists():
                try:
                    temp_file.unlink()
                except OSError:
                    pass  # Best effort cleanup
        except (TypeError, ValueError) as e:
            print(f"[SSOT_SERIALIZE_FAIL] error={type(e).__name__}: {e}")
            if temp_file and temp_file.exists():
                try:
                    temp_file.unlink()
                except OSError:
                    pass
    
    def _log_reconcile(self, source: str, action: str, diff_summary: str = ""):
        """Log reconciliation events for audit trail"""
        log_entry = {
            'timestamp': time.time(),
            'datetime': datetime.now(timezone.utc).isoformat(),
            'source': source,
            'action': action,
            'diff_summary': diff_summary,
            'resulting_hash': self._env_hash
        }
        
        # Append to reconciliation log
        log_file = get_absolute_path('shared_data') / 'env_reconcile.log'
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry) + '\n')
        except (PermissionError, OSError) as e:
            print(f"[LOG_WRITE_FAIL] path={log_file}, error={type(e).__name__}: {e}")
    
    def get_env_hash(self) -> str:
        """Get current environment hash"""
        return self._env_hash or "unknown"
    
    def get_material_env(self) -> Dict[str, str]:
        """Get material environment variables"""
        return self._material_env.copy()
    
    def get_ssot_hash(self) -> str:
        """Get SSOT environment hash"""
        return self._ssot_snapshot.env_hash if self._ssot_snapshot else "unknown"
    
    def detect_drift(self) -> Optional[DriftDiff]:
        """Detect environment drift between current and SSOT"""
        if not self._ssot_snapshot:
            return None
        
        current_env = self._material_env
        ssot_env = self._ssot_snapshot.material_env
        
        added = {k: v for k, v in current_env.items() if k not in ssot_env}
        removed = {k: v for k, v in ssot_env.items() if k not in current_env}
        changed = {
            k: (ssot_env[k], v) for k, v in current_env.items() 
            if k in ssot_env and ssot_env[k] != v
        }
        
        if not (added or removed or changed):
            return None
        
        # Determine severity
        severity = DriftSeverity.SOFT
        for key in (added.keys() | removed.keys() | changed.keys()):
            if key in self.SAFETY_CRITICAL_KEYS:
                severity = DriftSeverity.HARD
                break
        
        return DriftDiff(
            added=added,
            removed=removed,
            changed=changed,
            severity=severity
        )
    
    def get_drift_status(self) -> Dict[str, Any]:
        """Get drift status for UI display"""
        drift = self.detect_drift()
        
        if not drift:
            return {
                'status': 'green',
                'message': 'No drift detected',
                'current_hash': self.get_env_hash(),
                'ssot_hash': self.get_ssot_hash(),
                'severity': DriftSeverity.NONE.value
            }
        
        status = 'red' if drift.severity == DriftSeverity.HARD else 'yellow'
        message = f'Drift detected ({drift.severity.value})'
        
        return {
            'status': status,
            'message': message,
            'current_hash': self.get_env_hash(),
            'ssot_hash': self.get_ssot_hash(),
            'severity': drift.severity.value,
            'diff': {
                'added': len(drift.added),
                'removed': len(drift.removed),
                'changed': len(drift.changed)
            }
        }
    
    def reconcile_to_runtime(self) -> bool:
        """Reconcile SSOT to current runtime environment"""
        try:
            # Detect drift before saving
            diff = self.detect_drift()
            
            # Calculate diff summary (for logging purposes)
            if diff:
                diff_count = len(diff.added) + len(diff.removed) + len(diff.changed)
                # Note: diff_summary logged in _save_ssot via _log_reconcile
            
            # Save current runtime as SSOT
            self._save_ssot('runtime')
            return True
            
        except (PermissionError, OSError) as e:
            print(f"[RECONCILE_FAIL] op=save_runtime, error={type(e).__name__}: {e}")
            return False
    
    def reconcile_to_ssot(self) -> bool:
        """Reconcile runtime to SSOT (requires service restart)"""
        if not self._ssot_snapshot:
            return False
        
        try:
            # This would require restarting services with SSOT values
            # For now, just update the runtime to match SSOT
            self._material_env = self._ssot_snapshot.material_env.copy()
            self._compute_hash()
            
            # Log the reconciliation
            diff = self.detect_drift()
            diff_summary = "Reconciled to SSOT"
            if diff:
                diff_summary = f"Reconciled to SSOT - {len(diff.added + diff.removed + diff.changed)} changes"
            
            self._log_reconcile('ssot', 'Reconciled to SSOT', diff_summary)
            
            return True
            
        except (TypeError, ValueError, KeyError) as e:
            print(f"[RECONCILE_FAIL] op=load_ssot, error={type(e).__name__}: {e}")
            return False
    
    def get_masked_diff(self) -> Dict[str, Any]:
        """Get drift diff with masked secrets for UI display"""
        drift = self.detect_drift()
        if not drift:
            return {}
        
        def mask_secret(key: str, value: str) -> str:
            if any(pattern in key.lower() for pattern in ['key', 'secret', 'token', 'password']):
                return f"{value[:4]}...{value[-4:]}" if len(value) > 8 else "***"
            return value
        
        return {
            'added': {k: mask_secret(k, v) for k, v in drift.added.items()},
            'removed': {k: mask_secret(k, v) for k, v in drift.removed.items()},
            'changed': {
                k: (mask_secret(k, v1), mask_secret(k, v2)) 
                for k, (v1, v2) in drift.changed.items()
            },
            'severity': drift.severity.value
        }
    
    def get_mode_status(self) -> Dict[str, Any]:
        """Get current trading mode status"""
        testnet = self._material_env.get('TESTNET', 'false').lower() in ('true', '1', 'yes')
        live_mode = self._material_env.get('LIVE_MODE', 'false').lower() in ('true', '1', 'yes')
        
        if testnet:
            mode = 'TESTNET'
            color = 'blue'
        elif live_mode:
            mode = 'LIVE'
            color = 'red'
        else:
            mode = 'UNKNOWN'
            color = 'gray'
        
        return {
            'mode': mode,
            'color': color,
            'locked': self._ssot_snapshot is not None
        }
    
    def get_sources_info(self) -> Dict[str, Any]:
        """Get environment sources information"""
        return {
            'loaded_sources': self._loaded_sources,
            'ssot_source': self._ssot_snapshot.source if self._ssot_snapshot else 'none',
            'ssot_updated': self._ssot_snapshot.updated_at if self._ssot_snapshot else 0,
            'ssot_path': str(self.ssot_file.absolute())
        }
    
    @classmethod
    def self_test(cls) -> Dict[str, Any]:
        """Self-test for consistency across services"""
        manager = cls()
        
        return {
            'material_keys': sorted(manager.material_keys()),
            'excluded_volatile_keys': sorted(manager.excluded_volatile_keys()),
            'ssot_path': str(manager.get_ssot_path().absolute()),
            'current_hash': manager.get_env_hash(),
            'material_env_count': len(manager.get_material_env())
        }
    
    def should_block_trading(self) -> Tuple[bool, str]:
        """Check if trading should be blocked due to drift"""
        drift = self.detect_drift()
        
        if not drift:
            return False, ""
        
        if drift.severity == DriftSeverity.HARD:
            critical_keys = []
            for key in (drift.added.keys() | drift.removed.keys() | drift.changed.keys()):
                if key in self.SAFETY_CRITICAL_KEYS:
                    critical_keys.append(key)
            
            return True, f"Safety-critical drift detected in: {', '.join(critical_keys)}"
        
        return False, ""


# Global instance
_env_manager = EnvironmentManager()


# Public API functions
def get_env_hash() -> str:
    """Get current environment hash"""
    return _env_manager.get_env_hash()


def get_material_env() -> Dict[str, str]:
    """Get material environment variables"""
    return _env_manager.get_material_env()


def get_env(key: str, default: Any = None, cast_type: type = str) -> Any:
    """Get environment variable with type casting"""
    value = _env_manager.get_material_env().get(key, default)
    
    if value is None:
        return None
    
    try:
        if cast_type == bool:
            return str(value).lower() in ('true', '1', 'yes', 'on')
        elif cast_type == int:
            return int(value)
        elif cast_type == float:
            return float(value)
        else:
            return str(value)
    except (ValueError, TypeError):
        return default


def detect_env_drift() -> Optional[DriftDiff]:
    """Detect environment drift"""
    return _env_manager.detect_drift()


def get_drift_status() -> Dict[str, Any]:
    """Get drift status for UI"""
    return _env_manager.get_drift_status()


def reconcile_to_runtime() -> bool:
    """Reconcile SSOT to runtime"""
    return _env_manager.reconcile_to_runtime()


def reconcile_to_ssot() -> bool:
    """Reconcile runtime to SSOT"""
    return _env_manager.reconcile_to_ssot()


def get_mode_status() -> Dict[str, Any]:
    """Get trading mode status"""
    return _env_manager.get_mode_status()


def should_block_trading() -> Tuple[bool, str]:
    """Check if trading should be blocked"""
    return _env_manager.should_block_trading()


def get_masked_diff() -> Dict[str, Any]:
    """Get masked drift diff for UI"""
    return _env_manager.get_masked_diff()


def get_sources_info() -> Dict[str, Any]:
    """Get environment sources info"""
    return _env_manager.get_sources_info()


def refresh_environment():
    """Refresh environment from current OS environment"""
    _env_manager.refresh_environment()


def get_ssot_path() -> Path:
    """Get the canonical SSOT file path"""
    return EnvironmentManager.get_ssot_path()


def material_keys() -> Set[str]:
    """Get material key patterns for consistency checking"""
    return _env_manager.material_keys()


def excluded_volatile_keys() -> Set[str]:
    """Get excluded volatile keys for consistency checking"""
    return _env_manager.excluded_volatile_keys()


def self_test() -> Dict[str, Any]:
    """Run self-test for consistency across services"""
    return EnvironmentManager.self_test()


if __name__ == '__main__':
    # Test environment manager
    print("Environment Manager Test:")
    print(f"ENV_HASH: {get_env_hash()}")
    print(f"Mode: {get_mode_status()}")
    print(f"Drift Status: {get_drift_status()}")
    print(f"Sources: {get_sources_info()}")