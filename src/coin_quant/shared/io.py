"""
Atomic I/O utilities for Coin Quant R11

Windows-safe atomic writes and readers with unified helper.
Provides atomic JSON, text, and NDJSON operations.
"""

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Union


class AtomicIOError(Exception):
    """Atomic I/O related error"""
    pass


class AtomicWriter:
    """Windows-safe atomic writer"""
    
    def __init__(self, max_retries: int = 3, retry_delay: float = 0.1):
        self.max_retries = max_retries
        self.retry_delay = retry_delay
    
    def write_json(self, file_path: Union[str, Path], data: Dict[str, Any], 
                   ensure_dirs: bool = True) -> bool:
        """
        Atomic JSON file write.
        
        Args:
            file_path: Target file path
            data: Data to write
            ensure_dirs: Whether to ensure parent directories exist
            
        Returns:
            True if successful, False otherwise
        """
        try:
            file_path = Path(file_path)
            
            if ensure_dirs:
                file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Generate temporary filename (PID + UUID)
            temp_file = file_path.parent / f".tmp_{os.getpid()}_{uuid.uuid4().hex[:8]}.json"
            
            # Serialize JSON data
            json_data = json.dumps(data, ensure_ascii=False, indent=2)
            
            # Atomic write with retry
            return self._atomic_write_with_retry(temp_file, json_data, file_path)
            
        except Exception as e:
            raise AtomicIOError(f"JSON write failed for {file_path}: {e}")
    
    def write_text(self, file_path: Union[str, Path], content: str, 
                   encoding: str = 'utf-8', ensure_dirs: bool = True) -> bool:
        """
        Atomic text file write.
        
        Args:
            file_path: Target file path
            content: Content to write
            encoding: Text encoding
            ensure_dirs: Whether to ensure parent directories exist
            
        Returns:
            True if successful, False otherwise
        """
        try:
            file_path = Path(file_path)
            
            if ensure_dirs:
                file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Generate temporary filename
            temp_file = file_path.parent / f".tmp_{os.getpid()}_{uuid.uuid4().hex[:8]}.txt"
            
            # Atomic write with retry
            return self._atomic_write_with_retry(temp_file, content, file_path, encoding)
            
        except Exception as e:
            raise AtomicIOError(f"Text write failed for {file_path}: {e}")
    
    def append_ndjson(self, file_path: Union[str, Path], data: Dict[str, Any],
                      ensure_dirs: bool = True) -> bool:
        """
        Atomic NDJSON file append.
        
        Args:
            file_path: Target file path
            data: Data to append
            ensure_dirs: Whether to ensure parent directories exist
            
        Returns:
            True if successful, False otherwise
        """
        try:
            file_path = Path(file_path)
            
            if ensure_dirs:
                file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Generate NDJSON line
            json_line = json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n'
            
            # Direct append to file (NDJSON only needs append, no atomic write needed)
            with open(file_path, 'a', encoding='utf-8') as f:
                f.write(json_line)
                f.flush()
                os.fsync(f.fileno())  # Force write to disk
            
            return True
            
        except Exception as e:
            raise AtomicIOError(f"NDJSON append failed for {file_path}: {e}")
    
    def _atomic_write_with_retry(self, temp_file: Path, content: str, 
                                target_file: Path, encoding: str = 'utf-8') -> bool:
        """
        Atomic write with retry logic.
        
        Args:
            temp_file: Temporary file path
            target_file: Target file path
            content: Content to write
            encoding: Text encoding
            
        Returns:
            True if successful, False otherwise
        """
        for attempt in range(self.max_retries):
            try:
                # Write to temporary file
                with open(temp_file, 'w', encoding=encoding) as f:
                    f.write(content)
                    f.flush()
                    os.fsync(f.fileno())  # Force write to disk
                
                # Atomic move (rename)
                if os.name == 'nt':  # Windows
                    # On Windows, we need to handle the case where target exists
                    if target_file.exists():
                        target_file.unlink()
                    temp_file.rename(target_file)
                else:  # Unix-like
                    temp_file.replace(target_file)
                
                return True
                
            except (OSError, IOError) as e:
                # Clean up temporary file on failure
                if temp_file.exists():
                    try:
                        temp_file.unlink()
                    except OSError:
                        pass
                
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                    continue
                else:
                    raise AtomicIOError(f"Atomic write failed after {self.max_retries} attempts: {e}")
        
        return False


class AtomicReader:
    """Atomic file reader with error handling"""
    
    @staticmethod
    def read_json(file_path: Union[str, Path], default: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        Read JSON file with error handling.
        
        Args:
            file_path: File path to read
            default: Default value if file doesn't exist or is invalid
            
        Returns:
            Parsed JSON data or default value
        """
        try:
            file_path = Path(file_path)
            if not file_path.exists():
                return default
            
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
                
        except (json.JSONDecodeError, IOError, OSError):
            return default
    
    @staticmethod
    def read_text(file_path: Union[str, Path], default: Optional[str] = None, 
                  encoding: str = 'utf-8') -> Optional[str]:
        """
        Read text file with error handling.
        
        Args:
            file_path: File path to read
            default: Default value if file doesn't exist or is invalid
            encoding: Text encoding
            
        Returns:
            File content or default value
        """
        try:
            file_path = Path(file_path)
            if not file_path.exists():
                return default
            
            with open(file_path, 'r', encoding=encoding) as f:
                return f.read()
                
        except (IOError, OSError):
            return default


# Global instances for convenience
atomic_writer = AtomicWriter()
atomic_reader = AtomicReader()

# Path conversion utility
def to_str_path(path: Union[str, Path]) -> str:
    """Convert Path object to string for libraries that expect strings"""
    return str(path)

# Convenience functions for backward compatibility
def atomic_write_json(file_path: Union[str, Path], data: Dict[str, Any], 
                     ensure_dirs: bool = True) -> bool:
    """Convenience function for atomic JSON write"""
    return atomic_writer.write_json(file_path, data, ensure_dirs)

def safe_read_json(file_path: Union[str, Path], default: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Convenience function for safe JSON read"""
    return atomic_reader.read_json(file_path, default)
