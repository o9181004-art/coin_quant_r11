#!/usr/bin/env python3
"""
Canonical I/O API - Single Source of Truth (SSOT) Enforcement

Provides standardized path resolution and atomic writing with metadata injection.
All services must use this module for file I/O operations.
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Union
import tempfile
import shutil
import inspect

# Import path guard for policy enforcement
from guard.path_guard import assert_in_ssot

# Import memory drift guard for consistency validation
try:
    from guard.memory_drift_guard import validate_producer_consistency, validate_path_in_ssot
    _DRIFT_GUARD_AVAILABLE = True
except ImportError:
    _DRIFT_GUARD_AVAILABLE = False


class SSOTPathResolver:
    """Single Source of Truth path resolver"""
    
    def __init__(self):
        self._ssot_dir = None
        self._project_root = None
    
    def get_ssot_dir(self) -> Path:
        """Get SSOT directory: Env(SHARED_DATA) else CQ_ROOT/shared_data"""
        if self._ssot_dir is None:
            # Check SHARED_DATA environment variable first
            shared_data_env = os.getenv('SHARED_DATA')
            if shared_data_env:
                self._ssot_dir = Path(shared_data_env).resolve()
            else:
                # Fallback to CQ_ROOT/shared_data
                cq_root = os.getenv('CQ_ROOT')
                if cq_root:
                    self._ssot_dir = Path(cq_root).resolve() / 'shared_data'
                else:
                    # Ultimate fallback: project root/shared_data
                    project_root = self.get_project_root()
                    self._ssot_dir = project_root / 'shared_data'
            
            # Ensure SSOT directory exists
            self._ssot_dir.mkdir(parents=True, exist_ok=True)
            
        return self._ssot_dir
    
    def get_project_root(self) -> Path:
        """Get project root directory"""
        if self._project_root is None:
            # Find project root by looking for common markers
            current_path = Path(__file__).resolve()
            
            # Look for project markers going up the directory tree
            for parent in current_path.parents:
                if any((parent / marker).exists() for marker in ['config.env', 'requirements.txt', 'pyproject.toml']):
                    self._project_root = parent
                    break
            
            if self._project_root is None:
                # Fallback: assume current file is in project_root/shared/
                self._project_root = current_path.parent.parent
        
        return self._project_root
    
    def artifact(self, path: str) -> Path:
        """Get absolute path under SSOT (raise if outside)
        
        CRITICAL: This function enforces SSOT isolation and prevents path drift.
        
        - NO basename extraction (.name)
        - NO CWD rejoining
        - NO path mutation
        - ONLY absolute path resolution and validation
        
        Raises:
            ValueError: If path is outside SSOT or contains suspicious patterns
        """
        ssot_dir = self.get_ssot_dir()
        
        # Convert to string if Path object
        path_str = str(path)
        
        # Detect and reject bare filenames (path drift prevention)
        if '/' not in path_str and '\\' not in path_str and not os.path.isabs(path_str):
            # This is a bare filename like "account_info.json"
            # We allow it but log a warning and resolve to SSOT
            import warnings
            warnings.warn(
                f"Bare filename '{path_str}' detected. Should use full path from shared.paths module.",
                UserWarning,
                stacklevel=3
            )
        
        # Resolve the path
        if os.path.isabs(path_str):
            artifact_path = Path(path_str).resolve()
        else:
            # Relative path: join with SSOT dir
            artifact_path = (ssot_dir / path_str).resolve()
        
        # Security check: ensure path is under SSOT (no escaping)
        try:
            artifact_path.relative_to(ssot_dir)
        except ValueError:
            raise ValueError(
                f"SSOT VIOLATION: Path '{path}' resolves to '{artifact_path}' "
                f"which is OUTSIDE SSOT directory '{ssot_dir}'. "
                f"This indicates a path drift bug. Use paths from shared.paths module."
            )
        
        # Additional check: ensure no path traversal attempts
        if '..' in path_str:
            raise ValueError(
                f"SSOT VIOLATION: Path traversal detected in '{path_str}'. "
                f"Use absolute paths from shared.paths module."
            )
        
        return artifact_path


# Global path resolver instance
_path_resolver = SSOTPathResolver()


def get_ssot_dir() -> Path:
    """Get SSOT directory"""
    return _path_resolver.get_ssot_dir()


def artifact(path: str) -> Path:
    """Get absolute path under SSOT (raise if outside)"""
    return _path_resolver.artifact(path)


def _get_caller_metadata() -> Dict[str, Any]:
    """Get metadata about the calling module"""
    try:
        # Get the frame of the caller (2 levels up: _write_json_atomic -> write_json_atomic -> actual caller)
        frame = inspect.currentframe()
        for _ in range(3):
            frame = frame.f_back
            if frame is None:
                break
        
        if frame:
            module_name = frame.f_globals.get('__name__', 'unknown')
            filename = frame.f_code.co_filename
            function_name = frame.f_code.co_name
            
            return {
                'producer': module_name,
                'caller_file': os.path.basename(filename),
                'caller_function': function_name
            }
    except Exception:
        pass
    
    return {
        'producer': 'unknown',
        'caller_file': 'unknown',
        'caller_function': 'unknown'
    }


def _inject_metadata(obj: Any, schema_ver: str = "1.0") -> Any:
    """Inject canonical metadata into JSON object"""
    if isinstance(obj, dict):
        # Inject metadata into existing dict
        metadata = _get_caller_metadata()
        metadata.update({
            'schema_ver': schema_ver,
            'updated_at': datetime.utcnow().isoformat() + 'Z'
        })
        
        # Create new dict with metadata
        result = obj.copy()
        result['_metadata'] = metadata
        return result
    else:
        # For non-dict objects, wrap in metadata container
        metadata = _get_caller_metadata()
        metadata.update({
            'schema_ver': schema_ver,
            'updated_at': datetime.utcnow().isoformat() + 'Z'
        })
        
        return {
            '_metadata': metadata,
            '_data': obj
        }


def write_json_atomic(path: Union[str, Path], obj: Any, schema_ver: str = "1.0", **kwargs) -> bool:
    """
    Write JSON atomically with metadata injection
    
    Args:
        path: Path relative to SSOT or absolute path under SSOT
        obj: Object to serialize to JSON
        schema_ver: Schema version string
        **kwargs: Additional arguments for json.dump
    
    Returns:
        True if successful, False otherwise
    """
    try:
        # Enforce SSOT policy
        assert_in_ssot(str(path), "write_json_atomic")
        
        # Memory drift guard (optional)
        if _DRIFT_GUARD_AVAILABLE:
            metadata = _get_caller_metadata()
            producer = metadata.get('producer', 'unknown')
            validate_producer_consistency(str(path), producer)
            validate_path_in_ssot(str(path))
        
        # Resolve path through SSOT
        artifact_path = artifact(str(path))
        
        # Ensure parent directory exists
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Inject metadata
        obj_with_metadata = _inject_metadata(obj, schema_ver)
        
        # Prepare JSON data
        json_data = json.dumps(obj_with_metadata, ensure_ascii=False, **kwargs)
        
        # Atomic write using temporary file
        temp_fd, temp_path = tempfile.mkstemp(
            prefix=f'.tmp_{artifact_path.name}_',
            suffix='.json',
            dir=artifact_path.parent,
            text=True
        )
        
        try:
            # Write to temporary file
            with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                f.write(json_data)
            
            # Atomic move
            shutil.move(temp_path, artifact_path)
            
            return True
            
        except Exception:
            # Cleanup temporary file on error
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise
            
    except Exception as e:
        print(f"Error writing JSON to {path}: {e}", file=sys.stderr)
        return False


def write_ndjson_atomic(path: Union[str, Path], objects: list, schema_ver: str = "1.0", **kwargs) -> bool:
    """
    Write NDJSON atomically with metadata injection
    
    Args:
        path: Path relative to SSOT or absolute path under SSOT
        objects: List of objects to serialize to NDJSON
        schema_ver: Schema version string
        **kwargs: Additional arguments for json.dumps
    
    Returns:
        True if successful, False otherwise
    """
    try:
        # Enforce SSOT policy
        assert_in_ssot(str(path), "write_ndjson_atomic")
        
        # Resolve path through SSOT
        artifact_path = artifact(str(path))
        
        # Ensure parent directory exists
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Prepare NDJSON data
        lines = []
        for obj in objects:
            # Inject metadata into each object
            obj_with_metadata = _inject_metadata(obj, schema_ver)
            lines.append(json.dumps(obj_with_metadata, ensure_ascii=False, **kwargs))
        
        ndjson_data = '\n'.join(lines) + '\n'
        
        # Atomic write using temporary file
        temp_fd, temp_path = tempfile.mkstemp(
            prefix=f'.tmp_{artifact_path.name}_',
            suffix='.ndjson',
            dir=artifact_path.parent,
            text=True
        )
        
        try:
            # Write to temporary file
            with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                f.write(ndjson_data)
            
            # Atomic move
            shutil.move(temp_path, artifact_path)
            
            return True
            
        except Exception:
            # Cleanup temporary file on error
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise
            
    except Exception as e:
        print(f"Error writing NDJSON to {path}: {e}", file=sys.stderr)
        return False


def append_ndjson_atomic(path: Union[str, Path], obj: Any, schema_ver: str = "1.0", **kwargs) -> bool:
    """
    Append to NDJSON atomically with metadata injection
    
    Args:
        path: Path relative to SSOT or absolute path under SSOT
        obj: Object to append to NDJSON
        schema_ver: Schema version string
        **kwargs: Additional arguments for json.dumps
    
    Returns:
        True if successful, False otherwise
    """
    try:
        # Enforce SSOT policy
        assert_in_ssot(str(path), "append_ndjson_atomic")
        
        # Resolve path through SSOT
        artifact_path = artifact(str(path))
        
        # Ensure parent directory exists
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Inject metadata
        obj_with_metadata = _inject_metadata(obj, schema_ver)
        
        # Prepare JSON line
        json_line = json.dumps(obj_with_metadata, ensure_ascii=False, **kwargs) + '\n'
        
        # Atomic append using temporary file
        temp_fd, temp_path = tempfile.mkstemp(
            prefix=f'.tmp_{artifact_path.name}_',
            suffix='.ndjson',
            dir=artifact_path.parent,
            text=True
        )
        
        try:
            # Copy existing content if file exists
            if artifact_path.exists():
                with open(artifact_path, 'r', encoding='utf-8') as src:
                    shutil.copyfileobj(src, os.fdopen(temp_fd, 'w', encoding='utf-8'))
            else:
                os.fdopen(temp_fd, 'w', encoding='utf-8').close()
            
            # Append new line
            with open(temp_path, 'a', encoding='utf-8') as f:
                f.write(json_line)
            
            # Atomic move
            shutil.move(temp_path, artifact_path)
            
            return True
            
        except Exception:
            # Cleanup temporary file on error
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise
            
    except Exception as e:
        print(f"Error appending to NDJSON {path}: {e}", file=sys.stderr)
        return False


# Convenience functions for common operations
def write_health_json(data: Dict[str, Any]) -> bool:
    """Write health.json with canonical metadata"""
    try:
        from .paths import HEALTH_PATH
        return write_json_atomic(str(HEALTH_PATH), data, schema_ver="1.0", indent=2)
    except ImportError:
        # Fallback to relative path
        return write_json_atomic("shared_data/health.json", data, schema_ver="1.0", indent=2)


def write_databus_snapshot(data: Dict[str, Any]) -> bool:
    """Write databus_snapshot.json with canonical metadata"""
    return write_json_atomic("databus_snapshot.json", data, schema_ver="1.0", indent=2)


def write_account_info(data: Dict[str, Any]) -> bool:
    """Write account_info.json with canonical metadata
    
    IMPORTANT: Uses ACCOUNT_SNAPSHOT_PATH from shared.paths to prevent path drift
    """
    try:
        from .paths import ACCOUNT_SNAPSHOT_PATH
        return write_json_atomic(str(ACCOUNT_SNAPSHOT_PATH), data, schema_ver="1.0", indent=2)
    except ImportError:
        # Fallback to relative path with warning
        import warnings
        warnings.warn(
            "shared.paths not available, using fallback path for account_info.json",
            UserWarning
        )
        return write_json_atomic("account_info.json", data, schema_ver="1.0", indent=2)


def write_ares_status(data: Dict[str, Any]) -> bool:
    """Write ares_status.json with canonical metadata"""
    return write_json_atomic("ares/ares_status.json", data, schema_ver="1.0", indent=2)


def write_candidates_ndjson(candidates: list) -> bool:
    """Write candidates.ndjson with canonical metadata"""
    return write_ndjson_atomic("logs/candidates.ndjson", candidates, schema_ver="1.0")


def append_candidate(candidate: Dict[str, Any]) -> bool:
    """Append single candidate to candidates.ndjson"""
    return append_ndjson_atomic("logs/candidates.ndjson", candidate, schema_ver="1.0")


def write_trader_heartbeat(data: Dict[str, Any]) -> bool:
    """Write trader.heartbeat.json with canonical metadata"""
    return write_json_atomic("shared_data/health/trader.heartbeat.json", data, schema_ver="1.0", indent=2)


# Example usage and testing
if __name__ == "__main__":
    # Test the canonical I/O API
    print("Testing Canonical I/O API...")
    
    # Test path resolution
    ssot_dir = get_ssot_dir()
    print(f"SSOT Directory: {ssot_dir}")
    
    # Test artifact path resolution
    health_path = artifact("health.json")
    print(f"Health artifact path: {health_path}")
    
    # Test writing
    test_data = {
        "status": "running",
        "timestamp": time.time(),
        "services": ["feeder", "trader", "ares"]
    }
    
    success = write_json_atomic("test_canonical.json", test_data)
    print(f"Write test: {'SUCCESS' if success else 'FAILED'}")
    
    # Test NDJSON writing
    test_candidates = [
        {"symbol": "BTCUSDT", "side": "buy", "confidence": 0.8},
        {"symbol": "ETHUSDT", "side": "sell", "confidence": 0.7}
    ]
    
    success = write_ndjson_atomic("test_candidates.ndjson", test_candidates)
    print(f"NDJSON write test: {'SUCCESS' if success else 'FAILED'}")
    
    # Cleanup
    try:
        artifact("test_canonical.json").unlink()
        artifact("test_candidates.ndjson").unlink()
        print("Cleanup completed")
    except FileNotFoundError:
        pass
    
    print("Canonical I/O API test completed!")