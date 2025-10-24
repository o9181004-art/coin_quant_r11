#!/usr/bin/env python3
"""
Runtime Invariants Enforcer
============================
Enforce single runtime constraints to prevent recurrence issues.

Guarantees:
- Working directory is correct (C:/Users/Gil/Desktop/coin_quant)
- All critical paths are within repo root
- Python interpreter is the approved venv
- No path escapes outside repo
"""

import logging
import os
import sys
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)

# ====================================================
# Approved Paths (Absolute)
# ====================================================
APPROVED_REPO_ROOT = Path("C:/Users/Gil/Desktop/coin_quant")
APPROVED_VENV_PYTHON = Path("C:/Users/Gil/Desktop/coin_quant/venv_fixed/Scripts/python.exe")

# Alternative approved paths (for flexibility)
APPROVED_REPO_ROOTS = [
    APPROVED_REPO_ROOT,
    # Add alternatives if needed
]


# ====================================================
# Path Validation
# ====================================================
def validate_working_directory() -> bool:
    """
    Validate that current working directory is within approved repo.

    Returns:
        True if valid, False otherwise

    Side Effects:
        Logs error if invalid
    """
    cwd = Path.cwd().resolve()

    for approved in APPROVED_REPO_ROOTS:
        try:
            # Check if cwd is within approved repo
            cwd.relative_to(approved)
            return True
        except ValueError:
            continue

    logger.error(
        f"INVALID_CWD: Current directory {cwd} is outside approved repo roots. "
        f"Expected: {APPROVED_REPO_ROOT}"
    )
    return False


def validate_python_interpreter() -> bool:
    """
    Validate that Python interpreter is the approved venv.

    Returns:
        True if valid, False otherwise

    Side Effects:
        Logs error if invalid
    """
    current_python = Path(sys.executable).resolve()

    if current_python == APPROVED_VENV_PYTHON.resolve():
        return True

    logger.error(
        f"INVALID_PYTHON: Interpreter {current_python} is not approved. "
        f"Expected: {APPROVED_VENV_PYTHON}"
    )
    return False


def validate_critical_paths() -> Dict[str, Path]:
    """
    Validate and return critical paths.

    Returns:
        Dict with absolute paths for critical locations

    Raises:
        RuntimeError if any path is invalid
    """
    repo_root = Path.cwd().resolve()

    # Critical paths
    paths = {
        "repo_root": repo_root,
        "shared_data": repo_root / "shared_data",
        "health": repo_root / "shared_data" / "health",
        "databus": repo_root / "shared_data" / "databus_snapshot.json",
        "uds": repo_root / "shared_data" / "health" / "uds.json",
        "venv": Path(sys.executable).parent.parent,
    }

    # Validate all paths are within repo root
    for name, path in paths.items():
        if name == "venv":
            continue  # venv can be anywhere

        try:
            path.resolve().relative_to(repo_root)
        except ValueError:
            raise RuntimeError(
                f"INVALID_PATH: {name}={path} is outside repo root {repo_root}"
            )

    return paths


def log_runtime_invariants(service_name: str):
    """
    Log runtime invariants for a service.

    Args:
        service_name: Name of the service (e.g., "Feeder", "Trader")

    Side Effects:
        Logs one-line summary of all invariants
    """
    try:
        paths = validate_critical_paths()

        logger.info(
            f"[{service_name}] RUNTIME_INVARIANTS: "
            f"cwd={paths['repo_root']} "
            f"databus={paths['databus']} "
            f"health={paths['health']} "
            f"uds={paths['uds']} "
            f"venv={sys.executable}"
        )
    except Exception as e:
        logger.error(f"[{service_name}] INVARIANT_CHECK_FAILED: {e}")


def enforce_runtime_invariants(service_name: str) -> bool:
    """
    Enforce all runtime invariants.

    Args:
        service_name: Name of the service

    Returns:
        True if all invariants satisfied, False otherwise

    Side Effects:
        Exits process if invariants violated
    """
    print("=" * 60)
    print(f"{service_name} - Runtime Invariants Check")
    print("=" * 60)

    # Check 1: Working directory
    print("\n[1/3] Checking working directory...")
    if not validate_working_directory():
        print(f"❌ FAILED: Invalid working directory")
        print(f"   Current: {Path.cwd()}")
        print(f"   Expected: {APPROVED_REPO_ROOT}")
        print(f"   Action: cd {APPROVED_REPO_ROOT}")
        sys.exit(1)
    print(f"✅ OK: {Path.cwd()}")

    # Check 2: Python interpreter
    print("\n[2/3] Checking Python interpreter...")
    if not validate_python_interpreter():
        print(f"❌ FAILED: Invalid Python interpreter")
        print(f"   Current: {sys.executable}")
        print(f"   Expected: {APPROVED_VENV_PYTHON}")
        print(f"   Action: Use approved venv")
        sys.exit(1)
    print(f"✅ OK: {sys.executable}")

    # Check 3: Critical paths
    print("\n[3/3] Checking critical paths...")
    try:
        paths = validate_critical_paths()
        print(f"✅ OK: All paths within repo root")

        # Log invariants
        log_runtime_invariants(service_name)
    except RuntimeError as e:
        print(f"❌ FAILED: {e}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print(f"✅ All runtime invariants satisfied for {service_name}")
    print("=" * 60)

    return True


# ====================================================
# Testing
# ====================================================
if __name__ == "__main__":
    enforce_runtime_invariants("TEST_SERVICE")

