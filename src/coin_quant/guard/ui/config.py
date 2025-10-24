#!/usr/bin/env python3
"""
UI Configuration for Coin Quant R11

Handles environment variables and Streamlit configuration for the dashboard.
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class UiConfig:
    """UI configuration settings"""
    
    # Backend configuration
    monitoring_backend: str
    monitoring_endpoint: Optional[str]
    
    # Feature flags
    show_debug: bool
    show_advanced: bool
    cards_only: bool
    
    # Thresholds
    snapshot_age_warn: int  # seconds
    snapshot_age_halt: int  # seconds
    signal_age_warn: int    # seconds
    signal_age_halt: int    # seconds
    
    # Auto-refresh
    auto_refresh_enabled: bool
    auto_refresh_seconds: int
    
    # Trading mode
    is_testnet: bool
    is_simulation: bool
    is_mainnet: bool
    
    # Environment guardrails
    python_path_expected: Optional[str]
    
    @classmethod
    def from_env(cls) -> 'UiConfig':
        """Create UiConfig from environment variables"""
        return cls(
            monitoring_backend=os.getenv("MONITORING_BACKEND", "file"),
            monitoring_endpoint=os.getenv("MONITORING_ENDPOINT"),
            
            show_debug=os.getenv("UI_SHOW_DEBUG", "false").lower() == "true",
            show_advanced=os.getenv("UI_SHOW_ADVANCED", "false").lower() == "true",
            cards_only=os.getenv("UI_CARDS_ONLY", "false").lower() == "true",
            
            snapshot_age_warn=int(os.getenv("SNAPSHOT_AGE_WARN", "300")),
            snapshot_age_halt=int(os.getenv("SNAPSHOT_AGE_HALT", "900")),
            signal_age_warn=int(os.getenv("SIGNAL_AGE_WARN", "600")),
            signal_age_halt=int(os.getenv("SIGNAL_AGE_HALT", "1800")),
            
            auto_refresh_enabled=os.getenv("AUTO_REFRESH_ENABLED", "true").lower() == "true",
            auto_refresh_seconds=int(os.getenv("AUTO_REFRESH_SEC", "5")),
            
            is_testnet=os.getenv("BINANCE_USE_TESTNET", "true").lower() == "true",
            is_simulation=os.getenv("SIMULATION_MODE", "false").lower() == "true",
            is_mainnet=os.getenv("LIVE_TRADING_ENABLED", "false").lower() == "true",
            
            python_path_expected=os.getenv("PYTHON_PATH_EXPECTED")
        )
    
    def get_mode_display(self) -> str:
        """Get human-readable mode display"""
        if self.is_mainnet:
            return "MAINNET"
        elif self.is_testnet:
            return "TESTNET"
        elif self.is_simulation:
            return "SIMULATION"
        else:
            return "UNKNOWN"
    
    def get_mode_color(self) -> str:
        """Get color for mode display"""
        if self.is_mainnet:
            return "red"
        elif self.is_testnet:
            return "orange"
        elif self.is_simulation:
            return "green"
        else:
            return "gray"
