#!/usr/bin/env python3
"""
Windows-Safe File I/O Module (Re-export from canonical)
========================================================
⚠️ DEPRECATED: This module now re-exports from shared.io_canonical.
   Direct imports from shared.io_canonical are preferred.

All functions now delegate to shared.io_canonical for consistency.
"""

# Re-export from canonical (single source of truth)
from .io_canonical import (
    append_ndjson_safe,
    atomic_write_json,
    cleanup_temp_files,
    ensure_parent_dir,
    read_json_safe as read_json_cooperative,
    replace_tmp,
)

# Legacy WriteResult for backward compat
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class WriteResult:
    """[DEPRECATED] Result of atomic write operation"""
    success: bool
    path: str
    temp_path: Optional[str]
    attempts: int
    duration_ms: float
    error: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "path": self.path,
            "temp_path": self.temp_path,
            "attempts": self.attempts,
            "duration_ms": round(self.duration_ms, 2),
            "error": self.error,
        }


def atomic_write(path, data: bytes | str, encoding: str = "utf-8", **kwargs) -> WriteResult:
    """
    [DEPRECATED] Windows-safe atomic file write.
    
    For JSON files, use atomic_write_json() from io_canonical instead.
    
    Returns WriteResult for backward compatibility.
    """
    import time
    from pathlib import Path
    
    start = time.time()
    path = Path(path)
    
    try:
        if isinstance(data, dict):
            # JSON data
            success = atomic_write_json(path, data)
        else:
            # Raw data - basic atomic write
            import os
            import tempfile
            
            ensure_parent_dir(path)
            
            # Write to temp
            fd, tmp_path = tempfile.mkstemp(prefix=f".{path.name}.tmp_", dir=path.parent)
            try:
                if isinstance(data, str):
                    with open(fd, 'w', encoding=encoding) as f:
                        f.write(data)
                        f.flush()
                        os.fsync(f.fileno())
                else:
                    with open(fd, 'wb') as f:
                        f.write(data)
                        f.flush()
                        os.fsync(f.fileno())
                
                success = replace_tmp(tmp_path, path)
            finally:
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except:
                    pass
        
        duration = (time.time() - start) * 1000
        
        return WriteResult(
            success=success,
            path=str(path),
            temp_path=None,
            attempts=1,
            duration_ms=duration,
            error=None if success else "Write failed"
        )
    
    except Exception as e:
        duration = (time.time() - start) * 1000
        return WriteResult(
            success=False,
            path=str(path),
            temp_path=None,
            attempts=1,
            duration_ms=duration,
            error=str(e)
        )


# Backward compat aliases
read_ndjson_cooperative = None  # Not commonly used, removed


__all__ = [
    "atomic_write",
    "atomic_write_json",
    "read_json_cooperative",
    "append_ndjson_safe",
    "cleanup_temp_files",
    "WriteResult",
]
