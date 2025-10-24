#!/usr/bin/env python3
"""
Read-Only Data Loader - Safe SSOT Snapshot Reader
NO side effects, NO writes, NO API calls, NO trading module imports

All reads are wrapped in try/except and return (data, age_sec, is_stale)
Tolerates missing/malformed files gracefully
"""

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# TTL Configuration (seconds)
# These values match the TTLs in shared/health_manager.py
TTL_HEALTH = 15
TTL_STATE_BUS = 5  # FEEDER_TTL
TTL_UDS = 50
TTL_POSITIONS = 180
TTL_PNL_DAILY = 180
TTL_ACCOUNT_SNAPSHOT = 180
TTL_CIRCUIT_BREAKER = 60


class ReadOnlyDataLoader:
    """
    Read-only data loader for SSOT snapshots.

    All methods return (data, age_sec, is_stale) tuple.
    Never raises exceptions - returns (None, None, True) on failure.
    """

    def __init__(self, shared_data_dir: str = "shared_data"):
        self.shared_data_dir = Path(shared_data_dir)
        self._file_cache = {}  # mtime-based cache within single rerun
        self._cache_timestamp = time.time()

    def _clear_cache_if_stale(self):
        """Clear cache if older than 1 second (per-rerun cache)"""
        now = time.time()
        if now - self._cache_timestamp > 1.0:
            self._file_cache.clear()
            self._cache_timestamp = now

    def _read_json_file(
        self,
        filename: str,
        ttl_sec: int
    ) -> Tuple[Optional[Dict[str, Any]], Optional[float], bool]:
        """
        Read JSON file with TTL awareness.

        Args:
            filename: Filename relative to shared_data_dir
            ttl_sec: Time-to-live in seconds

        Returns:
            (data, age_sec, is_stale) tuple
            - data: Parsed JSON dict or None
            - age_sec: Age in seconds or None
            - is_stale: True if missing/malformed/expired
        """
        self._clear_cache_if_stale()

        file_path = self.shared_data_dir / filename

        # Check cache first (by mtime)
        try:
            if file_path.exists():
                mtime = file_path.stat().st_mtime
                cache_key = f"{filename}:{mtime}"

                if cache_key in self._file_cache:
                    return self._file_cache[cache_key]
        except Exception:
            pass

        # Read file
        try:
            if not file_path.exists():
                return (None, None, True)

            # Get file age
            mtime = file_path.stat().st_mtime
            age_sec = time.time() - mtime
            is_stale = age_sec > ttl_sec

            # Read and parse JSON
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            result = (data, age_sec, is_stale)

            # Cache result
            cache_key = f"{filename}:{mtime}"
            self._file_cache[cache_key] = result

            return result

        except Exception as e:
            # Graceful degradation - return None instead of raising
            return (None, None, True)

    def _read_ndjson_file(
        self,
        filename: str,
        max_lines: int = 10
    ) -> Tuple[Optional[List[Dict[str, Any]]], Optional[float], bool]:
        """
        Read NDJSON file (last N lines).

        Args:
            filename: Filename relative to shared_data_dir
            max_lines: Maximum number of lines to read from end

        Returns:
            (data, age_sec, is_stale) tuple
            - data: List of parsed JSON objects or None
            - age_sec: Age in seconds or None
            - is_stale: True if missing/malformed
        """
        file_path = self.shared_data_dir / filename

        try:
            if not file_path.exists():
                return (None, None, True)

            # Get file age
            mtime = file_path.stat().st_mtime
            age_sec = time.time() - mtime

            # Read last N lines
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            # Parse last max_lines
            recent_lines = lines[-max_lines:] if len(lines) > max_lines else lines
            data = []

            for line in recent_lines:
                line = line.strip()
                if line:
                    try:
                        data.append(json.loads(line))
                    except Exception:
                        continue  # Skip malformed lines

            return (data, age_sec, False)

        except Exception:
            return (None, None, True)

    # ============================================
    # Public API - Specific Data Sources
    # ============================================

    def get_health(self) -> Tuple[Optional[Dict[str, Any]], Optional[float], bool]:
        """
        Read health.json (TTL: 15s)

        Returns:
            (data, age_sec, is_stale)
        """
        return self._read_json_file("health.json", TTL_HEALTH)

    def get_state_bus(self) -> Tuple[Optional[Dict[str, Any]], Optional[float], bool]:
        """
        Read state_bus.json (TTL: 5s) - Feeder freshness

        Returns:
            (data, age_sec, is_stale)
        """
        return self._read_json_file("state_bus.json", TTL_STATE_BUS)

    def get_uds(self) -> Tuple[Optional[Dict[str, Any]], Optional[float], bool]:
        """
        Read uds_snapshot.json (TTL: 50s) - UDS (Universe Data Service) freshness

        Returns:
            (data, age_sec, is_stale)
        """
        return self._read_json_file("uds_snapshot.json", TTL_UDS)

    def get_positions(self) -> Tuple[Optional[Dict[str, Any]], Optional[float], bool]:
        """
        Read positions_snapshot.json (TTL: 180s)

        Returns:
            (data, age_sec, is_stale)
        """
        return self._read_json_file("positions_snapshot.json", TTL_POSITIONS)

    def get_pnl_daily(self) -> Tuple[Optional[Dict[str, Any]], Optional[float], bool]:
        """
        Read pnl_daily.json (TTL: 180s, optional)

        Returns:
            (data, age_sec, is_stale)
        """
        return self._read_json_file("pnl_daily.json", TTL_PNL_DAILY)

    def get_account_snapshot(self) -> Tuple[Optional[Dict[str, Any]], Optional[float], bool]:
        """
        Read account_snapshot.json (TTL: 180s, optional)

        Returns:
            (data, age_sec, is_stale)
        """
        return self._read_json_file("account_snapshot.json", TTL_ACCOUNT_SNAPSHOT)

    def get_pnl_rollup(self, max_lines: int = 10) -> Tuple[Optional[List[Dict[str, Any]]], Optional[float], bool]:
        """
        Read pnl_rollup.ndjson (last 10 fills, optional)

        Args:
            max_lines: Maximum number of recent fills to read

        Returns:
            (data, age_sec, is_stale)
        """
        return self._read_ndjson_file("pnl_rollup.ndjson", max_lines)

    def get_circuit_breaker(self) -> Tuple[Optional[Dict[str, Any]], Optional[float], bool]:
        """
        Read circuit_breaker.json (TTL: 60s, optional)

        Returns:
            (data, age_sec, is_stale)
        """
        return self._read_json_file("circuit_breaker.json", TTL_CIRCUIT_BREAKER)

    # ============================================
    # Helper Methods
    # ============================================

    def get_global_health_status(self) -> Tuple[str, str]:
        """
        Derive global health status from health.json components.

        Returns:
            (status, color) tuple
            - status: "GREEN", "YELLOW", "RED", or "UNKNOWN"
            - color: Streamlit color name
        """
        health_data, age_sec, is_stale = self.get_health()

        if health_data is None or is_stale:
            return ("UNKNOWN", "gray")

        try:
            components = health_data.get("components", {})

            # Core components to check
            core_components = ["feeder", "ares", "trader", "uds", "autoheal"]

            statuses = []
            for comp in core_components:
                comp_data = components.get(comp, {})
                status = comp_data.get("status", "UNKNOWN").upper()
                statuses.append(status)

            # Determine global status
            if all(s == "GREEN" for s in statuses):
                return ("GREEN", "green")
            elif any(s == "RED" for s in statuses):
                return ("RED", "red")
            elif any(s == "YELLOW" for s in statuses):
                return ("YELLOW", "orange")
            else:
                return ("UNKNOWN", "gray")

        except Exception:
            return ("UNKNOWN", "gray")

    def get_open_positions_count(self) -> int:
        """
        Get count of open positions.

        Returns:
            Number of open positions (0 if unavailable)
        """
        positions_data, _, is_stale = self.get_positions()

        if positions_data is None:
            return 0

        try:
            # Count non-zero positions
            count = 0
            for symbol, pos_data in positions_data.items():
                if isinstance(pos_data, dict):
                    qty = pos_data.get("qty", 0)
                    if qty > 0:
                        count += 1
            return count
        except Exception:
            return 0

    def get_equity_usdt(self) -> Tuple[Optional[float], Optional[float], bool]:
        """
        Get equity (total USDT) from account_snapshot.json.

        Returns:
            (equity, free_usdt, is_stale) tuple
        """
        account_data, age_sec, is_stale = self.get_account_snapshot()

        if account_data is None:
            return (None, None, True)

        try:
            balances = account_data.get("balances", {})
            usdt_data = balances.get("USDT", {})

            free = float(usdt_data.get("free", 0))
            locked = float(usdt_data.get("locked", 0))
            equity = free + locked

            return (equity, free, is_stale)

        except Exception:
            return (None, None, True)

    def get_today_pnl(self) -> Tuple[Optional[float], bool]:
        """
        Get today's PnL from pnl_daily.json.

        Returns:
            (pnl, is_stale) tuple
        """
        pnl_data, _, is_stale = self.get_pnl_daily()

        if pnl_data is None:
            return (None, True)

        try:
            pnl = float(pnl_data.get("today_pnl", 0))
            return (pnl, is_stale)
        except Exception:
            return (None, True)

    def get_top_balances(self, max_count: int = 8) -> List[Dict[str, Any]]:
        """
        Get top N non-zero asset balances from account_snapshot.json.

        Args:
            max_count: Maximum number of assets to return

        Returns:
            List of dicts with keys: asset, free, locked, est_usdt
        """
        account_data, _, is_stale = self.get_account_snapshot()

        if account_data is None:
            return []

        try:
            balances = account_data.get("balances", {})

            result = []
            for asset, balance_data in balances.items():
                if asset == "USDT":
                    continue  # Skip USDT (shown separately)

                free = float(balance_data.get("free", 0))
                locked = float(balance_data.get("locked", 0))
                total = free + locked

                if total >= 0.001:  # Only non-zero balances
                    est_usdt = balance_data.get("est_usdt", 0)

                    result.append({
                        "asset": asset,
                        "free": free,
                        "locked": locked,
                        "est_usdt": est_usdt
                    })

            # Sort by est_usdt descending
            result.sort(key=lambda x: x.get("est_usdt", 0), reverse=True)

            return result[:max_count]

        except Exception:
            return []


# Global singleton instance
_loader_instance: Optional[ReadOnlyDataLoader] = None


def get_data_loader() -> ReadOnlyDataLoader:
    """Get global ReadOnlyDataLoader instance"""
    global _loader_instance
    if _loader_instance is None:
        _loader_instance = ReadOnlyDataLoader()
    return _loader_instance
