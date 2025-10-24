"""
Phase 0: Environment Normalization & Guardrails
Ensures all services run from correct repo root with correct venv
"""

import sys
from pathlib import Path


def validate_environment(service_name: str):
    """
    Validate environment and working directory for a service
    
    Args:
        service_name: Name of the service for error messages
    
    Raises:
        SystemExit: If validation fails
    """
    # Get repo root (should be parent of shared/)
    REPO_ROOT = Path(__file__).parent.parent.resolve()
    
    # Check working directory
    if Path.cwd() != REPO_ROOT:
        print(f"❌ ERROR: {service_name} must run from repo root")
        print(f"Current: {Path.cwd()}")
        print(f"Expected: {REPO_ROOT}")
        print(f"Please run: cd {REPO_ROOT}")
        sys.exit(1)
    
    # Check Python interpreter (allow venv_new for Python 3.13 environment)
    venv_paths = [
        REPO_ROOT / "venv" / "Scripts" / "python.exe",
        REPO_ROOT / "venv_new" / "Scripts" / "python.exe"
    ]
    
    current_python = Path(sys.executable)
    valid_venv = any(current_python.resolve() == venv_path.resolve() for venv_path in venv_paths if venv_path.exists())
    
    if not valid_venv:
        print(f"❌ ERROR: {service_name} must use project venv Python")
        print(f"Current: {sys.executable}")
        print(f"Expected: One of {[str(p) for p in venv_paths if p.exists()]}")
        print(f"Please activate venv or use one of the expected paths")
        sys.exit(1)
    
    return REPO_ROOT


def get_absolute_path(relative_path: str) -> Path:
    """
    Get absolute path from repo root
    
    Args:
        relative_path: Path relative to repo root (e.g., "shared_data/health.json")
    
    Returns:
        Absolute Path object
    """
    REPO_ROOT = Path(__file__).parent.parent.resolve()
    return REPO_ROOT / relative_path

