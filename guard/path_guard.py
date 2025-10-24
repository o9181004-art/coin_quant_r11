#!/usr/bin/env python3
"""
Path Guard - SSOT Policy Enforcement

Provides policy guards to ensure all file operations stay within SSOT boundaries.
Any attempt to write outside SSOT fails fast with clear error messages.
"""

import os
import sys
import logging
from pathlib import Path
from typing import Union
# Avoid circular import - define SSOT resolution locally
import os
from pathlib import Path


# Configure logging for path guard violations
_logger = logging.getLogger('path_guard')
_logger.setLevel(logging.WARNING)

# Create handler for path guard violations
_handler = logging.StreamHandler(sys.stderr)
_formatter = logging.Formatter(
    '%(asctime)s - PATH_GUARD_VIOLATION - %(levelname)s - %(message)s'
)
_handler.setFormatter(_formatter)
_logger.addHandler(_handler)

# Also log to file
_log_file_handler = logging.FileHandler('logs/path_guard_violations.log', mode='a')
_log_file_handler.setFormatter(_formatter)
_logger.addHandler(_log_file_handler)


class PathGuardViolation(Exception):
    """Exception raised when path guard policy is violated"""
    pass


def _normalize_path(path: Union[str, Path]) -> Path:
    """Normalize and resolve a path"""
    if isinstance(path, str):
        path = Path(path)
    
    # Convert to absolute path
    if not path.is_absolute():
        path = path.resolve()
    
    return path


def _is_path_under_ssot(path: Union[str, Path], ssot_dir: Path) -> bool:
    """Check if path is under SSOT directory"""
    try:
        normalized_path = _normalize_path(path)
        normalized_ssot = _normalize_path(ssot_dir)
        
        # Check if path is under SSOT
        try:
            normalized_path.relative_to(normalized_ssot)
            return True
        except ValueError:
            return False
            
    except Exception:
        # If we can't determine, assume violation for safety
        return False


def _get_ssot_dir() -> Path:
    """Get SSOT directory without circular import"""
    # Check SHARED_DATA environment variable first
    shared_data_env = os.getenv('SHARED_DATA')
    if shared_data_env:
        return Path(shared_data_env).resolve()
    
    # Fallback to CQ_ROOT/shared_data
    cq_root = os.getenv('CQ_ROOT')
    if cq_root:
        return Path(cq_root).resolve() / 'shared_data'
    
    # Ultimate fallback: project root/shared_data
    current_path = Path(__file__).resolve()
    for parent in current_path.parents:
        if any((parent / marker).exists() for marker in ['config.env', 'requirements.txt', 'pyproject.toml']):
            return parent / 'shared_data'
    
    # If we can't find project root, assume current file is in project_root/shared/
    return current_path.parent.parent / 'shared_data'


def assert_in_ssot(path: Union[str, Path], operation: str = "write") -> None:
    """
    Assert that a path is within SSOT boundaries
    
    Args:
        path: Path to check
        operation: Operation being performed (for logging)
    
    Raises:
        PathGuardViolation: If path is outside SSOT
    
    Example:
        >>> assert_in_ssot("shared_data/health.json")
        >>> assert_in_ssot("C:/temp/file.txt")  # Raises PathGuardViolation
    """
    try:
        ssot_dir = _get_ssot_dir()
        
        if not _is_path_under_ssot(path, ssot_dir):
            normalized_path = _normalize_path(path)
            normalized_ssot = _normalize_path(ssot_dir)
            
            error_msg = (
                f"PATH_GUARD_VIOLATION: Attempted {operation} to path outside SSOT\n"
                f"  Target path: {normalized_path}\n"
                f"  SSOT boundary: {normalized_ssot}\n"
                f"  Operation: {operation}\n"
                f"  This operation has been blocked for security reasons.\n"
                f"  Use SSOT-relative paths like 'shared_data/filename.json'"
            )
            
            # Log the violation
            _logger.error(error_msg)
            
            # Raise exception
            raise PathGuardViolation(error_msg)
            
    except Exception as e:
        if isinstance(e, PathGuardViolation):
            raise
        else:
            # If we can't determine SSOT or check path, fail safely
            error_msg = f"PATH_GUARD_ERROR: Unable to verify path safety for {path}: {e}"
            _logger.error(error_msg)
            raise PathGuardViolation(error_msg)


def check_path_safety(path: Union[str, Path], operation: str = "write") -> bool:
    """
    Check if a path is safe to use (within SSOT)
    
    Args:
        path: Path to check
        operation: Operation being performed
    
    Returns:
        True if path is safe, False otherwise
    """
    try:
        assert_in_ssot(path, operation)
        return True
    except PathGuardViolation:
        return False


def get_ssot_relative_path(path: Union[str, Path]) -> str:
    """
    Get the SSOT-relative path for a given path
    
    Args:
        path: Path to convert
    
    Returns:
        SSOT-relative path string
    
    Raises:
        PathGuardViolation: If path is outside SSOT
    """
    ssot_dir = _get_ssot_dir()
    assert_in_ssot(path, "access")
    
    normalized_path = _normalize_path(path)
    normalized_ssot = _normalize_path(ssot_dir)
    
    return str(normalized_path.relative_to(normalized_ssot))


def validate_write_operation(path: Union[str, Path], operation_type: str = "write") -> None:
    """
    Validate a write operation is safe
    
    Args:
        path: Path being written to
        operation_type: Type of operation (write, append, etc.)
    
    Raises:
        PathGuardViolation: If operation is not safe
    """
    assert_in_ssot(path, operation_type)
    
    # Additional checks can be added here
    # For example, checking for dangerous file extensions, etc.


def validate_read_operation(path: Union[str, Path]) -> None:
    """
    Validate a read operation is safe
    
    Args:
        path: Path being read from
    
    Raises:
        PathGuardViolation: If operation is not safe
    """
    assert_in_ssot(path, "read")


# Context manager for path validation
class PathGuardContext:
    """Context manager for path validation"""
    
    def __init__(self, operation_type: str = "write"):
        self.operation_type = operation_type
        self.original_open = None
    
    def __enter__(self):
        # Store original open function
        self.original_open = open
        
        # Replace open with guarded version
        def guarded_open(file, mode='r', *args, **kwargs):
            if 'w' in mode or 'a' in mode or 'x' in mode:
                validate_write_operation(file, self.operation_type)
            elif 'r' in mode:
                validate_read_operation(file)
            return self.original_open(file, mode, *args, **kwargs)
        
        # Monkey patch open function
        import builtins
        builtins.open = guarded_open
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restore original open function
        if self.original_open:
            import builtins
            builtins.open = self.original_open


# Example usage and testing
if __name__ == "__main__":
    print("Testing Path Guard...")
    
    # Test valid paths
    try:
        assert_in_ssot("shared_data/health.json")
        print("✓ Valid SSOT path accepted")
    except PathGuardViolation:
        print("✗ Valid SSOT path rejected")
    
    # Test invalid paths
    try:
        assert_in_ssot("C:/temp/outside.txt")
        print("✗ Invalid path accepted (should be rejected)")
    except PathGuardViolation:
        print("✓ Invalid path correctly rejected")
    
    # Test path safety check
    safe = check_path_safety("shared_data/test.json")
    print(f"✓ Path safety check: {safe}")
    
    safe = check_path_safety("C:/temp/outside.txt")
    print(f"✓ Invalid path safety check: {safe}")
    
    # Test SSOT relative path
    try:
        rel_path = get_ssot_relative_path("shared_data/health.json")
        print(f"✓ SSOT relative path: {rel_path}")
    except PathGuardViolation as e:
        print(f"✗ SSOT relative path failed: {e}")
    
    print("Path Guard test completed!")
