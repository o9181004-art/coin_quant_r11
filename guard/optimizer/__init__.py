#!/usr/bin/env python3
"""
Guard Optimizer Module
ARES Service for candidates outbox
"""

from .ares_service import (ARESService, emit_candidate, get_ares_service,
                           start_ares_service, stop_ares_service)

__all__ = [
    "ARESService",
    "get_ares_service",
    "start_ares_service", 
    "stop_ares_service",
    "emit_candidate"
]
