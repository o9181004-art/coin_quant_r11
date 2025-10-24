#!/usr/bin/env python3
"""
Safe Readers API - Read-only access to SSOT data

UI components should only import from this module.
No write operations are exposed to prevent UI from modifying data.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Union, Callable
import sys

# Import canonical path resolution
from shared.io_canonical import artifact, get_ssot_dir


class SafeReaderError(Exception):
    """Exception raised by safe readers"""
    pass


def _validate_json_schema(data: Any, validator: Callable[[Any], bool]) -> bool:
    """Validate JSON data using provided validator"""
    try:
        return validator(data)
    except Exception:
        return False


def read_json_safely(path: Union[str, Path], 
                    default: Optional[Any] = None, 
                    validate: Optional[Callable[[Any], bool]] = None) -> Any:
    """
    Safely read JSON file with validation and error handling
    
    Args:
        path: Path relative to SSOT or absolute path under SSOT
        default: Default value to return if file doesn't exist or read fails
        validate: Optional validation function that takes the data and returns bool
    
    Returns:
        Parsed JSON data or default value
    
    Raises:
        SafeReaderError: If validation fails
    """
    try:
        # Resolve path through SSOT
        artifact_path = artifact(str(path))
        
        # Check if file exists
        if not artifact_path.exists():
            return default
        
        # Read and parse JSON
        with open(artifact_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Validate if validator provided
        if validate is not None:
            if not _validate_json_schema(data, validate):
                raise SafeReaderError(f"Validation failed for {path}")
        
        return data
        
    except SafeReaderError:
        raise
    except Exception as e:
        if default is not None:
            return default
        raise SafeReaderError(f"Failed to read {path}: {e}")


def read_ndjson_safely(path: Union[str, Path], 
                      default: Optional[list] = None,
                      validate: Optional[Callable[[Any], bool]] = None) -> list:
    """
    Safely read NDJSON file with validation and error handling
    
    Args:
        path: Path relative to SSOT or absolute path under SSOT
        default: Default value to return if file doesn't exist or read fails
        validate: Optional validation function that takes each line's data and returns bool
    
    Returns:
        List of parsed JSON objects
    
    Raises:
        SafeReaderError: If validation fails
    """
    try:
        # Resolve path through SSOT
        artifact_path = artifact(str(path))
        
        # Check if file exists
        if not artifact_path.exists():
            return default if default is not None else []
        
        # Read and parse NDJSON
        objects = []
        with open(artifact_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                
                try:
                    obj = json.loads(line)
                    
                    # Validate if validator provided
                    if validate is not None:
                        if not _validate_json_schema(obj, validate):
                            raise SafeReaderError(f"Validation failed for line {line_num} in {path}")
                    
                    objects.append(obj)
                    
                except json.JSONDecodeError as e:
                    raise SafeReaderError(f"Invalid JSON on line {line_num} in {path}: {e}")
        
        return objects
        
    except SafeReaderError:
        raise
    except Exception as e:
        if default is not None:
            return default
        raise SafeReaderError(f"Failed to read NDJSON {path}: {e}")


def read_health_json(default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Safely read health.json"""
    return read_json_safely("health.json", default)


def read_databus_snapshot(default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Safely read databus_snapshot.json"""
    return read_json_safely("databus_snapshot.json", default)


def read_account_info(default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Safely read account_info.json"""
    return read_json_safely("account_info.json", default)


def read_ares_status(default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Safely read ares_status.json"""
    return read_json_safely("ares/ares_status.json", default)


def read_candidates_ndjson(default: Optional[list] = None) -> list:
    """Safely read candidates.ndjson"""
    return read_ndjson_safely("logs/candidates.ndjson", default)


def read_trader_heartbeat(default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Safely read trader.heartbeat.json"""
    return read_json_safely("health/trader.heartbeat.json", default)


def get_artifact_info(path: Union[str, Path]) -> Dict[str, Any]:
    """
    Get information about an artifact (metadata, size, modification time)
    
    Args:
        path: Path relative to SSOT or absolute path under SSOT
    
    Returns:
        Dictionary with artifact information
    """
    try:
        artifact_path = artifact(str(path))
        
        if not artifact_path.exists():
            return {
                'exists': False,
                'path': str(artifact_path),
                'size': 0,
                'modified': None
            }
        
        stat = artifact_path.stat()
        
        # Try to read metadata from JSON if it's a JSON file
        metadata = {}
        if artifact_path.suffix == '.json':
            try:
                data = read_json_safely(path, {})
                if isinstance(data, dict) and '_metadata' in data:
                    metadata = data['_metadata']
            except Exception:
                pass
        
        return {
            'exists': True,
            'path': str(artifact_path),
            'size': stat.st_size,
            'modified': stat.st_mtime,
            'metadata': metadata
        }
        
    except Exception as e:
        return {
            'exists': False,
            'path': str(path),
            'error': str(e),
            'size': 0,
            'modified': None
        }


def list_artifacts(pattern: str = "*") -> list:
    """
    List artifacts matching pattern
    
    Args:
        pattern: Glob pattern to match (default: "*")
    
    Returns:
        List of artifact information dictionaries
    """
    try:
        ssot_dir = get_ssot_dir()
        artifacts = []
        
        for file_path in ssot_dir.rglob(pattern):
            if file_path.is_file():
                rel_path = file_path.relative_to(ssot_dir)
                info = get_artifact_info(str(rel_path))
                artifacts.append(info)
        
        return artifacts
        
    except Exception as e:
        print(f"Error listing artifacts: {e}", file=sys.stderr)
        return []


# Validation functions for common schemas
def validate_health_schema(data: Any) -> bool:
    """Validate health.json schema"""
    if not isinstance(data, dict):
        return False
    
    # Basic health schema validation
    required_fields = ['feeder', 'trader', 'ares']
    return all(field in data for field in required_fields)


def validate_account_schema(data: Any) -> bool:
    """Validate account_info.json schema"""
    if not isinstance(data, dict):
        return False
    
    # Basic account schema validation
    return 'balances' in data and 'accountType' in data


def validate_candidate_schema(data: Any) -> bool:
    """Validate trading candidate schema"""
    if not isinstance(data, dict):
        return False
    
    # Basic candidate schema validation
    required_fields = ['symbol', 'side', 'timestamp']
    return all(field in data for field in required_fields)


# Example usage and testing
if __name__ == "__main__":
    print("Testing Safe Readers API...")
    
    # Test reading non-existent file
    health_data = read_health_json(default={"status": "unknown"})
    print(f"Health data: {health_data}")
    
    # Test reading with validation
    try:
        account_data = read_account_info(default={})
        print(f"Account data keys: {list(account_data.keys()) if isinstance(account_data, dict) else 'Not a dict'}")
    except SafeReaderError as e:
        print(f"Account validation error: {e}")
    
    # Test artifact info
    health_info = get_artifact_info("health.json")
    print(f"Health artifact info: {health_info}")
    
    # Test listing artifacts
    artifacts = list_artifacts("*.json")
    print(f"Found {len(artifacts)} JSON artifacts")
    
    print("Safe Readers API test completed!")
