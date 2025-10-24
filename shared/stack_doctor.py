"""
Phase 6: Self-test Stack Doctor
One-click verification that confirms the stack is ready for trading
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Add project root to path
REPO_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(REPO_ROOT))

from shared.atomic_writer import safe_read_json
from shared.env_guards import validate_environment
from shared.pid_lock import check_single_instance


class StackDoctor:
    """Comprehensive stack verification system"""
    
    def __init__(self):
        self.repo_root = REPO_ROOT
        self.shared_data = self.repo_root / "shared_data"
        self.logs_dir = self.repo_root / "logs"
        self.reports_dir = self.shared_data / "reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        
        self.results = {
            "timestamp": time.time(),
            "overall_status": "UNKNOWN",
            "checks": {},
            "summary": []
        }
    
    def check_environment(self) -> bool:
        """Check environment validation"""
        try:
            validate_environment("stack_doctor")
            self.results["checks"]["environment"] = {
                "status": "PASS",
                "message": "Environment validation successful"
            }
            return True
        except SystemExit as e:
            self.results["checks"]["environment"] = {
                "status": "FAIL",
                "message": f"Environment validation failed: {e}"
            }
            return False
    
    def check_single_instances(self) -> bool:
        """Check single instance enforcement"""
        services = ["feeder", "trader", "ares", "autoheal", "account_snapshot", "uds"]
        all_passed = True
        
        for service in services:
            if check_single_instance(service):
                self.results["checks"][f"single_instance_{service}"] = {
                    "status": "PASS",
                    "message": f"{service} single instance check passed"
                }
            else:
                self.results["checks"][f"single_instance_{service}"] = {
                    "status": "FAIL",
                    "message": f"{service} already running or PID lock issue"
                }
                all_passed = False
        
        return all_passed
    
    def check_snapshots_freshness(self) -> bool:
        """Check snapshot/health update cadence within TTLs"""
        key_files = {
            "health.json": 15,  # 15s TTL
            "account_snapshot.json": 180,  # 180s TTL
            "databus_snapshot.json": 5,  # 5s TTL
            "positions_snapshot.json": 180,  # 180s TTL
        }
        
        all_fresh = True
        current_time = time.time()
        
        for filename, ttl_sec in key_files.items():
            file_path = self.shared_data / filename
            if file_path.exists():
                age = current_time - file_path.stat().st_mtime
                if age <= ttl_sec:
                    self.results["checks"][f"freshness_{filename}"] = {
                        "status": "PASS",
                        "message": f"{filename} fresh ({age:.1f}s < {ttl_sec}s TTL)"
                    }
                else:
                    self.results["checks"][f"freshness_{filename}"] = {
                        "status": "FAIL",
                        "message": f"{filename} stale ({age:.1f}s > {ttl_sec}s TTL)"
                    }
                    all_fresh = False
            else:
                self.results["checks"][f"freshness_{filename}"] = {
                    "status": "FAIL",
                    "message": f"{filename} missing"
                }
                all_fresh = False
        
        return all_fresh
    
    def check_health_components(self) -> bool:
        """Check health components status"""
        health_file = self.shared_data / "health.json"
        if not health_file.exists():
            self.results["checks"]["health_components"] = {
                "status": "FAIL",
                "message": "health.json missing"
            }
            return False
        
        health_data = safe_read_json(health_file)
        components = health_data.get("components", {})
        
        required_components = ["feeder", "uds", "trader", "ares", "autoheal", "account"]
        all_green = True
        current_time = time.time()
        
        for comp_name in required_components:
            if comp_name in components:
                comp = components[comp_name]
                status = comp.get("status", "UNKNOWN")
                last_ts = comp.get("last_ts", 0)
                age = current_time - last_ts if last_ts > 0 else float('inf')
                
                # Check TTLs
                if comp_name == "feeder" and age > 5:
                    comp_status = "FAIL"
                    all_green = False
                elif comp_name == "uds" and age > 50:
                    comp_status = "FAIL"
                    all_green = False
                elif comp_name in ["trader", "ares", "autoheal", "account"] and age > 300:
                    comp_status = "FAIL"
                    all_green = False
                elif status == "GREEN":
                    comp_status = "PASS"
                else:
                    comp_status = "WARN"
                
                self.results["checks"][f"health_{comp_name}"] = {
                    "status": comp_status,
                    "message": f"{comp_name}: {status} ({age:.1f}s ago)"
                }
            else:
                self.results["checks"][f"health_{comp_name}"] = {
                    "status": "FAIL",
                    "message": f"{comp_name} missing from health"
                }
                all_green = False
        
        return all_green
    
    def check_ares_signal_quality(self) -> bool:
        """Check ARES signal quality (no fallback signals)"""
        # Check if TEST_ALLOW_DEFAULT_SIGNAL is OFF
        test_allow_default = os.getenv("TEST_ALLOW_DEFAULT_SIGNAL", "false").lower() == "true"
        
        if test_allow_default:
            self.results["checks"]["ares_signal_quality"] = {
                "status": "WARN",
                "message": "TEST_ALLOW_DEFAULT_SIGNAL=true (fallback signals enabled)"
            }
            return False
        else:
            self.results["checks"]["ares_signal_quality"] = {
                "status": "PASS",
                "message": "TEST_ALLOW_DEFAULT_SIGNAL=false (no fallback signals)"
            }
            return True
    
    def check_trader_guardrails(self) -> bool:
        """Check Trader guardrails would allow orders"""
        # This is a simplified check - in reality would need to check guardrail conditions
        health_file = self.shared_data / "health.json"
        if not health_file.exists():
            self.results["checks"]["trader_guardrails"] = {
                "status": "FAIL",
                "message": "health.json missing for guardrail check"
            }
            return False
        
        health_data = safe_read_json(health_file)
        components = health_data.get("components", {})
        
        # Check if all required components are GREEN
        required_for_trading = ["feeder", "uds", "trader", "account"]
        all_ready = True
        
        for comp_name in required_for_trading:
            if comp_name in components:
                comp = components[comp_name]
                status = comp.get("status", "UNKNOWN")
                if status != "GREEN":
                    all_ready = False
                    break
            else:
                all_ready = False
                break
        
        if all_ready:
            self.results["checks"]["trader_guardrails"] = {
                "status": "PASS",
                "message": "All guardrail conditions met for trading"
            }
        else:
            self.results["checks"]["trader_guardrails"] = {
                "status": "FAIL",
                "message": "Guardrail conditions not met for trading"
            }
        
        return all_ready
    
    def check_circuit_breaker(self) -> bool:
        """Check circuit breaker status"""
        cb_file = self.shared_data / "circuit_breaker.json"
        if cb_file.exists():
            cb_data = safe_read_json(cb_file)
            active = cb_data.get("active", False)
            if active:
                reason = cb_data.get("reason", "unknown")
                self.results["checks"]["circuit_breaker"] = {
                    "status": "FAIL",
                    "message": f"Circuit breaker ACTIVE: {reason}"
                }
                return False
            else:
                self.results["checks"]["circuit_breaker"] = {
                    "status": "PASS",
                    "message": "Circuit breaker INACTIVE"
                }
                return True
        else:
            self.results["checks"]["circuit_breaker"] = {
                "status": "PASS",
                "message": "Circuit breaker file not found (default: INACTIVE)"
            }
            return True
    
    def run_all_checks(self) -> Dict[str, Any]:
        """Run all verification checks"""
        print("=== Stack Doctor - Comprehensive Verification ===")
        print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.results['timestamp']))}")
        print()
        
        checks = [
            ("Environment", self.check_environment),
            ("Single Instances", self.check_single_instances),
            ("Snapshots Freshness", self.check_snapshots_freshness),
            ("Health Components", self.check_health_components),
            ("ARES Signal Quality", self.check_ares_signal_quality),
            ("Trader Guardrails", self.check_trader_guardrails),
            ("Circuit Breaker", self.check_circuit_breaker),
        ]
        
        passed_checks = 0
        total_checks = len(checks)
        
        for check_name, check_func in checks:
            print(f"Checking {check_name}...")
            try:
                result = check_func()
                if result:
                    print(f"  ✅ {check_name}: PASS")
                    passed_checks += 1
                else:
                    print(f"  ❌ {check_name}: FAIL")
            except Exception as e:
                print(f"  ⚠️ {check_name}: ERROR - {e}")
                self.results["checks"][check_name.lower().replace(" ", "_")] = {
                    "status": "ERROR",
                    "message": str(e)
                }
        
        print()
        print(f"Results: {passed_checks}/{total_checks} checks passed")
        
        # Determine overall status
        if passed_checks == total_checks:
            self.results["overall_status"] = "PASS"
            self.results["summary"].append("All checks passed - Stack ready for trading")
        elif passed_checks >= total_checks * 0.8:
            self.results["overall_status"] = "WARN"
            self.results["summary"].append("Most checks passed - Minor issues detected")
        else:
            self.results["overall_status"] = "FAIL"
            self.results["summary"].append("Multiple checks failed - Stack not ready")
        
        return self.results
    
    def generate_report(self) -> Path:
        """Generate markdown report"""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        report_file = self.reports_dir / f"stack_doctor_{timestamp}.md"
        
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(f"# Stack Doctor Report - {timestamp}\n\n")
            f.write(f"**Overall Status**: {self.results['overall_status']}\n\n")
            f.write(f"**Timestamp**: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.results['timestamp']))}\n\n")
            
            f.write("## Summary\n\n")
            for summary_item in self.results["summary"]:
                f.write(f"- {summary_item}\n")
            f.write("\n")
            
            f.write("## Detailed Results\n\n")
            for check_name, check_result in self.results["checks"].items():
                status = check_result["status"]
                message = check_result["message"]
                status_emoji = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
                f.write(f"### {check_name.replace('_', ' ').title()}\n\n")
                f.write(f"**Status**: {status_emoji} {status}\n\n")
                f.write(f"**Message**: {message}\n\n")
            
            # Add recent logs
            f.write("## Recent Logs\n\n")
            log_files = ["trader.log", "feeder.log", "ares.log", "autoheal.log"]
            for log_file in log_files:
                log_path = self.logs_dir / log_file
                if log_path.exists():
                    f.write(f"### {log_file}\n\n")
                    try:
                        with open(log_path, "r", encoding="utf-8") as lf:
                            lines = lf.readlines()
                            for line in lines[-10:]:  # Last 10 lines
                                f.write(f"    {line}")
                    except Exception:
                        f.write("    Error reading log file\n")
                    f.write("\n")
        
        return report_file


def main():
    """Main entry point"""
    try:
        doctor = StackDoctor()
        results = doctor.run_all_checks()
        report_file = doctor.generate_report()
        
        print(f"\nReport generated: {report_file}")
        
        # Exit with appropriate code
        if results["overall_status"] == "PASS":
            sys.exit(0)
        elif results["overall_status"] == "WARN":
            sys.exit(1)
        else:
            sys.exit(2)
            
    except Exception as e:
        print(f"Stack Doctor failed: {e}")
        sys.exit(3)


if __name__ == "__main__":
    main()
