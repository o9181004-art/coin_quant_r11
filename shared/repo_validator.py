"""
Repository validator - ensures we're running in the correct coin_quant repo.
Prevents accidental execution in coin_quant_refactor.
"""

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


class RepoValidator:
    """Validates repository location and Python environment"""
    
    EXPECTED_REPO_ROOT = Path(r"C:\Users\Gil\Desktop\coin_quant")
    EXPECTED_PYTHON = EXPECTED_REPO_ROOT / "venv_fixed" / "Scripts" / "python.exe"
    
    @classmethod
    def validate_repo(cls, fail_fast: bool = True) -> dict:
        """
        Validate that we're running in the correct repository.
        
        Args:
            fail_fast: If True, raise exception on validation failure
        
        Returns:
            {
                "valid": bool,
                "errors": list,
                "warnings": list,
                "repo_root": Path,
                "python_path": Path
            }
        """
        errors = []
        warnings = []
        
        # Get current working directory
        current_dir = Path.cwd()
        
        # Get current Python interpreter
        current_python = Path(sys.executable)
        
        # Check 1: Are we in coin_quant_refactor?
        if "refactor" in str(current_dir).lower():
            errors.append(
                f"ERROR: Running in refactor repo: {current_dir}\n"
                f"Expected: {cls.EXPECTED_REPO_ROOT}"
            )
        
        # Check 2: Is Python from refactor venv?
        if "refactor" in str(current_python).lower():
            errors.append(
                f"ERROR: Using refactor Python: {current_python}\n"
                f"Expected: {cls.EXPECTED_PYTHON}"
            )
        
        # Check 3: Are we in the correct repo?
        if current_dir != cls.EXPECTED_REPO_ROOT:
            # Allow subdirectories
            if cls.EXPECTED_REPO_ROOT not in current_dir.parents:
                warnings.append(
                    f"WARNING: Not in expected repo root\n"
                    f"Current: {current_dir}\n"
                    f"Expected: {cls.EXPECTED_REPO_ROOT}"
                )
        
        # Check 4: Is Python version correct?
        if sys.version_info[:2] != (3, 11):
            errors.append(
                f"ERROR: Wrong Python version: {sys.version_info[0]}.{sys.version_info[1]}\n"
                f"Expected: 3.11"
            )
        
        # Check 5: Is Python from correct venv?
        if not current_python.is_relative_to(cls.EXPECTED_REPO_ROOT):
            warnings.append(
                f"WARNING: Python not from expected venv\n"
                f"Current: {current_python}\n"
                f"Expected: {cls.EXPECTED_PYTHON}"
            )
        
        valid = len(errors) == 0
        
        result = {
            "valid": valid,
            "errors": errors,
            "warnings": warnings,
            "repo_root": current_dir,
            "python_path": current_python
        }
        
        # Log results
        if errors:
            for error in errors:
                logger.error(error)
        
        if warnings:
            for warning in warnings:
                logger.warning(warning)
        
        # Fail fast if requested
        if fail_fast and not valid:
            error_msg = "\n\n".join(errors)
            raise RuntimeError(
                f"Repository validation failed:\n\n{error_msg}\n\n"
                f"Please run from: {cls.EXPECTED_REPO_ROOT}\n"
                f"With Python: {cls.EXPECTED_PYTHON}"
            )
        
        return result
    
    @classmethod
    def get_repo_paths(cls) -> dict:
        """
        Get canonical repository paths.
        
        Returns:
            {
                "repo_root": Path,
                "shared_data": Path,
                "logs": Path,
                "config": Path,
                "python_exe": Path
            }
        """
        return {
            "repo_root": cls.EXPECTED_REPO_ROOT,
            "shared_data": cls.EXPECTED_REPO_ROOT / "shared_data",
            "logs": cls.EXPECTED_REPO_ROOT / "logs",
            "config": cls.EXPECTED_REPO_ROOT / "config.env",
            "python_exe": cls.EXPECTED_PYTHON
        }


def validate_on_import(fail_fast: bool = False):
    """
    Validate repository on module import.
    Call this at the top of critical modules.
    
    Args:
        fail_fast: If True, raise exception on validation failure
    """
    result = RepoValidator.validate_repo(fail_fast=fail_fast)
    
    if result["valid"]:
        logger.info(f"✅ Repository validation passed: {result['repo_root']}")
    else:
        logger.error(f"❌ Repository validation failed")
        for error in result["errors"]:
            logger.error(error)


__all__ = ["RepoValidator", "validate_on_import"]

