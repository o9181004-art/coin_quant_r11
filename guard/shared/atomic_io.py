#!/usr/bin/env python3
"""
Atomic I/O helper for Stack Doctor reports
Ensures UTF-8 (no BOM) and atomic writes with fsync
"""

import os
from pathlib import Path
from typing import Union


def atomic_write_text(path: Union[str, Path], text: str) -> None:
    """
    Atomically write text to a file using UTF-8 encoding (no BOM).

    Process:
    1. Ensure parent directories exist
    2. Write to temporary file (path + ".tmp")
    3. Fsync to ensure data is on disk
    4. Atomically replace the target file

    Args:
        path: Target file path
        text: Text content to write

    Raises:
        OSError: If write or replace fails
    """
    path = Path(path)

    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    # Temporary file path
    tmp_path = path.with_suffix(path.suffix + ".tmp")

    try:
        # Write to temporary file with UTF-8 (no BOM), Unix line endings
        with open(tmp_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
            f.flush()
            # Force write to disk
            os.fsync(f.fileno())

        # Atomically replace the target file
        # On Windows, replace() will overwrite if target exists
        tmp_path.replace(path)

    except Exception as e:
        # Clean up temporary file on error
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except:
                pass
        raise OSError(f"Failed to atomically write {path}: {e}") from e


def atomic_write_json(path: Union[str, Path], data: dict) -> None:
    """
    Atomically write JSON data to a file.

    Args:
        path: Target file path
        data: Dictionary to serialize as JSON
    """
    import json
    text = json.dumps(data, ensure_ascii=False, indent=2)
    atomic_write_text(path, text)


if __name__ == "__main__":
    # Test
    import tempfile
    import time

    test_dir = Path(tempfile.mkdtemp())
    test_file = test_dir / "test.txt"

    print(f"Testing atomic write to: {test_file}")

    # Test 1: Simple write
    atomic_write_text(test_file, "Hello, World!\n")
    assert test_file.exists()
    assert test_file.read_text(encoding='utf-8') == "Hello, World!\n"
    print("✅ Test 1: Simple write passed")

    # Test 2: Overwrite
    atomic_write_text(test_file, "Updated content\n")
    assert test_file.read_text(encoding='utf-8') == "Updated content\n"
    print("✅ Test 2: Overwrite passed")

    # Test 3: JSON write
    test_json = test_dir / "test.json"
    atomic_write_json(test_json, {"status": "ok", "items": []})
    assert test_json.exists()
    import json
    data = json.loads(test_json.read_text(encoding='utf-8'))
    assert data["status"] == "ok"
    print("✅ Test 3: JSON write passed")

    # Test 4: UTF-8 with special characters
    test_utf8 = test_dir / "test_utf8.txt"
    atomic_write_text(test_utf8, "한글 테스트\n日本語\n中文\n")
    content = test_utf8.read_text(encoding='utf-8')
    assert "한글" in content
    print("✅ Test 4: UTF-8 special characters passed")

    # Cleanup
    import shutil
    shutil.rmtree(test_dir)

    print("\n✅ All atomic I/O tests passed!")
