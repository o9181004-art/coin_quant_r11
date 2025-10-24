#!/usr/bin/env python3
"""
CSS Loader - Safe CSS injection for Streamlit
Loads CSS from external files and injects into Streamlit
"""

from pathlib import Path
from typing import Optional

import streamlit as st


def load_css_file(css_file_path: Path) -> str:
    """Load CSS content from file"""
    try:
        if not css_file_path.exists():
            return ""
        
        with open(css_file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"Error loading CSS file {css_file_path}: {e}")
        return ""

def inject_css_safe(css_content: str) -> None:
    """Safely inject CSS into Streamlit"""
    if not css_content or not css_content.strip():
        return
    
    try:
        # Escape any potential issues in CSS content
        safe_css = css_content.replace('</style>', '')  # Prevent style tag injection
        st.markdown(f"<style>{safe_css}</style>", unsafe_allow_html=True)
    except Exception as e:
        print(f"Error injecting CSS: {e}")

def load_and_inject_css(css_file_path: Path) -> bool:
    """Load CSS from file and inject into Streamlit"""
    try:
        css_content = load_css_file(css_file_path)
        if css_content:
            inject_css_safe(css_content)
            return True
        return False
    except Exception as e:
        print(f"Error loading and injecting CSS: {e}")
        return False

def get_default_css_path() -> Path:
    """Get the default CSS file path"""
    return Path(__file__).parent / "styles.css"

def inject_default_css() -> bool:
    """Inject the default CSS file"""
    return load_and_inject_css(get_default_css_path())

# CSS utility functions for common patterns
def create_metric_card_css() -> str:
    """Create CSS for metric cards"""
    return """
    .metric-card {
        background-color: #1e1e1e;
        border: 1px solid #333;
        border-radius: 0.5rem;
        padding: 1rem;
        margin-bottom: 1rem;
        text-align: center;
    }
    .metric-value {
        font-size: 1.6rem;
        font-weight: bold;
        color: #4CAF50;
        margin-bottom: 0.5rem;
    }
    .metric-label {
        font-size: 0.8rem;
        color: #888;
        margin-bottom: 0.5rem;
    }
    """

def create_symbol_card_css() -> str:
    """Create CSS for symbol cards"""
    return """
    .symbol-card {
        background-color: #1e1e1e;
        border: 1px solid #333;
        border-radius: 0.5rem;
        padding: 1rem;
        margin-bottom: 1rem;
        transition: all 0.3s ease;
    }
    .symbol-card:hover {
        border-color: #444;
        transform: translateY(-2px);
    }
    .symbol-name {
        font-size: 1.2rem;
        font-weight: bold;
        color: #fff;
        margin-bottom: 0.5rem;
    }
    .symbol-price {
        font-size: 1rem;
        color: #4CAF50;
        margin-bottom: 0.5rem;
    }
    """

def create_balance_display_css() -> str:
    """Create CSS for balance display"""
    return """
    .balance-display {
        text-align: center;
        padding: 1rem;
        background-color: #1e1e1e;
        border-radius: 0.5rem;
        border: 1px solid #333;
        margin-bottom: 1rem;
    }
    .balance-value {
        font-size: 1.6rem;
        font-weight: bold;
        color: #4CAF50;
    }
    .balance-label {
        font-size: 0.8rem;
        color: #888;
        margin-top: 0.5rem;
    }
    """

def create_notification_css() -> str:
    """Create CSS for notifications"""
    return """
    .notification-container {
        position: fixed;
        top: 20px;
        right: 20px;
        z-index: 1000;
        max-width: 400px;
    }
    .notification {
        background-color: #1e1e1e;
        border: 1px solid #333;
        border-radius: 0.5rem;
        padding: 1rem;
        margin-bottom: 0.5rem;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        animation: slideIn 0.3s ease-out;
    }
    @keyframes slideIn {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    """

def inject_utility_css() -> None:
    """Inject utility CSS functions"""
    utility_css = "\n".join([
        create_metric_card_css(),
        create_symbol_card_css(),
        create_balance_display_css(),
        create_notification_css()
    ])
    inject_css_safe(utility_css)