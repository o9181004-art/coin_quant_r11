#!/usr/bin/env python3
"""
Thread and BLAS guards for CQ_LEAN mode
Sets appropriate thread limits for memory optimization
"""

import os
import sys
from typing import Dict, Any


def set_thread_limits() -> Dict[str, int]:
    """Set thread limits for all numerical libraries"""
    
    # Get thread limits from environment or use defaults
    max_threads = int(os.getenv("NUMEXPR_MAX_THREADS", "2"))
    omp_threads = int(os.getenv("OMP_NUM_THREADS", "2"))
    mkl_threads = int(os.getenv("MKL_NUM_THREADS", "2"))
    openblas_threads = int(os.getenv("OPENBLAS_NUM_THREADS", "2"))
    polars_threads = int(os.getenv("POLARS_MAX_THREADS", "2"))
    
    # Set environment variables
    os.environ["NUMEXPR_MAX_THREADS"] = str(max_threads)
    os.environ["OMP_NUM_THREADS"] = str(omp_threads)
    os.environ["MKL_NUM_THREADS"] = str(mkl_threads)
    os.environ["OPENBLAS_NUM_THREADS"] = str(openblas_threads)
    os.environ["POLARS_MAX_THREADS"] = str(polars_threads)
    
    # Set thread limits for libraries that are already imported
    try:
        import numpy as np
        if hasattr(np, 'set_num_threads'):
            np.set_num_threads(max_threads)
    except ImportError:
        pass
    
    try:
        import pandas as pd
        # Pandas doesn't have direct thread control, but we can set OMP
        pass
    except ImportError:
        pass
    
    try:
        import polars as pl
        # Polars respects POLARS_MAX_THREADS environment variable
        pass
    except ImportError:
        pass
    
    try:
        import numexpr as ne
        ne.set_num_threads(max_threads)
    except ImportError:
        pass
    
    return {
        "max_threads": max_threads,
        "omp_threads": omp_threads,
        "mkl_threads": mkl_threads,
        "openblas_threads": openblas_threads,
        "polars_threads": polars_threads
    }


def configure_blas_libraries() -> Dict[str, Any]:
    """Configure BLAS libraries for optimal performance"""
    
    config = {}
    
    # Intel MKL configuration
    try:
        import mkl
        mkl.set_num_threads(int(os.getenv("MKL_NUM_THREADS", "2")))
        config["mkl_threads"] = mkl.get_max_threads()
    except ImportError:
        config["mkl_threads"] = None
    
    # OpenBLAS configuration
    try:
        import openblas
        openblas.set_num_threads(int(os.getenv("OPENBLAS_NUM_THREADS", "2")))
        config["openblas_threads"] = openblas.get_num_threads()
    except ImportError:
        config["openblas_threads"] = None
    
    # NumPy configuration
    try:
        import numpy as np
        if hasattr(np, 'set_num_threads'):
            np.set_num_threads(int(os.getenv("OMP_NUM_THREADS", "2")))
        config["numpy_threads"] = getattr(np, 'get_num_threads', lambda: None)()
    except ImportError:
        config["numpy_threads"] = None
    
    return config


def get_thread_info() -> Dict[str, Any]:
    """Get current thread configuration information"""
    
    info = {
        "environment": {
            "NUMEXPR_MAX_THREADS": os.getenv("NUMEXPR_MAX_THREADS"),
            "OMP_NUM_THREADS": os.getenv("OMP_NUM_THREADS"),
            "MKL_NUM_THREADS": os.getenv("MKL_NUM_THREADS"),
            "OPENBLAS_NUM_THREADS": os.getenv("OPENBLAS_NUM_THREADS"),
            "POLARS_MAX_THREADS": os.getenv("POLARS_MAX_THREADS"),
        },
        "libraries": {}
    }
    
    # Check library thread counts
    try:
        import numpy as np
        info["libraries"]["numpy"] = getattr(np, 'get_num_threads', lambda: None)()
    except ImportError:
        info["libraries"]["numpy"] = None
    
    try:
        import numexpr as ne
        info["libraries"]["numexpr"] = ne.get_num_threads()
    except ImportError:
        info["libraries"]["numexpr"] = None
    
    try:
        import mkl
        info["libraries"]["mkl"] = mkl.get_max_threads()
    except ImportError:
        info["libraries"]["mkl"] = None
    
    try:
        import openblas
        info["libraries"]["openblas"] = openblas.get_num_threads()
    except ImportError:
        info["libraries"]["openblas"] = None
    
    return info


def optimize_for_lean_mode():
    """Optimize thread configuration for lean mode"""
    
    from shared.lean_mode import is_lean
    
    if not is_lean:
        return
    
    print("🔧 Configuring thread limits for lean mode...")
    
    # Set thread limits
    thread_config = set_thread_limits()
    print(f"✓ Thread limits set: {thread_config}")
    
    # Configure BLAS libraries
    blas_config = configure_blas_libraries()
    print(f"✓ BLAS configuration: {blas_config}")
    
    # Print final configuration
    thread_info = get_thread_info()
    print(f"✓ Final thread configuration: {thread_info}")
    
    return thread_config, blas_config


def validate_thread_configuration() -> bool:
    """Validate that thread configuration is correct"""
    
    from shared.lean_mode import is_lean
    
    if not is_lean:
        return True
    
    # Check environment variables
    max_threads = int(os.getenv("NUMEXPR_MAX_THREADS", "0"))
    if max_threads > 2:
        print(f"⚠️ Warning: NUMEXPR_MAX_THREADS={max_threads} exceeds lean mode limit of 2")
        return False
    
    omp_threads = int(os.getenv("OMP_NUM_THREADS", "0"))
    if omp_threads > 2:
        print(f"⚠️ Warning: OMP_NUM_THREADS={omp_threads} exceeds lean mode limit of 2")
        return False
    
    print("✅ Thread configuration validation passed")
    return True


# Auto-configure on import if in lean mode
if os.getenv("CQ_LEAN"):
    optimize_for_lean_mode()
