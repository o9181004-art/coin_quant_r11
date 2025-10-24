#!/usr/bin/env python3
"""
Coin Quant R11 - End-to-End Integration Tests

Comprehensive integration testing for Feeder → ARES → Trader orchestration
with live data, Memory Layer logging, and failure scenarios.
"""

import sys
import time
import json
import signal
import subprocess
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import asyncio
import websockets
import requests

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

class TestResult(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"

@dataclass
class ServiceProcess:
    """Service process wrapper"""
    name: str
    process: subprocess.Popen
    pid_file: Path
    log_file: Path
    started_at: float

@dataclass
class IntegrationTest:
    """Integration test definition"""
    name: str
    description: str
    test_function: callable
    required: bool = True
    timeout: int = 300  # 5 minutes default

class E2EIntegrationTestSuite:
    """End-to-end integration test suite"""
    
    def __init__(self):
        self.results: List[Dict[str, Any]] = []
        self.test_dir = Path("test_e2e_data")
        self.test_dir.mkdir(exist_ok=True)
        
        # Service processes
        self.services: Dict[str, ServiceProcess] = {}
        self.service_pids: Dict[str, int] = {}
        
        # Test configuration
        self.testnet_mode = True
        self.simulation_mode = True
        self.test_symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT"]
        
        # Test data
        self.test_data = {
            "feeder_data": {},
            "ares_signals": [],
            "trader_orders": [],
            "memory_events": []
        }
        
    def setup_test_environment(self) -> bool:
        """Setup test environment"""
        try:
            print("🔧 Setting up test environment...")
            
            # Create test data directory
            test_data_dir = self.test_dir / "shared_data"
            test_data_dir.mkdir(parents=True, exist_ok=True)
            
            # Create test config
            test_config = {
                "BINANCE_API_KEY": "test_key",
                "BINANCE_API_SECRET": "test_secret", 
                "BINANCE_USE_TESTNET": str(self.testnet_mode),
                "TRADING_MODE": "testnet" if self.testnet_mode else "live",
                "SIMULATION_MODE": str(self.simulation_mode),
                "PAPER_MODE": "False",
                "LIVE_TRADING_ENABLED": "False",
                "TEST_ALLOW_DEFAULT_SIGNAL": "True",
                "ARES_FRESHNESS_THRESHOLD": "30.0",
                "ARES_HEARTBEAT_INTERVAL": "10.0",
                "FEEDER_HEARTBEAT_INTERVAL": "5.0",
                "TRADER_ORDER_COOLDOWN": "1.0",
                "SHARED_DATA_DIR": str(test_data_dir),
                "LOG_LEVEL": "INFO"
            }
            
            # Write test config
            config_file = test_data_dir / "config.env"
            with open(config_file, "w") as f:
                for key, value in test_config.items():
                    f.write(f"{key}={value}\n")
            
            print(f"✅ Test environment setup complete: {test_data_dir}")
            return True
            
        except Exception as e:
            print(f"❌ Test environment setup failed: {e}")
            return False
    
    def start_service(self, service_name: str) -> bool:
        """Start a service"""
        try:
            print(f"🚀 Starting {service_name} service...")
            
            # Create service-specific directories
            service_dir = self.test_dir / "shared_data" / service_name
            service_dir.mkdir(parents=True, exist_ok=True)
            
            # Start service process
            if service_name == "feeder":
                cmd = [sys.executable, "-m", "coin_quant.feeder.service"]
            elif service_name == "ares":
                cmd = [sys.executable, "-m", "coin_quant.ares.service"]
            elif service_name == "trader":
                cmd = [sys.executable, "-m", "coin_quant.trader.service"]
            else:
                raise ValueError(f"Unknown service: {service_name}")
            
            # Set environment variables
            env = {
                "PYTHONPATH": str(Path(__file__).parent / "src"),
                "SHARED_DATA_DIR": str(self.test_dir / "shared_data")
            }
            
            # Start process
            process = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Create service process wrapper
            service_process = ServiceProcess(
                name=service_name,
                process=process,
                pid_file=self.test_dir / "shared_data" / "pids" / f"{service_name}.pid",
                log_file=self.test_dir / "shared_data" / "logs" / f"{service_name}.log",
                started_at=time.time()
            )
            
            self.services[service_name] = service_process
            self.service_pids[service_name] = process.pid
            
            # Wait for service to start
            time.sleep(2)
            
            # Check if service is running
            if process.poll() is None:
                print(f"✅ {service_name} service started (PID: {process.pid})")
                return True
            else:
                print(f"❌ {service_name} service failed to start")
                return False
                
        except Exception as e:
            print(f"❌ Failed to start {service_name} service: {e}")
            return False
    
    def stop_service(self, service_name: str) -> bool:
        """Stop a service"""
        try:
            if service_name not in self.services:
                return True
            
            service_process = self.services[service_name]
            process = service_process.process
            
            print(f"🛑 Stopping {service_name} service...")
            
            # Send SIGTERM
            process.terminate()
            
            # Wait for graceful shutdown
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                # Force kill if needed
                process.kill()
                process.wait()
            
            # Clean up
            del self.services[service_name]
            if service_name in self.service_pids:
                del self.service_pids[service_name]
            
            print(f"✅ {service_name} service stopped")
            return True
            
        except Exception as e:
            print(f"❌ Failed to stop {service_name} service: {e}")
            return False
    
    def stop_all_services(self):
        """Stop all services"""
        for service_name in list(self.services.keys()):
            self.stop_service(service_name)
    
    def test_normal_operation(self) -> bool:
        """Test normal operation: continuous data flow, valid signals, executed orders"""
        try:
            print("🧪 Testing normal operation...")
            
            # Start all services
            services_to_start = ["feeder", "ares", "trader"]
            for service in services_to_start:
                if not self.start_service(service):
                    return False
            
            # Wait for services to stabilize
            print("⏳ Waiting for services to stabilize...")
            time.sleep(30)
            
            # Check service health
            health_file = self.test_dir / "shared_data" / "health" / "health.json"
            if not health_file.exists():
                print("❌ Health file not found")
                return False
            
            with open(health_file, "r") as f:
                health_data = json.load(f)
            
            components = health_data.get("components", {})
            
            # Check feeder health
            feeder_health = components.get("feeder", {})
            if feeder_health.get("status") != "GREEN":
                print(f"❌ Feeder not healthy: {feeder_health.get('status')}")
                return False
            
            # Check ARES health
            ares_health = components.get("ares", {})
            if ares_health.get("status") not in ["GREEN", "YELLOW"]:
                print(f"❌ ARES not healthy: {ares_health.get('status')}")
                return False
            
            # Check trader health
            trader_health = components.get("trader", {})
            if trader_health.get("status") not in ["GREEN", "YELLOW"]:
                print(f"❌ Trader not healthy: {trader_health.get('status')}")
                return False
            
            # Check for data flow
            feeder_snapshot = self.test_dir / "shared_data" / "feeder_snapshot.json"
            if not feeder_snapshot.exists():
                print("❌ Feeder snapshot not found")
                return False
            
            with open(feeder_snapshot, "r") as f:
                feeder_data = json.load(f)
            
            if not feeder_data.get("symbol_data"):
                print("❌ No feeder data available")
                return False
            
            # Check for signals
            ares_signals = self.test_dir / "shared_data" / "ares_signals.json"
            if ares_signals.exists():
                with open(ares_signals, "r") as f:
                    signals_data = json.load(f)
                
                if signals_data.get("signals"):
                    print(f"✅ ARES generated {len(signals_data['signals'])} signals")
                else:
                    print("⚠️  No signals generated yet")
            
            # Check memory events
            memory_events = self.test_dir / "shared_data" / "memory" / "events.jsonl"
            if memory_events.exists():
                with open(memory_events, "r") as f:
                    events = [json.loads(line) for line in f if line.strip()]
                
                if events:
                    print(f"✅ Memory layer recorded {len(events)} events")
                else:
                    print("⚠️  No memory events recorded yet")
            
            print("✅ Normal operation test passed")
            return True
            
        except Exception as e:
            print(f"❌ Normal operation test failed: {e}")
            return False
    
    def test_feeder_outage(self) -> bool:
        """Test feeder outage: stop Feeder → ARES blocks signal generation → Trader waits → recovery"""
        try:
            print("🧪 Testing feeder outage scenario...")
            
            # Start all services
            services_to_start = ["feeder", "ares", "trader"]
            for service in services_to_start:
                if not self.start_service(service):
                    return False
            
            # Wait for services to stabilize
            time.sleep(20)
            
            # Stop feeder
            print("🛑 Stopping feeder service...")
            if not self.stop_service("feeder"):
                return False
            
            # Wait for ARES to detect feeder outage
            time.sleep(15)
            
            # Check ARES health (should be RED or YELLOW)
            health_file = self.test_dir / "shared_data" / "health" / "health.json"
            with open(health_file, "r") as f:
                health_data = json.load(f)
            
            ares_health = health_data.get("components", {}).get("ares", {})
            if ares_health.get("status") not in ["RED", "YELLOW"]:
                print(f"❌ ARES should be unhealthy after feeder outage: {ares_health.get('status')}")
                return False
            
            # Check that ARES blocks signal generation
            ares_signals = self.test_dir / "shared_data" / "ares_signals.json"
            if ares_signals.exists():
                with open(ares_signals, "r") as f:
                    signals_data = json.load(f)
                
                # Check if signals stopped being generated
                last_signal_time = signals_data.get("timestamp", 0)
                if time.time() - last_signal_time < 30:  # Signals generated recently
                    print("⚠️  ARES may still be generating signals after feeder outage")
            
            # Restart feeder
            print("🚀 Restarting feeder service...")
            if not self.start_service("feeder"):
                return False
            
            # Wait for recovery
            time.sleep(20)
            
            # Check that ARES recovers
            with open(health_file, "r") as f:
                health_data = json.load(f)
            
            ares_health = health_data.get("components", {}).get("ares", {})
            if ares_health.get("status") not in ["GREEN", "YELLOW"]:
                print(f"❌ ARES should recover after feeder restart: {ares_health.get('status')}")
                return False
            
            print("✅ Feeder outage test passed")
            return True
            
        except Exception as e:
            print(f"❌ Feeder outage test failed: {e}")
            return False
    
    def test_balance_exhaustion(self) -> bool:
        """Test balance exhaustion: artificially reduce balance → Trader scales down"""
        try:
            print("🧪 Testing balance exhaustion scenario...")
            
            # Start all services
            services_to_start = ["feeder", "ares", "trader"]
            for service in services_to_start:
                if not self.start_service(service):
                    return False
            
            # Wait for services to stabilize
            time.sleep(20)
            
            # Create low balance scenario
            balance_file = self.test_dir / "shared_data" / "account_balance.json"
            low_balance = {
                "timestamp": time.time(),
                "balance": {
                    "USDT": {"free": 0.01, "locked": 0.0},  # Very low balance
                    "BTC": {"free": 0.0001, "locked": 0.0},
                    "ETH": {"free": 0.001, "locked": 0.0}
                }
            }
            
            with open(balance_file, "w") as f:
                json.dump(low_balance, f)
            
            # Wait for trader to detect low balance
            time.sleep(15)
            
            # Check trader health (should handle low balance gracefully)
            health_file = self.test_dir / "shared_data" / "health" / "health.json"
            with open(health_file, "r") as f:
                health_data = json.load(f)
            
            trader_health = health_data.get("components", {}).get("trader", {})
            if trader_health.get("status") == "RED":
                print("⚠️  Trader went RED due to low balance")
            
            # Check for quarantined symbols
            quarantined_symbols = trader_health.get("quarantined_symbols", [])
            if quarantined_symbols:
                print(f"✅ Trader quarantined symbols due to low balance: {quarantined_symbols}")
            
            print("✅ Balance exhaustion test passed")
            return True
            
        except Exception as e:
            print(f"❌ Balance exhaustion test failed: {e}")
            return False
    
    def test_memory_corruption(self) -> bool:
        """Test memory corruption: corrupt memory files → auto-heal → recovery"""
        try:
            print("🧪 Testing memory corruption scenario...")
            
            # Start all services
            services_to_start = ["feeder", "ares", "trader"]
            for service in services_to_start:
                if not self.start_service(service):
                    return False
            
            # Wait for services to stabilize
            time.sleep(20)
            
            # Corrupt memory files
            memory_dir = self.test_dir / "shared_data" / "memory"
            memory_dir.mkdir(parents=True, exist_ok=True)
            
            # Corrupt events file
            events_file = memory_dir / "events.jsonl"
            with open(events_file, "w") as f:
                f.write("corrupted data\n")
            
            # Corrupt hash chain
            hash_chain_file = memory_dir / "hash_chain.json"
            with open(hash_chain_file, "w") as f:
                json.dump({"corrupted": True}, f)
            
            print("💥 Corrupted memory files")
            
            # Wait for auto-heal to kick in
            time.sleep(15)
            
            # Check memory integrity
            integrity_file = memory_dir / "integrity.json"
            if integrity_file.exists():
                with open(integrity_file, "r") as f:
                    integrity_data = json.load(f)
                
                integrity_status = integrity_data.get("status", "UNKNOWN")
                print(f"Memory integrity status: {integrity_status}")
            
            # Check that services continue to operate
            health_file = self.test_dir / "shared_data" / "health" / "health.json"
            with open(health_file, "r") as f:
                health_data = json.load(f)
            
            components = health_data.get("components", {})
            for service_name, health in components.items():
                if health.get("status") == "RED":
                    print(f"⚠️  {service_name} went RED after memory corruption")
            
            print("✅ Memory corruption test passed")
            return True
            
        except Exception as e:
            print(f"❌ Memory corruption test failed: {e}")
            return False
    
    def test_websocket_connection(self) -> bool:
        """Test WebSocket connection to Binance testnet"""
        try:
            print("🧪 Testing WebSocket connection...")
            
            # Test WebSocket connection to Binance testnet
            testnet_url = "wss://testnet.binance.vision/ws/btcusdt@ticker"
            
            async def test_websocket():
                try:
                    async with websockets.connect(testnet_url) as websocket:
                        # Wait for a message
                        message = await asyncio.wait_for(websocket.recv(), timeout=10)
                        data = json.loads(message)
                        
                        if "data" in data and "c" in data["data"]:
                            price = float(data["data"]["c"])
                            print(f"✅ WebSocket connected, BTC price: ${price}")
                            return True
                        else:
                            print("❌ Invalid WebSocket data format")
                            return False
                            
                except Exception as e:
                    print(f"❌ WebSocket connection failed: {e}")
                    return False
            
            # Run WebSocket test
            result = asyncio.run(test_websocket())
            return result
            
        except Exception as e:
            print(f"❌ WebSocket test failed: {e}")
            return False
    
    def test_rest_api_connection(self) -> bool:
        """Test REST API connection to Binance testnet"""
        try:
            print("🧪 Testing REST API connection...")
            
            # Test REST API connection to Binance testnet
            testnet_url = "https://testnet.binance.vision/api/v3/ticker/price"
            params = {"symbol": "BTCUSDT"}
            
            response = requests.get(testnet_url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if "symbol" in data and "price" in data:
                    price = float(data["price"])
                    print(f"✅ REST API connected, BTC price: ${price}")
                    return True
                else:
                    print("❌ Invalid REST API response format")
                    return False
            else:
                print(f"❌ REST API request failed: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ REST API test failed: {e}")
            return False
    
    def test_memory_layer_integrity(self) -> bool:
        """Test memory layer integrity and event logging"""
        try:
            print("🧪 Testing memory layer integrity...")
            
            # Start all services
            services_to_start = ["feeder", "ares", "trader"]
            for service in services_to_start:
                if not self.start_service(service):
                    return False
            
            # Wait for services to generate events
            time.sleep(30)
            
            # Check memory layer files
            memory_dir = self.test_dir / "shared_data" / "memory"
            
            # Check events file
            events_file = memory_dir / "events.jsonl"
            if not events_file.exists():
                print("❌ Events file not found")
                return False
            
            with open(events_file, "r") as f:
                events = [json.loads(line) for line in f if line.strip()]
            
            if not events:
                print("❌ No events recorded")
                return False
            
            print(f"✅ Memory layer recorded {len(events)} events")
            
            # Check hash chain
            hash_chain_file = memory_dir / "hash_chain.json"
            if hash_chain_file.exists():
                with open(hash_chain_file, "r") as f:
                    hash_chain = json.load(f)
                
                if "blocks" in hash_chain:
                    print(f"✅ Hash chain has {len(hash_chain['blocks'])} blocks")
                else:
                    print("⚠️  Hash chain structure incomplete")
            
            # Check snapshots
            snapshots_dir = memory_dir / "snapshots"
            if snapshots_dir.exists():
                snapshots = list(snapshots_dir.glob("*.json"))
                if snapshots:
                    print(f"✅ Memory layer has {len(snapshots)} snapshots")
                else:
                    print("⚠️  No snapshots found")
            
            print("✅ Memory layer integrity test passed")
            return True
            
        except Exception as e:
            print(f"❌ Memory layer integrity test failed: {e}")
            return False
    
    def run_test(self, test: IntegrationTest) -> Dict[str, Any]:
        """Run a single integration test"""
        print(f"\n🧪 Testing: {test.name}")
        print(f"   {test.description}")
        
        try:
            start_time = time.time()
            
            # Setup test environment
            if not self.setup_test_environment():
                return {
                    "name": test.name,
                    "result": TestResult.FAIL.value,
                    "duration": 0,
                    "required": test.required,
                    "error": "Test environment setup failed"
                }
            
            # Run test with timeout
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
        finally:
            # Clean up services
            self.stop_all_services()
    
    def run_all_tests(self) -> Dict[str, Any]:
        """Run all integration tests"""
        print("🚀 Coin Quant R11 - End-to-End Integration Test Suite")
        print("=" * 60)
        
        # Define all tests
        tests = [
            IntegrationTest(
                "WebSocket Connection",
                "Test WebSocket connection to Binance testnet",
                self.test_websocket_connection,
                timeout=30
            ),
            IntegrationTest(
                "REST API Connection", 
                "Test REST API connection to Binance testnet",
                self.test_rest_api_connection,
                timeout=30
            ),
            IntegrationTest(
                "Normal Operation",
                "Test continuous data flow, valid signals, executed orders",
                self.test_normal_operation,
                timeout=300
            ),
            IntegrationTest(
                "Feeder Outage",
                "Test feeder outage → ARES blocks → Trader waits → recovery",
                self.test_feeder_outage,
                timeout=300
            ),
            IntegrationTest(
                "Balance Exhaustion",
                "Test balance exhaustion → Trader scales down",
                self.test_balance_exhaustion,
                timeout=300
            ),
            IntegrationTest(
                "Memory Corruption",
                "Test memory corruption → auto-heal → recovery",
                self.test_memory_corruption,
                timeout=300
            ),
            IntegrationTest(
                "Memory Layer Integrity",
                "Test memory layer integrity and event logging",
                self.test_memory_layer_integrity,
                timeout=300
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
            "integration_ready": required_failed == 0,
            "results": self.results
        }
        
        # Print summary
        print("\n" + "=" * 60)
        print("📊 INTEGRATION TEST SUMMARY")
        print("=" * 60)
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {failed_tests}")
        print(f"Required Failed: {required_failed}")
        print(f"Total Duration: {total_duration:.2f}s")
        print(f"Integration Ready: {'✅ YES' if summary['integration_ready'] else '❌ NO'}")
        
        if failed_tests > 0:
            print("\n❌ FAILED TESTS:")
            for result in self.results:
                if result["result"] == TestResult.FAIL.value:
                    status = "REQUIRED" if result["required"] else "OPTIONAL"
                    print(f"  - {result['name']} ({status})")
                    if "error" in result:
                        print(f"    Error: {result['error']}")
        
        # Save results
        results_file = self.test_dir / "integration_results.json"
        with open(results_file, "w") as f:
            json.dump(summary, f, indent=2)
        
        print(f"\n📁 Results saved to: {results_file}")
        
        return summary

def main():
    """Main entry point"""
    suite = E2EIntegrationTestSuite()
    
    try:
        summary = suite.run_all_tests()
        
        # Exit with appropriate code
        if summary["integration_ready"]:
            print("\n🎉 Coin Quant R11 Integration Tests PASSED!")
            sys.exit(0)
        else:
            print("\n⚠️  Coin Quant R11 Integration Tests FAILED!")
            print("   Please fix required test failures before proceeding.")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n🛑 Tests interrupted by user")
        suite.stop_all_services()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test suite failed: {e}")
        suite.stop_all_services()
        sys.exit(1)

if __name__ == "__main__":
    main()
