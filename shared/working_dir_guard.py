#!/usr/bin/env python3
"""
Working Directory Guard
Validates CQ_ROOT and logs all critical paths on service startup
"""
import os
import sys
import time
from pathlib import Path
from typing import Dict, Any
from .path_registry import get_cq_root, log_paths, validate_cq_root, get_all_paths


class WorkingDirectoryGuard:
    """Working directory validation and path logging"""
    
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.cq_root = get_cq_root()
        self.cwd = Path.cwd()
        self.start_time = time.time()
        
        # Validate and log
        self._validate_environment()
        self._log_startup_info()
    
    def _validate_environment(self):
        """Validate environment setup"""
        # Check CQ_ROOT structure
        required_files = ["run_dashboard.ps1", "shared", "shared_data"]
        missing_files = []
        
        for req_file in required_files:
            if not (self.cq_root / req_file).exists():
                missing_files.append(req_file)
        
        if missing_files:
            print(f"ERROR: Missing coin_quant structure in {self.cq_root}: {missing_files}", flush=True)
            sys.exit(1)
        
        # Check working directory
        cwd_valid = validate_cq_root()
        if not cwd_valid:
            print(f"WARNING: CWD {self.cwd} is not within CQ_ROOT {self.cq_root}", flush=True)
            print("Continuing anyway since paths are absolute...", flush=True)
    
    def _log_startup_info(self):
        """Log comprehensive startup information"""
        print("\n" + "=" * 80, flush=True)
        print(f"WORKING DIRECTORY GUARD - {self.service_name.upper()}", flush=True)
        print("=" * 80, flush=True)
        
        # Basic info
        print(f"Service Name: {self.service_name}", flush=True)
        print(f"Start Time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.start_time))}", flush=True)
        print(f"CQ_ROOT: {self.cq_root}", flush=True)
        print(f"Current Working Directory: {self.cwd}", flush=True)
        print(f"Python Executable: {sys.executable}", flush=True)
        print(f"Python Version: {sys.version}", flush=True)
        
        # Environment variables
        env_vars = ["CQ_ROOT", "SHARED_DATA", "TRADING_MODE", "TESTNET", "KIS_ACCOUNT"]
        print("\nEnvironment Variables:", flush=True)
        for var in env_vars:
            value = os.getenv(var, "NOT_SET")
            print(f"  {var}: {value}", flush=True)
        
        # Path validation
        print("\nPath Validation:", flush=True)
        paths = get_all_paths()
        for key, path in paths.items():
            exists = "✓ EXISTS" if path.exists() else "✗ MISSING"
            print(f"  {key:25s}: {exists} {path}", flush=True)
        
        # Critical path checks
        print("\nCritical Path Checks:", flush=True)
        critical_paths = [
            ("HEALTH_UDS", "UDS heartbeat file"),
            ("DATABUS_SNAPSHOT", "Databus snapshot"),
            ("ACCOUNT_SNAPSHOT", "Account snapshot"),
            ("HEALTH", "Main health file"),
        ]
        
        for path_key, description in critical_paths:
            path = paths[path_key]
            exists = path.exists()
            age = "N/A"
            
            if exists:
                try:
                    mtime = path.stat().st_mtime
                    age = f"{time.time() - mtime:.1f}s"
                except:
                    age = "ERROR"
            
            status = "✓" if exists else "✗"
            print(f"  {status} {description:20s}: {age:>8s} {path}", flush=True)
        
        print("=" * 80, flush=True)
        print(f"{self.service_name.upper()} STARTUP COMPLETE", flush=True)
        print("=" * 80 + "\n", flush=True)


def initialize_working_dir_guard(service_name: str) -> WorkingDirectoryGuard:
    """Initialize working directory guard for a service"""
    return WorkingDirectoryGuard(service_name)
