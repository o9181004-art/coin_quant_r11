#!/usr/bin/env python3
"""
Lazy Loading Helpers for UI Components

Provides bounded, timeout-protected data loading for UI panels:
- Log/Trades panels: bounded tail reader with size limits
- Account/Balance panels: cached snapshot with staleness checks
- Signals/Health panels: exception-safe probes with fallbacks

Author: coin_quant
Date: 2025-10-09
"""

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import streamlit as st

from guard.ui.boot_controller import get_ffr_guard, with_timeout


class BoundedTailReader:
    """Bounded tail reader for log files with size limits"""
    
    def __init__(self, max_lines: int = 1000, timeout_ms: int = 200):
        self.max_lines = max_lines
        self.timeout_ms = timeout_ms
        self.ffr = get_ffr_guard()
    
    @with_timeout(200)
    def read_tail(self, file_path: Union[str, Path]) -> Tuple[List[str], float, bool]:
        """
        Read last N lines from file with timeout protection.
        
        Returns:
            (lines, age_seconds, is_stale)
        """
        try:
            start_time = time.time()
            file_path = Path(file_path)
            
            if not file_path.exists():
                return [], 0.0, True
            
            # Check file size to avoid reading huge files
            file_size = file_path.stat().st_size
            if file_size > 10 * 1024 * 1024:  # 10MB limit
                print(f"[LazyLoader] File too large: {file_path} ({file_size} bytes)")
                return [], 0.0, True
            
            # Read last N lines efficiently
            lines = []
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    # Read file in chunks from end
                    f.seek(0, 2)  # Seek to end
                    file_size = f.tell()
                    
                    if file_size == 0:
                        return [], 0.0, True
                    
                    # Read backwards in chunks
                    chunk_size = min(8192, file_size)
                    f.seek(max(0, file_size - chunk_size))
                    chunk = f.read(chunk_size)
                    
                    # Extract lines
                    lines = chunk.splitlines()
                    if len(lines) > self.max_lines:
                        lines = lines[-self.max_lines:]
                    
            except (UnicodeDecodeError, IOError) as e:
                print(f"[LazyLoader] Read error: {e}")
                return [], 0.0, True
            
            age_seconds = time.time() - file_path.stat().st_mtime
            elapsed_ms = (time.time() - start_time) * 1000
            
            if elapsed_ms > self.timeout_ms:
                print(f"[LazyLoader] Read timeout: {elapsed_ms:.1f}ms > {self.timeout_ms}ms")
                return lines, age_seconds, True
            
            return lines, age_seconds, age_seconds > 60  # Stale if > 60s old
            
        except Exception as e:
            print(f"[LazyLoader] Error reading {file_path}: {e}")
            return [], 0.0, True


class CachedSnapshotReader:
    """Cached snapshot reader with staleness checks"""
    
    def __init__(self, cache_ttl: float = 60.0, timeout_ms: int = 200):
        self.cache_ttl = cache_ttl
        self.timeout_ms = timeout_ms
        self.ffr = get_ffr_guard()
        self._cache = {}
    
    @with_timeout(200)
    def read_snapshot(self, file_path: Union[str, Path]) -> Tuple[Optional[Dict], float, bool]:
        """
        Read cached snapshot with staleness checks.
        
        Returns:
            (data, age_seconds, is_stale)
        """
        try:
            start_time = time.time()
            file_path = Path(file_path)
            cache_key = str(file_path)
            
            # Check cache first
            if cache_key in self._cache:
                cached_data, cached_time = self._cache[cache_key]
                age_seconds = time.time() - cached_time
                
                if age_seconds < self.cache_ttl:
                    return cached_data, age_seconds, False
            
            # Read from file if cache miss or stale
            if not file_path.exists():
                return None, 0.0, True
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Update cache
                self._cache[cache_key] = (data, time.time())
                
                age_seconds = time.time() - file_path.stat().st_mtime
                elapsed_ms = (time.time() - start_time) * 1000
                
                if elapsed_ms > self.timeout_ms:
                    print(f"[CachedReader] Read timeout: {elapsed_ms:.1f}ms > {self.timeout_ms}ms")
                
                return data, age_seconds, age_seconds > self.cache_ttl
                
            except (json.JSONDecodeError, IOError) as e:
                print(f"[CachedReader] Read error: {e}")
                return None, 0.0, True
                
        except Exception as e:
            print(f"[CachedReader] Error reading {file_path}: {e}")
            return None, 0.0, True


class SafeProbeRunner:
    """Exception-safe probe runner with timeouts and fallbacks"""
    
    def __init__(self, timeout_ms: int = 300):
        self.timeout_ms = timeout_ms
        self.ffr = get_ffr_guard()
    
    @with_timeout(300)
    def run_probe(self, probe_name: str, probe_func, *args, **kwargs) -> Tuple[Any, bool]:
        """
        Run probe with timeout protection and exception handling.
        
        Returns:
            (result, success)
        """
        try:
            start_time = time.time()
            result = probe_func(*args, **kwargs)
            elapsed_ms = (time.time() - start_time) * 1000
            
            if elapsed_ms > self.timeout_ms:
                print(f"[SafeProbe] {probe_name} timeout: {elapsed_ms:.1f}ms > {self.timeout_ms}ms")
                return None, False
            
            return result, True
            
        except Exception as e:
            print(f"[SafeProbe] {probe_name} failed: {e}")
            return None, False


# Global instances
_tail_reader = None
_snapshot_reader = None
_probe_runner = None


def get_tail_reader() -> BoundedTailReader:
    """Get global tail reader instance"""
    global _tail_reader
    if _tail_reader is None:
        max_lines = int(os.getenv("UI_TAIL_LIMIT", "1000"))
        timeout_ms = int(os.getenv("UI_READ_BUDGET_MS", "200"))
        _tail_reader = BoundedTailReader(max_lines, timeout_ms)
    return _tail_reader


def get_snapshot_reader() -> CachedSnapshotReader:
    """Get global snapshot reader instance"""
    global _snapshot_reader
    if _snapshot_reader is None:
        timeout_ms = int(os.getenv("UI_READ_BUDGET_MS", "200"))
        _snapshot_reader = CachedSnapshotReader(timeout_ms=timeout_ms)
    return _snapshot_reader


def get_probe_runner() -> SafeProbeRunner:
    """Get global probe runner instance"""
    global _probe_runner
    if _probe_runner is None:
        timeout_ms = int(os.getenv("UI_READ_BUDGET_MS", "300"))
        _probe_runner = SafeProbeRunner(timeout_ms)
    return _probe_runner


# Convenience functions for UI components
def load_trades_tail(file_path: Union[str, Path], max_lines: int = None) -> Tuple[List[Dict], float, bool]:
    """Load trades with bounded tail reading"""
    reader = get_tail_reader()
    if max_lines:
        reader.max_lines = max_lines
    
    lines, age_sec, is_stale = reader.read_tail(file_path)
    
    # Parse JSONL
    trades = []
    for line in lines:
        try:
            trade = json.loads(line.strip())
            trades.append(trade)
        except json.JSONDecodeError:
            continue
    
    return trades, age_sec, is_stale


def load_positions_snapshot(file_path: Union[str, Path] = None) -> Tuple[Optional[Dict], float, bool]:
    """Load positions with cached snapshot reading"""
    if file_path is None:
        file_path = Path("shared_data") / "positions.json"
    
    reader = get_snapshot_reader()
    return reader.read_snapshot(file_path)


def load_account_snapshot(file_path: Union[str, Path] = None) -> Tuple[Optional[Dict], float, bool]:
    """Load account balance with cached snapshot reading"""
    if file_path is None:
        file_path = Path("shared_data") / "account_summary.json"
    
    reader = get_snapshot_reader()
    return reader.read_snapshot(file_path)


def run_health_probe(probe_name: str, probe_func, *args, **kwargs) -> Tuple[Any, bool]:
    """Run health probe with timeout protection"""
    runner = get_probe_runner()
    return runner.run_probe(probe_name, probe_func, *args, **kwargs)


# UI Helper functions
def render_stale_indicator(age_seconds: float, is_stale: bool):
    """Render stale data indicator"""
    if is_stale:
        st.warning(f"⚠️ 데이터가 오래됨 ({age_seconds:.1f}초 전)")
    elif age_seconds > 30:
        st.info(f"ℹ️ 데이터 나이: {age_seconds:.1f}초")


def render_empty_state(message: str = "데이터가 없습니다"):
    """Render empty state placeholder"""
    st.info(f"📭 {message}")


def render_loading_state(message: str = "로딩 중..."):
    """Render loading state placeholder"""
    st.info(f"⏳ {message}")
