"""
System Startup Manager
Initializes all preventive patches and watchdogs.
"""
import time


def start_preventive_patches():
    """Start all preventive patches and watchdogs"""
    print("[STARTUP] Starting preventive patches...")
    
    try:
        # Start Account Freshness Watchdog
        from shared.account_freshness_watchdog import get_account_watchdog
        account_watchdog = get_account_watchdog()
        account_watchdog.start()
        print("[STARTUP] ✅ Account Freshness Watchdog started")
        
        # Start Memory Watchdog
        from shared.memory_watchdog import get_memory_watchdog
        memory_watchdog = get_memory_watchdog()
        memory_watchdog.start()
        print("[STARTUP] ✅ Memory Watchdog started")
        
        # Initialize ARES Data Manager (run daily purge if needed)
        from shared.ares_data_manager import get_ares_manager
        ares_manager = get_ares_manager()
        purged, count = ares_manager.run_daily_purge_if_needed()
        if purged:
            print(f"[STARTUP] ✅ ARES Data Manager purged {count} old files")
        else:
            print("[STARTUP] ✅ ARES Data Manager initialized")
        
        # Initialize Pre-trade Health Gate
        from shared.pretrade_health_gate import get_health_gate
        get_health_gate()
        print("[STARTUP] ✅ Pre-trade Health Gate initialized")
        
        # Initialize WebSocket Connection Manager
        from shared.websocket_connection_manager import get_connection_manager
        get_connection_manager()
        print("[STARTUP] ✅ WebSocket Connection Manager initialized")
        
        print("[STARTUP] 🎯 All preventive patches started successfully")
        return True
        
    except Exception as e:
        print(f"[STARTUP] ❌ Failed to start preventive patches: {e}")
        return False


def stop_preventive_patches():
    """Stop all preventive patches and watchdogs"""
    print("[SHUTDOWN] Stopping preventive patches...")
    
    try:
        # Stop Account Freshness Watchdog
        from shared.account_freshness_watchdog import get_account_watchdog
        account_watchdog = get_account_watchdog()
        account_watchdog.stop()
        print("[SHUTDOWN] ✅ Account Freshness Watchdog stopped")
        
        # Stop Memory Watchdog
        from shared.memory_watchdog import get_memory_watchdog
        memory_watchdog = get_memory_watchdog()
        memory_watchdog.stop()
        print("[SHUTDOWN] ✅ Memory Watchdog stopped")
        
        print("[SHUTDOWN] 🎯 All preventive patches stopped successfully")
        return True
        
    except Exception as e:
        print(f"[SHUTDOWN] ❌ Failed to stop preventive patches: {e}")
        return False


def get_system_status():
    """Get overall system status from all patches"""
    system_status = {
        "timestamp": time.time(),
        "patches": {}
    }
    
    try:
        # Account Freshness Watchdog status
        from shared.account_freshness_watchdog import get_account_watchdog
        account_watchdog = get_account_watchdog()
        system_status["patches"]["account_watchdog"] = account_watchdog.get_status()
        
        # Memory Watchdog status
        from shared.memory_watchdog import get_memory_watchdog
        memory_watchdog = get_memory_watchdog()
        system_status["patches"]["memory_watchdog"] = memory_watchdog.get_status()
        
        # ARES Data Manager status
        from shared.ares_data_manager import get_ares_manager
        ares_manager = get_ares_manager()
        system_status["patches"]["ares_manager"] = ares_manager.get_status()
        
        # Pre-trade Health Gate status
        from shared.pretrade_health_gate import get_health_gate
        health_gate = get_health_gate()
        system_status["patches"]["health_gate"] = health_gate.get_gate_status()
        
    except Exception as e:
        system_status["error"] = str(e)
    
    return system_status


if __name__ == "__main__":
    # Test startup
    if start_preventive_patches():
        print("\n[TEST] System status:")
        system_status = get_system_status()
        for patch_name, patch_status in system_status["patches"].items():
            print(f"  {patch_name}: {patch_status}")
        
        print("\n[TEST] Stopping...")
        stop_preventive_patches()
    else:
        print("[TEST] Failed to start preventive patches")
