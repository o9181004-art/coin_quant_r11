#!/usr/bin/env python3
"""
BOM-Resilient JSON I/O
======================
Robust JSON load/dump with BOM handling and atomic writes.

Features:
- BOM-resilient reading (tries utf-8, falls back to utf-8-sig)
- Atomic writes (temp → fsync → replace)
- UTF-8 without BOM output
- Symbol validation on load

Usage:
    from shared.json_io import load_json, dump_json_atomic

    # Read (handles BOM automatically)
    data = load_json("data.json")

    # Write (atomic, UTF-8, no BOM)
    dump_json_atomic("data.json", data)
"""

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Union

logger = logging.getLogger(__name__)


def load_json(
    path: Union[str, Path], default: Any = None, validate_symbols: bool = False
) -> Any:
    """
    Load JSON with BOM-resilient encoding.

    Args:
        path: File path
        default: Default value if file doesn't exist or fails to load
        validate_symbols: If True, validate symbol fields are UPPERCASE

    Returns:
        Loaded data or default

    Raises:
        FileNotFoundError: If file doesn't exist and default is None
        json.JSONDecodeError: If JSON is malformed and default is None
    """
    path = Path(path)

    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(f"JSON file not found: {path}")

    # Try multiple encodings (BOM-resilient)
    # NOTE: Try utf-8-sig first to handle BOM, then utf-8
    last_error = None
    for encoding in ["utf-8-sig", "utf-8", "latin-1"]:
        try:
            with open(path, "r", encoding=encoding) as f:
                data = json.load(f)

            # Validate symbols if requested
            if validate_symbols:
                _validate_symbols_uppercase(data, str(path))

            return data

        except UnicodeDecodeError as e:
            last_error = e
            continue
        except json.JSONDecodeError as e:
            # JSON error - if it's a BOM error, try next encoding
            if "BOM" in str(e) and encoding != "utf-8-sig":
                last_error = e
                continue
            # Other JSON errors - don't try other encodings
            if default is not None:
                logger.warning(f"JSON decode error in {path}: {e}, returning default")
                return default
            raise
        except Exception as e:
            if default is not None:
                logger.error(f"Failed to load {path}: {e}, returning default")
                return default
            raise

    # All encodings failed
    if default is not None:
        logger.error(
            f"All encodings failed for {path}: {last_error}, returning default"
        )
        return default
    raise UnicodeDecodeError(
        "multiple encodings", b"", 0, 0, f"Failed to read {path} with any encoding"
    )


def dump_json_atomic(
    path: Union[str, Path],
    obj: Any,
    indent: int = 2,
    ensure_ascii: bool = False,
    validate_symbols: bool = False,
) -> bool:
    """
    Atomically write JSON (temp → fsync → replace).
    Always writes UTF-8 without BOM.

    Args:
        path: Target file path
        obj: Object to serialize
        indent: JSON indentation
        ensure_ascii: If True, escape non-ASCII characters
        validate_symbols: If True, validate symbol fields are UPPERCASE before write

    Returns:
        True if successful, False otherwise
    """
    path = Path(path)

    try:
        # Validate symbols if requested
        if validate_symbols:
            _validate_symbols_uppercase(obj, str(path))

        # Ensure directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        # Create temp file in same directory (ensures same filesystem for atomic rename)
        fd, temp_path = tempfile.mkstemp(
            dir=path.parent, prefix=".tmp_", suffix=".json"
        )

        try:
            # Write to temp file (UTF-8, no BOM)
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                json.dump(obj, f, indent=indent, ensure_ascii=ensure_ascii)
                f.write("\n")  # Trailing newline
                f.flush()
                os.fsync(f.fileno())  # Ensure written to disk

            # Atomic replace
            temp_path_obj = Path(temp_path)
            temp_path_obj.replace(path)

            return True

        except Exception as e:
            # Clean up temp file on error
            try:
                Path(temp_path).unlink()
            except:
                pass
            raise

    except Exception as e:
        logger.error(f"Failed to write JSON atomically to {path}: {e}")
        return False


def load_jsonl(
    path: Union[str, Path], default: List[Dict] = None, validate_symbols: bool = False
) -> List[Dict]:
    """
    Load JSONL (newline-delimited JSON) with BOM-resilient encoding.

    Args:
        path: File path
        default: Default value if file doesn't exist
        validate_symbols: If True, validate symbol fields are UPPERCASE

    Returns:
        List of JSON objects
    """
    path = Path(path)

    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(f"JSONL file not found: {path}")

    # Try multiple encodings (BOM-resilient)
    # NOTE: Try utf-8-sig first to handle BOM
    last_error = None
    for encoding in ["utf-8-sig", "utf-8"]:
        try:
            with open(path, "r", encoding=encoding) as f:
                lines = f.readlines()

            data = []
            for line_num, line in enumerate(lines, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    obj = json.loads(line)

                    # Validate symbols if requested
                    if validate_symbols:
                        _validate_symbols_uppercase(obj, f"{path}:{line_num}")

                    data.append(obj)
                except json.JSONDecodeError as e:
                    logger.warning(f"Skipping malformed JSON at {path}:{line_num}: {e}")
                    continue

            return data

        except UnicodeDecodeError as e:
            last_error = e
            continue
        except Exception as e:
            if default is not None:
                logger.error(f"Failed to load JSONL {path}: {e}, returning default")
                return default
            raise

    # All encodings failed
    if default is not None:
        logger.error(
            f"All encodings failed for {path}: {last_error}, returning default"
        )
        return default
    raise UnicodeDecodeError(
        "multiple encodings", b"", 0, 0, f"Failed to read {path} with any encoding"
    )


def dump_jsonl_atomic(
    path: Union[str, Path], objects: List[Dict], validate_symbols: bool = False
) -> bool:
    """
    Atomically write JSONL (newline-delimited JSON).
    Always writes UTF-8 without BOM.

    Args:
        path: Target file path
        objects: List of objects to serialize
        validate_symbols: If True, validate symbol fields before write

    Returns:
        True if successful
    """
    path = Path(path)

    try:
        # Validate symbols if requested
        if validate_symbols:
            for i, obj in enumerate(objects):
                _validate_symbols_uppercase(obj, f"{path}[{i}]")

        # Ensure directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        # Create temp file
        fd, temp_path = tempfile.mkstemp(
            dir=path.parent, prefix=".tmp_", suffix=".jsonl"
        )

        try:
            # Write to temp file
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                for obj in objects:
                    f.write(json.dumps(obj, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())

            # Atomic replace
            Path(temp_path).replace(path)

            return True

        except Exception:
            # Clean up temp file
            try:
                Path(temp_path).unlink()
            except:
                pass
            raise

    except Exception as e:
        logger.error(f"Failed to write JSONL atomically to {path}: {e}")
        return False


def _validate_symbols_uppercase(obj: Any, context: str):
    """
    Validate that symbol fields are UPPERCASE.

    Args:
        obj: Object to validate
        context: Context for error messages

    Raises:
        ValueError: If lowercase or empty symbol found
    """
    if isinstance(obj, dict):
        # Check "symbol" field
        if "symbol" in obj:
            symbol = obj["symbol"]
            if not isinstance(symbol, str):
                raise ValueError(
                    f"Symbol must be string in {context}, got {type(symbol)}"
                )

            if not symbol or not symbol.strip():
                raise ValueError(f"Empty symbol in {context}")

            if symbol != symbol.upper():
                raise ValueError(
                    f"Lowercase symbol in {context}: '{symbol}' (must be '{symbol.upper()}')"
                )

        # Check nested dicts
        for key, value in obj.items():
            # Check if key is a symbol (ends with USDT)
            if isinstance(key, str) and key.lower().endswith("usdt"):
                if key != key.upper():
                    raise ValueError(
                        f"Lowercase symbol key in {context}: '{key}' (must be '{key.upper()}')"
                    )

            # Recurse into nested structures
            if isinstance(value, (dict, list)):
                _validate_symbols_uppercase(value, f"{context}.{key}")

    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            _validate_symbols_uppercase(item, f"{context}[{i}]")


def atomic_write(path: Union[str, Path], content: str) -> bool:
    """
    Atomically write text content (for backward compatibility).
    Always writes UTF-8 without BOM.

    Args:
        path: Target file path
        content: Text content to write

    Returns:
        True if successful
    """
    path = Path(path)

    try:
        # Ensure directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        # Create temp file
        fd, temp_path = tempfile.mkstemp(
            dir=path.parent, prefix=".tmp_", suffix=path.suffix
        )

        try:
            # Write to temp file (UTF-8, no BOM)
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)
                if not content.endswith("\n"):
                    f.write("\n")  # Ensure trailing newline
                f.flush()
                os.fsync(f.fileno())

            # Atomic replace
            Path(temp_path).replace(path)

            return True

        except Exception:
            # Clean up temp file
            try:
                Path(temp_path).unlink()
            except:
                pass
            raise

    except Exception as e:
        logger.error(f"Failed to write atomically to {path}: {e}")
        return False


# Backward compatibility aliases
atomic_write_json = dump_json_atomic


if __name__ == "__main__":
    import sys
    import tempfile

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    print("=" * 60)
    print("JSON I/O Test")
    print("=" * 60)

    # Create temp directory
    temp_dir = Path(tempfile.mkdtemp())

    try:
        # Test 1: Write and read JSON
        print("\n[Test 1] Atomic JSON write/read")
        test_file = temp_dir / "test.json"
        test_data = {"symbols": ["BTCUSDT", "ETHUSDT"], "count": 2}

        assert dump_json_atomic(test_file, test_data) == True
        loaded = load_json(test_file)
        assert loaded == test_data
        print("  ✅ Passed")

        # Test 2: BOM handling
        print("\n[Test 2] BOM-resilient read")
        # Write with BOM
        bom_file = temp_dir / "bom.json"
        with open(bom_file, "w", encoding="utf-8-sig") as f:
            json.dump(test_data, f)

        # Read should handle BOM
        loaded = load_json(bom_file)
        assert loaded == test_data
        print("  ✅ Passed")

        # Test 3: Symbol validation
        print("\n[Test 3] Symbol validation")
        valid_data = {"symbol": "BTCUSDT", "price": 50000}
        invalid_data = {"symbol": "btcusdt", "price": 50000}

        # Valid should pass
        load_json(test_file, default={})  # No validation by default

        # Invalid should fail with validation
        invalid_file = temp_dir / "invalid.json"
        with open(invalid_file, "w", encoding="utf-8") as f:
            json.dump(invalid_data, f)

        try:
            load_json(invalid_file, validate_symbols=True)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Lowercase symbol" in str(e)
        print("  ✅ Passed")

        # Test 4: JSONL
        print("\n[Test 4] JSONL write/read")
        jsonl_file = temp_dir / "test.jsonl"
        jsonl_data = [
            {"symbol": "BTCUSDT", "price": 50000},
            {"symbol": "ETHUSDT", "price": 3000},
        ]

        assert dump_jsonl_atomic(jsonl_file, jsonl_data) == True
        loaded = load_jsonl(jsonl_file)
        assert len(loaded) == 2
        assert loaded[0]["symbol"] == "BTCUSDT"
        print("  ✅ Passed")

        print("\n" + "=" * 60)
        print("✅ All tests passed")
        print("=" * 60)

    finally:
        # Cleanup
        import shutil

        shutil.rmtree(temp_dir)

    sys.exit(0)
