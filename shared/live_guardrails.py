#!/usr/bin/env python3
"""
LIVE Mode Guardrails
Critical safety checks to prevent test flags on LIVE trading
"""

import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Tuple


class LiveGuardrails:
    """LIVE mode safety guardrails"""
    
    def __init__(self):
        self.is_live = os.getenv("BINANCE_USE_TESTNET", "true").lower() == "false"
        self.test_flags = [
            "TEST_FORCE_SIGNAL",
            "RISK_TEST_MODE", 
            "TEST_FORCE_DAILY_LOSS_BREACH",
            "TEST_FORCE_FILTER_VIOLATION"
        ]
    
    def check_test_flags(self) -> Tuple[bool, str]:
        """Check if any test flags are enabled on LIVE"""
        if not self.is_live:
            return True, "TESTNET mode - test flags allowed"
        
        enabled_flags = []
        for flag in self.test_flags:
            if os.getenv(flag, "false").lower() == "true":
                enabled_flags.append(flag)
        
        if enabled_flags:
            error_msg = f"LIVE MODE: Test flags are ENABLED and must be DISABLED: {', '.join(enabled_flags)}"
            return False, error_msg
        
        return True, "LIVE mode - all test flags disabled"
    
    def check_preflight_conditions(self) -> Tuple[bool, str]:
        """Pre-flight go/no-go check for LIVE trading"""
        if not self.is_live:
            return True, "TESTNET mode - preflight checks skipped"
        
        checks = []
        
        # 1. Health file freshness (≤ 15s)
        health_file = Path("shared_data/health.json")
        if health_file.exists():
            health_age = time.time() - health_file.stat().st_mtime
            if health_age > 15:
                checks.append(f"Health file stale ({health_age:.1f}s > 15s)")
        else:
            checks.append("Health file missing")
        
        # 2. All required components GREEN status
        try:
            with open(health_file, "r", encoding="utf-8") as f:
                import json
                health_data = json.load(f)
                components = health_data.get("components", {})
                
                required_components = ["feeder", "uds", "trader", "ares", "autoheal"]
                for component in required_components:
                    comp_data = components.get(component, {})
                    status = comp_data.get("status")
                    last_ts = comp_data.get("last_ts", 0)
                    age = time.time() - last_ts if last_ts > 0 else float('inf')
                    
                    if status != "GREEN":
                        checks.append(f"{component.upper()} not GREEN: {status}")
                    elif age > 300:  # 5 minutes TTL for all components
                        checks.append(f"{component.upper()} stale ({age:.1f}s > 300s)")
                        
        except Exception as e:
            checks.append(f"Health data read error: {e}")
        
        # 3. Circuit breaker inactive
        cb_file = Path("shared_data/circuit_breaker.json")
        if cb_file.exists():
            try:
                with open(cb_file, "r", encoding="utf-8") as f:
                    import json
                    cb_data = json.load(f)
                    if cb_data.get("active", False):
                        reason = cb_data.get("reason", "unknown")
                        checks.append(f"Circuit breaker ACTIVE: {reason}")
            except Exception as e:
                checks.append(f"Circuit breaker read error: {e}")
        
        # 4. Account snapshot freshness and balance check
        account_file = Path("shared_data/account_snapshot.json")
        if account_file.exists():
            try:
                # Check account snapshot freshness
                account_age = time.time() - account_file.stat().st_mtime
                account_ttl = int(os.getenv("ACCOUNT_SNAPSHOT_TTL_SEC", "180"))
                if account_age > account_ttl:
                    checks.append(f"Account snapshot stale ({account_age:.1f}s > {account_ttl}s TTL)")
                
                with open(account_file, "r", encoding="utf-8") as f:
                    import json
                    account_data = json.load(f)
                    free_usdt = account_data.get("free", {}).get("USDT", 0)
                    
                    # Get risk profile settings
                    try:
                        from shared.risk_profile_manager import \
                            get_risk_profile_manager
                        profile_manager = get_risk_profile_manager()
                        max_concurrent = profile_manager.get_max_concurrent()
                        min_notional = float(os.getenv("MIN_NOTIONAL_USDT", "10"))
                        
                        # Calculate required balance: min_notional × (max_concurrent + 1)
                        required_balance = min_notional * (max_concurrent + 1)
                        
                        if free_usdt < required_balance:
                            checks.append(f"Free balance insufficient: ${free_usdt:.2f} < ${required_balance:.2f} (min_notional × (max_concurrent + 1))")
                    except Exception as e:
                        # Fallback to simple check
                        min_balance = float(os.getenv("MIN_FREE_BALANCE_USDT", "100"))
                        if free_usdt < min_balance:
                            checks.append(f"Free balance too low: ${free_usdt:.2f} < ${min_balance:.2f}")
                            
            except Exception as e:
                checks.append(f"Account data read error: {e}")
        else:
            checks.append(f"Account snapshot missing (required for LIVE trading)")
        
        if checks:
            return False, f"Pre-flight checks failed: {'; '.join(checks)}"
        
        return True, "Pre-flight checks passed"
    
    def enforce_live_safety(self) -> bool:
        """Enforce all LIVE safety checks"""
        print("🔒 LIVE Mode Guardrails Check")
        print("=" * 40)
        
        # Check test flags
        flags_ok, flags_msg = self.check_test_flags()
        print(f"Test Flags: {'✅' if flags_ok else '❌'} {flags_msg}")
        
        if not flags_ok:
            print(f"\n🚨 CRITICAL ERROR: {flags_msg}")
            print("System will NOT start in LIVE mode with test flags enabled.")
            return False
        
        # Check pre-flight conditions
        preflight_ok, preflight_msg = self.check_preflight_conditions()
        print(f"Pre-flight: {'✅' if preflight_ok else '❌'} {preflight_msg}")
        
        if not preflight_ok:
            print(f"\n🚨 CRITICAL ERROR: {preflight_msg}")
            print("System will NOT start in LIVE mode with failed pre-flight checks.")
            return False
        
        print("\n✅ All LIVE safety checks passed")
        return True
    
    def get_safety_status(self) -> Dict[str, Any]:
        """Get current safety status for monitoring"""
        flags_ok, flags_msg = self.check_test_flags()
        preflight_ok, preflight_msg = self.check_preflight_conditions()
        
        return {
            "is_live": self.is_live,
            "test_flags_ok": flags_ok,
            "test_flags_message": flags_msg,
            "preflight_ok": preflight_ok,
            "preflight_message": preflight_msg,
            "safe_to_trade": flags_ok and (preflight_ok or not self.is_live),
            "timestamp": time.time()
        }

def enforce_live_guardrails() -> bool:
    """Main function to enforce LIVE guardrails"""
    guardrails = LiveGuardrails()
    return guardrails.enforce_live_safety()

def get_live_safety_status() -> Dict[str, Any]:
    """Get LIVE safety status"""
    guardrails = LiveGuardrails()
    return guardrails.get_safety_status()

if __name__ == "__main__":
    # Command line interface
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        status = get_live_safety_status()
        print("LIVE Safety Status:")
        for key, value in status.items():
            print(f"  {key}: {value}")
    else:
        success = enforce_live_guardrails()
        sys.exit(0 if success else 1)
