"""
Coin Quant R11 - Clean, Minimal, Stable Python 3.11 Runtime

A greenfield extraction of the core trading system components:
- Feeder: Multi-symbol data ingestion
- ARES: Signal generation with health gating
- Trader: Order execution with failsafe logic
- Memory: Immutable audit trail and integrity verification

This package enforces absolute imports and eliminates CWD dependencies.
"""

__version__ = "1.0.0-rc1"
__author__ = "Coin Quant Team"
__description__ = "Clean, minimal, and stable Python 3.11 trading runtime"

# Ensure Python 3.11+ requirement
import sys
if sys.version_info < (3, 11):
    raise RuntimeError("Coin Quant R11 requires Python 3.11 or higher")

# Core service modules
from . import shared
from . import feeder
from . import ares
from . import trader
from . import memory

__all__ = [
    "shared",
    "feeder", 
    "ares",
    "trader",
    "memory",
]
