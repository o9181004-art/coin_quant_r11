#!/usr/bin/env python3
"""
Green Gate - Check if services are GREEN before full rendering
========================================
Provides lightweight health check for UI gating.

Usage:
    from shared.green_gate import check_services_green, get_service_status_summary
    
    if check_services_green():
        render_full_dashboard()
    else:
        render_skeleton_dashboard()
"""

import json
import time
from pathlib import Path
from typing import Dict, Tuple


def check_services_green(require_both: bool = True, max_age_sec: float = 10.0, check_snapshots: bool = False) -> bool:
    """
    Check if Feeder and/or Trader are GREEN.
    
    Args:
        require_both: If True, both must be GREEN. If False, at least one must be GREEN.
        max_age_sec: Maximum acceptable age for health data (default: 10s)
        check_snapshots: If True, also check that DataBus and account snapshots are fresh (≤120s)
    
    Returns:
        True if service(s) are GREEN and fresh (and snapshots fresh if requested), False otherwise
    """
    health_file = Path("shared_data/health.json")
    
    if not health_file.exists():
        return False
    
    try:
        # Read health data
        with open(health_file, 'r', encoding='utf-8') as f:
            health_data = json.load(f)
        
        # Check health data age
        health_age = time.time() - health_data.get('timestamp', 0)
        if health_age > max_age_sec:
            return False
        
        # Get component statuses
        components = health_data.get('components', {})
        
        feeder_status = components.get('feeder', {})
        trader_status = components.get('trader', {})
        
        # Check if GREEN and fresh
        current_time = time.time()
        
        feeder_green = (
            feeder_status.get('status') == 'GREEN' and
            (current_time - feeder_status.get('last_ts', 0)) <= 5.0  # FEEDER_TTL
        )
        
        trader_green = (
            trader_status.get('status') == 'GREEN' and
            (current_time - trader_status.get('last_ts', 0)) <= 60.0  # TRADER_TTL
        )
        
        services_green = (feeder_green and trader_green) if require_both else (feeder_green or trader_green)
        
        # If snapshots check is requested, verify freshness
        if check_snapshots and services_green:
            # Check DataBus snapshot
            databus_file = Path("shared_data/databus_snapshot.json")
            if databus_file.exists():
                databus_age = current_time - databus_file.stat().st_mtime
                if databus_age > 120.0:
                    return False
            else:
                return False  # DataBus snapshot must exist
            
            # Check account snapshot
            account_file = Path("shared_data/account_snapshot.json")
            if account_file.exists():
                account_age = current_time - account_file.stat().st_mtime
                if account_age > 120.0:
                    return False
            # Account snapshot is optional
        
        return services_green
        
    except Exception:
        return False


def get_service_status_summary() -> Dict[str, any]:
    """
    Get detailed service status summary for UI display.
    
    Returns:
        Dict with keys:
        - feeder_state: GREEN/YELLOW/RED/UNKNOWN
        - trader_state: GREEN/YELLOW/RED/UNKNOWN
        - feeder_age: Age of feeder heartbeat (seconds)
        - trader_age: Age of trader heartbeat (seconds)
        - health_age: Age of health.json file (seconds)
        - both_green: True if both services are GREEN
    """
    health_file = Path("shared_data/health.json")
    
    summary = {
        'feeder_state': 'UNKNOWN',
        'trader_state': 'UNKNOWN',
        'feeder_age': float('inf'),
        'trader_age': float('inf'),
        'health_age': float('inf'),
        'both_green': False
    }
    
    if not health_file.exists():
        return summary
    
    try:
        # Read health data
        with open(health_file, 'r', encoding='utf-8') as f:
            health_data = json.load(f)
        
        # Health file age
        summary['health_age'] = time.time() - health_data.get('timestamp', 0)
        
        # Get component statuses
        components = health_data.get('components', {})
        current_time = time.time()
        
        # Feeder
        feeder_status = components.get('feeder', {})
        summary['feeder_state'] = feeder_status.get('status', 'UNKNOWN')
        summary['feeder_age'] = current_time - feeder_status.get('last_ts', 0)
        
        # Trader
        trader_status = components.get('trader', {})
        summary['trader_state'] = trader_status.get('status', 'UNKNOWN')
        summary['trader_age'] = current_time - trader_status.get('last_ts', 0)
        
        # Both GREEN check
        summary['both_green'] = (
            summary['feeder_state'] == 'GREEN' and
            summary['trader_state'] == 'GREEN' and
            summary['feeder_age'] <= 5.0 and
            summary['trader_age'] <= 60.0
        )
        
    except Exception:
        pass
    
    return summary


def format_service_status(status: Dict) -> str:
    """
    Format service status for display.
    
    Args:
        status: Status dict from get_service_status_summary()
    
    Returns:
        Formatted status string
    """
    feeder_emoji = {
        'GREEN': '🟢',
        'YELLOW': '🟡',
        'RED': '🔴',
        'UNKNOWN': '⚪'
    }.get(status['feeder_state'], '⚪')
    
    trader_emoji = {
        'GREEN': '🟢',
        'YELLOW': '🟡',
        'RED': '🔴',
        'UNKNOWN': '⚪'
    }.get(status['trader_state'], '⚪')
    
    feeder_age_str = f"{status['feeder_age']:.1f}s" if status['feeder_age'] < float('inf') else "N/A"
    trader_age_str = f"{status['trader_age']:.1f}s" if status['trader_age'] < float('inf') else "N/A"
    
    return (
        f"{feeder_emoji} Feeder: {status['feeder_state']} (age: {feeder_age_str}) | "
        f"{trader_emoji} Trader: {status['trader_state']} (age: {trader_age_str})"
    )


if __name__ == "__main__":
    # Test
    print("Testing Green Gate...")
    
    both_green = check_services_green(require_both=True)
    print(f"Both services GREEN: {both_green}")
    
    status = get_service_status_summary()
    print(f"Status summary: {status}")
    print(f"Formatted: {format_service_status(status)}")

