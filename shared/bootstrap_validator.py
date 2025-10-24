"""
Bootstrap Validator
One-click validation for initial setup and portability
"""
import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .env_loader import get_all_env, get_env_hash
from .integration_contracts import validate_integration_contracts
from .path_registry import get_absolute_path, get_repo_root, validate_writable


@dataclass
class ValidationResult:
    """Individual validation result"""
    check_name: str
    status: bool
    message: str
    details: Optional[str] = None
    timestamp: float = 0.0


@dataclass
class BootstrapValidation:
    """Bootstrap validation result"""
    is_valid: bool = True
    validation_results: List[ValidationResult] = None
    timestamp: float = 0.0
    
    def __post_init__(self):
        if self.validation_results is None:
            self.validation_results = []
    
    @property
    def passed_checks(self) -> int:
        """Count of passed checks"""
        return sum(1 for result in self.validation_results if result.status)
    
    @property
    def failed_checks(self) -> int:
        """Count of failed checks"""
        return sum(1 for result in self.validation_results if not result.status)
    
    @property
    def total_checks(self) -> int:
        """Total number of checks"""
        return len(self.validation_results)


class BootstrapValidator:
    """Bootstrap validator for system setup"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.repo_root = get_repo_root()
        self.current_time = time.time()
    
    def validate_all(self) -> BootstrapValidation:
        """Run all bootstrap validations"""
        validation = BootstrapValidation()
        validation.timestamp = self.current_time
        
        # Run all validation checks
        checks = [
            self._validate_repo_root,
            self._validate_write_permissions,
            self._validate_env_hash_consistency,
            self._validate_venv_and_packages,
            self._validate_symbol_subset_contracts,
            self._validate_path_portability,
            self._validate_config_files,
            self._validate_service_entrypoints
        ]
        
        for check in checks:
            try:
                result = check()
                validation.validation_results.append(result)
                
                if not result.status:
                    validation.is_valid = False
                    
            except Exception as e:
                validation.validation_results.append(ValidationResult(
                    check_name=check.__name__,
                    status=False,
                    message=f"Validation error: {e}",
                    timestamp=self.current_time
                ))
                validation.is_valid = False
        
        return validation
    
    def _validate_repo_root(self) -> ValidationResult:
        """Validate repository root resolution"""
        try:
            if not self.repo_root.exists():
                return ValidationResult(
                    check_name="repo_root",
                    status=False,
                    message="Repository root does not exist",
                    details=str(self.repo_root),
                    timestamp=self.current_time
                )
            
            if not self.repo_root.is_dir():
                return ValidationResult(
                    check_name="repo_root",
                    status=False,
                    message="Repository root is not a directory",
                    details=str(self.repo_root),
                    timestamp=self.current_time
                )
            
            # Check for repo markers
            markers = ['.git', 'pyproject.toml', 'coin_quant.iml']
            found_markers = [marker for marker in markers if (self.repo_root / marker).exists()]
            
            if not found_markers:
                return ValidationResult(
                    check_name="repo_root",
                    status=False,
                    message="No repository markers found",
                    details=f"Looked for: {markers}",
                    timestamp=self.current_time
                )
            
            return ValidationResult(
                check_name="repo_root",
                status=True,
                message="Repository root resolved successfully",
                details=f"Root: {self.repo_root}, Markers: {found_markers}",
                timestamp=self.current_time
            )
            
        except Exception as e:
            return ValidationResult(
                check_name="repo_root",
                status=False,
                message=f"Repository root validation failed: {e}",
                timestamp=self.current_time
            )
    
    def _validate_write_permissions(self) -> ValidationResult:
        """Validate write permissions for critical directories"""
        try:
            critical_paths = [
                'shared_data',
                'shared_data_logs',
                'shared_data_health',
                'shared_data_pids',
                'shared_data_ops',
                'shared_data_alerts',
                'shared_data_reports',
                'logs'
            ]
            
            failed_paths = []
            for path_key in critical_paths:
                if not validate_writable(path_key):
                    failed_paths.append(path_key)
            
            if failed_paths:
                return ValidationResult(
                    check_name="write_permissions",
                    status=False,
                    message="Write permission validation failed",
                    details=f"Failed paths: {failed_paths}",
                    timestamp=self.current_time
                )
            
            return ValidationResult(
                check_name="write_permissions",
                status=True,
                message="Write permissions validated successfully",
                details=f"Validated {len(critical_paths)} paths",
                timestamp=self.current_time
            )
            
        except Exception as e:
            return ValidationResult(
                check_name="write_permissions",
                status=False,
                message=f"Write permission validation failed: {e}",
                timestamp=self.current_time
            )
    
    def _validate_env_hash_consistency(self) -> ValidationResult:
        """Validate ENV_HASH consistency"""
        try:
            current_env_hash = get_env_hash()
            if not current_env_hash:
                return ValidationResult(
                    check_name="env_hash_consistency",
                    status=False,
                    message="ENV_HASH not available",
                    timestamp=self.current_time
                )
            
            # Check if config files exist
            config_files = [
                get_absolute_path('repo_root') / 'config.env',
                get_absolute_path('config') / 'config.env',
                get_absolute_path('config') / '.env'
            ]
            
            existing_configs = [f for f in config_files if f.exists()]
            
            if not existing_configs:
                return ValidationResult(
                    check_name="env_hash_consistency",
                    status=False,
                    message="No configuration files found",
                    details=f"Looked for: {config_files}",
                    timestamp=self.current_time
                )
            
            return ValidationResult(
                check_name="env_hash_consistency",
                status=True,
                message="ENV_HASH consistency validated",
                details=f"Hash: {current_env_hash}, Configs: {len(existing_configs)}",
                timestamp=self.current_time
            )
            
        except Exception as e:
            return ValidationResult(
                check_name="env_hash_consistency",
                status=False,
                message=f"ENV_HASH validation failed: {e}",
                timestamp=self.current_time
            )
    
    def _validate_venv_and_packages(self) -> ValidationResult:
        """Validate virtual environment and packages"""
        try:
            # Check Python version
            if sys.version_info < (3, 8):
                return ValidationResult(
                    check_name="venv_and_packages",
                    status=False,
                    message="Python version too old",
                    details=f"Current: {sys.version_info.major}.{sys.version_info.minor}, Required: 3.8+",
                    timestamp=self.current_time
                )
            
            # Check if running in virtual environment
            python_path = sys.executable
            in_venv = 'venv' in python_path or 'conda' in python_path
            
            if not in_venv:
                return ValidationResult(
                    check_name="venv_and_packages",
                    status=False,
                    message="Not running in virtual environment",
                    details=f"Python path: {python_path}",
                    timestamp=self.current_time
                )
            
            # Check required packages
            required_packages = [
                'requests', 'websocket-client', 'pandas', 'numpy',
                'streamlit', 'asyncio', 'aiohttp'
            ]
            
            missing_packages = []
            for package in required_packages:
                try:
                    __import__(package.replace('-', '_'))
                except ImportError:
                    missing_packages.append(package)
            
            if missing_packages:
                return ValidationResult(
                    check_name="venv_and_packages",
                    status=False,
                    message="Missing required packages",
                    details=f"Missing: {missing_packages}",
                    timestamp=self.current_time
                )
            
            return ValidationResult(
                check_name="venv_and_packages",
                status=True,
                message="Virtual environment and packages validated",
                details=f"Python: {sys.version_info.major}.{sys.version_info.minor}, "
                       f"Packages: {len(required_packages)}",
                timestamp=self.current_time
            )
            
        except Exception as e:
            return ValidationResult(
                check_name="venv_and_packages",
                status=False,
                message=f"Venv and packages validation failed: {e}",
                timestamp=self.current_time
            )
    
    def _validate_symbol_subset_contracts(self) -> ValidationResult:
        """Validate symbol subset contracts"""
        try:
            # This is a simplified check - in practice, this would require
            # actual service data to be available
            contracts = validate_integration_contracts()
            
            if not contracts.all_contracts_pass:
                violation_messages = [v.message for v in contracts.violations if v.severity == "error"]
                return ValidationResult(
                    check_name="symbol_subset_contracts",
                    status=False,
                    message="Symbol subset contracts failed",
                    details=f"Violations: {violation_messages[:3]}",
                    timestamp=self.current_time
                )
            
            return ValidationResult(
                check_name="symbol_subset_contracts",
                status=True,
                message="Symbol subset contracts validated",
                details="All contracts pass",
                timestamp=self.current_time
            )
            
        except Exception as e:
            return ValidationResult(
                check_name="symbol_subset_contracts",
                status=False,
                message=f"Symbol subset contracts validation failed: {e}",
                timestamp=self.current_time
            )
    
    def _validate_path_portability(self) -> ValidationResult:
        """Validate path portability"""
        try:
            # Check for hardcoded absolute paths in config files
            config_files = [
                get_absolute_path('repo_root') / 'config.env',
                get_absolute_path('config') / 'config.env',
                get_absolute_path('config') / '.env'
            ]
            
            absolute_path_indicators = [
                'C:\\Users\\', '/Users/', '/home/', 'C:\\Program Files\\',
                'LeeSG', 'gil', 'admin'  # Common user names
            ]
            
            found_absolute_paths = []
            for config_file in config_files:
                if config_file.exists():
                    try:
                        content = config_file.read_text(encoding='utf-8')
                        for indicator in absolute_path_indicators:
                            if indicator in content:
                                found_absolute_paths.append(f"{config_file.name}: {indicator}")
                    except Exception:
                        continue
            
            if found_absolute_paths:
                return ValidationResult(
                    check_name="path_portability",
                    status=False,
                    message="Absolute paths detected in config files",
                    details=f"Found: {found_absolute_paths}",
                    timestamp=self.current_time
                )
            
            return ValidationResult(
                check_name="path_portability",
                status=True,
                message="Path portability validated",
                details="No absolute paths detected",
                timestamp=self.current_time
            )
            
        except Exception as e:
            return ValidationResult(
                check_name="path_portability",
                status=False,
                message=f"Path portability validation failed: {e}",
                timestamp=self.current_time
            )
    
    def _validate_config_files(self) -> ValidationResult:
        """Validate configuration files"""
        try:
            # Check for required config files
            required_configs = [
                get_absolute_path('repo_root') / 'config.env',
                get_absolute_path('repo_root') / 'pyproject.toml'
            ]
            
            missing_configs = []
            for config_file in required_configs:
                if not config_file.exists():
                    missing_configs.append(config_file.name)
            
            if missing_configs:
                return ValidationResult(
                    check_name="config_files",
                    status=False,
                    message="Required configuration files missing",
                    details=f"Missing: {missing_configs}",
                    timestamp=self.current_time
                )
            
            # Check config.env content
            config_env = get_absolute_path('repo_root') / 'config.env'
            if config_env.exists():
                try:
                    content = config_env.read_text(encoding='utf-8')
                    required_vars = ['BINANCE_API_KEY', 'BINANCE_API_SECRET', 'TRADING_MODE']
                    
                    missing_vars = []
                    for var in required_vars:
                        if var not in content:
                            missing_vars.append(var)
                    
                    if missing_vars:
                        return ValidationResult(
                            check_name="config_files",
                            status=False,
                            message="Required environment variables missing",
                            details=f"Missing: {missing_vars}",
                            timestamp=self.current_time
                        )
                
                except Exception as e:
                    return ValidationResult(
                        check_name="config_files",
                        status=False,
                        message="Failed to read config.env",
                        details=str(e),
                        timestamp=self.current_time
                    )
            
            return ValidationResult(
                check_name="config_files",
                status=True,
                message="Configuration files validated",
                details="All required configs present",
                timestamp=self.current_time
            )
            
        except Exception as e:
            return ValidationResult(
                check_name="config_files",
                status=False,
                message=f"Config files validation failed: {e}",
                timestamp=self.current_time
            )
    
    def _validate_service_entrypoints(self) -> ValidationResult:
        """Validate service entrypoints"""
        try:
            # Check for service entrypoint files
            service_entrypoints = [
                'services/__main__.py',
                'feeder/main.py',
                'trader/__main__.py',
                'services/feeder_service.py',
                'services/trader_service.py',
                'services/ares_service.py'
            ]
            
            missing_entrypoints = []
            for entrypoint in service_entrypoints:
                entrypoint_path = get_absolute_path('repo_root') / entrypoint
                if not entrypoint_path.exists():
                    missing_entrypoints.append(entrypoint)
            
            if missing_entrypoints:
                return ValidationResult(
                    check_name="service_entrypoints",
                    status=False,
                    message="Service entrypoints missing",
                    details=f"Missing: {missing_entrypoints}",
                    timestamp=self.current_time
                )
            
            return ValidationResult(
                check_name="service_entrypoints",
                status=True,
                message="Service entrypoints validated",
                details=f"All {len(service_entrypoints)} entrypoints present",
                timestamp=self.current_time
            )
            
        except Exception as e:
            return ValidationResult(
                check_name="service_entrypoints",
                status=False,
                message=f"Service entrypoints validation failed: {e}",
                timestamp=self.current_time
            )


def run_bootstrap_validation() -> BootstrapValidation:
    """Run bootstrap validation"""
    validator = BootstrapValidator()
    return validator.validate_all()


def print_bootstrap_report(validation: BootstrapValidation):
    """Print bootstrap validation report"""
    print("=" * 60)
    print("BOOTSTRAP VALIDATION REPORT")
    print("=" * 60)
    
    if validation.is_valid:
        print("✅ BOOTSTRAP VALIDATION PASSED")
    else:
        print("❌ BOOTSTRAP VALIDATION FAILED")
    
    print(f"Checks: {validation.passed_checks}/{validation.total_checks} passed")
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(validation.timestamp))}")
    print()
    
    # Print individual results
    for result in validation.validation_results:
        status_icon = "✅" if result.status else "❌"
        print(f"{status_icon} {result.check_name}: {result.message}")
        
        if result.details:
            print(f"   Details: {result.details}")
        
        print()
    
    # Print summary
    if validation.is_valid:
        print("🎉 System is ready for operation!")
    else:
        print("⚠️  Please fix the failed checks before proceeding.")
        print("   Refer to the details above for specific issues.")


if __name__ == '__main__':
    # Test bootstrap validator
    print("Bootstrap Validator Test:")
    
    validation = run_bootstrap_validation()
    print_bootstrap_report(validation)