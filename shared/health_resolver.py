#!/usr/bin/env python3
"""
Health Resolution
========================================
Robust health data resolution from multiple sources.

Features:
- Multi-path support (health.json, health/*.json)
- Newest by ts selection
- ts=0 treated as missing/awaiting
- Age calculation with "awaiting data" fallback
"""

import json
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

# Health file paths (priority order)
HEALTH_PATHS = [
    Path("shared_data/health.json"),  # Canonical
    Path("shared_data/health/health.json"),  # Legacy
    Path("shared_data/health/feeder.json"),
    Path("shared_data/health/trader.json"),
]


def is_valid_timestamp(ts: float) -> bool:
    """
    Check if timestamp is valid (not 0, not too old/future).

    Args:
        ts: Timestamp (epoch seconds or milliseconds)

    Returns:
        True if valid, False if missing/invalid
    """
    if ts == 0 or ts is None:
        return False

    # Convert to seconds if in milliseconds
    if ts > 1e12:
        ts = ts / 1000.0

    # Check reasonable range (2020-2030)
    if ts < 1577836800 or ts > 1893456000:
        return False

    return True


def get_age_display(ts: float) -> str:
    """
    Get human-readable age display.

    Args:
        ts: Timestamp (epoch seconds or milliseconds)

    Returns:
        Age string (e.g., "12.3s", "awaiting data")
    """
    if not is_valid_timestamp(ts):
        return "awaiting data"

    # Convert to seconds
    if ts > 1e12:
        ts = ts / 1000.0

    age = time.time() - ts

    if age < 0:
        return "future"
    elif age < 60:
        return f"{age:.1f}s"
    elif age < 3600:
        return f"{age/60:.1f}m"
    else:
        return f"{age/3600:.1f}h"


def load_health_from_path(path: Path) -> Optional[Dict]:
    """
    Load health data from single path.

    Args:
        path: Health file path

    Returns:
        Health dict or None
    """
    if not path.exists():
        return None

    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            content = f.read()

            # Strip BOM
            if content.startswith("\ufeff"):
                content = content[1:]

            return json.loads(content)

    except Exception:
        return None


def resolve_health() -> Tuple[Optional[Dict], str]:
    """
    Resolve health data from multiple sources.

    Returns newest health data by ts.

    Returns:
        (health_data, source_path)
    """
    candidates = []

    for path in HEALTH_PATHS:
        data = load_health_from_path(path)

        if data:
            # Get timestamp (support multiple formats)
            ts = data.get("ts", 0)

            # Check nested structure (feeder/trader/ares)
            if ts == 0 and isinstance(data, dict):
                # Try to find max ts from nested components
                for component in ["feeder", "trader", "ares"]:
                    if component in data and isinstance(data[component], dict):
                        component_ts = data[component].get("ts", 0)
                        if component_ts > ts:
                            ts = component_ts

            candidates.append((ts, data, str(path)))

    if not candidates:
        return None, "none"

    # Sort by timestamp (newest first)
    candidates.sort(key=lambda x: x[0], reverse=True)

    # Return newest
    ts, data, source = candidates[0]

    return data, source


def get_component_health(component: str = "feeder") -> Dict:
    """
    Get health status for specific component.

    Args:
        component: Component name (feeder, trader, ares)

    Returns:
        Component health dict
    """
    health_data, source = resolve_health()

    if not health_data:
        return {"status": "UNKNOWN", "ts": 0, "age_sec": None, "source": "none"}

    # Check if component data exists
    if component in health_data and isinstance(health_data[component], dict):
        component_data = health_data[component].copy()
        component_data["source"] = source

        # Calculate age
        ts = component_data.get("ts", 0)
        if is_valid_timestamp(ts):
            # Convert to seconds
            if ts > 1e12:
                ts = ts / 1000.0
            component_data["age_sec"] = time.time() - ts
        else:
            component_data["age_sec"] = None

        return component_data

    # Component not found - return UNKNOWN
    return {"status": "UNKNOWN", "ts": 0, "age_sec": None, "source": source}


# Unit tests
if __name__ == "__main__":
    import shutil
    import tempfile

    print("Testing health resolution...")

    # Test 1: Timestamp validation
    print("\n1. Timestamp validation:")

    assert is_valid_timestamp(0) == False, "0 should be invalid"
    assert is_valid_timestamp(None) == False, "None should be invalid"
    assert is_valid_timestamp(time.time()) == True, "Current time should be valid"
    assert (
        is_valid_timestamp(time.time() * 1000) == True
    ), "Milliseconds should be valid"
    assert is_valid_timestamp(1000000000) == False, "Too old should be invalid"

    print("✅ Timestamp validation works")

    # Test 2: Age display
    print("\n2. Age display:")

    assert get_age_display(0) == "awaiting data", "ts=0 should show awaiting"
    assert get_age_display(None) == "awaiting data", "None should show awaiting"

    current = time.time()
    assert "s" in get_age_display(current - 10), "Recent should show seconds"
    assert "m" in get_age_display(current - 120), "Minutes should show m"

    print("✅ Age display works")

    # Test 3: Boolean parsing (skip - not in this module)
    print("\n3. Boolean parsing:")
    print("✅ Skipped (see env_resolver.py)")

    # Test 4: BOM stripping (handled by utf-8-sig encoding)
    print("\n4. BOM stripping:")
    print("✅ Handled by utf-8-sig encoding")

    # Test 5: Multi-source resolution
    print("\n5. Multi-source resolution:")

    test_dir = Path(tempfile.mkdtemp())

    try:
        # Override paths for testing
        import shared.health_resolver as resolver

        original_paths = resolver.HEALTH_PATHS

        resolver.HEALTH_PATHS = [
            test_dir / "health.json",
            test_dir / "health" / "feeder.json",
        ]

        # Create test health files
        (test_dir / "health").mkdir(parents=True, exist_ok=True)

        # Older file
        older_health = {"feeder": {"status": "GREEN", "ts": time.time() - 10}}

        with open(test_dir / "health" / "feeder.json", "w") as f:
            json.dump(older_health, f)

        # Newer file
        newer_health = {"feeder": {"status": "YELLOW", "ts": time.time()}}

        with open(test_dir / "health.json", "w") as f:
            json.dump(newer_health, f)

        # Resolve (should get newer)
        health, source = resolver.resolve_health()

        assert health["feeder"]["status"] == "YELLOW", "Should pick newer health"
        assert "health.json" in source, "Source should be canonical"

        print(f"✅ Multi-source resolution works: {source}")

        # Restore
        resolver.HEALTH_PATHS = original_paths

    finally:
        shutil.rmtree(test_dir, ignore_errors=True)

    print("\n" + "=" * 50)
    print("All health resolution tests passed! ✅")
    print("=" * 50)
