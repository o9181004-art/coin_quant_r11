"""
ARES service for Coin Quant R11

Signal generation with health gating.
Blocks on stale/missing Feeder health, no default signals.
"""

from . import service

__all__ = [
    "service",
]
