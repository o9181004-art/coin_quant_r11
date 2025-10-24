#!/usr/bin/env python3
"""
Optimized data loaders for Streamlit UI with bounded I/O and caching.

Replaces full-file reads with tail-first, cached loading.
"""
import json
import os
from pathlib import Path
from typing import Dict, List, Optional

import streamlit as st

from guard.ui.utils.log_tail_reader import LogReadResult, LogTailReader
from guard.ui.utils.performance import (record_cache_hit, record_cache_miss,
                                        time_section)

# Config
MAX_TRADES_LINES = int(os.getenv("UI_TRADES_LINES", "1000"))
MAX_ALERT_LINES = int(os.getenv("UI_ALERT_LINES", "500"))
CACHE_TTL_FAST = int(os.getenv("UI_CACHE_TTL_FAST", "5"))
CACHE_TTL_SLOW = int(os.getenv("UI_CACHE_TTL_SLOW", "60"))


@st.cache_data(ttl=CACHE_TTL_FAST)
def load_recent_executions_optimized(max_lines: int = MAX_TRADES_LINES) -> List[Dict]:
    """
    Load recent trade executions with bounded I/O.
    
    Replaces full-file reads with tail-first loading.
    Cache invalidates every 5s or when file changes.
    
    Args:
        max_lines: Maximum lines to read
        
    Returns:
        List of execution records
    """
    with time_section("load_recent_executions"):
        executions = []
        
        # 1. Try trades.jsonl first
        trades_file = Path("trades/trades.jsonl")
        if trades_file.exists():
            try:
                reader = LogTailReader(str(trades_file))
                result = reader.read(max_lines=max_lines, reverse=True)
                
                for record in result.records:
                    if "_raw" in record:
                        continue  # Skip malformed lines
                    
                    executions.append({
                        "ts": record.get("ts", 0),
                        "type": record.get("side", "").upper(),
                        "side": record.get("side", "").upper(),
                        "symbol": record.get("symbol", ""),
                        "qty": record.get("qty", 0),
                        "price": record.get("price", 0),
                        "pnl": record.get("pnl"),
                        "profit": record.get("profit"),
                        "fee": record.get("fee", 0),
                        "source": record.get("source", ""),
                    })
                
                record_cache_hit()
                return executions
                
            except Exception as e:
                print(f"[PERF] trades.jsonl read failed: {e}")
                record_cache_miss()
        
        # 2. Fallback: orders_log.ndjson
        try:
            orders_file = Path("data/orders_log.ndjson")
            if orders_file.exists():
                reader = LogTailReader(str(orders_file))
                result = reader.read(max_lines=min(max_lines, 50), reverse=True)
                
                for record in result.records:
                    if "_raw" in record:
                        continue
                    
                    executions.append({
                        "ts": record.get("ts", 0),
                        "type": record.get("type", ""),
                        "symbol": record.get("symbol", ""),
                        "qty": record.get("qty", 0),
                        "price": record.get("res", {}).get("fills", [{}])[0].get("price", 0),
                    })
                
                record_cache_miss()
                
        except Exception as e:
            print(f"[PERF] orders_log read failed: {e}")
        
        return executions


@st.cache_data(ttl=CACHE_TTL_FAST)
def load_notifications_optimized(max_lines: int = MAX_ALERT_LINES) -> List[Dict]:
    """
    Load recent notifications with bounded I/O.
    
    Args:
        max_lines: Maximum lines to read
        
    Returns:
        List of notification records
    """
    with time_section("load_notifications"):
        notifications = []
        
        notif_file = Path("logs/notifications.log")
        if not notif_file.exists():
            return notifications
        
        try:
            reader = LogTailReader(str(notif_file))
            result = reader.read(max_lines=max_lines, reverse=True)
            
            for record in result.records:
                if "_raw" in record:
                    # Parse raw text log line
                    notifications.append({
                        "message": record["_raw"],
                        "timestamp": 0  # Unknown
                    })
                else:
                    notifications.append(record)
            
            record_cache_hit()
            
        except Exception as e:
            print(f"[PERF] notifications read failed: {e}")
            record_cache_miss()
        
        return notifications


@st.cache_data(ttl=CACHE_TTL_SLOW)
def load_symbol_history_optimized(symbol: str, max_records: int = 300) -> List[Dict]:
    """
    Load symbol price history with bounded I/O.
    
    Args:
        symbol: Trading symbol
        max_records: Maximum records to load
        
    Returns:
        List of price records
    """
    with time_section(f"load_history_{symbol}"):
        history_file = Path(f"shared_data/snapshots/prices_{symbol.upper()}.json")
        
        if not history_file.exists():
            return []
        
        try:
            reader = LogTailReader(str(history_file))
            result = reader.read(max_lines=max_records, reverse=False)
            
            record_cache_hit()
            return result.records
            
        except Exception as e:
            print(f"[PERF] history read failed: {e}")
            record_cache_miss()
            return []


@st.cache_data(ttl=CACHE_TTL_SLOW)
def load_ares_candidates_optimized(symbol: str, max_lines: int = 100) -> List[Dict]:
    """
    Load ARES candidates for a symbol.
    
    Args:
        symbol: Trading symbol
        max_lines: Maximum lines
        
    Returns:
        List of candidate records
    """
    with time_section(f"load_ares_{symbol}"):
        candidates_file = Path(f"shared_data/ares/{symbol.lower()}_candidates.json")
        
        if not candidates_file.exists():
            return []
        
        try:
            reader = LogTailReader(str(candidates_file))
            result = reader.read(max_lines=max_lines, reverse=True)
            
            record_cache_hit()
            return result.records
            
        except Exception as e:
            print(f"[PERF] ARES candidates read failed: {e}")
            record_cache_miss()
            return []


# Pagination support
def load_more_executions(offset_token: Optional[str], step: int = 2000) -> Dict:
    """
    Load more executions (pagination).
    
    Args:
        offset_token: Token from previous load
        step: Lines to load
        
    Returns:
        Dict with records and next_token
    """
    trades_file = Path("trades/trades.jsonl")
    if not trades_file.exists():
        return {"records": [], "next_token": None, "has_more": False}
    
    try:
        reader = LogTailReader(str(trades_file))
        result = reader.read(
            max_lines=step,
            offset_token=offset_token,
            reverse=True
        )
        
        executions = []
        for record in result.records:
            if "_raw" not in record:
                executions.append({
                    "ts": record.get("ts", 0),
                    "type": record.get("side", "").upper(),
                    "side": record.get("side", "").upper(),
                    "symbol": record.get("symbol", ""),
                    "qty": record.get("qty", 0),
                    "price": record.get("price", 0),
                    "pnl": record.get("pnl"),
                    "profit": record.get("profit"),
                    "fee": record.get("fee", 0),
                })
        
        return {
            "records": executions,
            "next_token": result.next_token,
            "has_more": result.has_more
        }
        
    except Exception as e:
        print(f"[PERF] load_more failed: {e}")
        return {"records": [], "next_token": None, "has_more": False}


# Clear cache functions
def clear_executions_cache():
    """Clear executions cache"""
    load_recent_executions_optimized.clear()


def clear_notifications_cache():
    """Clear notifications cache"""
    load_notifications_optimized.clear()


def clear_all_caches():
    """Clear all data caches"""
    load_recent_executions_optimized.clear()
    load_notifications_optimized.clear()
    load_symbol_history_optimized.clear()
    load_ares_candidates_optimized.clear()

