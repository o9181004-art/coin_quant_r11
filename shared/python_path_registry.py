#!/usr/bin/env python3
"""
Python Path Registry
Ensures deterministic Python interpreter path across all services
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from .atomic_io import atomic_write
from .path_registry import get_absolute_path


class PythonPathRegistry:
    """
    Manages Python interpreter path determinism
    Records resolved path in SSOT and validates on each service start
    """
    
    def __init__(self):
        self.logger = logging.getLogger('PythonPath')
        self.registry_path = get_absolute_path('shared_data') / 'runtime' / 'python_executable.txt'
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.current_python = sys.executable
        self.registered_python: Optional[str] = None
        
        self._load_registry()
    
    def _load_registry(self):
        """Load registered Python path"""
        if self.registry_path.exists():
            try:
                self.registered_python = self.registry_path.read_text(encoding='utf-8').strip()
            except Exception as e:
                self.logger.error(f"Failed to load Python registry: {e}")
    
    def _save_registry(self):
        """Save Python path to registry"""
        try:
            atomic_write(self.registry_path, self.current_python)
            self.registered_python = self.current_python
            self.logger.info(f"Python path registered: {self.current_python}")
        except Exception as e:
            self.logger.error(f"Failed to save Python registry: {e}")
    
    def register_current_python(self):
        """Register current Python interpreter"""
        self._save_registry()
    
    def validate_python_path(self) -> tuple[bool, str]:
        """
        Validate that current Python matches registered Python
        
        Returns:
            (is_valid, message)
        """
        if not self.registered_python:
            # No registered path yet, register current
            self.register_current_python()
            return True, f"Registered: {self.current_python}"
        
        # Normalize paths for comparison
        current_norm = Path(self.current_python).resolve()
        registered_norm = Path(self.registered_python).resolve()
        
        if current_norm == registered_norm:
            return True, "Python path matches"
        
        # Different paths - this is an error
        message = (
            f"Python path mismatch!\n"
            f"Current:    {current_norm}\n"
            f"Registered: {registered_norm}\n"
            f"This can cause service startup failures."
        )
        
        return False, message
    
    def get_registered_python(self) -> Optional[str]:
        """Get registered Python path"""
        return self.registered_python
    
    def get_current_python(self) -> str:
        """Get current Python path"""
        return self.current_python
    
    def get_python_info(self) -> dict:
        """Get Python environment info"""
        return {
            "current_python": self.current_python,
            "registered_python": self.registered_python,
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "platform": sys.platform,
            "prefix": sys.prefix,
            "base_prefix": sys.base_prefix,
            "in_venv": sys.prefix != sys.base_prefix
        }


# Global instance
_python_registry = PythonPathRegistry()


def register_current_python():
    """Register current Python interpreter"""
    _python_registry.register_current_python()


def validate_python_path() -> tuple[bool, str]:
    """Validate Python path"""
    return _python_registry.validate_python_path()


def get_registered_python() -> Optional[str]:
    """Get registered Python path"""
    return _python_registry.get_registered_python()


def get_current_python() -> str:
    """Get current Python path"""
    return _python_registry.get_current_python()


def get_python_info() -> dict:
    """Get Python info"""
    return _python_registry.get_python_info()


# Auto-validate on import
def _auto_validate():
    """Auto-validate Python path on import"""
    is_valid, message = validate_python_path()
    if not is_valid:
        logging.getLogger('PythonPath').error(message)


_auto_validate()

