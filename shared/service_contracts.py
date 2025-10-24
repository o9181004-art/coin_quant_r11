"""
Service Entrypoints & Readiness Contracts
Standardized service startup, preflight checks, and readiness validation
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

from .env_loader import get_env, get_env_hash
from .path_registry import get_absolute_path
from .io_safe import atomic_write


@dataclass
class ServiceReadiness:
    """Service readiness status"""
    service_name: str
    entrypoint_ok: bool = False
    interpreter_ok: bool = False
    venv_ok: bool = False
    packages_ok: bool = False
    rest_ping_ok: bool = False
    exchange_info_loaded: bool = False
    time_sane: bool = False
    last_rest_ok_ts: float = 0.0
    error_message: str = ""
    timestamp: float = 0.0
    
    @property
    def is_ready(self) -> bool:
        """Check if service is ready for operation"""
        return (
            self.entrypoint_ok and
            self.interpreter_ok and
            self.venv_ok and
            self.packages_ok and
            self.rest_ping_ok and
            self.exchange_info_loaded and
            self.time_sane
        )


class ServiceEntrypoint:
    """Base class for service entrypoints with preflight checks"""
    
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.env_hash = get_env_hash()
        self.start_time = time.time()
        self.readiness = ServiceReadiness(service_name=service_name)
        self.logger = logging.getLogger(f"{__name__}.{service_name}")
        
        # Log entrypoint start
        print(f"ENTRYPOINT_START module={service_name} env_hash={self.env_hash}")
    
    def log_entrypoint_ok(self):
        """Log successful entrypoint initialization"""
        self.readiness.entrypoint_ok = True
        print(f"ENTRYPOINT_OK module={self.service_name}")
    
    def validate_interpreter(self) -> bool:
        """Validate Python interpreter"""
        try:
            # Check Python version
            if sys.version_info < (3, 8):
                self.readiness.error_message = f"Python {sys.version_info.major}.{sys.version_info.minor} < 3.8 required"
                return False
            
            # Check if running in expected environment
            python_path = sys.executable
            if 'venv' not in python_path and 'conda' not in python_path:
                self.logger.warning(f"Not running in virtual environment: {python_path}")
            
            self.readiness.interpreter_ok = True
            return True
        except Exception as e:
            self.readiness.error_message = f"Interpreter validation failed: {e}"
            return False
    
    def validate_packages(self) -> bool:
        """Validate required packages"""
        try:
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
                self.readiness.error_message = f"Missing packages: {', '.join(missing_packages)}"
                return False
            
            self.readiness.packages_ok = True
            return True
        except Exception as e:
            self.readiness.error_message = f"Package validation failed: {e}"
            return False
    
    def validate_time_sanity(self) -> bool:
        """Validate system time is sane"""
        try:
            current_time = time.time()
            
            # Check if time is reasonable (not in the past, not too far in future)
            # Allow some tolerance for clock drift
            if current_time < 1600000000:  # Before 2020
                self.readiness.error_message = f"System time too old: {current_time}"
                return False
            
            if current_time > 2000000000:  # After 2033
                self.readiness.error_message = f"System time too far in future: {current_time}"
                return False
            
            self.readiness.time_sane = True
            return True
        except Exception as e:
            self.readiness.error_message = f"Time validation failed: {e}"
            return False
    
    def validate_rest_connection(self) -> bool:
        """Validate REST API connection (to be implemented by subclasses)"""
        # Base implementation - subclasses should override
        self.readiness.rest_ping_ok = True
        self.readiness.last_rest_ok_ts = time.time()
        return True
    
    def validate_exchange_info(self) -> bool:
        """Validate exchange info loading (to be implemented by subclasses)"""
        # Base implementation - subclasses should override
        self.readiness.exchange_info_loaded = True
        return True
    
    def run_preflight_checks(self) -> bool:
        """Run all preflight checks"""
        checks = [
            self.validate_interpreter,
            self.validate_packages,
            self.validate_time_sanity,
            self.validate_rest_connection,
            self.validate_exchange_info
        ]
        
        for check in checks:
            if not check():
                self.logger.error(f"Preflight check failed: {self.readiness.error_message}")
                return False
        
        self.readiness.timestamp = time.time()
        return True
    
    def save_readiness_status(self):
        """Save readiness status to file"""
        try:
            readiness_file = get_absolute_path('shared_data_health') / f"{self.service_name}_readiness.json"
            atomic_write(readiness_file, json.dumps(asdict(self.readiness), indent=2))
        except Exception as e:
            self.logger.error(f"Failed to save readiness status: {e}")


class FeederEntrypoint(ServiceEntrypoint):
    """Feeder service entrypoint"""
    
    def __init__(self):
        super().__init__("feeder")
    
    def validate_rest_connection(self) -> bool:
        """Validate Binance REST connection"""
        try:
            import requests

            # Test Binance API connectivity
            url = "https://api.binance.com/api/v3/ping"
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                self.readiness.rest_ping_ok = True
                self.readiness.last_rest_ok_ts = time.time()
                return True
            else:
                self.readiness.error_message = f"Binance API ping failed: {response.status_code}"
                return False
        except Exception as e:
            self.readiness.error_message = f"REST connection failed: {e}"
            return False
    
    def validate_exchange_info(self) -> bool:
        """Validate exchange info loading"""
        try:
            # Check if universe cache exists and is fresh
            universe_file = get_absolute_path('shared_data') / 'universe.json'
            if universe_file.exists():
                # Check file age
                file_age = time.time() - universe_file.stat().st_mtime
                if file_age < 3600:  # Less than 1 hour old
                    self.readiness.exchange_info_loaded = True
                    return True
            
            self.readiness.error_message = "Exchange info not loaded or stale"
            return False
        except Exception as e:
            self.readiness.error_message = f"Exchange info validation failed: {e}"
            return False


class TraderEntrypoint(ServiceEntrypoint):
    """Trader service entrypoint"""
    
    def __init__(self):
        super().__init__("trader")
    
    def validate_rest_connection(self) -> bool:
        """Validate Binance REST connection"""
        try:
            import requests

            # Test Binance API connectivity
            url = "https://api.binance.com/api/v3/ping"
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                self.readiness.rest_ping_ok = True
                self.readiness.last_rest_ok_ts = time.time()
                return True
            else:
                self.readiness.error_message = f"Binance API ping failed: {response.status_code}"
                return False
        except Exception as e:
            self.readiness.error_message = f"REST connection failed: {e}"
            return False
    
    def validate_exchange_info(self) -> bool:
        """Validate exchange info loading"""
        try:
            # Check if exchange info is loaded
            exchange_info_file = get_absolute_path('shared_data') / 'exchange_info.json'
            if exchange_info_file.exists():
                # Check file age
                file_age = time.time() - exchange_info_file.stat().st_mtime
                if file_age < 3600:  # Less than 1 hour old
                    self.readiness.exchange_info_loaded = True
                    return True
            
            self.readiness.error_message = "Exchange info not loaded or stale"
            return False
        except Exception as e:
            self.readiness.error_message = f"Exchange info validation failed: {e}"
            return False


class AresEntrypoint(ServiceEntrypoint):
    """ARES service entrypoint"""
    
    def __init__(self):
        super().__init__("ares")
    
    def validate_rest_connection(self) -> bool:
        """ARES doesn't need REST connection"""
        self.readiness.rest_ping_ok = True
        self.readiness.last_rest_ok_ts = time.time()
        return True
    
    def validate_exchange_info(self) -> bool:
        """ARES doesn't need exchange info"""
        self.readiness.exchange_info_loaded = True
        return True


def create_service_entrypoint(service_name: str) -> ServiceEntrypoint:
    """Factory function to create service entrypoints"""
    if service_name == "feeder":
        return FeederEntrypoint()
    elif service_name == "trader":
        return TraderEntrypoint()
    elif service_name == "ares":
        return AresEntrypoint()
    else:
        return ServiceEntrypoint(service_name)


def validate_service_readiness(service_name: str) -> ServiceReadiness:
    """Validate service readiness"""
    entrypoint = create_service_entrypoint(service_name)
    
    # Run preflight checks
    entrypoint.run_preflight_checks()
    
    # Save status
    entrypoint.save_readiness_status()
    
    return entrypoint.readiness


if __name__ == '__main__':
    # Test service entrypoints
    print("Service Entrypoints Test:")
    
    for service_name in ["feeder", "trader", "ares"]:
        print(f"\n--- {service_name.upper()} ---")
        readiness = validate_service_readiness(service_name)
        print(f"Ready: {readiness.is_ready}")
        print(f"Error: {readiness.error_message}")
        print(f"Checks: entrypoint={readiness.entrypoint_ok}, interpreter={readiness.interpreter_ok}, "
              f"packages={readiness.packages_ok}, rest={readiness.rest_ping_ok}, "
              f"exchange={readiness.exchange_info_loaded}, time={readiness.time_sane}")