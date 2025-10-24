"""
Feeder service for Coin Quant R11

Multi-symbol data ingestion with self-healing capabilities.
Publishes health status and maintains data freshness.
"""

from . import service

__all__ = [
    "service",
]
