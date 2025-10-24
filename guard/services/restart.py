#!/usr/bin/env python3
"""
Restart Service - Windows-safe service restart handlers
Sets cwd=repo_root, env["PYTHONPATH"]=repo_root, and starts with -m
"""

import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional

from shared.paths import get_repo_root

logger = logging.getLogger(__name__)


def restart_service(service_name: str) -> bool:
    """
    Restart a service with proper environment setup
    
    Args:
        service_name: Name of service to restart (feeder, trader, ares, etc.)
        
    Returns:
        True if restart was successful
    """
    try:
        repo_root = get_repo_root()
        
        # Kill existing processes
        _kill_service_processes(service_name)
        
        # Wait a bit for cleanup
        time.sleep(2)
        
        # Start new process
        success = _start_service(service_name, repo_root)
        
        if success:
            logger.info(f"✅ {service_name} service restarted successfully")
        else:
            logger.error(f"❌ {service_name} service restart failed")
            
        return success
        
    except Exception as e:
        logger.error(f"Failed to restart {service_name}: {e}")
        return False


def _kill_service_processes(service_name: str):
    """Kill existing service processes"""
    try:
        import psutil

        # Find processes by name
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.info['cmdline']
                if cmdline and any(service_name in arg for arg in cmdline):
                    logger.info(f"Killing {service_name} process: PID {proc.info['pid']}")
                    proc.terminate()
                    proc.wait(timeout=5)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                continue
                
    except Exception as e:
        logger.error(f"Error killing {service_name} processes: {e}")


def _cleanup_stale_artifacts(service_name: str):
    """Clean up stale artifacts for service"""
    try:
        if service_name == "trader":
            # Remove stale lock files
            lock_files = [
                Path("logs/trader.lock"),
                Path("shared_data/trader.pid")
            ]
            
            for lock_file in lock_files:
                if lock_file.exists():
                    # Check if PID is alive
                    try:
                        if lock_file.name.endswith('.pid'):
                            with open(lock_file, 'r') as f:
                                pid = int(f.read().strip())
                            # Check if process is alive
                            import psutil
                            if not psutil.pid_exists(pid):
                                lock_file.unlink()
                                logger.info(f"Removed stale PID file: {lock_file}")
                        else:
                            # Remove lock files
                            lock_file.unlink()
                            logger.info(f"Removed stale lock file: {lock_file}")
                    except Exception:
                        # Remove if we can't check
                        lock_file.unlink()
                        logger.info(f"Removed stale file: {lock_file}")
    except Exception as e:
        logger.warning(f"Failed to cleanup stale artifacts: {e}")


def _validate_service_startup(service_name: str, process: subprocess.Popen) -> bool:
    """Validate that service started successfully"""
    try:
        # Wait for startup
        start_time = time.time()
        timeout = 10  # seconds
        
        for _ in range(timeout):
            time.sleep(1)
            
            # Check if process is alive
            if process.poll() is not None:
                logger.error(f"Service {service_name} exited early")
                return False
            
            # Check for ENTRYPOINT_OK and heartbeat timestamp
            if service_name == "trader":
                # Check trader health file
                trader_health_file = Path("shared_data/health/trader.json")
                if trader_health_file.exists():
                    try:
                        import json
                        with open(trader_health_file, 'r', encoding='utf-8') as f:
                            trader_health = json.load(f)
                        
                        # Check entrypoint_ok and timestamp is newer than spawn time
                        if (trader_health.get("entrypoint_ok", False) and 
                            trader_health.get("timestamp", 0) > start_time):
                            logger.info(f"Service {service_name} validated successfully")
                            return True
                    except Exception:
                        pass
            elif service_name == "feeder":
                # Check state bus file
                state_bus_file = Path("shared_data/state_bus.json")
                if state_bus_file.exists():
                    try:
                        import json
                        with open(state_bus_file, 'r', encoding='utf-8') as f:
                            state_bus = json.load(f)
                        
                        # Check timestamp is newer than spawn time
                        if state_bus.get("prices", {}).get("last_ts", 0) > start_time:
                            logger.info(f"Service {service_name} validated successfully")
                            return True
                    except Exception:
                        pass
            elif service_name == "ares":
                # Check candidates file
                candidates_file = Path("shared_data/logs/candidates.ndjson")
                if candidates_file.exists():
                    try:
                        with open(candidates_file, 'r', encoding='utf-8') as f:
                            lines = f.readlines()
                            if lines:
                                import json
                                last_candidate = json.loads(lines[-1].strip())
                                # Check timestamp is newer than spawn time
                                if last_candidate.get("timestamp", 0) > start_time:
                                    logger.info(f"Service {service_name} validated successfully")
                                    return True
                    except Exception:
                        pass
            
            # For other services, just check if process is alive
            if service_name not in ["trader", "feeder", "ares"]:
                logger.info(f"Service {service_name} validated successfully")
                return True
        
        logger.error(f"Service {service_name} failed to validate within timeout")
        return False
        
    except Exception as e:
        logger.error(f"Failed to validate service {service_name}: {e}")
        return False


def _start_service(service_name: str, repo_root: Path) -> bool:
    """Start service with proper environment"""
    try:
        # Service module mapping
        service_map = {
            "feeder": "guard.feeder",
            "trader": "guard.trader",
            "ares": "guard.optimizer.ares_service",
            "state_bus_writer": "guard.feeder.state_bus_writer",
            "filters_manager": "guard.trader.filters_manager"
        }
        
        if service_name not in service_map:
            logger.error(f"Unknown service: {service_name}")
            return False
            
        module_name = service_map[service_name]
        
        # Cleanup stale artifacts
        _cleanup_stale_artifacts(service_name)
        
        # Environment setup
        env = os.environ.copy()
        env["PYTHONPATH"] = str(repo_root)
        
        # Command to run
        cmd = [
            "python", "-m", module_name
        ]
        
        # Start process
        logger.info(f"Starting {service_name}: {' '.join(cmd)}")
        
        process = subprocess.Popen(
            cmd,
            cwd=repo_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Validate startup
        success = _validate_service_startup(service_name, process)
        
        if success:
            logger.info(f"✅ {service_name} started successfully (PID: {process.pid})")
            return True
        else:
            logger.error(f"❌ {service_name} failed to start")
            process.terminate()
            return False
            
    except Exception as e:
        logger.error(f"Error starting {service_name}: {e}")
        return False


def get_service_status(service_name: str) -> Dict[str, Any]:
    """Get service status"""
    try:
        import psutil
        
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
            try:
                cmdline = proc.info['cmdline']
                if cmdline and any(service_name in arg for arg in cmdline):
                    processes.append({
                        "pid": proc.info['pid'],
                        "name": proc.info['name'],
                        "cmdline": " ".join(cmdline),
                        "create_time": proc.info['create_time']
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
                
        return {
            "service_name": service_name,
            "running": len(processes) > 0,
            "processes": processes,
            "process_count": len(processes)
        }
        
    except Exception as e:
        logger.error(f"Error getting {service_name} status: {e}")
        return {
            "service_name": service_name,
            "running": False,
            "processes": [],
            "process_count": 0,
            "error": str(e)
        }


def restart_all_services() -> Dict[str, bool]:
    """Restart all services"""
    services = ["feeder", "trader", "ares", "state_bus_writer", "filters_manager"]
    results = {}
    
    for service in services:
        results[service] = restart_service(service)
        time.sleep(2)  # Stagger restarts
        
    return results


if __name__ == "__main__":
    # Test restart functionality
    logging.basicConfig(level=logging.INFO)
    
    # Test service status
    for service in ["feeder", "trader", "ares"]:
        status = get_service_status(service)
        print(f"{service}: {status}")
        
    # Test restart (commented out for safety)
    # restart_service("feeder")