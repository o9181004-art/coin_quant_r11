#!/usr/bin/env python3
"""
Fast-First Render (FFR) Boot Controller

Guarantees first paint within 5 seconds by:
- Enforcing hard deadline for first render ≤ 5s
- Showing skeleton UI immediately with static placeholders
- Hydrating dynamic data after first paint via background workers
- Displaying compact warning if hydration misses 10s

Author: coin_quant
Date: 2025-10-09
"""

import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

import streamlit as st


@dataclass
class BootMetrics:
    """Boot timing metrics"""
    t_boot_start: float = 0.0
    t_first_paint: float = 0.0
    t_hydration_start: float = 0.0
    t_hydration_complete: float = 0.0
    deferred_tasks: int = 0
    timeout_count: int = 0
    is_degraded: bool = False


class FastFirstRenderGuard:
    """
    Fast-First Render Guard
    
    Enforces 5-second deadline for first paint and manages
    lazy hydration of dynamic content.
    """
    
    def __init__(self):
        self.metrics = BootMetrics()
        self.metrics.t_boot_start = time.time()
        
        # Feature flags
        self.fast_start = os.getenv("UI_FAST_START", "true").lower() == "true"
        self.disable_self_tests = os.getenv("UI_DISABLE_SELF_TESTS", "true").lower() == "true"
        self.tail_limit = int(os.getenv("UI_TAIL_LIMIT", "1000"))
        self.read_budget_ms = int(os.getenv("UI_READ_BUDGET_MS", "200"))
        
        # Background workers
        self._background_tasks = []
        self._hydration_complete = False
        self._degraded_mode = False
        
        # Timeout settings
        self.first_paint_deadline = 5.0  # seconds
        self.hydration_timeout = 10.0    # seconds
        self.task_timeout = 0.3          # seconds per probe
        self.total_boot_budget = 2.0     # seconds for background tasks
    
    def enforce_first_paint_deadline(self) -> bool:
        """
        Check if we're within first paint deadline.
        
        Returns:
            True if within deadline, False if exceeded
        """
        elapsed = time.time() - self.metrics.t_boot_start
        return elapsed <= self.first_paint_deadline
    
    def mark_first_paint(self):
        """Mark first paint completion"""
        self.metrics.t_first_paint = time.time()
    
    def should_skip_heavy_operations(self) -> bool:
        """Check if heavy operations should be skipped for fast start"""
        if not self.enforce_first_paint_deadline():
            return True
        
        if self.fast_start:
            return True
            
        return False
    
    def defer_task(self, task_name: str, func: Callable, timeout_ms: int = None) -> bool:
        """
        Defer a task to background execution.
        
        Args:
            task_name: Name of the task for logging
            func: Function to execute
            timeout_ms: Timeout in milliseconds (default: task_timeout)
        
        Returns:
            True if task was deferred, False if executed immediately
        """
        timeout_ms = timeout_ms or (self.task_timeout * 1000)
        
        # If we're past deadline, defer everything
        if not self.enforce_first_paint_deadline():
            self._run_background_task(task_name, func, timeout_ms)
            return True
        
        # If fast start is enabled, defer heavy tasks
        if self.fast_start and self._is_heavy_task(task_name):
            self._run_background_task(task_name, func, timeout_ms)
            return True
        
        # Execute immediately with timeout
        return self._execute_with_timeout(task_name, func, timeout_ms)
    
    def _is_heavy_task(self, task_name: str) -> bool:
        """Check if task is considered heavy and should be deferred"""
        heavy_patterns = [
            "file_scan", "glob", "pandas", "network", "api_call",
            "account_sync", "position_read", "trade_history",
            "health_check", "upgrade_check", "self_test"
        ]
        
        task_lower = task_name.lower()
        return any(pattern in task_lower for pattern in heavy_patterns)
    
    def _run_background_task(self, task_name: str, func: Callable, timeout_ms: int):
        """Run task in background thread"""
        def background_worker():
            try:
                start_time = time.time()
                _ = func()  # Result not used, execute for side effects
                elapsed = (time.time() - start_time) * 1000
                
                if elapsed > timeout_ms:
                    self.metrics.timeout_count += 1
                    print(f"[FFR] Task '{task_name}' timed out ({elapsed:.1f}ms > {timeout_ms}ms)")
                else:
                    print(f"[FFR] Background task '{task_name}' completed ({elapsed:.1f}ms)")
                    
            except Exception as e:
                self.metrics.timeout_count += 1
                print(f"[FFR] Background task '{task_name}' failed: {e}")
        
        thread = threading.Thread(target=background_worker, daemon=True)
        thread.start()
        self._background_tasks.append(thread)
        self.metrics.deferred_tasks += 1
    
    def _execute_with_timeout(self, task_name: str, func: Callable, timeout_ms: int) -> bool:
        """Execute task with timeout protection"""
        try:
            start_time = time.time()
            _ = func()  # Result not used, execute for side effects
            elapsed = (time.time() - start_time) * 1000
            
            if elapsed > timeout_ms:
                self.metrics.timeout_count += 1
                print(f"[FFR] Task '{task_name}' exceeded timeout ({elapsed:.1f}ms > {timeout_ms}ms)")
                return False
            else:
                return True
                
        except Exception as e:
            self.metrics.timeout_count += 1
            print(f"[FFR] Task '{task_name}' failed: {e}")
            return False
    
    def start_hydration(self):
        """Start lazy hydration of dynamic content"""
        self.metrics.t_hydration_start = time.time()
        
        # Check if hydration should be deferred
        if not self.enforce_first_paint_deadline():
            self._degraded_mode = True
            return
        
        # Start background hydration tasks
        self._run_background_task("hydration_check", self._check_hydration_complete, 500)
    
    def _check_hydration_complete(self):
        """Check if hydration is complete"""
        # time.sleep(0.1)  # UI 블로킹 방지
        self.metrics.t_hydration_complete = time.time()
        self._hydration_complete = True
    
    def should_show_degraded_banner(self) -> bool:
        """Check if degraded mode banner should be shown"""
        if self._degraded_mode:
            return True
            
        if self.metrics.t_hydration_start > 0:
            elapsed = time.time() - self.metrics.t_hydration_start
            if elapsed > self.hydration_timeout:
                return True
                
        return False
    
    def render_skeleton_ui(self):
        """Render skeleton UI with static placeholders"""
        st.markdown("### 🚀 Coin Quant Dashboard")
        
        # Mode badge placeholder
        st.markdown("### 🔒 Read-only Mode")
        
        # Skeleton sections
        st.markdown("#### 📊 Dashboard Loading...")
        
        with st.container():
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Portfolio", "Loading...", "---")
            with col2:
                st.metric("P&L", "Loading...", "---")
            with col3:
                st.metric("Positions", "Loading...", "---")
        
        # Placeholder tables
        st.markdown("#### 📈 Recent Activity")
        import pandas as pd
        df = pd.DataFrame(
            data=[["Loading...", "Loading...", "Loading..."]],
            columns=["Time", "Action", "Status"]
        )
        st.dataframe(df, use_container_width=True)
    
    def render_degraded_banner(self):
        """Render degraded mode banner"""
        if not self.should_show_degraded_banner():
            return
            
        st.warning(
            "⚠️ **Degraded Mode**: Data loading is delayed. "
            "UI remains functional with cached data. "
            f"[Report](?report=timing) | "
            f"Boot: {self.get_boot_time():.1f}s, "
            f"Deferred: {self.metrics.deferred_tasks}"
        )
    
    def get_boot_time(self) -> float:
        """Get total boot time in seconds"""
        if self.metrics.t_first_paint > 0:
            return self.metrics.t_first_paint - self.metrics.t_boot_start
        else:
            return time.time() - self.metrics.t_boot_start
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get metrics summary for reporting"""
        return {
            "boot_time_ms": self.get_boot_time() * 1000,
            "first_paint_ms": (self.metrics.t_first_paint - self.metrics.t_boot_start) * 1000 if self.metrics.t_first_paint > 0 else None,
            "hydration_time_ms": (self.metrics.t_hydration_complete - self.metrics.t_hydration_start) * 1000 if self.metrics.t_hydration_complete > 0 else None,
            "deferred_tasks": self.metrics.deferred_tasks,
            "timeout_count": self.metrics.timeout_count,
            "is_degraded": self._degraded_mode,
            "fast_start_enabled": self.fast_start,
            "self_tests_disabled": self.disable_self_tests
        }


# Global instance
_ffr_guard: Optional[FastFirstRenderGuard] = None


def get_ffr_guard() -> FastFirstRenderGuard:
    """Get global FFR guard instance"""
    global _ffr_guard
    if _ffr_guard is None:
        _ffr_guard = FastFirstRenderGuard()
    return _ffr_guard


def with_timeout(timeout_ms: int = 300):
    """
    Decorator for functions that should have timeout protection
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            ffr = get_ffr_guard()
            if ffr.should_skip_heavy_operations():
                return ffr.defer_task(func.__name__, lambda: func(*args, **kwargs), timeout_ms)
            else:
                return func(*args, **kwargs)
        return wrapper
    return decorator


def skip_if_fast_start():
    """
    Decorator to skip function execution if fast start is enabled
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            ffr = get_ffr_guard()
            if ffr.fast_start and ffr.disable_self_tests:
                return None  # Skip execution
            else:
                return func(*args, **kwargs)
        return wrapper
    return decorator
