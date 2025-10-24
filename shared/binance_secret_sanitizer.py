#!/usr/bin/env python3
"""
Binance API Secret Sanitizer
========================================
Strict sanitization and validation of API secrets.
"""

import logging
from typing import Tuple

logger = logging.getLogger(__name__)


def sanitize_secret(raw_secret: str) -> Tuple[str, dict]:
    """
    Sanitize API secret with strict validation.

    Args:
        raw_secret: Raw secret string from environment

    Returns:
        (sanitized_secret, metadata_dict)
    """
    metadata = {
        "original_len": len(raw_secret) if raw_secret else 0,
        "sanitized_len": 0,
        "changes_made": [],
        "printable_only": False,
        "has_non_ascii": False,
        "has_control_chars": False,
        "sanitized": False,
    }

    if not raw_secret:
        return "", metadata

    # Step 1: Strip leading/trailing whitespace
    step1 = raw_secret.strip()
    if len(step1) != len(raw_secret):
        metadata["changes_made"].append("whitespace_stripped")

    # Step 2: Remove surrounding quotes/backticks
    step2 = step1
    for quote_char in ['"', "'", "`"]:
        if (
            step2.startswith(quote_char)
            and step2.endswith(quote_char)
            and len(step2) > 1
        ):
            step2 = step2[1:-1]
            metadata["changes_made"].append(f"quotes_removed_{quote_char}")

    # Step 3: Check for BOM and remove
    if step2.startswith("\ufeff"):
        step2 = step2[1:]
        metadata["changes_made"].append("BOM_removed")

    # Step 4: Remove other control characters (but keep printable)
    step3 = ""
    has_control = False
    has_non_ascii = False

    for char in step2:
        # Check if character is printable ASCII (32-126)
        if 32 <= ord(char) <= 126:
            step3 += char
        elif char in ["\n", "\r", "\t"]:
            # Control chars - skip
            has_control = True
        elif ord(char) > 127:
            # Non-ASCII
            has_non_ascii = True
            # For API keys, we might want to keep them or reject
            # Binance keys are typically alphanumeric
            step3 += char  # Keep for now, but flag
        else:
            # Other control characters
            has_control = True

    if has_control:
        metadata["changes_made"].append("control_chars_removed")
        metadata["has_control_chars"] = True

    if has_non_ascii:
        metadata["has_non_ascii"] = True

    # Final sanitized secret
    sanitized = step3
    metadata["sanitized_len"] = len(sanitized)
    metadata["printable_only"] = all(32 <= ord(c) <= 126 for c in sanitized)
    metadata["sanitized"] = len(metadata["changes_made"]) > 0

    # Validation warnings
    if metadata["has_non_ascii"]:
        logger.warning("API secret contains non-ASCII characters - might be invalid")

    if not metadata["printable_only"]:
        logger.warning(
            "API secret contains non-printable characters - might be invalid"
        )

    if metadata["sanitized"]:
        logger.warning(f"SECRET_SANITIZED: {', '.join(metadata['changes_made'])}")
        logger.warning(
            f"Original length: {metadata['original_len']}, Sanitized: {metadata['sanitized_len']}"
        )

    return sanitized, metadata


def validate_secret_format(secret: str) -> Tuple[bool, str]:
    """
    Validate API secret format (Binance-specific).

    Args:
        secret: Sanitized secret

    Returns:
        (is_valid, error_message)
    """
    if not secret:
        return False, "Secret is empty"

    # Binance secrets are typically 64 characters, alphanumeric
    if len(secret) < 32:
        return False, f"Secret too short ({len(secret)} chars, expected ≥32)"

    if len(secret) > 128:
        return False, f"Secret too long ({len(secret)} chars, expected ≤128)"

    # Check if alphanumeric (Binance keys are typically base64-like)
    if not all(c.isalnum() or c in ["+", "/", "=", "-", "_"] for c in secret):
        return (
            False,
            "Secret contains invalid characters (expected alphanumeric + base64)",
        )

    return True, "OK"


if __name__ == "__main__":
    # Test cases
    test_cases = [
        ("normal_secret_12345678901234567890123456789012", "Normal secret"),
        (
            "  leading_spaces_123456789012345678901234567890  ",
            "Leading/trailing spaces",
        ),
        ('"quoted_secret_12345678901234567890123456789012"', "Quoted secret"),
        ("\ufeffBOM_secret_12345678901234567890123456789012", "BOM prefix"),
        ("secret\nwith\nnewlines123456789012345678901234", "Newlines"),
        ("secret\twith\ttabs12345678901234567890123456789", "Tabs"),
    ]

    print("=" * 60)
    print(" Secret Sanitizer Tests")
    print("=" * 60)
    print()

    for raw, description in test_cases:
        print(f"Test: {description}")
        print(f"  Raw length: {len(raw)}")

        sanitized, metadata = sanitize_secret(raw)

        print(f"  Sanitized length: {metadata['sanitized_len']}")
        print(f"  Changes: {metadata['changes_made']}")
        print(f"  Printable only: {metadata['printable_only']}")

        is_valid, msg = validate_secret_format(sanitized)
        print(f"  Valid: {is_valid} ({msg})")
        print()
