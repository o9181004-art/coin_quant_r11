"""
Windows-safe atomic JSON writer with retry logic.
Handles ERROR_ACCESS_DENIED and ERROR_SHARING_VIOLATION gracefully.
"""

import ctypes
import json
import logging
import os
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class WriteResult:
    """Result of atomic write operation"""
    ok: bool
    retries: int = 0
    last_errno: Optional[int] = None
    latency_ms: float = 0.0
    error_message: str = ""


# Windows error codes
ERROR_ACCESS_DENIED = 5
ERROR_SHARING_VIOLATION = 32

# Windows API constants
MOVEFILE_REPLACE_EXISTING = 0x1
MOVEFILE_WRITE_THROUGH = 0x8


def _move_file_windows(src: str, dst: str, max_retries: int = 8) -> WriteResult:
    """
    Windows-specific atomic move using MoveFileExW with retry logic.
    
    Args:
        src: Source file path
        dst: Destination file path
        max_retries: Maximum number of retries (default: 8)
    
    Returns:
        WriteResult with ok, retries, last_errno
    """
    start_time = time.time()
    
    # Load MoveFileExW from kernel32.dll
    try:
        kernel32 = ctypes.windll.kernel32
        MoveFileExW = kernel32.MoveFileExW
        MoveFileExW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
        MoveFileExW.restype = ctypes.c_bool
    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        return WriteResult(
            ok=False,
            retries=0,
            last_errno=None,
            latency_ms=latency_ms,
            error_message=f"Failed to load MoveFileExW: {e}"
        )
    
    flags = MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH
    backoff_ms = [5, 10, 20, 40, 80, 160, 320, 640]
    
    for retry in range(max_retries + 1):
        result = MoveFileExW(src, dst, flags)
        
        if result:
            # Success!
            latency_ms = (time.time() - start_time) * 1000
            return WriteResult(
                ok=True,
                retries=retry,
                latency_ms=latency_ms
            )
        
        # Get last error
        last_errno = ctypes.get_last_error()
        
        # Check if error is retryable
        if last_errno not in (ERROR_ACCESS_DENIED, ERROR_SHARING_VIOLATION):
            # Non-retryable error
            latency_ms = (time.time() - start_time) * 1000
            return WriteResult(
                ok=False,
                retries=retry,
                last_errno=last_errno,
                latency_ms=latency_ms,
                error_message=f"Non-retryable Windows error: {last_errno}"
            )
        
        # Retryable error - backoff and retry
        if retry < max_retries:
            sleep_ms = backoff_ms[min(retry, len(backoff_ms) - 1)]
            # Add jitter (±20%)
            jitter = random.uniform(0.8, 1.2)
            sleep_s = (sleep_ms * jitter) / 1000
            time.sleep(sleep_s)
    
    # All retries exhausted
    latency_ms = (time.time() - start_time) * 1000
    return WriteResult(
        ok=False,
        retries=max_retries,
        last_errno=last_errno,
        latency_ms=latency_ms,
        error_message=f"Max retries exhausted, last error: {last_errno}"
    )


def atomic_write_json(
    path: Path,
    obj: Any,
    max_retries: int = 8,
    indent: Optional[int] = None
) -> WriteResult:
    """
    Atomically write JSON to file with Windows-safe retry logic.
    
    Process:
    1. Write to temporary file with buffering=0
    2. Flush and fsync
    3. Use MoveFileExW (Windows) or os.replace (Unix) to atomically replace target
    4. Retry on ERROR_ACCESS_DENIED (5) or ERROR_SHARING_VIOLATION (32)
    
    Args:
        path: Target file path
        obj: Object to serialize as JSON
        max_retries: Maximum number of retries for Windows (default: 8)
        indent: JSON indentation (None for compact)
    
    Returns:
        WriteResult with ok, retries, last_errno, latency_ms
    """
    start_time = time.time()
    
    # Ensure parent directory exists
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Create temporary file with unique name
    pid = os.getpid()
    rand = random.randint(10000, 99999)
    tmp_path = path.parent / f"{path.name}.tmp_{pid}_{rand}"
    
    try:
        # Serialize to JSON
        json_bytes = json.dumps(
            obj,
            indent=indent,
            ensure_ascii=False
        ).encode('utf-8')
        
        # Write to temporary file with no buffering
        with open(tmp_path, 'wb', buffering=0) as f:
            f.write(json_bytes)
            f.flush()
            os.fsync(f.fileno())
        
        # Atomic move
        if sys.platform == 'win32':
            result = _move_file_windows(str(tmp_path), str(path), max_retries)
        else:
            # Unix: os.replace is atomic
            try:
                os.replace(tmp_path, path)
                latency_ms = (time.time() - start_time) * 1000
                result = WriteResult(ok=True, latency_ms=latency_ms)
            except Exception as e:
                latency_ms = (time.time() - start_time) * 1000
                result = WriteResult(
                    ok=False,
                    latency_ms=latency_ms,
                    error_message=str(e)
                )
        
        # Clean up temp file if move failed
        if not result.ok and tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass
        
        return result
        
    except Exception as e:
        # Clean up temp file
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass
        
        latency_ms = (time.time() - start_time) * 1000
        return WriteResult(
            ok=False,
            latency_ms=latency_ms,
            error_message=f"Write failed: {e}"
        )


def safe_read_json(
    path: Path,
    default: Optional[Dict] = None,
    throttle_ms: float = 300
) -> Dict[str, Any]:
    """
    Safely read JSON file with throttling and error handling.
    
    - Opens, reads, closes immediately (no persistent handle)
    - Returns cached snapshot on FileNotFoundError or JSONDecodeError
    - Throttles reads to max once per throttle_ms
    
    Args:
        path: File path to read
        default: Default value if file not found or invalid (default: {})
        throttle_ms: Minimum interval between reads in milliseconds
    
    Returns:
        Parsed JSON object or default
    """
    if default is None:
        default = {}
    
    path = Path(path)
    
    # Check throttle
    cache_key = str(path)
    if not hasattr(safe_read_json, "_cache"):
        safe_read_json._cache = {}
    
    now = time.time()
    if cache_key in safe_read_json._cache:
        last_read, cached_data = safe_read_json._cache[cache_key]
        if (now - last_read) * 1000 < throttle_ms:
            # Within throttle window, return cached data
            return cached_data
    
    # Read file
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Update cache
        safe_read_json._cache[cache_key] = (now, data)
        return data
        
    except FileNotFoundError:
        logger.debug(f"File not found: {path}, returning default")
        return default
        
    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON in {path}: {e}, returning default")
        return default
        
    except Exception as e:
        logger.error(f"Error reading {path}: {e}, returning default")
        return default


__all__ = ["atomic_write_json", "safe_read_json", "WriteResult"]

