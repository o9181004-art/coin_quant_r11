#!/usr/bin/env python3
"""
Watchlist Loader V2 - UPPERCASE SSOT Enforcement
================================================
Single Source of Truth for watchlist with strict UPPERCASE policy.

Priority Order:
1. Environment variable WATCHLIST (comma-separated)
2. shared_data/watchlist.txt (canonical file)
3. config.env WATCHLIST setting
4. Fallback: BTCUSDT

Guarantees:
- All symbols returned as UPPERCASE
- Deprecation warnings for legacy locations
- Duplicate file detection
- Fail-fast on conflicting watchlists
"""

import json
import logging
import os
from pathlib import Path
from typing import List, Optional, Set, Tuple

from shared.symbol_normalizer import normalize_list, normalize_symbol

logger = logging.getLogger(__name__)

# ====================================================
# SSOT Configuration
# ====================================================

# Canonical watchlist file (SSOT)
CANONICAL_WATCHLIST_PATH = Path("shared_data") / "watchlist.txt"

# Legacy paths (deprecated, will trigger warnings)
LEGACY_PATHS = [
    Path("shared_data") / "coin_watchlist.json",
    Path("config") / "watchlist.txt",
    Path("watchlist.json"),
]

# Default fallback
DEFAULT_WATCHLIST = ["BTCUSDT"]


class WatchlistLoader:
    """
    Watchlist Loader V2 - UPPERCASE SSOT
    
    Features:
    - Strict UPPERCASE enforcement
    - Single Source of Truth priority
    - Legacy path deprecation warnings
    - Duplicate file detection
    - Runtime guards
    """
    
    def __init__(self, max_symbols: int = 40):
        """
        Initialize watchlist loader.
        
        Args:
            max_symbols: Maximum number of symbols allowed
        """
        self.max_symbols = max_symbols
        self.logger = logging.getLogger(__name__)
        
        # State tracking
        self._cached_watchlist: Optional[List[str]] = None
        self._source: Optional[str] = None
        self._warned_legacy: Set[str] = set()
    
    def load_watchlist(self, fail_on_conflict: bool = True) -> List[str]:
        """
        Load watchlist from SSOT with priority fallback.
        
        Priority:
        1. ENV var WATCHLIST
        2. shared_data/watchlist.txt (canonical)
        3. config.env WATCHLIST
        4. Fallback: BTCUSDT
        
        Args:
            fail_on_conflict: If True, exit on conflicting watchlists
        
        Returns:
            List of UPPERCASE symbols
        
        Raises:
            SystemExit: If fail_on_conflict=True and conflicts detected
        """
        # Check for duplicate/conflicting files
        if fail_on_conflict:
            self._check_conflicts()
        
        # Priority 1: Environment variable
        env_watchlist = os.getenv("WATCHLIST", "").strip()
        if env_watchlist:
            symbols = [s.strip() for s in env_watchlist.split(",") if s.strip()]
            if symbols:
                normalized = normalize_list(symbols, source="env:WATCHLIST")
                self._source = "env:WATCHLIST"
                self._cached_watchlist = self._enforce_limits(normalized)
                self.logger.info(
                    f"✅ Watchlist loaded from ENV: {len(self._cached_watchlist)} symbols (UPPERCASE enforced)"
                )
                return self._cached_watchlist
        
        # Priority 2: Canonical file (shared_data/watchlist.txt)
        if CANONICAL_WATCHLIST_PATH.exists():
            try:
                symbols = self._load_from_file(CANONICAL_WATCHLIST_PATH)
                if symbols:
                    normalized = normalize_list(symbols, source=f"file:{CANONICAL_WATCHLIST_PATH}")
                    self._source = str(CANONICAL_WATCHLIST_PATH)
                    self._cached_watchlist = self._enforce_limits(normalized)
                    self.logger.info(
                        f"✅ Watchlist loaded from canonical file: {len(self._cached_watchlist)} symbols (UPPERCASE enforced)"
                    )
                    return self._cached_watchlist
            except Exception as e:
                self.logger.error(f"Failed to load canonical watchlist: {e}")
        
        # Priority 3: Check legacy paths (with deprecation warning)
        for legacy_path in LEGACY_PATHS:
            if legacy_path.exists() and str(legacy_path) not in self._warned_legacy:
                self._warned_legacy.add(str(legacy_path))
                self.logger.warning(
                    f"⚠️ DEPRECATED: Watchlist found at {legacy_path}. "
                    f"Please migrate to {CANONICAL_WATCHLIST_PATH}"
                )
                
                try:
                    symbols = self._load_from_file(legacy_path)
                    if symbols:
                        normalized = normalize_list(symbols, source=f"file:{legacy_path}")
                        self._source = f"{legacy_path} (deprecated)"
                        self._cached_watchlist = self._enforce_limits(normalized)
                        self.logger.info(
                            f"✅ Watchlist loaded from legacy file: {len(self._cached_watchlist)} symbols"
                        )
                        return self._cached_watchlist
                except Exception as e:
                    self.logger.error(f"Failed to load legacy watchlist from {legacy_path}: {e}")
        
        # Priority 4: Fallback to default
        self.logger.warning(f"⚠️ No watchlist found, using default: {DEFAULT_WATCHLIST}")
        self._source = "default"
        self._cached_watchlist = DEFAULT_WATCHLIST.copy()
        
        # Create canonical file with default
        self._save_to_canonical(self._cached_watchlist)
        
        return self._cached_watchlist
    
    def _load_from_file(self, path: Path) -> List[str]:
        """
        Load symbols from file (supports .txt and .json).
        
        Args:
            path: Path to watchlist file
        
        Returns:
            List of raw symbols (not normalized yet)
        """
        if not path.exists():
            return []
        
        content = path.read_text(encoding="utf-8").strip()
        
        if not content:
            return []
        
        # JSON format
        if path.suffix == ".json":
            try:
                data = json.loads(content)
                if isinstance(data, list):
                    return [str(s).strip() for s in data if s]
                return []
            except json.JSONDecodeError:
                self.logger.error(f"Invalid JSON in {path}")
                return []
        
        # Plain text format (one symbol per line or comma-separated)
        lines = content.replace(",", "\n").split("\n")
        return [line.strip() for line in lines if line.strip()]
    
    def _save_to_canonical(self, symbols: List[str]):
        """
        Save watchlist to canonical file.
        
        Args:
            symbols: List of UPPERCASE symbols
        """
        try:
            CANONICAL_WATCHLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
            
            # Save as plain text (one symbol per line)
            content = "\n".join(symbols)
            CANONICAL_WATCHLIST_PATH.write_text(content, encoding="utf-8")
            
            self.logger.info(f"✅ Saved watchlist to canonical file: {CANONICAL_WATCHLIST_PATH}")
        except Exception as e:
            self.logger.error(f"Failed to save canonical watchlist: {e}")
    
    def _enforce_limits(self, symbols: List[str]) -> List[str]:
        """
        Enforce max symbols limit.
        
        Args:
            symbols: List of symbols
        
        Returns:
            Truncated list if needed
        """
        if len(symbols) > self.max_symbols:
            self.logger.warning(
                f"⚠️ Watchlist contains {len(symbols)} symbols, "
                f"exceeds limit of {self.max_symbols}. Using first {self.max_symbols}."
            )
            return symbols[: self.max_symbols]
        
        return symbols
    
    def _check_conflicts(self):
        """
        Check for conflicting watchlist files.
        Fails fast if multiple files with different content exist.
        """
        existing_files = []
        contents = {}
        
        # Check canonical path
        if CANONICAL_WATCHLIST_PATH.exists():
            try:
                symbols = normalize_list(
                    self._load_from_file(CANONICAL_WATCHLIST_PATH),
                    source="conflict_check"
                )
                existing_files.append(CANONICAL_WATCHLIST_PATH)
                contents[str(CANONICAL_WATCHLIST_PATH)] = set(symbols)
            except Exception:
                pass
        
        # Check legacy paths
        for legacy_path in LEGACY_PATHS:
            if legacy_path.exists():
                try:
                    symbols = normalize_list(
                        self._load_from_file(legacy_path),
                        source="conflict_check"
                    )
                    existing_files.append(legacy_path)
                    contents[str(legacy_path)] = set(symbols)
                except Exception:
                    pass
        
        # No conflicts if 0 or 1 file
        if len(existing_files) <= 1:
            return
        
        # Check if all files have same content
        all_contents = list(contents.values())
        first_content = all_contents[0]
        
        if all(content == first_content for content in all_contents):
            # Same content, just warn about duplicates
            self.logger.warning(
                f"⚠️ Multiple watchlist files detected (same content): "
                f"{[str(p) for p in existing_files]}\n"
                f"  → Recommend keeping only: {CANONICAL_WATCHLIST_PATH}"
            )
            return
        
        # Different content - fail fast
        self.logger.error(
            f"❌ WATCHLIST CONFLICT DETECTED:\n"
            f"  Files: {[str(p) for p in existing_files]}\n"
            f"  Contents differ - cannot determine correct watchlist.\n"
            f"  Remediation:\n"
            f"    1. Review each file\n"
            f"    2. Choose correct watchlist\n"
            f"    3. Save to {CANONICAL_WATCHLIST_PATH}\n"
            f"    4. Delete other files"
        )
        raise SystemExit(1)
    
    def get_source(self) -> str:
        """Get current watchlist source"""
        return self._source or "not loaded"
    
    def save_watchlist(self, symbols: List[str]) -> bool:
        """
        Save watchlist to canonical file (with UPPERCASE enforcement).
        
        Args:
            symbols: List of symbols (any case)
        
        Returns:
            True if successful
        """
        try:
            # Normalize to UPPERCASE
            normalized = normalize_list(symbols, source="save_watchlist")
            
            # Enforce limits
            limited = self._enforce_limits(normalized)
            
            # Save to canonical
            self._save_to_canonical(limited)
            
            # Update cache
            self._cached_watchlist = limited
            self._source = str(CANONICAL_WATCHLIST_PATH)
            
            return True
        except Exception as e:
            self.logger.error(f"Failed to save watchlist: {e}")
            return False
    
    def add_symbol(self, symbol: str) -> bool:
        """
        Add symbol to watchlist (with UPPERCASE enforcement).
        
        Args:
            symbol: Symbol to add (any case)
        
        Returns:
            True if successful
        """
        current = self.load_watchlist(fail_on_conflict=False)
        normalized = normalize_symbol(symbol, source="add_symbol")
        
        if normalized in current:
            self.logger.warning(f"Symbol already in watchlist: {normalized}")
            return False
        
        if len(current) >= self.max_symbols:
            self.logger.error(f"Watchlist full ({self.max_symbols} symbols)")
            return False
        
        current.append(normalized)
        return self.save_watchlist(current)
    
    def remove_symbol(self, symbol: str) -> bool:
        """
        Remove symbol from watchlist (case-insensitive).
        
        Args:
            symbol: Symbol to remove (any case)
        
        Returns:
            True if successful
        """
        current = self.load_watchlist(fail_on_conflict=False)
        normalized = normalize_symbol(symbol, source="remove_symbol")
        
        if normalized not in current:
            self.logger.warning(f"Symbol not in watchlist: {normalized}")
            return False
        
        current.remove(normalized)
        return self.save_watchlist(current)
    
    def validate_all_uppercase(self) -> Tuple[bool, List[str]]:
        """
        Validate that all symbols in watchlist are UPPERCASE.
        
        Returns:
            (all_uppercase, violations) - violations is list of non-uppercase symbols
        """
        current = self.load_watchlist(fail_on_conflict=False)
        violations = [s for s in current if s != s.upper()]
        
        return (len(violations) == 0, violations)
    
    def get_watchlist_summary(self) -> str:
        """Get one-line watchlist summary for logging"""
        symbols = self.load_watchlist(fail_on_conflict=False)
        return f"watchlist={','.join(symbols)} (source={self.get_source()}, UPPERCASE=enforced)"


# ====================================================
# Module-level convenience functions
# ====================================================

def load_watchlist() -> List[str]:
    """Convenience function to load watchlist (singleton pattern)"""
    loader = WatchlistLoader()
    return loader.load_watchlist()


def get_watchlist_summary() -> str:
    """Convenience function to get watchlist summary"""
    loader = WatchlistLoader()
    return loader.get_watchlist_summary()


# ====================================================
# Testing
# ====================================================
if __name__ == "__main__":
    import sys
    
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    
    print("=" * 60)
    print("Watchlist Loader V2 Test")
    print("=" * 60)
    
    loader = WatchlistLoader()
    
    # Test 1: Load watchlist
    print("\n[Test 1] Load Watchlist")
    symbols = loader.load_watchlist()
    print(f"  Loaded: {symbols}")
    print(f"  Source: {loader.get_source()}")
    
    # Test 2: UPPERCASE validation
    print("\n[Test 2] UPPERCASE Validation")
    all_upper, violations = loader.validate_all_uppercase()
    if all_upper:
        print("  ✅ All symbols are UPPERCASE")
    else:
        print(f"  ❌ Violations: {violations}")
    
    # Test 3: Add symbol (with mixed case)
    print("\n[Test 3] Add Symbol (mixed case)")
    if loader.add_symbol("ethUSDT"):
        print("  ✅ Added ETHUSDT (normalized from ethUSDT)")
    
    # Test 4: Summary
    print("\n[Test 4] Summary")
    print(f"  {loader.get_watchlist_summary()}")
    
    # Test 5: Save and reload
    print("\n[Test 5] Save and Reload")
    test_symbols = ["btcusdt", "ETHUSDT", "BnbUsdt"]
    print(f"  Saving: {test_symbols}")
    loader.save_watchlist(test_symbols)
    
    reloaded = loader.load_watchlist()
    print(f"  Reloaded: {reloaded}")
    
    if all(s == s.upper() for s in reloaded):
        print("  ✅ All symbols saved as UPPERCASE")
    else:
        print("  ❌ Some symbols not UPPERCASE")
    
    print("\n" + "=" * 60)
    print("✅ Tests complete")
    print("=" * 60)

