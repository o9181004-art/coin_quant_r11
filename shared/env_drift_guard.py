#!/usr/bin/env python3
"""
Environment Drift Guard
==================================================
Detect environment configuration drift across services.
"""

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Dict, Optional


class EnvDriftGuard:
    """
    Guard against environment configuration drift.

    Features:
    - ENV_HASH calculation from config.env
    - Active venv path validation
    - .env resolved path validation
    - Cross-service consistency check
    """

    def __init__(self):
        """Initialize drift guard"""
        self.project_root = Path.cwd()
        self.env_file = self.project_root / "config.env"
        self.venv_path = self._get_venv_path()
        self.env_hash = self._calculate_env_hash()

    def _get_venv_path(self) -> Optional[Path]:
        """Get active venv path"""
        # Check if running in venv
        if hasattr(sys, "real_prefix") or (
            hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
        ):
            return Path(sys.prefix)

        return None

    def _calculate_env_hash(self) -> str:
        """
        Calculate hash of config.env file.

        Returns:
            SHA256 hash of env file (first 16 chars)
        """
        if not self.env_file.exists():
            return "NO_ENV_FILE"

        try:
            with open(self.env_file, "r", encoding="utf-8") as f:
                content = f.read()

            # Hash content
            hash_obj = hashlib.sha256(content.encode("utf-8"))
            return hash_obj.hexdigest()[:16]

        except Exception:
            return "ENV_READ_ERROR"

    def get_env_fingerprint(self) -> Dict[str, any]:
        """
        Get environment fingerprint for logging/comparison.

        Returns:
            Dict with env_hash, venv_path, env_file_path
        """
        return {
            "env_hash": self.env_hash,
            "venv_path": str(self.venv_path) if self.venv_path else "NOT_IN_VENV",
            "env_file": str(self.env_file),
            "env_file_exists": self.env_file.exists(),
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "python_executable": sys.executable,
            "working_directory": str(Path.cwd()),
        }

    def validate(self, expected_venv_name: str = "cq_ref311") -> tuple[bool, str]:
        """
        Validate environment configuration.

        Args:
            expected_venv_name: Expected venv name

        Returns:
            (valid, error_message)
        """
        # Check venv
        if not self.venv_path:
            return False, "Not running in virtual environment"

        if expected_venv_name and expected_venv_name not in str(self.venv_path):
            return (
                False,
                f"Wrong venv: expected '{expected_venv_name}', got '{self.venv_path}'",
            )

        # Check env file
        if not self.env_file.exists():
            return False, f"config.env not found at {self.env_file}"

        # Check Python version
        if sys.version_info.major < 3 or (
            sys.version_info.major == 3 and sys.version_info.minor < 10
        ):
            return (
                False,
                f"Python 3.10+ required, got {sys.version_info.major}.{sys.version_info.minor}",
            )

        return True, "Environment OK"

    def save_fingerprint(self, service_name: str):
        """
        Save fingerprint for cross-service validation.

        Args:
            service_name: Name of the service
        """
        fingerprint_file = (
            self.project_root / "shared_data" / f"env_fingerprint_{service_name}.json"
        )
        fingerprint_file.parent.mkdir(parents=True, exist_ok=True)

        fingerprint = self.get_env_fingerprint()
        fingerprint["service_name"] = service_name

        with open(fingerprint_file, "w") as f:
            json.dump(fingerprint, f, indent=2)

    def compare_with(self, other_service: str) -> tuple[bool, str]:
        """
        Compare with another service's fingerprint.

        Args:
            other_service: Name of the other service

        Returns:
            (match, difference_message)
        """
        fingerprint_file = (
            self.project_root / "shared_data" / f"env_fingerprint_{other_service}.json"
        )

        if not fingerprint_file.exists():
            return False, f"No fingerprint found for {other_service}"

        try:
            with open(fingerprint_file, "r") as f:
                other_fingerprint = json.load(f)

            my_fingerprint = self.get_env_fingerprint()

            # Compare critical fields
            if my_fingerprint["env_hash"] != other_fingerprint["env_hash"]:
                return (
                    False,
                    f"ENV_HASH mismatch: {my_fingerprint['env_hash']} vs {other_fingerprint['env_hash']}",
                )

            if my_fingerprint["venv_path"] != other_fingerprint["venv_path"]:
                return (
                    False,
                    f"VENV mismatch: {my_fingerprint['venv_path']} vs {other_fingerprint['venv_path']}",
                )

            return True, "Fingerprints match"

        except Exception as e:
            return False, f"Fingerprint comparison failed: {e}"


if __name__ == "__main__":
    # Test drift guard
    guard = EnvDriftGuard()

    print("=" * 60)
    print(" Environment Drift Guard")
    print("=" * 60)
    print()

    fingerprint = guard.get_env_fingerprint()

    for key, value in fingerprint.items():
        print(f"  {key}: {value}")

    print()

    valid, message = guard.validate()

    if valid:
        print(f"✅ {message}")
    else:
        print(f"❌ {message}")
