#!/usr/bin/env python3
"""
Performance instrumentation for Streamlit UI.

Tracks render timings, cache hit rates, and provides performance insights.
"""
import os
import time
from contextlib import contextmanager
from typing import Dict, List, Optional

import streamlit as st

# Performance logging enabled?
ENABLE_PERF_LOG = os.getenv("UI_ENABLE_PERFORMANCE_LOG", "false").lower() == "true"

# Performance data storage (in session_state)
PERF_KEY = "_performance_data"


def init_performance_tracking():
    """Initialize performance tracking in session state"""
    if PERF_KEY not in st.session_state:
        st.session_state[PERF_KEY] = {
            "timings": {},  # section_name -> [duration_ms, ...]
            "last_log_time": 0,
            "cache_hits": 0,
            "cache_misses": 0,
        }


@contextmanager
def time_section(section_name: str):
    """
    Context manager to time a section render.
    
    Usage:
        with time_section("trades_table"):
            render_trades_table()
    """
    if not ENABLE_PERF_LOG:
        yield
        return
    
    init_performance_tracking()
    
    start = time.time()
    try:
        yield
    finally:
        duration_ms = (time.time() - start) * 1000
        
        # Store timing
        perf_data = st.session_state[PERF_KEY]
        if section_name not in perf_data["timings"]:
            perf_data["timings"][section_name] = []
        
        perf_data["timings"][section_name].append(duration_ms)
        
        # Keep only last 10 timings
        perf_data["timings"][section_name] = perf_data["timings"][section_name][-10:]
        
        # Log once per 60s
        current_time = time.time()
        if current_time - perf_data["last_log_time"] > 60:
            log_performance_summary()
            perf_data["last_log_time"] = current_time


def log_performance_summary():
    """Log performance summary"""
    if PERF_KEY not in st.session_state:
        return
    
    perf_data = st.session_state[PERF_KEY]
    timings = perf_data["timings"]
    
    if not timings:
        return
    
    print("\n" + "=" * 60)
    print("📊 Performance Summary (last 60s)")
    print("=" * 60)
    
    for section_name, durations in timings.items():
        if not durations:
            continue
        
        avg_ms = sum(durations) / len(durations)
        max_ms = max(durations)
        min_ms = min(durations)
        
        status = "✅" if avg_ms < 100 else "⚠️ " if avg_ms < 500 else "🐌"
        print(f"{status} {section_name:30s}: {avg_ms:>6.1f}ms (min={min_ms:.1f}, max={max_ms:.1f})")
    
    # Cache stats
    cache_hits = perf_data.get("cache_hits", 0)
    cache_misses = perf_data.get("cache_misses", 0)
    total = cache_hits + cache_misses
    
    if total > 0:
        hit_rate = cache_hits / total * 100
        print(f"\n💾 Cache hit rate: {hit_rate:.1f}% ({cache_hits}/{total})")
    
    print("=" * 60)


def record_cache_hit():
    """Record a cache hit"""
    if ENABLE_PERF_LOG:
        init_performance_tracking()
        st.session_state[PERF_KEY]["cache_hits"] += 1


def record_cache_miss():
    """Record a cache miss"""
    if ENABLE_PERF_LOG:
        init_performance_tracking()
        st.session_state[PERF_KEY]["cache_misses"] += 1


def render_performance_panel():
    """Render performance panel (for debugging)"""
    if not ENABLE_PERF_LOG:
        st.info("Performance logging disabled. Set UI_ENABLE_PERFORMANCE_LOG=true to enable.")
        return
    
    init_performance_tracking()
    perf_data = st.session_state[PERF_KEY]
    
    st.subheader("📊 Performance Metrics")
    
    # Timings
    timings = perf_data["timings"]
    if timings:
        st.write("### Render Timings (last 10 renders)")
        
        timing_data = []
        for section_name, durations in timings.items():
            if not durations:
                continue
            
            avg_ms = sum(durations) / len(durations)
            max_ms = max(durations)
            min_ms = min(durations)
            
            timing_data.append({
                "Section": section_name,
                "Avg (ms)": f"{avg_ms:.1f}",
                "Min (ms)": f"{min_ms:.1f}",
                "Max (ms)": f"{max_ms:.1f}",
                "Renders": len(durations)
            })
        
        if timing_data:
            import pandas as pd
            df = pd.DataFrame(timing_data)
            st.dataframe(df, use_container_width=True)
    else:
        st.info("No timing data yet. Interact with the dashboard to collect data.")
    
    # Cache stats
    cache_hits = perf_data.get("cache_hits", 0)
    cache_misses = perf_data.get("cache_misses", 0)
    total = cache_hits + cache_misses
    
    if total > 0:
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Cache Hits", cache_hits)
        
        with col2:
            st.metric("Cache Misses", cache_misses)
        
        with col3:
            hit_rate = cache_hits / total * 100
            st.metric("Hit Rate", f"{hit_rate:.1f}%")
    
    # Clear button
    if st.button("Clear Performance Data"):
        st.session_state[PERF_KEY] = {
            "timings": {},
            "last_log_time": 0,
            "cache_hits": 0,
            "cache_misses": 0,
        }
        st.rerun()


# Decorator for performance tracking
def track_performance(section_name: str):
    """
    Decorator to track function performance.
    
    Usage:
        @track_performance("my_function")
        def my_expensive_function():
            ...
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            with time_section(section_name):
                return func(*args, **kwargs)
        return wrapper
    return decorator

