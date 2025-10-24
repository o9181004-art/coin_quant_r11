#!/usr/bin/env python3
"""
Canonical JSON I/O - No BOM, Atomic Operations
Windows-safe JSON operations with epoch seconds timestamps
"""

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Union


def now_epoch_s() -> int:
    """
    Get current UTC epoch seconds
    
    Returns:
        Current UTC epoch seconds as integer
    """
    return int(time.time())


def write_json_atomic_nobom(path: Path, obj: Any) -> None:
    """
    Write JSON atomically without BOM
    
    Args:
        path: Target file path
        obj: Object to serialize
    """
    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Create temporary file
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False, dir=path.parent) as tmp:
        json.dump(obj, tmp, ensure_ascii=False, separators=(',', ':'))
        tmp.flush()
        os.fsync(tmp.fileno())
        temp_path = Path(tmp.name)
    
    # Atomic replace
    try:
        temp_path.replace(path)
    except Exception as e:
        # Cleanup temp file on failure
        temp_path.unlink(missing_ok=True)
        raise e


def append_ndjson_nobom(path: Path, line_obj: dict) -> None:
    """
    Append NDJSON line without BOM
    
    Args:
        path: Target file path
        line_obj: Dictionary to append as JSON line
    """
    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Append line
    with open(path, 'a', encoding='utf-8') as f:
        json.dump(line_obj, f, ensure_ascii=False, separators=(',', ':'))
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())


def read_json_nobom(path: Path, default: Any = None) -> Any:
    """
    Read JSON without BOM
    
    Args:
        path: File path to read
        default: Default value if file doesn't exist or is invalid
        
    Returns:
        Parsed JSON object or default
    """
    if not path.exists():
        return default
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return default


def read_ndjson_lines(path: Path, max_lines: int = None) -> list:
    """
    Read NDJSON lines
    
    Args:
        path: File path to read
        max_lines: Maximum number of lines to read (None for all)
        
    Returns:
        List of parsed JSON objects
    """
    if not path.exists():
        return []
    
    lines = []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                try:
                    obj = json.loads(line)
                    lines.append(obj)
                    
                    if max_lines and len(lines) >= max_lines:
                        lines = lines[-max_lines:]  # Keep only recent lines
                        
                except json.JSONDecodeError:
                    continue
                    
    except (UnicodeDecodeError, OSError):
        pass
    
    return lines


def get_last_ndjson_line(path: Path) -> dict:
    """
    Get the last line from NDJSON file
    
    Args:
        path: File path to read
        
    Returns:
        Last JSON object or empty dict
    """
    lines = read_ndjson_lines(path, max_lines=1)
    return lines[-1] if lines else {}


def ensure_epoch_seconds(timestamp: Union[int, float]) -> int:
    """
    Ensure timestamp is in epoch seconds (not milliseconds)
    
    Args:
        timestamp: Timestamp to normalize
        
    Returns:
        Epoch seconds as integer
    """
    ts = int(timestamp)
    
    # If timestamp is too large, assume it's milliseconds
    if ts > 1e10:  # After year 2286
        ts = ts // 1000
    
    return ts


def add_epoch_timestamp(obj: dict) -> dict:
    """
    Add epoch seconds timestamp to object
    
    Args:
        obj: Dictionary to add timestamp to
        
    Returns:
        Dictionary with timestamp added
    """
    obj = obj.copy()
    obj['timestamp'] = int(time.time())
    return obj


def add_expires_at(obj: dict, ttl_seconds: int = 120) -> dict:
    """
    Add expiration timestamp to object
    
    Args:
        obj: Dictionary to add expiration to
        ttl_seconds: Time to live in seconds
        
    Returns:
        Dictionary with expires_at added
    """
    obj = obj.copy()
    obj['expires_at'] = int(time.time()) + ttl_seconds
    return obj


if __name__ == "__main__":
    # Test the JSON I/O functions
    test_dir = Path("shared_data/test_jsonio")
    test_dir.mkdir(parents=True, exist_ok=True)
    
    # Test JSON write/read
    test_json = test_dir / "test.json"
    test_data = {"test": True, "timestamp": int(time.time())}
    
    print("Testing JSON I/O...")
    write_json_atomic_nobom(test_json, test_data)
    read_data = read_json_nobom(test_json)
    print(f"JSON test: {'✅' if read_data == test_data else '❌'}")
    
    # Test NDJSON append/read
    test_ndjson = test_dir / "test.ndjson"
    
    for i in range(3):
        line_data = {"id": i, "message": f"Test line {i}", "timestamp": int(time.time())}
        append_ndjson_nobom(test_ndjson, line_data)
    
    lines = read_ndjson_lines(test_ndjson)
    print(f"NDJSON test: {'✅' if len(lines) == 3 else '❌'}")
    
    # Test last line
    last_line = get_last_ndjson_line(test_ndjson)
    print(f"Last line test: {'✅' if last_line.get('id') == 2 else '❌'}")
    
    # Test epoch normalization
    now_ms = int(time.time() * 1000)
    normalized = ensure_epoch_seconds(now_ms)
    print(f"Epoch normalization: {'✅' if normalized == int(time.time()) else '❌'}")
    
    # Cleanup
    test_json.unlink(missing_ok=True)
    test_ndjson.unlink(missing_ok=True)
    test_dir.rmdir()
    
    print("JSON I/O tests completed")
