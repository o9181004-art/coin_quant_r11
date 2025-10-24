"""
Pre-trade Health Gate
Surgical gate that blocks orders if any critical health check fails.
"""
import json
import time
import psutil
from typing import Tuple, Dict, Any
from pathlib import Path


class PreTradeHealthGate:
    """Pre-trade health gate with strict validation"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.last_log_time = {}  # For debounced logging
        
    def check_account_freshness(self) -> Tuple[bool, str]:
        """Check if account snapshot is fresh (≤180s)"""
        snapshot_file = self.project_root / "shared_data" / "account_snapshot.json"
        
        if not snapshot_file.exists():
            return False, "ACCOUNT_MISSING: snapshot file not found"
            
        try:
            file_age = time.time() - snapshot_file.stat().st_mtime
            if file_age > 180:
                return False, f"ACCOUNT_STALE: {file_age:.1f}s > 180s limit"
            return True, f"OK ({file_age:.1f}s)"
        except Exception as e:
            return False, f"ACCOUNT_ERROR: {str(e)}"
    
    def check_trader_health(self) -> Tuple[bool, str]:
        """Check if trader service is healthy"""
        health_file = self.project_root / "shared_data" / "health.json"
        
        if not health_file.exists():
            return False, "TRADER_MISSING: health file not found"
            
        try:
            with open(health_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            trader_status = data.get("trader", {})
            if trader_status.get("status") != "OK":
                return False, f"TRADER_UNHEALTHY: {trader_status.get('status', 'unknown')}"
                
            return True, "OK"
        except Exception as e:
            return False, f"TRADER_ERROR: {str(e)}"
    
    def check_feeder_stream(self) -> Tuple[bool, str]:
        """Check if feeder stream is alive"""
        health_file = self.project_root / "shared_data" / "health.json"
        
        if not health_file.exists():
            return False, "FEEDER_MISSING: health file not found"
            
        try:
            with open(health_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            feeder_status = data.get("feeder", {})
            if feeder_status.get("status") != "OK":
                return False, f"FEEDER_UNHEALTHY: {feeder_status.get('status', 'unknown')}"
                
            return True, "OK"
        except Exception as e:
            return False, f"FEEDER_ERROR: {str(e)}"
    
    def check_memory_usage(self) -> Tuple[bool, str]:
        """Check if memory usage is acceptable (<90%)"""
        try:
            memory_percent = psutil.virtual_memory().percent
            if memory_percent >= 90:
                return False, f"MEMORY_HIGH: {memory_percent:.1f}% >= 90% limit"
            return True, f"OK ({memory_percent:.1f}%)"
        except Exception as e:
            return False, f"MEMORY_ERROR: {str(e)}"
    
    def check_all_gates(self) -> Tuple[bool, str, Dict[str, Any]]:
        """Check all health gates - returns (can_trade, reason, details)"""
        checks = {
            "account": self.check_account_freshness(),
            "trader": self.check_trader_health(),
            "feeder": self.check_feeder_stream(),
            "memory": self.check_memory_usage()
        }
        
        details = {}
        for check_name, (passed, reason) in checks.items():
            details[check_name] = {"passed": passed, "reason": reason}
            if not passed:
                # Debounced logging (once per 5 minutes per check)
                now = time.time()
                last_log = self.last_log_time.get(check_name, 0)
                if now - last_log > 300:  # 5 minutes
                    print(f"[PRETRADE_GATE] {check_name.upper()}: {reason}")
                    self.last_log_time[check_name] = now
                return False, reason, details
        
        return True, "ALL_GATES_PASS", details
    
    def get_gate_status(self) -> Dict[str, Any]:
        """Get current status of all gates for UI display"""
        _, _, details = self.check_all_gates()
        
        # Calculate overall status
        all_passed = all(check["passed"] for check in details.values())
        
        return {
            "overall_status": "PASS" if all_passed else "FAIL",
            "checks": details,
            "timestamp": time.time()
        }


# Global instance
_health_gate = None

def get_health_gate() -> PreTradeHealthGate:
    """Get singleton health gate instance"""
    global _health_gate
    if _health_gate is None:
        _health_gate = PreTradeHealthGate()
    return _health_gate
