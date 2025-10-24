#!/usr/bin/env python3
"""
Venv Path Helper - Get absolute venv Python path
========================================
Provides utility to get the absolute path to the project's venv Python interpreter.

Usage:
    from shared.venv_path_helper import get_venv_python_absolute_path
    
    python_exe = get_venv_python_absolute_path()
    # Returns: C:\Users\...\coin_quant\venv_fixed\Scripts\python.exe
"""

import os
import sys
from pathlib import Path


def get_venv_python_absolute_path(venv_name: str = "venv_fixed") -> str:
    """
    Get absolute path to venv Python interpreter.
    
    Args:
        venv_name: Name of venv directory (default: venv_fixed)
    
    Returns:
        Absolute path string to python.exe (Windows) or python (Unix)
    """
    # Get project root (assume this file is in shared/)
    project_root = Path(__file__).resolve().parent.parent
    
    if sys.platform == "win32":
        python_exe = project_root / venv_name / "Scripts" / "python.exe"
    else:
        python_exe = project_root / venv_name / "bin" / "python"
    
    return str(python_exe.resolve())


def get_venv_streamlit_absolute_path(venv_name: str = "venv_fixed") -> str:
    """
    Get absolute path to venv streamlit executable.
    
    Args:
        venv_name: Name of venv directory (default: venv_fixed)
    
    Returns:
        Absolute path string to streamlit.exe (Windows) or streamlit (Unix)
    """
    project_root = Path(__file__).resolve().parent.parent
    
    if sys.platform == "win32":
        streamlit_exe = project_root / venv_name / "Scripts" / "streamlit.exe"
    else:
        streamlit_exe = project_root / venv_name / "bin" / "streamlit"
    
    return str(streamlit_exe.resolve())


def get_project_root() -> Path:
    """Get project root directory path."""
    return Path(__file__).resolve().parent.parent


if __name__ == "__main__":
    # Test
    print(f"Project root: {get_project_root()}")
    print(f"Python path: {get_venv_python_absolute_path()}")
    print(f"Streamlit path: {get_venv_streamlit_absolute_path()}")
    
    # Check if paths exist
    python_path = Path(get_venv_python_absolute_path())
    if python_path.exists():
        print(f"✅ Python executable found")
    else:
        print(f"❌ Python executable not found: {python_path}")
    
    streamlit_path = Path(get_venv_streamlit_absolute_path())
    if streamlit_path.exists():
        print(f"✅ Streamlit executable found")
    else:
        print(f"❌ Streamlit executable not found: {streamlit_path}")

