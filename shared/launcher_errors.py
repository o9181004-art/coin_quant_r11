"""
Standardized launcher error handling for all services.
Ensures clear, actionable error messages with proper logging.
"""

import sys
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class LaunchResult:
    """Standardized launch result object"""
    ok: bool
    code: str  # MISSING_ENV, SCRIPT_NOT_FOUND, IMPORT_ERROR, PORT_IN_USE, PYTHON_VERSION_MISMATCH, etc.
    detail: str
    log_file: Optional[str] = None
    
    def get_ui_message(self) -> str:
        """Get compact UI message (first line of detail)"""
        return self.detail.split('\n')[0] if self.detail else self.code


class LaunchLogger:
    """Centralized launcher logging"""
    
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.log_dir = Path("logs/ops")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / f"launch_{service_name}.log"
    
    def log_error(self, code: str, detail: str, exception: Optional[Exception] = None) -> LaunchResult:
        """Log error with full traceback and return standardized result"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        log_content = [
            f"[{timestamp}] LAUNCH FAILED: {self.service_name}",
            f"CODE: {code}",
            f"DETAIL: {detail}",
        ]
        
        if exception:
            log_content.append("\nFULL TRACEBACK:")
            log_content.append(traceback.format_exc())
        
        log_text = "\n".join(log_content) + "\n" + "="*80 + "\n"
        
        # Append to log file
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_text)
        
        return LaunchResult(
            ok=False,
            code=code,
            detail=detail,
            log_file=str(self.log_file)
        )
    
    def log_success(self, detail: str = "Service started successfully") -> LaunchResult:
        """Log success"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        log_content = [
            f"[{timestamp}] LAUNCH SUCCESS: {self.service_name}",
            f"DETAIL: {detail}",
            "="*80
        ]
        
        log_text = "\n".join(log_content) + "\n"
        
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_text)
        
        return LaunchResult(
            ok=True,
            code="SUCCESS",
            detail=detail,
            log_file=str(self.log_file)
        )


def check_python_version() -> Optional[LaunchResult]:
    """
    Enforce Python 3.11 ONLY.
    Returns LaunchResult if version mismatch, None if OK.
    """
    version_info = sys.version_info[:2]
    
    if version_info != (3, 11):
        found_version = f"{version_info[0]}.{version_info[1]}"
        venv_path = Path(sys.executable).parent.parent
        
        detail = (
            f"Python version mismatch: found {found_version}, require 3.11.x\n"
            f"Current venv: {venv_path}\n"
            f"Please activate venv_fixed or venv_refactor with Python 3.11"
        )
        
        return LaunchResult(
            ok=False,
            code="PYTHON_VERSION_MISMATCH",
            detail=detail
        )
    
    return None


__all__ = ["LaunchResult", "LaunchLogger", "check_python_version"]

