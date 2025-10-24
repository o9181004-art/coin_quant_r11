#!/usr/bin/env python3
"""
Tests for UI Path Resolution and Data Access Layer

Minimal tests to ensure path resolution and DAL work correctly.
"""

import sys
import tempfile
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from coin_quant.shared.pathing import get_project_root, get_paths, Paths
from coin_quant.shared.data_access import FileBackend, DataBus, create_data_bus


def test_project_root_resolution():
    """Test that project root resolves correctly"""
    project_root = get_project_root()
    assert project_root.exists(), f"Project root should exist: {project_root}"
    assert (project_root / "pyproject.toml").exists() or (project_root / "src" / "coin_quant").exists(), \
        "Project root should contain pyproject.toml or src/coin_quant"


def test_paths_initialization():
    """Test that Paths class initializes correctly"""
    paths = get_paths()
    assert paths.project_root.exists(), "Project root should exist"
    assert paths.shared_data.exists() or not paths.shared_data.exists(), "shared_data may or may not exist"
    
    # Test path resolution
    assert isinstance(paths.health_dir, Path), "health_dir should be a Path object"
    assert isinstance(paths.databus_snapshot, Path), "databus_snapshot should be a Path object"


def test_paths_json_conversion():
    """Test that Paths can convert to JSON-serializable format"""
    paths = get_paths()
    
    # Test to_jsonable method
    test_data = {
        "health_dir": paths.health_dir,
        "databus_snapshot": paths.databus_snapshot,
        "nested": {
            "path": paths.project_root
        },
        "list": [paths.shared_data, "string", 123]
    }
    
    jsonable_data = paths.to_jsonable(test_data)
    
    # All Path objects should be converted to strings
    assert isinstance(jsonable_data["health_dir"], str), "health_dir should be converted to string"
    assert isinstance(jsonable_data["databus_snapshot"], str), "databus_snapshot should be converted to string"
    assert isinstance(jsonable_data["nested"]["path"], str), "nested path should be converted to string"
    assert isinstance(jsonable_data["list"][0], str), "list path should be converted to string"


def test_file_backend_missing_files():
    """Test that FileBackend handles missing files gracefully"""
    backend = FileBackend()
    
    # Test with non-existent file
    result = backend._safe_read_json(Path("/non/existent/file.json"))
    assert result is None, "Should return None for non-existent file"
    
    # Test with non-existent file and default value
    result = backend._safe_read_json(Path("/non/existent/file.json"), default={})
    assert result == {}, "Should return default value for non-existent file"


def test_data_bus_creation():
    """Test that DataBus can be created"""
    data_bus = create_data_bus()
    assert isinstance(data_bus, DataBus), "Should create DataBus instance"
    
    # Test repositories are initialized
    assert data_bus.prices is not None, "Price repository should be initialized"
    assert data_bus.signals is not None, "Signal repository should be initialized"
    assert data_bus.positions is not None, "Position repository should be initialized"
    assert data_bus.health is not None, "Health repository should be initialized"


def test_data_bus_symbol_data():
    """Test that DataBus can get symbol data without crashing"""
    data_bus = create_data_bus()
    
    # Test with a symbol that likely doesn't exist
    symbol_data = data_bus.get_symbol_data("TESTUSDT")
    
    # Should return a dict with expected structure
    assert isinstance(symbol_data, dict), "Should return a dictionary"
    assert "symbol" in symbol_data, "Should contain symbol key"
    assert "price" in symbol_data, "Should contain price key"
    assert "signal" in symbol_data, "Should contain signal key"
    assert "position" in symbol_data, "Should contain position key"


def test_data_bus_multiple_symbols():
    """Test that DataBus can handle multiple symbols"""
    data_bus = create_data_bus()
    
    symbols = ["BTCUSDT", "ETHUSDT", "TESTUSDT"]
    symbols_data = data_bus.get_all_symbols_data(symbols)
    
    assert isinstance(symbols_data, dict), "Should return a dictionary"
    assert len(symbols_data) == len(symbols), f"Should return data for all {len(symbols)} symbols"
    
    for symbol in symbols:
        assert symbol in symbols_data, f"Should contain data for {symbol}"
        assert isinstance(symbols_data[symbol], dict), f"Data for {symbol} should be a dictionary"


if __name__ == "__main__":
    print("Running UI Path and DAL tests...")
    
    try:
        test_project_root_resolution()
        print("✅ Project root resolution test passed")
        
        test_paths_initialization()
        print("✅ Paths initialization test passed")
        
        test_paths_json_conversion()
        print("✅ Paths JSON conversion test passed")
        
        test_file_backend_missing_files()
        print("✅ File backend missing files test passed")
        
        test_data_bus_creation()
        print("✅ Data bus creation test passed")
        
        test_data_bus_symbol_data()
        print("✅ Data bus symbol data test passed")
        
        test_data_bus_multiple_symbols()
        print("✅ Data bus multiple symbols test passed")
        
        print("\n🎉 All tests passed!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
