#!/usr/bin/env python3
"""
Health Schema Guard
Validates health.json structure before write to prevent corrupted health data
"""

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class HealthSchemaError(Exception):
    """Health schema validation error"""

    pass


def validate_health_schema(health_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Validate health.json schema before write.

    Required schema:
    {
        "ts": <unix_seconds>,
        "aggregator_pid": <int>,
        "components": {
            "feeder": { "symbols": {"BTCUSDT": {...}, "ETHUSDT": {...}}, ...},
            "trader": {...},
            "ares": {...}
        },
        "telemetry": {...} (optional)
    }

    Args:
        health_data: Health data to validate

    Returns:
        (is_valid, error_message)
    """
    try:
        # 1. Check top-level structure
        if not isinstance(health_data, dict):
            return False, f"Health data must be dict, got {type(health_data)}"

        # 2. Check required top-level fields
        if "ts" not in health_data:
            return False, "Missing required field: 'ts'"

        ts = health_data["ts"]
        if not isinstance(ts, (int, float)):
            return False, f"'ts' must be number, got {type(ts)}"

        # Validate ts is in seconds (not ms)
        if ts > 1e10:  # After year 2286 (milliseconds)
            return False, f"'ts' appears to be milliseconds ({ts}), must be seconds"

        # Validate ts is recent (within 1 hour)
        now = time.time()
        if abs(now - ts) > 3600:
            logger.warning(f"'ts' is stale: {ts} vs now {now} (diff: {abs(now - ts)}s)")

        if "aggregator_pid" in health_data:
            if not isinstance(health_data["aggregator_pid"], int):
                return (
                    False,
                    f"'aggregator_pid' must be int, got {type(health_data['aggregator_pid'])}",
                )

        # 3. Check components
        if "components" not in health_data:
            return False, "Missing required field: 'components'"

        components = health_data["components"]
        if not isinstance(components, dict):
            return False, f"'components' must be dict, got {type(components)}"

        # 4. Validate feeder component (most critical)
        if "feeder" in components:
            feeder = components["feeder"]
            if not isinstance(feeder, dict):
                return False, f"'components.feeder' must be dict, got {type(feeder)}"

            # Validate feeder.symbols
            if "symbols" in feeder:
                symbols = feeder["symbols"]
                if not isinstance(symbols, dict):
                    return (
                        False,
                        f"'components.feeder.symbols' must be dict, got {type(symbols)}",
                    )

                # Validate symbol keys are uppercase USDT pairs
                for symbol_key in symbols.keys():
                    if not isinstance(symbol_key, str):
                        return (
                            False,
                            f"Symbol key must be string, got {type(symbol_key)}: {symbol_key}",
                        )

                    if not symbol_key:
                        return False, "Empty symbol key found in feeder.symbols"

                    if symbol_key != symbol_key.upper():
                        return False, f"Symbol key must be UPPERCASE: {symbol_key}"

                    if not symbol_key.endswith("USDT"):
                        return False, f"Symbol key must end with USDT: {symbol_key}"

                    # Validate symbol value
                    symbol_data = symbols[symbol_key]
                    if not isinstance(symbol_data, dict):
                        return (
                            False,
                            f"Symbol data for {symbol_key} must be dict, got {type(symbol_data)}",
                        )

        # 5. Validate trader component (if present)
        if "trader" in components:
            trader = components["trader"]
            if not isinstance(trader, dict):
                return False, f"'components.trader' must be dict, got {type(trader)}"

        # 6. Validate ares component (if present)
        if "ares" in components:
            ares = components["ares"]
            if not isinstance(ares, dict):
                return False, f"'components.ares' must be dict, got {type(ares)}"

        # All checks passed
        return True, None

    except Exception as e:
        return False, f"Validation exception: {e}"


def guard_health_write(health_data: Dict[str, Any]) -> bool:
    """
    Guard health.json write - validate before allowing write.

    Args:
        health_data: Health data to validate

    Returns:
        True if validation passed, False otherwise
    """
    is_valid, error_msg = validate_health_schema(health_data)

    if not is_valid:
        logger.error(f"❌ HEALTH_SCHEMA_GUARD: Validation failed: {error_msg}")
        logger.error(
            "Refusing to write invalid health data - keeping last good version"
        )
        return False

    logger.debug("✅ HEALTH_SCHEMA_GUARD: Validation passed")
    return True


def normalize_health_timestamps(health_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize all timestamps in health data to seconds.

    Args:
        health_data: Health data to normalize

    Returns:
        Normalized health data
    """
    data = health_data.copy()

    # Normalize top-level ts
    if "ts" in data and isinstance(data["ts"], (int, float)):
        if data["ts"] > 1e10:  # Milliseconds
            logger.warning(
                f"Converting health.ts from ms to s: {data['ts']} → {data['ts'] / 1000}"
            )
            data["ts"] = int(data["ts"] / 1000)

    # Normalize component timestamps
    if "components" in data and isinstance(data["components"], dict):
        for component_name, component_data in data["components"].items():
            if isinstance(component_data, dict):
                # Normalize last_update
                if "last_update" in component_data:
                    lu = component_data["last_update"]
                    if isinstance(lu, (int, float)) and lu > 1e10:
                        logger.warning(
                            f"Converting {component_name}.last_update from ms to s"
                        )
                        component_data["last_update"] = int(lu / 1000)

                # Normalize symbol timestamps in feeder
                if component_name == "feeder" and "symbols" in component_data:
                    symbols = component_data["symbols"]
                    if isinstance(symbols, dict):
                        for symbol_key, symbol_data in symbols.items():
                            if (
                                isinstance(symbol_data, dict)
                                and "last_update" in symbol_data
                            ):
                                lu = symbol_data["last_update"]
                                if isinstance(lu, (int, float)) and lu > 1e10:
                                    symbol_data["last_update"] = int(lu / 1000)

    return data


if __name__ == "__main__":
    # Self-test

    # Valid health data
    valid_health = {
        "ts": int(time.time()),
        "aggregator_pid": 12345,
        "components": {
            "feeder": {
                "symbols": {
                    "BTCUSDT": {"last_update": int(time.time()), "status": "active"},
                    "ETHUSDT": {"last_update": int(time.time()), "status": "active"},
                },
                "status": "running",
            },
            "trader": {"status": "running"},
            "ares": {"status": "running"},
        },
    }

    is_valid, error = validate_health_schema(valid_health)
    print(f"Valid health test: {is_valid} (error: {error})")
    assert is_valid, f"Should be valid: {error}"

    # Invalid: lowercase symbol
    invalid_lowercase = valid_health.copy()
    invalid_lowercase["components"] = {
        "feeder": {
            "symbols": {
                "btcusdt": {"status": "active"},  # lowercase
            }
        }
    }

    is_valid, error = validate_health_schema(invalid_lowercase)
    print(f"Lowercase symbol test: {is_valid} (error: {error})")
    assert not is_valid, "Should reject lowercase symbol"

    # Invalid: empty symbol
    invalid_empty = valid_health.copy()
    invalid_empty["components"] = {
        "feeder": {
            "symbols": {
                "": {"status": "active"},  # empty
            }
        }
    }

    is_valid, error = validate_health_schema(invalid_empty)
    print(f"Empty symbol test: {is_valid} (error: {error})")
    assert not is_valid, "Should reject empty symbol"

    # Invalid: milliseconds timestamp
    invalid_ms = valid_health.copy()
    invalid_ms["ts"] = int(time.time() * 1000)  # ms

    is_valid, error = validate_health_schema(invalid_ms)
    print(f"Milliseconds timestamp test: {is_valid} (error: {error})")
    assert not is_valid, "Should reject milliseconds timestamp"

    print("✅ All tests passed")
