"""
Validation script for Coin Quant R11

Tests the new package structure and basic functionality.
"""

import sys
import os
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

def test_imports():
    """Test that all modules can be imported"""
    try:
        import coin_quant
        import coin_quant.shared
        import coin_quant.feeder
        import coin_quant.ares
        import coin_quant.trader
        import coin_quant.memory
        
        print("✅ All modules imported successfully")
        return True
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False

def test_shared_utilities():
    """Test shared utilities"""
    try:
        from coin_quant.shared.time import utc_now_seconds, age_seconds
        from coin_quant.shared.io import atomic_write_json, safe_read_json
        from coin_quant.shared.health import health_manager
        from coin_quant.shared.config import config_manager
        
        # Test time utilities
        now = utc_now_seconds()
        age = age_seconds(now - 10)
        assert age == 10, f"Expected age 10, got {age}"
        
        print("✅ Shared utilities working")
        return True
    except Exception as e:
        print(f"❌ Shared utilities test failed: {e}")
        return False

def test_memory_layer():
    """Test memory layer components"""
    try:
        from coin_quant.memory.client import MemoryClient
        
        # Create test data directory
        test_dir = Path("test_memory")
        test_dir.mkdir(exist_ok=True)
        
        # Create memory client
        client = MemoryClient(test_dir)
        
        # Test event chain
        success = client.append_event("test", {"message": "hello"})
        assert success, "Event append failed"
        
        events = client.get_events()
        assert len(events) == 1, f"Expected 1 event, got {len(events)}"
        
        # Test snapshot store
        success = client.create_snapshot({"test": "data"})
        assert success, "Snapshot creation failed"
        
        snapshot = client.get_latest_snapshot()
        assert snapshot is not None, "No snapshot found"
        
        # Test hash chain
        success = client.add_block([{"test": "data"}])
        assert success, "Block addition failed"
        
        is_valid, errors = client.verify_chain()
        assert is_valid, f"Chain verification failed: {errors}"
        
        print("✅ Memory layer working")
        return True
    except Exception as e:
        print(f"❌ Memory layer test failed: {e}")
        return False

def test_service_placeholders():
    """Test service placeholders"""
    try:
        from coin_quant.feeder.service import FeederService
        from coin_quant.ares.service import AresService
        from coin_quant.trader.service import TraderService
        
        # Test that services can be instantiated
        feeder = FeederService()
        ares = AresService()
        trader = TraderService()
        
        print("✅ Service placeholders working")
        return True
    except Exception as e:
        print(f"❌ Service placeholders test failed: {e}")
        return False

def main():
    """Run all validation tests"""
    print("Running Coin Quant R11 validation tests...")
    
    tests = [
        test_imports,
        test_shared_utilities,
        test_memory_layer,
        test_service_placeholders
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with exception: {e}")
    
    print(f"\nValidation tests completed: {passed}/{total} passed")
    
    if passed == total:
        print("🎉 All tests passed!")
        return True
    else:
        print("❌ Some tests failed")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
