#!/usr/bin/env python3
"""
Shared JSON utilities with no-BOM and atomic write support
Provides consistent JSON writing across the entire codebase
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Union

logger = logging.getLogger(__name__)


def write_json(
    path: Union[str, Path],
    obj: Any,
    nobom: bool = True,
    atomic: bool = True,
    indent: int = 2,
    ensure_ascii: bool = False
) -> bool:
    """
    Write JSON with no-BOM and optional atomic write

    Args:
        path: File path to write to
        obj: Object to serialize to JSON
        nobom: If True, ensure no BOM (Byte Order Mark) in output
        atomic: If True, use temp file + atomic replace
        indent: JSON indentation (default: 2)
        ensure_ascii: If True, escape non-ASCII characters (default: False)

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        path = Path(path)

        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        # Serialize to JSON string
        json_str = json.dumps(obj, indent=indent, ensure_ascii=ensure_ascii)

        if atomic:
            # Atomic write: temp file + replace
            temp_path = path.with_suffix('.tmp')

            # Write to temp file with UTF-8 encoding (no BOM)
            with open(temp_path, 'w', encoding='utf-8') as f:
                f.write(json_str)

            # Atomic replace
            temp_path.replace(path)
        else:
            # Direct write with UTF-8 encoding (no BOM)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(json_str)

        return True

    except Exception as e:
        logger.error(f"Failed to write JSON to {path}: {e}")
        return False


def write_ndjson_line(
    path: Union[str, Path],
    obj: Any,
    nobom: bool = True,
    ensure_ascii: bool = False
) -> bool:
    """
    Append a single NDJSON line with no-BOM

    Args:
        path: File path to append to
        obj: Object to serialize to JSON
        nobom: If True, ensure no BOM (Byte Order Mark) in output
        ensure_ascii: If True, escape non-ASCII characters (default: False)

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        path = Path(path)

        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        # Serialize to JSON string (compact, no indent)
        json_str = json.dumps(obj, ensure_ascii=ensure_ascii, separators=(',', ':'))

        # Append line with UTF-8 encoding (no BOM)
        with open(path, 'a', encoding='utf-8') as f:
            f.write(json_str + '\n')

        return True

    except Exception as e:
        logger.error(f"Failed to append NDJSON line to {path}: {e}")
        return False


def read_json(
    path: Union[str, Path],
    default: Any = None
) -> Any:
    """
    Read JSON file with UTF-8 encoding

    Args:
        path: File path to read from
        default: Default value if file doesn't exist or read fails

    Returns:
        Parsed JSON object or default value
    """
    try:
        path = Path(path)

        if not path.exists():
            return default

        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    except Exception as e:
        logger.error(f"Failed to read JSON from {path}: {e}")
        return default


def read_ndjson(
    path: Union[str, Path],
    max_lines: int = None
) -> list:
    """
    Read NDJSON file with UTF-8 encoding

    Args:
        path: File path to read from
        max_lines: Maximum number of lines to read (None = all)

    Returns:
        List of parsed JSON objects
    """
    try:
        path = Path(path)

        if not path.exists():
            return []

        results = []
        with open(path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                if max_lines and i >= max_lines:
                    break

                line = line.strip()
                if line:
                    try:
                        results.append(json.loads(line))
                    except json.JSONDecodeError as e:
                        logger.warning(f"Failed to parse NDJSON line {i+1} in {path}: {e}")

        return results

    except Exception as e:
        logger.error(f"Failed to read NDJSON from {path}: {e}")
        return []


# Convenience functions for common patterns

def write_state_bus(obj: Dict[str, Any]) -> bool:
    """Write to state_bus.json with atomic write"""
    return write_json("shared_data/state_bus.json", obj, atomic=True)


def write_positions(obj: Dict[str, Any]) -> bool:
    """Write to positions.json with atomic write"""
    return write_json("shared_data/positions.json", obj, atomic=True)


def write_exchange_filters(obj: Dict[str, Any]) -> bool:
    """Write to exchange_filters.json with atomic write"""
    return write_json("shared_data/exchange_filters.json", obj, atomic=True)


def append_candidate(obj: Dict[str, Any]) -> bool:
    """Append candidate to candidates.ndjson"""
    return write_ndjson_line("shared_data/logs/candidates.ndjson", obj)


# Example usage
if __name__ == "__main__":
    import time

    # Test atomic JSON write
    test_data = {
        "timestamp": int(time.time()),
        "symbols": ["BTCUSDT", "ETHUSDT"],
        "status": "active"
    }

    success = write_json("test_output.json", test_data)
    print(f"Write JSON: {'✅' if success else '❌'}")

    # Test NDJSON append
    test_line = {
        "timestamp": int(time.time()),
        "symbol": "BTCUSDT",
        "signal": "BUY"
    }

    success = write_ndjson_line("test_output.ndjson", test_line)
    print(f"Write NDJSON: {'✅' if success else '❌'}")

    # Test read
    data = read_json("test_output.json")
    print(f"Read JSON: {data}")

    lines = read_ndjson("test_output.ndjson")
    print(f"Read NDJSON: {lines}")
