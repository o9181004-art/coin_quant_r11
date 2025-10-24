#!/usr/bin/env python3
"""
Optimized JSON I/O with orjson, NDJSON, and gzip support
Memory-efficient file operations for CQ_LEAN mode
"""

import os
import gzip
import json
from typing import Any, Dict, List, Optional, Union, Iterator
from pathlib import Path

# Try to import orjson for better performance
try:
    import orjson
    HAS_ORJSON = True
except ImportError:
    HAS_ORJSON = False
    print("⚠️ orjson not available, falling back to standard json")

from shared.lean_mode import is_lean, lean_cache


def get_json_module():
    """Get appropriate JSON module based on availability and lean mode"""
    if is_lean and HAS_ORJSON:
        return orjson
    return json


def safe_json_dumps(data: Any, **kwargs) -> bytes:
    """Safe JSON serialization with lean optimizations"""
    json_module = get_json_module()
    
    if json_module == orjson:
        # orjson options for lean mode
        options = orjson.OPT_SORT_KEYS | orjson.OPT_SERIALIZE_NUMPY
        # Note: OPT_COMPACT removed as it's not available in current orjson version
        return json_module.dumps(data, option=options)
    else:
        # Standard json with lean optimizations
        if is_lean:
            kwargs.setdefault('separators', (',', ':'))  # Compact
            kwargs.setdefault('ensure_ascii', False)
        return json_module.dumps(data, **kwargs).encode('utf-8')


def safe_json_loads(data: Union[bytes, str]) -> Any:
    """Safe JSON deserialization"""
    json_module = get_json_module()
    
    if isinstance(data, str):
        data = data.encode('utf-8')
    
    if json_module == orjson:
        return json_module.loads(data)
    else:
        return json_module.loads(data.decode('utf-8'))


def write_json_lean(file_path: Union[str, Path], data: Any, use_gzip: bool = None) -> bool:
    """Write JSON with lean optimizations"""
    try:
        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Determine if we should use gzip
        if use_gzip is None:
            use_gzip = is_lean and file_path.suffix not in ['.json', '.jsonl']
        
        # Serialize data
        json_data = safe_json_dumps(data)
        
        # Write file
        if use_gzip:
            with gzip.open(file_path.with_suffix(file_path.suffix + '.gz'), 'wb') as f:
                f.write(json_data)
        else:
            with open(file_path, 'wb') as f:
                f.write(json_data)
        
        return True
        
    except Exception as e:
        print(f"JSON write error {file_path}: {e}")
        return False


def read_json_lean(file_path: Union[str, Path], use_cache: bool = True) -> Optional[Any]:
    """Read JSON with lean optimizations and caching"""
    try:
        file_path = Path(file_path)
        
        # Check cache first
        if use_cache and is_lean:
            cache_key = f"json:{file_path}"
            cached_data = lean_cache.get(cache_key)
            if cached_data is not None:
                return cached_data
        
        # Try gzipped version first
        gz_path = file_path.with_suffix(file_path.suffix + '.gz')
        if gz_path.exists():
            with gzip.open(gz_path, 'rb') as f:
                data = f.read()
        elif file_path.exists():
            with open(file_path, 'rb') as f:
                data = f.read()
        else:
            return None
        
        # Deserialize
        result = safe_json_loads(data)
        
        # Cache result
        if use_cache and is_lean:
            lean_cache.set(cache_key, result)
        
        return result
        
    except Exception as e:
        print(f"JSON read error {file_path}: {e}")
        return None


def write_ndjson_lean(file_path: Union[str, Path], records: List[Dict], use_gzip: bool = None) -> bool:
    """Write NDJSON (line-delimited JSON) with lean optimizations"""
    try:
        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Determine if we should use gzip
        if use_gzip is None:
            use_gzip = is_lean
        
        # Write records
        if use_gzip:
            gz_path = file_path.with_suffix(file_path.suffix + '.gz')
            with gzip.open(gz_path, 'wt', encoding='utf-8') as f:
                for record in records:
                    json_line = safe_json_dumps(record).decode('utf-8')
                    f.write(json_line + '\n')
        else:
            with open(file_path, 'w', encoding='utf-8') as f:
                for record in records:
                    json_line = safe_json_dumps(record).decode('utf-8')
                    f.write(json_line + '\n')
        
        return True
        
    except Exception as e:
        print(f"NDJSON write error {file_path}: {e}")
        return False


def read_ndjson_lean(file_path: Union[str, Path], max_lines: int = None) -> List[Dict]:
    """Read NDJSON with lean optimizations and streaming"""
    try:
        file_path = Path(file_path)
        
        # Try gzipped version first
        gz_path = file_path.with_suffix(file_path.suffix + '.gz')
        if gz_path.exists():
            file_handle = gzip.open(gz_path, 'rt', encoding='utf-8')
        elif file_path.exists():
            file_handle = open(file_path, 'r', encoding='utf-8')
        else:
            return []
        
        records = []
        with file_handle as f:
            for i, line in enumerate(f):
                if max_lines and i >= max_lines:
                    break
                line = line.strip()
                if line:
                    try:
                        record = safe_json_loads(line)
                        records.append(record)
                    except Exception as e:
                        print(f"NDJSON line parse error: {e}")
                        continue
        
        return records
        
    except Exception as e:
        print(f"NDJSON read error {file_path}: {e}")
        return []


def stream_ndjson_lean(file_path: Union[str, Path]) -> Iterator[Dict]:
    """Stream NDJSON records for memory efficiency"""
    try:
        file_path = Path(file_path)
        
        # Try gzipped version first
        gz_path = file_path.with_suffix(file_path.suffix + '.gz')
        if gz_path.exists():
            file_handle = gzip.open(gz_path, 'rt', encoding='utf-8')
        elif file_path.exists():
            file_handle = open(file_path, 'r', encoding='utf-8')
        else:
            return
        
        with file_handle as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        record = safe_json_loads(line)
                        yield record
                    except Exception as e:
                        print(f"NDJSON stream parse error: {e}")
                        continue
        
    except Exception as e:
        print(f"NDJSON stream error {file_path}: {e}")


def append_ndjson_lean(file_path: Union[str, Path], record: Dict, use_gzip: bool = None) -> bool:
    """Append single record to NDJSON file"""
    try:
        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Determine if we should use gzip
        if use_gzip is None:
            use_gzip = is_lean
        
        # Serialize record
        json_line = safe_json_dumps(record).decode('utf-8')
        
        # Append to file
        if use_gzip:
            gz_path = file_path.with_suffix(file_path.suffix + '.gz')
            with gzip.open(gz_path, 'at', encoding='utf-8') as f:
                f.write(json_line + '\n')
        else:
            with open(file_path, 'a', encoding='utf-8') as f:
                f.write(json_line + '\n')
        
        return True
        
    except Exception as e:
        print(f"NDJSON append error {file_path}: {e}")
        return False


def get_file_size_mb(file_path: Union[str, Path]) -> float:
    """Get file size in MB"""
    try:
        file_path = Path(file_path)
        if file_path.exists():
            return file_path.stat().st_size / 1024 / 1024
        
        # Check gzipped version
        gz_path = file_path.with_suffix(file_path.suffix + '.gz')
        if gz_path.exists():
            return gz_path.stat().st_size / 1024 / 1024
        
        return 0.0
    except Exception:
        return 0.0


def cleanup_old_files(directory: Union[str, Path], pattern: str = "*.json", max_age_hours: int = 24):
    """Clean up old files to save disk space"""
    if not is_lean:
        return
        
    try:
        directory = Path(directory)
        if not directory.exists():
            return
        
        import time
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        
        for file_path in directory.glob(pattern):
            try:
                file_age = current_time - file_path.stat().st_mtime
                if file_age > max_age_seconds:
                    file_path.unlink()
                    print(f"🗑️ Cleaned up old file: {file_path}")
            except Exception as e:
                print(f"Cleanup error for {file_path}: {e}")
                
    except Exception as e:
        print(f"File cleanup error: {e}")
