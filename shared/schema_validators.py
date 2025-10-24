#!/usr/bin/env python3
"""
Schema Validators
Lightweight validators for timestamp presence and age thresholds
"""
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional, Tuple


class ValidationResult:
    """Validation result with detailed information"""
    
    def __init__(self, is_valid: bool, age_sec: float, error_msg: str = "", details: Dict[str, Any] = None):
        self.is_valid = is_valid
        self.age_sec = age_sec
        self.error_msg = error_msg
        self.details = details or {}
    
    def __str__(self):
        if self.is_valid:
            return f"VALID (age: {self.age_sec:.1f}s)"
        else:
            return f"INVALID (age: {self.age_sec:.1f}s) - {self.error_msg}"


class SchemaValidator:
    """Schema validation with age threshold checking"""
    
    def __init__(self):
        self.current_time = time.time()
    
    def validate_file_with_ts(self, file_path: Path, max_age_sec: float = 300.0) -> ValidationResult:
        """
        Validate file exists, has valid JSON, contains 'ts' field, and is within age threshold
        
        Args:
            file_path: Path to file to validate
            max_age_sec: Maximum allowed age in seconds
            
        Returns:
            ValidationResult with validation status and details
        """
        try:
            # Check file existence
            if not file_path.exists():
                return ValidationResult(
                    is_valid=False,
                    age_sec=float('inf'),
                    error_msg=f"file not found: {file_path}",
                    details={"path": str(file_path), "exists": False}
                )
            
            # Read and parse JSON
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except json.JSONDecodeError as e:
                return ValidationResult(
                    is_valid=False,
                    age_sec=float('inf'),
                    error_msg=f"invalid JSON: {e}",
                    details={"path": str(file_path), "json_error": str(e)}
                )
            except Exception as e:
                return ValidationResult(
                    is_valid=False,
                    age_sec=float('inf'),
                    error_msg=f"read error: {e}",
                    details={"path": str(file_path), "read_error": str(e)}
                )
            
            # Check for 'ts' field
            if 'ts' not in data:
                return ValidationResult(
                    is_valid=False,
                    age_sec=float('inf'),
                    error_msg="missing 'ts' field",
                    details={"path": str(file_path), "fields": list(data.keys())}
                )
            
            # Validate timestamp
            ts_value = data['ts']
            if not isinstance(ts_value, (int, float)):
                return ValidationResult(
                    is_valid=False,
                    age_sec=float('inf'),
                    error_msg=f"invalid 'ts' type: {type(ts_value)}",
                    details={"path": str(file_path), "ts_value": ts_value, "ts_type": str(type(ts_value))}
                )
            
            if ts_value <= 0:
                return ValidationResult(
                    is_valid=False,
                    age_sec=float('inf'),
                    error_msg=f"invalid 'ts' value: {ts_value}",
                    details={"path": str(file_path), "ts_value": ts_value}
                )
            
            # Calculate age
            age_sec = self.current_time - ts_value
            
            # Check age threshold
            if age_sec > max_age_sec:
                return ValidationResult(
                    is_valid=False,
                    age_sec=age_sec,
                    error_msg=f"age {age_sec:.1f}s exceeds threshold {max_age_sec}s",
                    details={
                        "path": str(file_path),
                        "ts_value": ts_value,
                        "current_time": self.current_time,
                        "max_age_sec": max_age_sec
                    }
                )
            
            # Valid
            return ValidationResult(
                is_valid=True,
                age_sec=age_sec,
                details={
                    "path": str(file_path),
                    "ts_value": ts_value,
                    "current_time": self.current_time,
                    "fields": list(data.keys())
                }
            )
            
        except Exception as e:
            return ValidationResult(
                is_valid=False,
                age_sec=float('inf'),
                error_msg=f"validation error: {e}",
                details={"path": str(file_path), "exception": str(e)}
            )
    
    def validate_uds_heartbeat(self, uds_path: Path) -> ValidationResult:
        """Validate UDS heartbeat file"""
        result = self.validate_file_with_ts(uds_path, max_age_sec=60.0)
        
        if not result.is_valid:
            return result
        
        # Additional UDS-specific validation
        try:
            with open(uds_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Check for source field
            if 'source' not in data:
                return ValidationResult(
                    is_valid=False,
                    age_sec=result.age_sec,
                    error_msg="missing 'source' field in UDS heartbeat",
                    details=result.details
                )
            
            # Check for service_name field
            if 'service_name' not in data:
                return ValidationResult(
                    is_valid=False,
                    age_sec=result.age_sec,
                    error_msg="missing 'service_name' field in UDS heartbeat",
                    details=result.details
                )
            
            return result
            
        except Exception as e:
            return ValidationResult(
                is_valid=False,
                age_sec=result.age_sec,
                error_msg=f"UDS validation error: {e}",
                details=result.details
            )
    
    def validate_account_snapshot(self, account_path: Path) -> ValidationResult:
        """Validate account snapshot file"""
        result = self.validate_file_with_ts(account_path, max_age_sec=180.0)
        
        if not result.is_valid:
            return result
        
        # Additional account-specific validation
        try:
            with open(account_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Check for required account fields
            required_fields = ['balances', 'positions']
            missing_fields = [field for field in required_fields if field not in data]
            
            if missing_fields:
                return ValidationResult(
                    is_valid=False,
                    age_sec=result.age_sec,
                    error_msg=f"missing account fields: {missing_fields}",
                    details=result.details
                )
            
            return result
            
        except Exception as e:
            return ValidationResult(
                is_valid=False,
                age_sec=result.age_sec,
                error_msg=f"account validation error: {e}",
                details=result.details
            )


def validate_file_schema(file_path: Path, max_age_sec: float = 300.0) -> ValidationResult:
    """Convenience function to validate any file with timestamp"""
    validator = SchemaValidator()
    return validator.validate_file_with_ts(file_path, max_age_sec)


def validate_uds_schema(uds_path: Path) -> ValidationResult:
    """Convenience function to validate UDS heartbeat"""
    validator = SchemaValidator()
    return validator.validate_uds_heartbeat(uds_path)


def validate_account_schema(account_path: Path) -> ValidationResult:
    """Convenience function to validate account snapshot"""
    validator = SchemaValidator()
    return validator.validate_account_snapshot(account_path)


def get_file_age(file_path: Path) -> float:
    """Get file age in seconds (simple file mtime check)"""
    try:
        if not file_path.exists():
            return float('inf')
        
        mtime = file_path.stat().st_mtime
        return time.time() - mtime
        
    except Exception:
        return float('inf')


def log_validation_result(service_name: str, result: ValidationResult, file_type: str = "file"):
    """Log validation result with appropriate level"""
    if result.is_valid:
        print(f"[{service_name}] {file_type.upper()} VALID: {result}", flush=True)
    else:
        print(f"[{service_name}] {file_type.upper()} INVALID: {result}", flush=True)
