"""
Memory layer for Coin Quant R11

Immutable audit trail and integrity verification system.
Provides event chain, snapshot store, hash chain, and client capabilities.
"""

from . import event_chain
from . import snapshot_store
from . import hash_chain
from . import client

__all__ = [
    "event_chain",
    "snapshot_store", 
    "hash_chain",
    "client",
]
