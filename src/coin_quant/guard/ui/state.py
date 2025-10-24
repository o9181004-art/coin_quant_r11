#!/usr/bin/env python3
"""
Streamlit Session State Management for Coin Quant R11

Handles session state for UI controls and user preferences.
"""

import streamlit as st
from typing import Any, Dict, Optional


class SessionState:
    """Manages Streamlit session state"""
    
    @staticmethod
    def get(key: str, default: Any = None) -> Any:
        """Get value from session state"""
        return st.session_state.get(key, default)
    
    @staticmethod
    def set(key: str, value: Any) -> None:
        """Set value in session state"""
        st.session_state[key] = value
    
    @staticmethod
    def update(key: str, value: Any) -> None:
        """Update value in session state (same as set)"""
        st.session_state[key] = value
    
    # Auto-refresh controls
    @staticmethod
    def get_auto_refresh() -> bool:
        """Get auto-refresh enabled state"""
        return SessionState.get("auto_refresh_enabled", True)
    
    @staticmethod
    def set_auto_refresh(enabled: bool) -> None:
        """Set auto-refresh enabled state"""
        SessionState.set("auto_refresh_enabled", enabled)
    
    @staticmethod
    def get_refresh_interval() -> int:
        """Get refresh interval in seconds"""
        return SessionState.get("refresh_interval", 5)
    
    @staticmethod
    def set_refresh_interval(seconds: int) -> None:
        """Set refresh interval in seconds"""
        SessionState.set("refresh_interval", seconds)
    
    # Selected symbol
    @staticmethod
    def get_selected_symbol() -> Optional[str]:
        """Get currently selected symbol"""
        return SessionState.get("selected_symbol")
    
    @staticmethod
    def set_selected_symbol(symbol: str) -> None:
        """Set currently selected symbol"""
        SessionState.set("selected_symbol", symbol)
    
    # View preferences
    @staticmethod
    def get_view_mode() -> str:
        """Get current view mode"""
        return SessionState.get("view_mode", "overview")
    
    @staticmethod
    def set_view_mode(mode: str) -> None:
        """Set current view mode"""
        SessionState.set("view_mode", mode)
    
    # Debug settings
    @staticmethod
    def get_show_debug() -> bool:
        """Get show debug info state"""
        return SessionState.get("show_debug", False)
    
    @staticmethod
    def set_show_debug(show: bool) -> None:
        """Set show debug info state"""
        SessionState.set("show_debug", show)
    
    # Filters
    @staticmethod
    def get_symbol_filter() -> str:
        """Get symbol filter string"""
        return SessionState.get("symbol_filter", "")
    
    @staticmethod
    def set_symbol_filter(filter_str: str) -> None:
        """Set symbol filter string"""
        SessionState.set("symbol_filter", filter_str)
    
    # Last refresh timestamp
    @staticmethod
    def get_last_refresh() -> Optional[float]:
        """Get last refresh timestamp"""
        return SessionState.get("last_refresh")
    
    @staticmethod
    def appearance_dark_mode() -> bool:
        """Check if dark mode is enabled"""
        return SessionState.get("dark_mode", True)
    
    @staticmethod
    def set_dark_mode(enabled: bool) -> None:
        """Set dark mode"""
        SessionState.set("dark_mode", enabled)
    
    # Initialize default values
    @staticmethod
    def initialize_defaults() -> None:
        """Initialize default session state values"""
        defaults = {
            "auto_refresh_enabled": True,
            "refresh_interval": 5,
            "view_mode": "overview",
            "show_debug": False,
            "symbol_filter": "",
            "dark_mode": True
        }
        
        for key, value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = value
