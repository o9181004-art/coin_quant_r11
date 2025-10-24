"""
Trader service for Coin Quant R11

Order execution with balance checks and failsafe logic.
Honors simulation mode, performs pre-order balance checks,
down-scales order size, bounded retries, symbol quarantine.
"""

from . import service

__all__ = [
    "service",
]
