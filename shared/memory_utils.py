"""
Memory-optimized data structures and utilities
"""

import gc
import os
from collections import deque
from typing import Any, Optional, Union

import numpy as np
import pandas as pd


class BoundedDeque(deque):
    """Memory-bounded deque with automatic cleanup"""
    
    def __init__(self, maxlen: int, cleanup_callback: Optional[callable] = None):
        super().__init__(maxlen=maxlen)
        self.cleanup_callback = cleanup_callback
        self._maxlen = maxlen  # maxlen 값을 별도로 저장
    
    def append(self, item: Any):
        """Append with cleanup callback"""
        if len(self) >= self._maxlen and self.cleanup_callback:
            self.cleanup_callback(self[0])
        super().append(item)
    
    def extend(self, iterable):
        """Extend with cleanup callback"""
        for item in iterable:
            self.append(item)


class MemoryOptimizedDataFrame:
    """Memory-optimized DataFrame wrapper"""
    
    def __init__(self, data=None, dtype: str = "float32", max_rows: int = 720):
        self.max_rows = max_rows
        self.dtype = dtype
        
        if data is not None:
            self.df = pd.DataFrame(data, dtype=dtype)
        else:
            self.df = pd.DataFrame()
    
    def append(self, data: Union[dict, pd.DataFrame]):
        """Append data with automatic trimming"""
        if isinstance(data, dict):
            new_row = pd.DataFrame([data], dtype=self.dtype)
        else:
            new_row = data.astype(self.dtype)
        
        self.df = pd.concat([self.df, new_row], ignore_index=True)
        
        # Trim if exceeds max_rows
        if len(self.df) > self.max_rows:
            self.df = self.df.tail(self.max_rows).reset_index(drop=True)
    
    def get_latest(self, n: int = 1) -> pd.DataFrame:
        """Get latest n rows"""
        return self.df.tail(n)
    
    def get_all(self) -> pd.DataFrame:
        """Get all data"""
        return self.df
    
    def clear(self):
        """Clear all data"""
        self.df = pd.DataFrame()


class RingBuffer:
    """Memory-efficient ring buffer"""
    
    def __init__(self, maxlen: int, dtype: str = "float32"):
        self.maxlen = maxlen
        self.dtype = dtype
        self.buffer = np.zeros(maxlen, dtype=dtype)
        self.head = 0
        self.size = 0
    
    def append(self, value: float):
        """Append value to buffer"""
        self.buffer[self.head] = value
        self.head = (self.head + 1) % self.maxlen
        if self.size < self.maxlen:
            self.size += 1
    
    def get_latest(self, n: int = 1) -> np.ndarray:
        """Get latest n values"""
        if n > self.size:
            n = self.size
        
        if n == 0:
            return np.array([], dtype=self.dtype)
        
        start_idx = (self.head - n) % self.maxlen
        if start_idx + n <= self.maxlen:
            return self.buffer[start_idx:start_idx + n]
        else:
            return np.concatenate([
                self.buffer[start_idx:],
                self.buffer[:n - (self.maxlen - start_idx)]
            ])
    
    def get_all(self) -> np.ndarray:
        """Get all values"""
        return self.get_latest(self.size)


def optimize_dataframe_memory(df: pd.DataFrame, target_dtype: str = "float32") -> pd.DataFrame:
    """Optimize DataFrame memory usage"""
    if df.empty:
        return df
    
    # Convert numeric columns to target dtype
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        if df[col].dtype != target_dtype:
            try:
                df[col] = df[col].astype(target_dtype)
            except (ValueError, OverflowError):
                # Skip if conversion fails
                pass
    
    # Convert object columns to category if beneficial
    for col in df.select_dtypes(include=['object']).columns:
        if df[col].nunique() / len(df) < 0.5:  # Less than 50% unique values
            df[col] = df[col].astype('category')
    
    return df


def cleanup_memory():
    """Force garbage collection"""
    gc.collect()


def get_memory_usage() -> dict:
    """Get current memory usage"""
    import psutil
    process = psutil.Process()
    memory_info = process.memory_info()
    
    return {
        "rss_mb": memory_info.rss / 1024 / 1024,
        "vms_mb": memory_info.vms / 1024 / 1024,
        "percent": process.memory_percent()
    }


def log_memory_usage(service_name: str, event: str = "check"):
    """Log current memory usage"""
    usage = get_memory_usage()
    print(f"[{service_name}] {event}: RSS={usage['rss_mb']:.1f}MB, VMS={usage['vms_mb']:.1f}MB, %={usage['percent']:.1f}%")


# Configuration
MEMORY_CONFIG = {
    "low_mem": os.getenv("LOW_MEM", "true").lower() == "true",
    "symbol_limit": int(os.getenv("SYMBOL_LIMIT", "20")),
    "history_bars_max": int(os.getenv("HISTORY_BARS_MAX", "720")),
    "tick_buffer_max": int(os.getenv("TICK_BUFFER_MAX", "200")),
    "ws_queue_max": int(os.getenv("WS_QUEUE_MAX", "2000")),
    "ares_dtype": os.getenv("ARES_DTYPE", "float32"),
    "ares_copy_on_write": os.getenv("ARES_COPY_ON_WRITE", "true").lower() == "true",
    "cache_max_entries": int(os.getenv("CACHE_MAX_ENTRIES", "64")),
    "cache_ttl_sec": int(os.getenv("CACHE_TTL_SEC", "120")),
    "record_ws": os.getenv("RECORD_WS", "false").lower() == "true",
    "ui_heavy_charts": os.getenv("UI_HEAVY_CHARTS", "false").lower() == "true",
}
