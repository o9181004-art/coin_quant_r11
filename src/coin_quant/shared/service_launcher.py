"""
Service Launcher for Coin Quant R11 Dashboard
Provides functionality to start/stop services from the dashboard
"""

import subprocess
import sys
import time
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class ServiceLauncher:
    """Service launcher for dashboard integration"""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve()
        self.python_exe = self.project_root / "venv" / "Scripts" / "python.exe"
        self.running_processes: Dict[str, subprocess.Popen] = {}
        
        # Service configurations
        self.services = {
            "feeder": {
                "module": "coin_quant.feeder.service",
                "command": [str(self.python_exe), "-m", "coin_quant.feeder.service"]
            },
            "trader": {
                "module": "coin_quant.trader.service", 
                "command": [str(self.python_exe), "-m", "coin_quant.trader.service"]
            },
            "ares": {
                "module": "coin_quant.ares.service",
                "command": [str(self.python_exe), "-m", "coin_quant.ares.service"]
            }
        }
    
    def start_service(self, service_name: str) -> bool:
        """Start a service"""
        try:
            if service_name not in self.services:
                logger.error(f"Unknown service: {service_name}")
                return False
            
            if service_name in self.running_processes:
                logger.warning(f"Service {service_name} is already running")
                return True
            
            logger.info(f"Starting {service_name} service...")
            
            # Start the service
            process = subprocess.Popen(
                self.services[service_name]["command"],
                cwd=str(self.project_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
            )
            
            # Wait a moment and check if process started successfully
            time.sleep(2)
            if process.poll() is None:
                self.running_processes[service_name] = process
                logger.info(f"✅ {service_name} service started successfully (PID: {process.pid})")
                return True
            else:
                stdout, stderr = process.communicate()
                logger.error(f"❌ {service_name} service failed to start")
                logger.error(f"STDOUT: {stdout}")
                logger.error(f"STDERR: {stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to start {service_name} service: {e}")
            return False
    
    def stop_service(self, service_name: str) -> bool:
        """Stop a service"""
        try:
            if service_name not in self.running_processes:
                logger.warning(f"Service {service_name} is not running")
                return True
            
            process = self.running_processes[service_name]
            logger.info(f"Stopping {service_name} service (PID: {process.pid})...")
            
            # Terminate the process
            process.terminate()
            
            # Wait for graceful shutdown
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                # Force kill if graceful shutdown fails
                process.kill()
                process.wait()
            
            del self.running_processes[service_name]
            logger.info(f"✅ {service_name} service stopped successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to stop {service_name} service: {e}")
            return False
    
    def is_service_running(self, service_name: str) -> bool:
        """Check if a service is running"""
        if service_name not in self.running_processes:
            return False
        
        process = self.running_processes[service_name]
        return process.poll() is None
    
    def get_service_status(self, service_name: str) -> Dict:
        """Get service status"""
        status = {
            "running": False,
            "pid": None,
            "uptime": None
        }
        
        if service_name in self.running_processes:
            process = self.running_processes[service_name]
            if process.poll() is None:
                status["running"] = True
                status["pid"] = process.pid
                # Calculate uptime (simplified)
                status["uptime"] = "running"
        
        return status
    
    def stop_all_services(self):
        """Stop all running services"""
        for service_name in list(self.running_processes.keys()):
            self.stop_service(service_name)


def get_service_launcher() -> ServiceLauncher:
    """Get service launcher instance"""
    # Find project root
    current_path = Path(__file__).resolve()
    for _ in range(10):  # Max 10 levels up
        if (current_path / "pyproject.toml").exists() or (current_path / "src" / "coin_quant").exists():
            return ServiceLauncher(current_path)
        current_path = current_path.parent
    
    # Fallback to current directory
    return ServiceLauncher(Path.cwd())
