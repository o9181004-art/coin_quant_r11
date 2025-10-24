#!/usr/bin/env python3
"""
Startup Diagnostics
========================================
Print compact startup diagnostic block for services.

Shows:
- Python path, venv, version
- Service name, PID
- Canonical paths (health, databus, account)
- Lock resolution result
- Exit code semantics
"""

import os
import sys
from pathlib import Path


def print_startup_diagnostics(
    service_name: str,
    lock_result: tuple = None,
    additional_info: dict = None
):
    """
    Print startup diagnostics block.
    
    Args:
        service_name: Service name (e.g., "Feeder", "Trader")
        lock_result: (success, message, exit_code) from PID lock
        additional_info: Additional info dict
    """
    print("")
    print("="*70)
    print(f" {service_name.upper()} - Startup Diagnostics")
    print("="*70)
    
    # Python info
    python_version = sys.version.split()[0]
    interpreter_path = sys.executable
    venv = 'venv_fixed' if 'venv_fixed' in interpreter_path else 'OTHER'
    
    print(f"Python: {python_version}")
    print(f"Interpreter: {interpreter_path}")
    print(f"venv: {venv}")
    print(f"PID: {os.getpid()}")
    print(f"Service: {service_name}")
    
    # Canonical paths
    print("")
    print("Canonical Paths:")
    print(f"  Health: shared_data/health.json")
    print(f"  DataBus: shared_data/databus_snapshot.json")
    print(f"  Account: shared_data/account_snapshot.json")
    
    # Lock resolution
    if lock_result:
        success, message, exit_code = lock_result
        
        print("")
        print("Lock Resolution:")
        
        if success:
            if exit_code == 0:
                print(f"  Status: FRESH (new start)")
            elif exit_code == 10:
                print(f"  Status: STALE_PURGED (auto-cleaned)")
            else:
                print(f"  Status: ACQUIRED (exit code {exit_code})")
        else:
            if exit_code == 11:
                print(f"  Status: ACTIVE_PROCESS (start aborted)")
            elif exit_code == 12:
                print(f"  Status: PERMISSION_ERROR")
            else:
                print(f"  Status: FAILED (exit code {exit_code})")
        
        print(f"  Message: {message}")
    
    # Additional info
    if additional_info:
        print("")
        print("Additional Info:")
        for key, value in additional_info.items():
            print(f"  {key}: {value}")
    
    # Exit code semantics
    print("")
    print("Exit Code Semantics:")
    print("  0 = Fresh start")
    print("  10 = Stale lock auto-purged, started OK")
    print("  11 = Active process detected, start aborted")
    print("  12 = Lock permission issue")
    
    print("="*70)
    print("")


def check_dependencies(required: list) -> dict:
    """
    Check if required dependencies are installed.
    
    Args:
        required: List of package names
    
    Returns:
        Dict with missing packages and remediation
    """
    missing = []
    
    for package in required:
        try:
            __import__(package)
        except ImportError:
            missing.append(package)
    
    if missing:
        remediation = f"pip install {' '.join(missing)}"
        
        return {
            'all_present': False,
            'missing': missing,
            'remediation': remediation
        }
    
    return {
        'all_present': True,
        'missing': [],
        'remediation': None
    }


def assert_binance_connector():
    """
    Assert binance-connector is installed for TESTNET/LIVE mode.
    
    Exits with remediation text if missing.
    """
    use_testnet = os.getenv("BINANCE_USE_TESTNET", "false").lower() == "true"
    live_enabled = os.getenv("LIVE_TRADING_ENABLED", "false").lower() == "true"
    
    if not use_testnet and not live_enabled:
        # Neither testnet nor live - skip check
        return
    
    try:
        import binance
    except ImportError:
        print("")
        print("="*70)
        print(" ERROR: Missing Dependency")
        print("="*70)
        print("")
        print("binance-connector is required for trading operations.")
        print("")
        print("Remediation:")
        print("  pip install python-binance")
        print("  or")
        print("  pip install binance-connector")
        print("")
        print("Then restart the service.")
        print("="*70)
        print("")
        sys.exit(1)


# Unit tests
if __name__ == "__main__":
    print("Testing startup diagnostics...")
    
    # Test 1: Print diagnostics
    print("\n1. Print diagnostics:")
    print_startup_diagnostics(
        service_name="TestService",
        lock_result=(True, "Lock acquired", 0),
        additional_info={'mode': 'TESTNET', 'watchlist': 10}
    )
    print("✅ Diagnostics printed")
    
    # Test 2: Check dependencies
    print("\n2. Check dependencies:")
    result = check_dependencies(['os', 'sys', 'time'])
    assert result['all_present'], "Standard modules should be present"
    print(f"✅ Dependencies check works: {result}")
    
    result2 = check_dependencies(['nonexistent_package_xyz'])
    assert not result2['all_present'], "Nonexistent should be missing"
    assert 'pip install' in result2['remediation'], "Should have remediation"
    print(f"✅ Missing detection works: {result2}")
    
    print("\n" + "="*50)
    print("All startup diagnostics tests passed! ✅")
    print("="*50)

