#!/usr/bin/env python3
"""
Environment Resolution
========================================
Robust environment variable resolution with multiple sources.

Resolution order (first-hit wins):
1. env_ssot.json
2. state_bus.json
3. .env / config.env
4. Streamlit secrets
5. Process environment

Features:
- Synonym support (is_testnet, use_testnet, BINANCE_USE_TESTNET)
- Boolean parsing (true/false, 1/0, yes/no)
- BOM-tolerant JSON/TOML parsing
- Debug source tracking
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# Environment file paths (resolution order)
ENV_SOURCES = [
    Path("shared_data/env_ssot.json"),
    Path("shared_data/state_bus.json"),
    Path("config.env"),
    Path(".env"),
]

# Synonym mappings
ENV_SYNONYMS = {
    "is_testnet": [
        "is_testnet",
        "use_testnet",
        "BINANCE_USE_TESTNET",
        "binance_use_testnet",
    ],
    "trading_mode": ["mode", "trading_mode", "TRADING_MODE"],
    "live_enabled": ["live_enabled", "LIVE_TRADING_ENABLED", "live_trading_enabled"],
}


def strip_bom(content: str) -> str:
    """
    Strip UTF-8 BOM and zero-width characters.

    Args:
        content: Raw file content

    Returns:
        Cleaned content
    """
    # UTF-8 BOM
    if content.startswith("\ufeff"):
        content = content[1:]

    # Zero-width characters
    zero_width_chars = [
        "\u200b",  # Zero width space
        "\u200c",  # Zero width non-joiner
        "\u200d",  # Zero width joiner
        "\ufeff",  # BOM
    ]

    for char in zero_width_chars:
        content = content.replace(char, "")

    return content


def parse_boolean(value: Any) -> bool:
    """
    Parse boolean from various formats.

    Accepts:
    - "true"/"false" (case-insensitive)
    - "True"/"False"
    - "yes"/"no"
    - 1/0
    - True/False

    Args:
        value: Value to parse

    Returns:
        Boolean value
    """
    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return value != 0

    if isinstance(value, str):
        value_lower = value.strip().lower()

        if value_lower in ["true", "yes", "1", "t", "y"]:
            return True

        if value_lower in ["false", "no", "0", "f", "n"]:
            return False

    # Default to False
    return False


def load_json_with_bom(path: Path) -> Optional[Dict]:
    """
    Load JSON file with BOM tolerance.

    Args:
        path: JSON file path

    Returns:
        Loaded dict or None
    """
    try:
        with open(path, "r", encoding="utf-8-sig") as f:  # utf-8-sig strips BOM
            content = f.read()
            content = strip_bom(content)
            return json.loads(content)

    except Exception:
        return None


def load_env_file(path: Path) -> Optional[Dict]:
    """
    Load .env file with BOM tolerance.

    Args:
        path: .env file path

    Returns:
        Dict of key=value pairs or None
    """
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            content = f.read()
            content = strip_bom(content)

        env_dict = {}
        for line in content.split("\n"):
            line = line.strip()

            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue

            # Parse key=value
            if "=" in line:
                key, value = line.split("=", 1)
                env_dict[key.strip()] = value.strip().strip('"').strip("'")

        return env_dict

    except Exception:
        return None


def resolve_env(key: str, default: Any = None) -> Tuple[Any, str]:
    """
    Resolve environment variable from multiple sources.

    Args:
        key: Environment variable key
        default: Default value if not found

    Returns:
        (value, source) tuple

    Resolution order:
        1. env_ssot.json
        2. state_bus.json
        3. config.env / .env
        4. Streamlit secrets (if available)
        5. Process environment
    """
    # Get synonyms for this key
    synonyms = ENV_SYNONYMS.get(key, [key])

    # 1. Check JSON sources
    for source_path in ENV_SOURCES:
        if not source_path.exists():
            continue

        if source_path.suffix == ".json":
            data = load_json_with_bom(source_path)
            if data:
                for synonym in synonyms:
                    if synonym in data:
                        return data[synonym], f"{source_path.name}:{synonym}"

        elif source_path.suffix == ".env":
            data = load_env_file(source_path)
            if data:
                for synonym in synonyms:
                    if synonym in data:
                        return data[synonym], f"{source_path.name}:{synonym}"

    # 4. Streamlit secrets
    try:
        import streamlit as st

        if hasattr(st, "secrets"):
            for synonym in synonyms:
                if synonym in st.secrets.get("env", {}):
                    return st.secrets["env"][synonym], f"st.secrets:{synonym}"
    except:
        pass

    # 5. Process environment
    for synonym in synonyms:
        if synonym in os.environ:
            return os.environ[synonym], f"os.environ:{synonym}"

    # Not found
    return default, "default"


def get_env_bool(key: str, default: bool = False) -> Tuple[bool, str]:
    """
    Get boolean environment variable.

    Args:
        key: Environment variable key
        default: Default value

    Returns:
        (bool_value, source)
    """
    value, source = resolve_env(key, default)
    return parse_boolean(value), source


def get_env_str(key: str, default: str = "") -> Tuple[str, str]:
    """
    Get string environment variable.

    Args:
        key: Environment variable key
        default: Default value

    Returns:
        (str_value, source)
    """
    value, source = resolve_env(key, default)
    return str(value) if value is not None else default, source


def get_all_env_debug() -> Dict[str, Dict]:
    """
    Get all environment variables with debug info.

    Returns:
        Dict of {key: {'value': ..., 'source': ...}}
    """
    keys_to_check = ["is_testnet", "trading_mode", "live_enabled"]

    debug_info = {}

    for key in keys_to_check:
        if key == "is_testnet":
            value, source = get_env_bool(key, False)
        else:
            value, source = get_env_str(key, "unknown")

        debug_info[key] = {"value": value, "source": source}

    return debug_info


# Unit tests
if __name__ == "__main__":
    import shutil
    import tempfile

    print("Testing environment resolution...")

    # Create temp directory
    test_dir = Path(tempfile.mkdtemp())

    try:
        # Test 1: Boolean parsing
        print("\n1. Boolean parsing:")

        test_cases = [
            ("true", True),
            ("false", False),
            ("True", True),
            ("False", False),
            ("yes", True),
            ("no", False),
            ("1", True),
            ("0", False),
            (True, True),
            (False, False),
            (1, True),
            (0, False),
        ]

        for input_val, expected in test_cases:
            result = parse_boolean(input_val)
            status = "✅" if result == expected else "❌"
            print(f"{status} parse_boolean({repr(input_val)}) = {result}")

        print("✅ Boolean parsing works")

        # Test 2: BOM stripping
        print("\n2. BOM stripping:")

        bom_content = '\ufeff{"test": true}'
        stripped = strip_bom(bom_content)
        assert stripped == '{"test": true}', "BOM should be stripped"
        print("✅ BOM stripping works")

        # Test 3: JSON with BOM
        print("\n3. JSON with BOM:")

        test_json = test_dir / "test_bom.json"
        with open(test_json, "w", encoding="utf-8-sig") as f:
            f.write('{"key": "value"}')

        data = load_json_with_bom(test_json)
        assert data == {"key": "value"}, "Should load despite BOM"
        print("✅ BOM-tolerant JSON loading works")

        # Test 4: .env file loading
        print("\n4. .env file loading:")

        test_env = test_dir / "test.env"
        test_env.write_text('KEY1=value1\nKEY2="value2"\n# Comment\nKEY3=value3')

        env_data = load_env_file(test_env)
        assert env_data["KEY1"] == "value1", "Should parse KEY1"
        assert env_data["KEY2"] == "value2", "Should strip quotes"
        assert env_data["KEY3"] == "value3", "Should parse KEY3"
        assert "Comment" not in env_data, "Should skip comments"
        print("✅ .env file loading works")

        print("\n" + "=" * 50)
        print("All environment resolution tests passed! ✅")
        print("=" * 50)

    finally:
        # Cleanup
        shutil.rmtree(test_dir, ignore_errors=True)
