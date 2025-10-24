#!/usr/bin/env python3
"""
Coin Quant R11 - Acceptance Test Suite

Comprehensive acceptance testing for all operational requirements.
Tests all 8 operational areas and validates RC readiness.
"""

import sys
import time
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

class TestResult(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"

@dataclass
class AcceptanceTest:
    name: str
    description: str
    test_function: callable
    required: bool = True

class AcceptanceTestSuite:
    """Comprehensive acceptance test suite for Coin Quant R11"""
    
    def __init__(self):
        self.results: List[Dict[str, Any]] = []
        self.test_dir = Path("test_acceptance_data")
        self.test_dir.mkdir(exist_ok=True)
        
    def run_test(self, test: AcceptanceTest) -> Dict[str, Any]:
        """Run a single acceptance test"""
        print(f"\n🧪 Testing: {test.name}")
        print(f"   {test.description}")
        
        try:
            start_time = time.time()
            result = test.test_function()
            duration = time.time() - start_time
            
            if result:
                print(f"   ✅ PASS ({duration:.2f}s)")
                return {
                    "name": test.name,
                    "result": TestResult.PASS.value,
                    "duration": duration,
                    "required": test.required
                }
            else:
                print(f"   ❌ FAIL ({duration:.2f}s)")
                return {
                    "name": test.name,
                    "result": TestResult.FAIL.value,
                    "duration": duration,
                    "required": test.required
                }
                
        except Exception as e:
            print(f"   ❌ ERROR: {e}")
            return {
                "name": test.name,
                "result": TestResult.FAIL.value,
                "duration": 0,
                "required": test.required,
                "error": str(e)
            }
    
    def test_health_contracts(self) -> bool:
        """Test health contracts and readiness gates"""
        try:
            from coin_quant.shared.health_contracts import get_health_manager, create_readiness_gate
            
            # Test health manager
            health_manager = get_health_manager()
            assert health_manager is not None, "Health manager not available"
            
            # Test readiness gate creation
            feeder_gate = create_readiness_gate("feeder")
            assert feeder_gate is not None, "Readiness gate creation failed"
            
            # Test health update
            health_manager.update_feeder_health(
                symbols=["BTCUSDT", "ETHUSDT"],
                ws_connected=True,
                rest_api_ok=True
            )
            
            # Test readiness check
            readiness = feeder_gate.check_readiness()
            assert isinstance(readiness, dict), "Readiness check failed"
            
            return True
            
        except Exception as e:
            print(f"Health contracts test failed: {e}")
            return False
    
    def test_config_ssot(self) -> bool:
        """Test configuration SSOT system"""
        try:
            from coin_quant.shared.config_ssot import get_config, validate_and_exit_on_error
            
            # Test config loading
            config = get_config()
            assert config is not None, "Config not available"
            
            # Test config summary
            summary = config.get_config_summary()
            assert "config_hash" in summary, "Config summary missing hash"
            assert "required_fields" in summary, "Config summary missing required fields"
            
            # Test validation (should not exit in test mode)
            try:
                errors = config.validate_configuration()
                if errors:
                    return False
                return True
            except Exception as e:
                return False
                
        except Exception as e:
            print(f"Config SSOT test failed: {e}")
            return False
    
    def test_memory_validation(self) -> bool:
        """Test memory layer validation"""
        try:
            from coin_quant.shared.memory_validator import get_memory_validator
            
            # Test validator
            validator = get_memory_validator()
            assert validator is not None, "Memory validator not available"
            
            # Test integrity validation
            report = validator.validate_integrity()
            assert report is not None, "Integrity validation failed"
            assert "status" in report, "Integrity report missing status"
            assert report["status"] in ["valid", "degraded", "corrupted", "quarantined"], f"Invalid status: {report['status']}"
            
            # Test debug bundle export
            bundle_path = validator.export_debug_bundle()
            assert bundle_path.exists(), "Debug bundle export failed"
            
            return True
            
        except Exception as e:
            print(f"Memory validation test failed: {e}")
            return False
    
    def test_observability(self) -> bool:
        """Test observability and logging"""
        try:
            from coin_quant.shared.observability import create_structured_logger, create_debug_bundle
            
            # Test structured logger
            logger = create_structured_logger("test")
            assert logger is not None, "Structured logger creation failed"
            
            # Test debug bundle
            bundle_path = create_debug_bundle(minutes_back=1)
            assert bundle_path.exists(), "Debug bundle creation failed"
            
            return True
            
        except Exception as e:
            print(f"Observability test failed: {e}")
            return False
    
    def test_run_scripts(self) -> bool:
        """Test run scripts and launcher"""
        try:
            # Test PowerShell scripts exist
            scripts_dir = Path("scripts")
            required_scripts = [
                "launch_feeder.ps1",
                "launch_ares.ps1", 
                "launch_trader.ps1",
                "launch_all.ps1"
            ]
            
            for script in required_scripts:
                script_path = scripts_dir / script
                assert script_path.exists(), f"Missing script: {script}"
            
            # Test Python launcher
            launcher_path = Path("launch.py")
            assert launcher_path.exists(), "Python launcher missing"
            
            return True
            
        except Exception as e:
            print(f"Run scripts test failed: {e}")
            return False
    
    def test_failure_drills(self) -> bool:
        """Test failure drills and recovery"""
        try:
            from coin_quant.shared.failure_drills import run_failure_drills
            
            # Test failure drills
            results = run_failure_drills()
            assert isinstance(results, list), "Failure drills failed"
            
            # Check that we got results for all drill types
            drill_types = {result.drill_type.value for result in results}
            expected_types = {"feeder_outage", "insufficient_balance", "memory_corruption"}
            assert drill_types == expected_types, f"Missing drill types: {expected_types - drill_types}"
            
            return True
            
        except Exception as e:
            print(f"Failure drills test failed: {e}")
            return False
    
    def test_documentation(self) -> bool:
        """Test documentation completeness"""
        try:
            required_docs = [
                "README.md",
                "RUNBOOK.md", 
                "SCHEMAS.md",
                "MIGRATION.md",
                "CI-CD.md",
                "RELEASE_READINESS.md",
                "CHANGELOG.md"
            ]
            
            for doc in required_docs:
                doc_path = Path(doc)
                assert doc_path.exists(), f"Missing documentation: {doc}"
                
                # Check that docs are not empty
                content = doc_path.read_text()
                assert len(content.strip()) > 100, f"Documentation too short: {doc}"
            
            return True
            
        except Exception as e:
            print(f"Documentation test failed: {e}")
            return False
    
    def test_ci_lint(self) -> bool:
        """Test CI/Lint configuration"""
        try:
            # Test GitHub Actions workflow
            workflow_path = Path(".github/workflows/ci-cd.yml")
            assert workflow_path.exists(), "CI/CD workflow missing"
            
            # Test pre-commit config
            precommit_path = Path(".pre-commit-config.yaml")
            assert precommit_path.exists(), "Pre-commit config missing"
            
            # Test pyproject.toml
            pyproject_path = Path("pyproject.toml")
            assert pyproject_path.exists(), "pyproject.toml missing"
            
            # Test requirements.txt
            requirements_path = Path("requirements.txt")
            assert requirements_path.exists(), "requirements.txt missing"
            
            return True
            
        except Exception as e:
            print(f"CI/Lint test failed: {e}")
            return False
    
    def test_release_candidate(self) -> bool:
        """Test release candidate readiness"""
        try:
            # Test version consistency
            from coin_quant import __version__
            assert __version__ == "1.0.0-rc1", f"Version mismatch: {__version__}"
            
            # Test package structure
            src_dir = Path("src/coin_quant")
            assert src_dir.exists(), "Source directory missing"
            
            required_modules = [
                "shared",
                "feeder", 
                "ares",
                "trader",
                "memory"
            ]
            
            for module in required_modules:
                module_path = src_dir / module
                assert module_path.exists(), f"Missing module: {module}"
            
            # Test smoke tests
            smoke_test_path = Path("test_smoke.py")
            assert smoke_test_path.exists(), "Smoke tests missing"
            
            return True
            
        except Exception as e:
            print(f"Release candidate test failed: {e}")
            return False
    
    def run_all_tests(self) -> Dict[str, Any]:
        """Run all acceptance tests"""
        print("🚀 Coin Quant R11 - Acceptance Test Suite")
        print("=" * 50)
        
        # Define all tests
        tests = [
            AcceptanceTest(
                "Health Contracts & Readiness Gates",
                "Test health management and readiness gates",
                self.test_health_contracts
            ),
            AcceptanceTest(
                "Configuration SSOT",
                "Test configuration management and validation",
                self.test_config_ssot
            ),
            AcceptanceTest(
                "Memory Layer Validation",
                "Test memory integrity and debug bundles",
                self.test_memory_validation
            ),
            AcceptanceTest(
                "Observability & Logs",
                "Test structured logging and debug bundles",
                self.test_observability
            ),
            AcceptanceTest(
                "Run Scripts & Developer Ergonomics",
                "Test launcher scripts and developer tools",
                self.test_run_scripts
            ),
            AcceptanceTest(
                "Failure Drills & Recovery",
                "Test failure simulation and recovery procedures",
                self.test_failure_drills
            ),
            AcceptanceTest(
                "Documentation & Handover",
                "Test documentation completeness",
                self.test_documentation
            ),
            AcceptanceTest(
                "CI/Lint",
                "Test CI/CD configuration and linting",
                self.test_ci_lint
            ),
            AcceptanceTest(
                "Release Candidate",
                "Test RC readiness and version consistency",
                self.test_release_candidate
            )
        ]
        
        # Run all tests
        for test in tests:
            result = self.run_test(test)
            self.results.append(result)
        
        # Generate summary
        return self.generate_summary()
    
    def generate_summary(self) -> Dict[str, Any]:
        """Generate test summary"""
        total_tests = len(self.results)
        passed_tests = len([r for r in self.results if r["result"] == TestResult.PASS.value])
        failed_tests = len([r for r in self.results if r["result"] == TestResult.FAIL.value])
        required_failed = len([r for r in self.results if r["result"] == TestResult.FAIL.value and r["required"]])
        
        total_duration = sum(r["duration"] for r in self.results)
        
        summary = {
            "total_tests": total_tests,
            "passed": passed_tests,
            "failed": failed_tests,
            "required_failed": required_failed,
            "total_duration": total_duration,
            "rc_ready": required_failed == 0,
            "results": self.results
        }
        
        # Print summary
        print("\n" + "=" * 50)
        print("📊 ACCEPTANCE TEST SUMMARY")
        print("=" * 50)
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {failed_tests}")
        print(f"Required Failed: {required_failed}")
        print(f"Total Duration: {total_duration:.2f}s")
        print(f"RC Ready: {'✅ YES' if summary['rc_ready'] else '❌ NO'}")
        
        if failed_tests > 0:
            print("\n❌ FAILED TESTS:")
            for result in self.results:
                if result["result"] == TestResult.FAIL.value:
                    status = "REQUIRED" if result["required"] else "OPTIONAL"
                    print(f"  - {result['name']} ({status})")
                    if "error" in result:
                        print(f"    Error: {result['error']}")
        
        # Save results
        results_file = self.test_dir / "acceptance_results.json"
        with open(results_file, "w") as f:
            json.dump(summary, f, indent=2)
        
        print(f"\n📁 Results saved to: {results_file}")
        
        return summary

def main():
    """Main entry point"""
    suite = AcceptanceTestSuite()
    summary = suite.run_all_tests()
    
    # Exit with appropriate code
    if summary["rc_ready"]:
        print("\n🎉 Coin Quant R11 is READY FOR RELEASE!")
        sys.exit(0)
    else:
        print("\n⚠️  Coin Quant R11 is NOT READY FOR RELEASE!")
        print("   Please fix required test failures before proceeding.")
        sys.exit(1)

if __name__ == "__main__":
    main()
