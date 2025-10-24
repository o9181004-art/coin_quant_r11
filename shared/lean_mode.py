#!/usr/bin/env python3
"""
CQ_LEAN Mode - Memory Optimization System
Reduces RAM usage across Feeder/ARES/Trader services
"""

import os
import gc
import sys
import time
import psutil
import threading
from typing import Optional, Dict, Any, Callable
from functools import lru_cache, wraps
from pathlib import Path

# CQ_LEAN mode detection
is_lean = bool(os.getenv("CQ_LEAN", "").strip())
lean_mode = is_lean  # Alias for backward compatibility

# Memory limits
MEM_LIMIT_MB = int(os.getenv("CQ_MEM_LIMIT_MB", "600"))
CACHE_TTL = int(os.getenv("CQ_CACHE_TTL", "300"))  # 5 minutes
WS_BATCH_SIZE = int(os.getenv("CQ_WS_BATCH", "10"))

# Thread limits
MAX_THREADS = int(os.getenv("NUMEXPR_MAX_THREADS", "2"))
OMP_THREADS = int(os.getenv("OMP_NUM_THREADS", "2"))
MKL_THREADS = int(os.getenv("MKL_NUM_THREADS", "2"))
OPENBLAS_THREADS = int(os.getenv("OPENBLAS_NUM_THREADS", "2"))
POLARS_THREADS = int(os.getenv("POLARS_MAX_THREADS", "2"))

# Set thread limits at startup
if is_lean:
    os.environ["NUMEXPR_MAX_THREADS"] = str(MAX_THREADS)
    os.environ["OMP_NUM_THREADS"] = str(OMP_THREADS)
    os.environ["MKL_NUM_THREADS"] = str(MKL_THREADS)
    os.environ["OPENBLAS_NUM_THREADS"] = str(OPENBLAS_THREADS)
    os.environ["POLARS_MAX_THREADS"] = str(POLARS_THREADS)


class LeanImporter:
    """Lazy import manager for heavy dependencies"""
    
    def __init__(self):
        self._imports = {}
        self._lean_imports = {}
    
    def register_lean_import(self, name: str, lean_func: Callable, full_func: Callable):
        """Register lean and full import functions"""
        self._lean_imports[name] = lean_func
        self._imports[name] = full_func
    
    def get_import(self, name: str):
        """Get appropriate import based on lean mode"""
        if is_lean and name in self._lean_imports:
            return self._lean_imports[name]()
        elif name in self._imports:
            return self._imports[name]()
        else:
            raise ImportError(f"No import registered for {name}")


# Global lazy importer
lean_importer = LeanImporter()


def lazy_import(module_name: str, lean_alternative: Optional[str] = None):
    """Decorator for lazy imports"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if is_lean and lean_alternative:
                try:
                    module = __import__(lean_alternative, fromlist=[''])
                except ImportError:
                    module = __import__(module_name, fromlist=[''])
            else:
                module = __import__(module_name, fromlist=[''])
            return func(module, *args, **kwargs)
        return wrapper
    return decorator


class MemoryWatchdog:
    """Memory usage monitor and controller"""
    
    def __init__(self):
        self.process = psutil.Process()
        self.last_check = 0
        self.check_interval = 5  # seconds
        self.memory_limit_bytes = MEM_LIMIT_MB * 1024 * 1024
        self.running = False
        self._thread = None
        
    def start(self):
        """Start memory monitoring"""
        if not is_lean:
            return
            
        self.running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop memory monitoring"""
        self.running = False
        if self._thread:
            self._thread.join(timeout=1)
    
    def _monitor_loop(self):
        """Memory monitoring loop"""
        while self.running:
            try:
                current_time = time.time()
                if current_time - self.last_check >= self.check_interval:
                    self._check_memory()
                    self.last_check = current_time
                time.sleep(1)
            except Exception as e:
                print(f"Memory watchdog error: {e}")
                time.sleep(5)
    
    def _check_memory(self):
        """Check current memory usage"""
        try:
            memory_info = self.process.memory_info()
            rss_mb = memory_info.rss / 1024 / 1024
            
            if memory_info.rss > self.memory_limit_bytes:
                print(f"⚠️ Memory limit exceeded: {rss_mb:.1f}MB > {MEM_LIMIT_MB}MB")
                self._emergency_cleanup()
            elif rss_mb > MEM_LIMIT_MB * 0.8:
                print(f"⚠️ Memory usage high: {rss_mb:.1f}MB")
                self._gentle_cleanup()
                
        except Exception as e:
            print(f"Memory check error: {e}")
    
    def _gentle_cleanup(self):
        """Gentle memory cleanup"""
        gc.collect()
        print("🧹 Gentle memory cleanup performed")
    
    def _emergency_cleanup(self):
        """Emergency memory cleanup"""
        gc.collect()
        # Force garbage collection multiple times
        for _ in range(3):
            gc.collect()
        print("🚨 Emergency memory cleanup performed")


class LeanCache:
    """Memory-efficient LRU cache with TTL"""
    
    def __init__(self, maxsize: int = 256, ttl: int = CACHE_TTL):
        self.maxsize = maxsize if is_lean else maxsize * 4
        self.ttl = ttl
        self._cache = {}
        self._timestamps = {}
        self._lock = threading.Lock()
    
    def get(self, key: str) -> Optional[Any]:
        """Get cached value"""
        if not is_lean:
            return None
            
        with self._lock:
            if key in self._cache:
                if time.time() - self._timestamps[key] < self.ttl:
                    return self._cache[key]
                else:
                    # Expired
                    del self._cache[key]
                    del self._timestamps[key]
            return None
    
    def set(self, key: str, value: Any):
        """Set cached value"""
        if not is_lean:
            return
            
        with self._lock:
            # Remove oldest if at capacity
            if len(self._cache) >= self.maxsize:
                oldest_key = min(self._timestamps.keys(), key=self._timestamps.get)
                del self._cache[oldest_key]
                del self._timestamps[oldest_key]
            
            self._cache[key] = value
            self._timestamps[key] = time.time()
    
    def clear(self):
        """Clear all cached values"""
        with self._lock:
            self._cache.clear()
            self._timestamps.clear()


# Global instances
memory_watchdog = MemoryWatchdog()
lean_cache = LeanCache()

# Start memory watchdog in lean mode
if is_lean:
    memory_watchdog.start()


def get_lean_config() -> Dict[str, Any]:
    """Get lean mode configuration"""
    return {
        "is_lean": is_lean,
        "mem_limit_mb": MEM_LIMIT_MB,
        "cache_ttl": CACHE_TTL,
        "ws_batch_size": WS_BATCH_SIZE,
        "max_threads": MAX_THREADS,
        "omp_threads": OMP_THREADS,
        "mkl_threads": MKL_THREADS,
        "openblas_threads": OPENBLAS_THREADS,
        "polars_threads": POLARS_THREADS,
    }


def log_memory_stats():
    """Log current memory statistics"""
    if not is_lean:
        return
        
    try:
        process = psutil.Process()
        memory_info = process.memory_info()
        rss_mb = memory_info.rss / 1024 / 1024
        vms_mb = memory_info.vms / 1024 / 1024
        
        print(f"📊 Memory Stats: RSS={rss_mb:.1f}MB, VMS={vms_mb:.1f}MB, Limit={MEM_LIMIT_MB}MB")
    except Exception as e:
        print(f"Memory stats error: {e}")


def cleanup_on_exit():
    """Cleanup function for graceful shutdown"""
    if is_lean:
        memory_watchdog.stop()
        lean_cache.clear()
        gc.collect()
        print("🧹 Lean mode cleanup completed")


# Register cleanup on exit
import atexit
atexit.register(cleanup_on_exit)
