#!/usr/bin/env python3
"""
API Gate Module
===============
Controls dashboard access based on API test results.
Only allows full dashboard if all 4 tests are GREEN.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional


def load_api_test_results() -> Optional[Dict[str, Any]]:
    """Load API test results from shared_data"""
    test_file = Path(__file__).parent.parent / "shared_data" / "api_test_results.json"

    if not test_file.exists():
        return None

    try:
        with open(test_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def check_api_gate() -> tuple[bool, str]:
    """
    Check if API gate is passed (all 4 tests GREEN).

    Returns:
        (passed: bool, message: str)
        - passed: True if all tests passed, False otherwise
        - message: Status message or hint for failed test
    """
    test_results = load_api_test_results()

    if not test_results:
        return (
            False,
            "No API test results found. Run self-test in Account API Status panel.",
        )

    all_passed = test_results.get("all_tests_passed", False)

    if all_passed:
        return True, "All API tests passed - dashboard ready"

    # Find first failed test
    tests = test_results.get("tests", [])
    for test in tests:
        if not test.get("success", False):
            step = test.get("step", "?")
            description = test.get("description", "Unknown")
            msg = test.get("msg", "Failed")
            return False, f"Test {step} failed: {description} - {msg}"

    return False, "Some API tests failed. Check Account API Status panel."


def get_api_gate_summary() -> Dict[str, Any]:
    """
    Get comprehensive API gate status summary.

    Returns:
        Dict with:
        - passed: bool
        - message: str
        - tests_passed: int
        - tests_total: int
        - base_url: str
        - clock_offset_ms: int
        - recv_window: int
    """
    test_results = load_api_test_results()

    if not test_results:
        return {
            "passed": False,
            "message": "No test results available",
            "tests_passed": 0,
            "tests_total": 4,
            "base_url": "N/A",
            "clock_offset_ms": 0,
            "recv_window": 10000,
        }

    summary = test_results.get("summary", {})

    return {
        "passed": test_results.get("all_tests_passed", False),
        "message": (
            "All tests passed"
            if test_results.get("all_tests_passed", False)
            else "Some tests failed"
        ),
        "tests_passed": summary.get("passed", 0),
        "tests_total": summary.get("total", 4),
        "base_url": test_results.get("base_url", "N/A"),
        "clock_offset_ms": test_results.get("clock_offset_ms", 0),
        "recv_window": test_results.get("recv_window", 10000),
    }


if __name__ == "__main__":
    # Test the gate
    passed, message = check_api_gate()
    print(f"API Gate: {'PASSED' if passed else 'FAILED'}")
    print(f"Message: {message}")

    summary = get_api_gate_summary()
    print(f"\nSummary:")
    print(f"  Tests: {summary['tests_passed']}/{summary['tests_total']}")
    print(f"  Base URL: {summary['base_url']}")
    print(f"  Clock offset: {summary['clock_offset_ms']}ms")
