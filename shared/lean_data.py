#!/usr/bin/env python3
"""
Memory-efficient data processing with Polars and optimized numpy
Replaces pandas with Polars for better memory usage in CQ_LEAN mode
"""

import os
from typing import Any, Dict, List, Optional, Union, Tuple
import numpy as np

from shared.lean_mode import is_lean, lean_cache, lazy_import


# Lazy imports for heavy dependencies
@lazy_import("pandas", "polars")
def get_dataframe_module(pandas_module, polars_module=None):
    """Get appropriate dataframe module based on lean mode"""
    if is_lean and polars_module:
        return polars_module
    return pandas_module


@lazy_import("pandas")
def get_pandas_module(pandas_module):
    """Get pandas module (fallback)"""
    return pandas_module


@lazy_import("polars")
def get_polars_module(polars_module):
    """Get polars module (preferred in lean mode)"""
    return polars_module


def create_dataframe(data: Any, **kwargs) -> Any:
    """Create dataframe with appropriate module based on lean mode"""
    if is_lean:
        try:
            polars = get_polars_module()
            return polars.DataFrame(data, **kwargs)
        except ImportError:
            pass
    
    # Fallback to pandas
    pandas = get_pandas_module()
    return pandas.DataFrame(data, **kwargs)


def read_csv_lean(file_path: str, **kwargs) -> Any:
    """Read CSV with lean optimizations"""
    if is_lean:
        try:
            polars = get_polars_module()
            # Polars optimizations for lean mode
            lean_kwargs = kwargs.copy()
            lean_kwargs.setdefault('dtypes', {
                'open': np.float32,
                'high': np.float32,
                'low': np.float32,
                'close': np.float32,
                'volume': np.float32,
                'timestamp': np.int64,
            })
            return polars.read_csv(file_path, **lean_kwargs)
        except ImportError:
            pass
    
    # Fallback to pandas
    pandas = get_pandas_module()
    return pandas.read_csv(file_path, **kwargs)


def optimize_dtypes(df: Any) -> Any:
    """Optimize dataframe dtypes for memory efficiency"""
    if not is_lean:
        return df
    
    try:
        # Try polars optimization
        if hasattr(df, 'with_columns'):
            # Polars DataFrame
            optimized_df = df.with_columns([
                df.select(pl.col(col).cast(pl.Float32) if df[col].dtype in [pl.Float64] else pl.col(col) 
                         for col in df.columns)
            ])
            return optimized_df
    except:
        pass
    
    try:
        # Pandas optimization
        pandas = get_pandas_module()
        if hasattr(df, 'astype'):
            # Pandas DataFrame
            dtype_map = {}
            for col in df.columns:
                if df[col].dtype == 'float64':
                    dtype_map[col] = 'float32'
                elif df[col].dtype == 'int64':
                    dtype_map[col] = 'int32'
                elif df[col].dtype == 'object':
                    # Try to convert to category if low cardinality
                    if df[col].nunique() / len(df) < 0.5:
                        dtype_map[col] = 'category'
            
            return df.astype(dtype_map)
    except:
        pass
    
    return df


def create_numpy_array(data: List[float], dtype: str = None) -> np.ndarray:
    """Create numpy array with optimized dtype"""
    if dtype is None:
        dtype = np.float32 if is_lean else np.float64
    
    return np.array(data, dtype=dtype)


def preallocate_array(shape: Tuple[int, ...], dtype: str = None) -> np.ndarray:
    """Preallocate numpy array to avoid memory fragmentation"""
    if dtype is None:
        dtype = np.float32 if is_lean else np.float64
    
    return np.empty(shape, dtype=dtype)


def calculate_features_lean(ohlcv_data: List[Dict]) -> Dict[str, float]:
    """Calculate technical features with memory optimizations"""
    if not ohlcv_data:
        return {}
    
    # Convert to numpy arrays with optimized dtypes
    closes = np.array([c['close'] for c in ohlcv_data], dtype=np.float32)
    highs = np.array([c['high'] for c in ohlcv_data], dtype=np.float32)
    lows = np.array([c['low'] for c in ohlcv_data], dtype=np.float32)
    volumes = np.array([c['volume'] for c in ohlcv_data], dtype=np.float32)
    
    features = {}
    
    # Simple moving averages (memory efficient)
    if len(closes) >= 20:
        features['sma_20'] = float(np.mean(closes[-20:]))
    if len(closes) >= 50:
        features['sma_50'] = float(np.mean(closes[-50:]))
    
    # RSI calculation (simplified)
    if len(closes) >= 14:
        deltas = np.diff(closes[-14:])
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)
        
        if avg_loss != 0:
            rs = avg_gain / avg_loss
            features['rsi'] = float(100 - (100 / (1 + rs)))
    
    # ATR calculation (simplified)
    if len(ohlcv_data) >= 14:
        tr_values = []
        for i in range(1, min(15, len(ohlcv_data))):
            high = highs[-i]
            low = lows[-i]
            prev_close = closes[-i-1] if i < len(closes) else closes[-i]
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_values.append(tr)
        
        features['atr'] = float(np.mean(tr_values))
    
    # Volume features
    if len(volumes) >= 20:
        features['volume_sma'] = float(np.mean(volumes[-20:]))
        features['volume_ratio'] = float(volumes[-1] / np.mean(volumes[-20:]))
    
    return features


def batch_process_data(data: List[Dict], batch_size: int = 100) -> Iterator[List[Dict]]:
    """Process data in batches to reduce memory usage"""
    for i in range(0, len(data), batch_size):
        yield data[i:i + batch_size]


def compress_dataframe(df: Any) -> Any:
    """Compress dataframe by removing unnecessary data"""
    if not is_lean:
        return df
    
    try:
        # Remove duplicate rows
        if hasattr(df, 'drop_duplicates'):
            df = df.drop_duplicates()
        
        # Remove columns with all NaN values
        if hasattr(df, 'dropna'):
            df = df.dropna(axis=1, how='all')
        
        return df
    except Exception as e:
        print(f"Dataframe compression error: {e}")
        return df


def get_memory_usage_mb(obj: Any) -> float:
    """Get memory usage of object in MB"""
    try:
        if hasattr(obj, 'memory_usage'):
            # Pandas DataFrame
            return obj.memory_usage(deep=True).sum() / 1024 / 1024
        elif hasattr(obj, 'estimated_size'):
            # Polars DataFrame
            return obj.estimated_size() / 1024 / 1024
        else:
            # Generic object
            import sys
            return sys.getsizeof(obj) / 1024 / 1024
    except Exception:
        return 0.0


def cache_dataframe(key: str, df: Any, ttl: int = 300) -> Any:
    """Cache dataframe with TTL"""
    if not is_lean:
        return df
    
    cached_df = lean_cache.get(key)
    if cached_df is not None:
        return cached_df
    
    lean_cache.set(key, df)
    return df


def clear_dataframe_cache():
    """Clear dataframe cache"""
    if is_lean:
        lean_cache.clear()


def optimize_for_streaming(df: Any, max_rows: int = 1000) -> Any:
    """Optimize dataframe for streaming operations"""
    if not is_lean:
        return df
    
    try:
        # Limit rows for streaming
        if hasattr(df, 'tail'):
            return df.tail(max_rows)
        elif hasattr(df, 'slice'):
            return df.slice(-max_rows)
        else:
            return df
    except Exception as e:
        print(f"Streaming optimization error: {e}")
        return df
