#!/usr/bin/env python3
"""
Python Interpreter Guard
========================================
Ensures ONLY the expected Python 3.11 venv is used.
If not, exits immediately with a clear error (no retry loops).

Usage:
    from shared.python_guard import enforce_python_interpreter
    enforce_python_interpreter()  # Exits if not 3.11 venv
"""

import sys
from pathlib import Path


def enforce_python_interpreter(expected_venv_name: str = "venv_fixed") -> None:
    """
    Hard stop if Python interpreter is not the expected 3.11 venv.
    
    Args:
        expected_venv_name: Expected venv directory name (default: venv_fixed)
    
    Exits:
        Immediately if interpreter does not match expected venv path.
        Returns silently if check passes.
    """
    current_python = Path(sys.executable).resolve()
    repo_root = Path(__file__).resolve().parent.parent
    expected_python = repo_root / expected_venv_name / "Scripts" / "python.exe"
    
    # Normalize paths for comparison
    current_python_norm = str(current_python).lower().replace("\\", "/")
    expected_python_norm = str(expected_python).lower().replace("\\", "/")
    
    if current_python_norm != expected_python_norm:
        # Hard stop - single line error
        print(f"❌ INTERPRETER_GUARD_FAILED: Expected {expected_python}, got {current_python}")
        sys.exit(1)
    
    # Silent success
    return


def get_expected_python_path(expected_venv_name: str = "venv_fixed") -> Path:
    """
    Get the expected Python interpreter path.
    
    Args:
        expected_venv_name: Expected venv directory name
    
    Returns:
        Path to expected python.exe
    """
    repo_root = Path(__file__).resolve().parent.parent
    return repo_root / expected_venv_name / "Scripts" / "python.exe"


def check_python_version(expected_major: int = 3, expected_minor: int = 11) -> bool:
    """
    Check if Python version matches expected version.
    
    Args:
        expected_major: Expected major version (default: 3)
        expected_minor: Expected minor version (default: 11)
    
    Returns:
        True if version matches, False otherwise
    """
    return sys.version_info.major == expected_major and sys.version_info.minor == expected_minor


if __name__ == "__main__":
    # Test the guard
    print("Testing Python Interpreter Guard...")
    try:
        enforce_python_interpreter()
        print(f"✅ Interpreter guard passed: {sys.executable}")
        print(f"   Python version: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    except SystemExit:
        print("❌ Interpreter guard failed - exiting")

