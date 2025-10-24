"""
Phase 1: Windows-Safe Atomic Write Helper
Handles WinError 183/32 with retry and unique temp names
"""

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict


class AtomicWriter:
    """Windows-safe atomic file writer with retry logic"""
    
    def __init__(self, max_retries: int = 5, backoff_ms: int = 50):
        """
        Initialize atomic writer
        
        Args:
            max_retries: Maximum number of retry attempts
            backoff_ms: Initial backoff delay in milliseconds
        """
        self.max_retries = max_retries
        self.backoff_ms = backoff_ms
    
    def write_json(self, file_path: Path, data: Dict[str, Any]) -> bool:
        """
        Atomically write JSON data to file with Windows error handling
        
        Args:
            file_path: Target file path
            data: Dictionary data to write
        
        Returns:
            True if successful, False otherwise
        """
        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        for attempt in range(self.max_retries):
            try:
                # Generate unique temp filename per attempt
                temp_name = f".{file_path.stem}.{uuid.uuid4().hex[:8]}.tmp"
                temp_path = file_path.parent / temp_name
                
                # Write to temp file
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                
                # Atomic replace (handles existing file on Windows)
                if file_path.exists():
                    # On Windows, we need to remove first if rename fails
                    try:
                        temp_path.replace(file_path)
                    except OSError as e:
                        if e.winerror == 183:  # File already exists
                            # Generate new temp name and retry
                            try:
                                os.remove(temp_path)
                            except OSError:
                                pass
                            continue
                        elif e.winerror == 32:  # File in use
                            # Backoff and retry
                            try:
                                os.remove(temp_path)
                            except OSError:
                                pass
                            time.sleep((self.backoff_ms * (2 ** attempt)) / 1000)
                            continue
                        else:
                            raise
                else:
                    temp_path.rename(file_path)
                
                return True
                
            except Exception as e:
                # Clean up temp file on error
                try:
                    if temp_path.exists():
                        os.remove(temp_path)
                except OSError:
                    pass
                
                if attempt == self.max_retries - 1:
                    print(f"AtomicWriter failed for {file_path}: {e}")
                    return False
                
                # Backoff before retry
                time.sleep((self.backoff_ms * (2 ** attempt)) / 1000)
        
        return False


# Singleton instance
_atomic_writer = AtomicWriter()


def atomic_write_json(file_path: Path, data: Dict[str, Any]) -> bool:
    """
    Convenience function for atomic JSON write
    
    Args:
        file_path: Target file path
        data: Dictionary data to write
    
    Returns:
        True if successful, False otherwise
    """
    return _atomic_writer.write_json(file_path, data)


def safe_read_json(file_path: Path, max_retries: int = 3, backoff_ms: int = 10) -> Dict[str, Any]:
    """
    Safely read JSON file with retry on partial/missing file
    
    Args:
        file_path: File path to read
        max_retries: Maximum retry attempts
        backoff_ms: Backoff delay in milliseconds
    
    Returns:
        Dictionary data or empty dict if file missing/invalid
    """
    for attempt in range(max_retries):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
        except (json.JSONDecodeError, OSError) as e:
            if attempt == max_retries - 1:
                return {}
            time.sleep((backoff_ms * (2 ** attempt)) / 1000)
    
    return {}

