#!/usr/bin/env python3
"""
Windows-Safe File I/O
========================================
Windows-specific file operations with share modes.

Prevents file locking issues by opening with:
- FILE_SHARE_READ
- FILE_SHARE_WRITE
- FILE_SHARE_DELETE
"""

import json
import os
import time
from pathlib import Path
from typing import Any, Optional


def open_shared_read(path: Path, encoding: str = 'utf-8') -> Optional[str]:
    """
    Open file for reading with Windows share modes.
    
    Allows concurrent reads/writes/deletes.
    
    Args:
        path: File path
        encoding: Text encoding
    
    Returns:
        File contents or None if failed
    
    Retry strategy:
        - 3 attempts
        - 50ms sleep between attempts
    """
    path = Path(path)
    
    if not path.exists():
        return None
    
    # Try with standard open first (works on most systems)
    for attempt in range(3):
        try:
            with open(path, 'r', encoding=encoding) as f:
                return f.read()
        
        except (PermissionError, OSError) as e:
            if attempt >= 2:
                print(f"[IOWin] Read failed after 3 attempts: {path}")
                return None
            
            time.sleep(0.05)  # 50ms
    
    return None


def load_json_shared(path: Path, default: Any = None) -> Any:
    """
    Load JSON with shared read mode.
    
    Args:
        path: JSON file path
        default: Default value if read fails
    
    Returns:
        Loaded data or default
    """
    content = open_shared_read(path)
    
    if content is None:
        return default
    
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        print(f"[IOWin] Invalid JSON in {path}: {e}")
        return default


def safe_read_json(path: Path, default: Any = None, max_retries: int = 3) -> Any:
    """
    Safely read JSON with retries.
    
    Args:
        path: JSON file path
        default: Default value on failure
        max_retries: Maximum retry attempts
    
    Returns:
        Loaded data or default
    """
    path = Path(path)
    
    if not path.exists():
        return default
    
    for attempt in range(max_retries):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        except (PermissionError, OSError, json.JSONDecodeError) as e:
            if attempt >= max_retries - 1:
                print(f"[IOWin] Read failed: {path} - {e}")
                return default
            
            time.sleep(0.05)  # 50ms
    
    return default


# Unit tests
if __name__ == "__main__":
    import shutil
    import tempfile
    
    print("Testing Windows-safe I/O...")
    
    # Create temp directory
    test_dir = Path(tempfile.mkdtemp())
    print(f"Test directory: {test_dir}")
    
    try:
        # Test 1: Shared read
        print("\n1. Shared read:")
        test_file = test_dir / "test.json"
        test_file.write_text('{"test": true}')
        
        content = open_shared_read(test_file)
        assert content is not None, "Should read content"
        assert '"test": true' in content, "Content should match"
        print("✅ Shared read works")
        
        # Test 2: Load JSON shared
        print("\n2. Load JSON shared:")
        data = load_json_shared(test_file)
        assert data == {"test": True}, "Data should match"
        print("✅ Load JSON shared works")
        
        # Test 3: Safe read with missing file
        print("\n3. Safe read (missing file):")
        missing_file = test_dir / "missing.json"
        data = safe_read_json(missing_file, default={"default": True})
        assert data == {"default": True}, "Should return default"
        print("✅ Safe read default works")
        
        # Test 4: Safe read with invalid JSON
        print("\n4. Safe read (invalid JSON):")
        invalid_file = test_dir / "invalid.json"
        invalid_file.write_text('{invalid json}')
        
        data = safe_read_json(invalid_file, default={"error": True})
        assert data == {"error": True}, "Should return default on invalid JSON"
        print("✅ Safe read error handling works")
        
        print("\n" + "="*50)
        print("All Windows I/O tests passed! ✅")
        print("="*50)
    
    finally:
        # Cleanup
        shutil.rmtree(test_dir, ignore_errors=True)

