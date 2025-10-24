#!/usr/bin/env python3
"""
Canonical paths for Stack Doctor reports
Single source of truth for all writer/reader/UI components
"""

from pathlib import Path

# Project root
REPO_ROOT = Path(__file__).parent.parent.parent.resolve()

# Stack Doctor report directory and files
STACK_DOCTOR_DIR = REPO_ROOT / "shared_data" / "reports" / "stack_doctor"
STACK_DOCTOR_LATEST_MD = STACK_DOCTOR_DIR / "latest.md"
STACK_DOCTOR_LATEST_JSON = STACK_DOCTOR_DIR / "latest.json"

# Ensure directory exists
def ensure_stack_doctor_dir():
    """Create Stack Doctor directory if it doesn't exist"""
    STACK_DOCTOR_DIR.mkdir(parents=True, exist_ok=True)
    return STACK_DOCTOR_DIR


if __name__ == "__main__":
    # Test
    print(f"REPO_ROOT: {REPO_ROOT}")
    print(f"STACK_DOCTOR_DIR: {STACK_DOCTOR_DIR}")
    print(f"STACK_DOCTOR_LATEST_MD: {STACK_DOCTOR_LATEST_MD}")
    print(f"STACK_DOCTOR_LATEST_JSON: {STACK_DOCTOR_LATEST_JSON}")

    # Ensure directory
    ensure_stack_doctor_dir()
    print(f"✅ Directory ensured: {STACK_DOCTOR_DIR.exists()}")
