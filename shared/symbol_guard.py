#!/usr/bin/env python3
"""
Symbol Guard - Pre-flight Validation
====================================
Scan inputs for lowercase symbols and malformed data before service starts.

Usage:
    from shared.symbol_guard import feeder_guard, trader_guard
    
    # In service startup
    feeder_guard()  # Abort if violations found
"""

import json
import logging
import re
import sys
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger(__name__)


def scan_for_lowercase_usdt(root: Path, max_size_mb: int = 30) -> List[Tuple[Path, str]]:
    """
    Scan for lowercase *usdt patterns in JSON/JSONL files.
    
    Args:
        root: Root directory to scan
        max_size_mb: Maximum file size to scan (MB)
    
    Returns:
        List of (file_path, offending_content) tuples
    """
    violations = []
    max_bytes = max_size_mb * 1024 * 1024
    
    # Scan JSON and JSONL files
    patterns = ["**/*.json", "**/*.jsonl"]
    
    for pattern in patterns:
        for file_path in root.glob(pattern):
            if not file_path.is_file():
                continue
            
            try:
                if file_path.stat().st_size > max_bytes:
                    continue
                
                content = file_path.read_text(encoding='utf-8')
                
                # Check for lowercase usdt patterns
                matches = re.findall(r'\b[a-z]+usdt\b', content)
                if matches:
                    violations.append((file_path, ', '.join(set(matches)[:5])))
            except Exception as e:
                logger.warning(f"Failed to scan {file_path}: {e}")
    
    return violations


def scan_for_malformed_symbols(root: Path, max_size_mb: int = 30) -> List[Tuple[Path, str]]:
    """
    Scan for malformed "symbol" fields (empty, lowercase, multi-quote).
    
    Args:
        root: Root directory to scan
        max_size_mb: Maximum file size to scan (MB)
    
    Returns:
        List of (file_path, issue_description) tuples
    """
    violations = []
    max_bytes = max_size_mb * 1024 * 1024
    
    patterns = ["**/*.json", "**/*.jsonl"]
    
    for pattern in patterns:
        for file_path in root.glob(pattern):
            if not file_path.is_file():
                continue
            
            try:
                if file_path.stat().st_size > max_bytes:
                    continue
                
                content = file_path.read_text(encoding='utf-8')
                
                # Check for empty symbols
                if re.search(r'"symbol"\s*:\s*""', content):
                    violations.append((file_path, "Empty symbol field"))
                    continue
                
                # Check for lowercase in symbol value
                if re.search(r'"symbol"\s*:\s*"[^"]*[a-z][^"]*usdt[^"]*"', content, re.IGNORECASE):
                    # Extract the actual symbol for reporting
                    match = re.search(r'"symbol"\s*:\s*"([^"]*)"', content)
                    if match:
                        symbol_value = match.group(1)
                        if symbol_value and symbol_value != symbol_value.upper():
                            violations.append((file_path, f"Lowercase symbol: {symbol_value}"))
                            continue
            except Exception as e:
                logger.warning(f"Failed to scan {file_path}: {e}")
    
    return violations


def validate_or_abort(service_name: str, data_dirs: List[str], abort_on_fail: bool = True):
    """
    Run pre-flight validation. Abort if violations found.
    
    Args:
        service_name: Name of service (for logging)
        data_dirs: List of directories to scan (relative to repo root)
        abort_on_fail: If True, exit on violations; if False, just log
    
    Returns:
        True if validation passed, False otherwise
    """
    logger.info(f"[{service_name}] Running symbol guard pre-flight check...")
    
    repo_root = Path(__file__).parent.parent
    all_violations = []
    
    for data_dir in data_dirs:
        scan_root = repo_root / data_dir
        if not scan_root.exists():
            logger.debug(f"[{service_name}] Skipping non-existent directory: {data_dir}")
            continue
        
        # Scan for lowercase
        lowercase_violations = scan_for_lowercase_usdt(scan_root)
        for file_path, issue in lowercase_violations:
            all_violations.append((file_path, f"Lowercase: {issue}"))
        
        # Scan for malformed
        malformed_violations = scan_for_malformed_symbols(scan_root)
        all_violations.extend(malformed_violations)
    
    if all_violations:
        logger.error(f"❌ [{service_name}] Symbol guard FAILED - {len(all_violations)} violation(s) detected:")
        
        # Show first 10 violations
        for file_path, issue in all_violations[:10]:
            try:
                rel_path = file_path.relative_to(repo_root)
            except ValueError:
                rel_path = file_path
            logger.error(f"  {rel_path}: {issue}")
        
        if len(all_violations) > 10:
            logger.error(f"  ... and {len(all_violations) - 10} more violation(s)")
        
        logger.error("")
        logger.error("🛠️  To fix, run:")
        logger.error("   python tools/sanitize_symbols.py")
        logger.error("")
        
        if abort_on_fail:
            sys.exit(1)
        
        return False
    
    logger.info(f"✅ [{service_name}] Symbol guard passed - no violations detected")
    return True


# ============================================================================
# Service-specific guards
# ============================================================================

def feeder_guard(abort_on_fail: bool = True) -> bool:
    """
    Pre-flight check for Feeder service.
    
    Args:
        abort_on_fail: If True, exit on violations
    
    Returns:
        True if validation passed
    """
    return validate_or_abort(
        "Feeder",
        ["shared_data/health", "shared_data/data", "shared_data"],
        abort_on_fail=abort_on_fail
    )


def trader_guard(abort_on_fail: bool = True) -> bool:
    """
    Pre-flight check for Trader service.
    
    Args:
        abort_on_fail: If True, exit on violations
    
    Returns:
        True if validation passed
    """
    return validate_or_abort(
        "Trader",
        ["shared_data/data", "shared_data"],
        abort_on_fail=abort_on_fail
    )


def ares_guard(abort_on_fail: bool = True) -> bool:
    """
    Pre-flight check for ARES service.
    
    Args:
        abort_on_fail: If True, exit on violations
    
    Returns:
        True if validation passed
    """
    return validate_or_abort(
        "ARES",
        ["shared_data/data", "shared_data"],
        abort_on_fail=abort_on_fail
    )


def account_snapshot_guard(abort_on_fail: bool = True) -> bool:
    """
    Pre-flight check for Account Snapshot service.
    
    Args:
        abort_on_fail: If True, exit on violations
    
    Returns:
        True if validation passed
    """
    return validate_or_abort(
        "AccountSnapshot",
        ["shared_data/accounts", "shared_data"],
        abort_on_fail=abort_on_fail
    )


# ============================================================================
# Quick validation (no abort)
# ============================================================================

def quick_validate(data_dir: str = "shared_data") -> Tuple[bool, int]:
    """
    Quick validation without abort.
    
    Args:
        data_dir: Directory to scan
    
    Returns:
        (passed, violation_count)
    """
    repo_root = Path(__file__).parent.parent
    scan_root = repo_root / data_dir
    
    if not scan_root.exists():
        return True, 0
    
    violations = []
    violations.extend(scan_for_lowercase_usdt(scan_root))
    violations.extend(scan_for_malformed_symbols(scan_root))
    
    return (len(violations) == 0, len(violations))


# ============================================================================
# Testing & CLI
# ============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Symbol Guard - Pre-flight Validation")
    parser.add_argument(
        "--service",
        choices=["feeder", "trader", "ares", "account_snapshot", "all"],
        default="all",
        help="Service to validate"
    )
    parser.add_argument(
        "--no-abort",
        action="store_true",
        help="Don't abort on violations, just report"
    )
    
    args = parser.parse_args()
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s: %(message)s'
    )
    
    abort_on_fail = not args.no_abort
    
    if args.service == "all":
        # Run all guards
        results = {
            "feeder": feeder_guard(abort_on_fail=False),
            "trader": trader_guard(abort_on_fail=False),
            "ares": ares_guard(abort_on_fail=False),
            "account_snapshot": account_snapshot_guard(abort_on_fail=False),
        }
        
        print("\n" + "=" * 60)
        print("Symbol Guard Report")
        print("=" * 60)
        
        all_passed = True
        for service, passed in results.items():
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"  {service:20s} {status}")
            if not passed:
                all_passed = False
        
        print("=" * 60)
        
        if all_passed:
            print("✅ All services passed")
            sys.exit(0)
        else:
            print("❌ Some services failed")
            if abort_on_fail:
                sys.exit(1)
    
    elif args.service == "feeder":
        feeder_guard(abort_on_fail=abort_on_fail)
    elif args.service == "trader":
        trader_guard(abort_on_fail=abort_on_fail)
    elif args.service == "ares":
        ares_guard(abort_on_fail=abort_on_fail)
    elif args.service == "account_snapshot":
        account_snapshot_guard(abort_on_fail=abort_on_fail)

