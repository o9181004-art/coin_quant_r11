#!/usr/bin/env python3
"""
Centralized UI Styles - Single source of truth for all CSS
Prevents duplicate CSS injection and layout shifts
"""

import streamlit as st


# Global flag to ensure CSS is injected only once per session
_CSS_INJECTED = False


def inject_global_css():
    """
    Inject global CSS styles once per session.
    This should be called early in the app, after st.set_page_config.

    Phase 1: If UI_SAFE_MODE is enabled, only minimal CSS will be injected.
    Phase 2: Full CSS with proper scoping and no layout-breaking rules.
    """
    global _CSS_INJECTED

    # Check session state to ensure injection happens only once per session
    if "global_css_injected" in st.session_state:
        return

    # Check for safe mode (Phase 1 Emergency Hotfix)
    try:
        from shared.ui_safe_mode import is_safe_mode_enabled, inject_safe_mode_css

        if is_safe_mode_enabled():
            inject_safe_mode_css()
            st.session_state.global_css_injected = True
            _CSS_INJECTED = True
            return
    except ImportError:
        pass  # Safe mode module not available, continue with normal CSS

    css = """
    <style id="global-css">
    /* ============================================
       GLOBAL LAYOUT STYLES (Phase 2 Root-Cause Fix)
       Single source of truth - injected once per session
       ============================================ */

    /* Dark theme base settings */
    .stApp {
        background-color: #0e1117 !important;
        color: #ffffff !important;
    }

    /* Sidebar base settings */
    .stSidebar {
        transition: transform 0.3s ease !important;
    }

    section[data-testid="stSidebar"] {
        position: relative !important;
        width: 300px !important;
        z-index: 999 !important;
        transition: transform 0.3s ease !important;
        background-color: #1e1e1e !important;
        color: #ffffff !important;
    }

    section[data-testid="stSidebar"][aria-expanded="false"] {
        transform: translateX(-100%) !important;
        width: 0 !important;
    }

    section[data-testid="stSidebar"] * {
        background-color: #1e1e1e !important;
        color: #ffffff !important;
    }

    section[data-testid="stSidebar"] input,
    section[data-testid="stSidebar"] select,
    section[data-testid="stSidebar"] textarea {
        background-color: #2d2d2d !important;
        color: #ffffff !important;
        border: 1px solid #404040 !important;
    }

    section[data-testid="stSidebar"] button {
        background-color: #2d2d2d !important;
        color: #ffffff !important;
        border: 1px solid #404040 !important;
    }

    section[data-testid="stSidebar"] button * {
        background-color: transparent !important;
        text-shadow: none !important;
    }

    /* Main content area - minimal adjustments only */
    .main .block-container {
        background-color: #0e1117 !important;
        max-width: 100% !important;
    }

    /* Text colors */
    .stApp, .stApp * {
        color: #ffffff !important;
    }

    .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6 {
        color: #ffffff !important;
        font-weight: 700;
        text-shadow: none !important;
    }

    .stApp p, .stApp div, .stApp span {
        color: #ffffff !important;
    }

    /* Header container */
    .header-container {
        background: linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%);
        border: 1px solid #404040;
        border-radius: 8px;
        padding: 12px 16px;
        margin-top: 0 !important;
        margin-bottom: 0.5rem !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
        min-height: 50px;
    }

    .header-grid {
        display: grid;
        grid-template-columns: 1fr 2fr 1fr;
        gap: 16px;
        align-items: center;
    }

    /* ============================================
       ALERT BAR STYLES
       ============================================ */

    .alert-bar-container {
        height: 48px;
        margin-bottom: 10px;
        width: 100%;
    }

    .alert-bar {
        height: 48px;
        background-color: rgba(40, 167, 69, 0.9);
        color: white;
        padding: 12px 15px;
        border-radius: 5px;
        border: 1px solid rgba(30, 126, 52, 0.8);
        box-shadow: 0 2px 8px rgba(0,0,0,0.15);
        display: flex;
        align-items: center;
        justify-content: space-between;
        font-size: 14px;
        font-weight: 500;
        animation: slideIn 0.3s ease-out;
    }

    .alert-bar--success {
        background-color: rgba(40, 167, 69, 0.9);
        border-color: rgba(30, 126, 52, 0.8);
    }

    .alert-bar--error {
        background-color: rgba(220, 53, 69, 0.9);
        border-color: rgba(189, 33, 48, 0.8);
    }

    .alert-bar--info {
        background-color: rgba(23, 162, 184, 0.9);
        border-color: rgba(19, 132, 150, 0.8);
    }

    @keyframes slideIn {
        from {
            opacity: 0;
            transform: translateY(-10px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }

    /* ============================================
       SYMBOL CARD STYLES
       ============================================ */

    .symbol-card {
        background: linear-gradient(135deg, #1e1e1e 0%, #2d2d2d 100%);
        border: 1px solid #333;
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 12px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        transition: all 0.3s ease;
        position: relative;
        overflow: hidden;
    }

    .symbol-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
        border-color: #555;
    }

    .card-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 12px;
    }

    .symbol-name {
        font-size: 1.1rem;
        font-weight: bold;
        color: #fff;
        letter-spacing: 0.5px;
    }

    .card-time {
        font-size: 0.8rem;
        color: #888;
    }

    /* ============================================
       UI TILE STYLES (for partial renderer)
       ============================================ */

    .ui-tile {
        height: 80px;
        padding: 10px;
        border-radius: 8px;
        margin: 5px 0;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
    }

    .ui-tile-small {
        height: 60px;
        padding: 8px;
    }

    .ui-tile-large {
        height: 100px;
        padding: 12px;
    }

    /* Color classes */
    .positive {
        color: #00ff00;
        background-color: rgba(0, 255, 0, 0.1);
    }

    .negative {
        color: #ff0000;
        background-color: rgba(255, 0, 0, 0.1);
    }

    .warning {
        color: #ffaa00;
        background-color: rgba(255, 170, 0, 0.1);
    }

    .neutral {
        color: #ffffff;
        background-color: rgba(255, 255, 255, 0.05);
    }

    .stale {
        color: #888888;
        background-color: rgba(136, 136, 136, 0.1);
    }

    /* Pulse animation */
    .pulse {
        animation: pulse 1s ease-in-out;
    }

    @keyframes pulse {
        0% { opacity: 1; }
        50% { opacity: 0.7; }
        100% { opacity: 1; }
    }

    /* ============================================
       STATUS STRIP STYLES
       ============================================ */

    .status-strip {
        height: 40px;
        padding: 8px;
        border-radius: 4px;
        margin: 2px 0;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }

    .status-badge {
        padding: 4px 8px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: bold;
    }

    .status-badge.on {
        background-color: #ff0000;
        color: white;
    }

    .status-badge.off {
        background-color: #00ff00;
        color: black;
    }

    .status-badge.stale {
        background-color: #ffaa00;
        color: black;
    }

    /* ============================================
       SYMBOL CARD GRID
       ============================================ */

    .symbol-card-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 10px;
    }

    /* ============================================
       ALERTS BAR (for partial renderer)
       ============================================ */

    .alerts-bar {
        height: 60px;
        padding: 10px;
        border-radius: 4px;
        margin: 5px 0;
        overflow-y: auto;
    }

    .alert-item {
        padding: 4px 8px;
        margin: 2px 0;
        border-radius: 4px;
        font-size: 14px;
    }

    .alert-success {
        background-color: rgba(0, 255, 0, 0.2);
        color: #00ff00;
    }

    .alert-warning {
        background-color: rgba(255, 170, 0, 0.2);
        color: #ffaa00;
    }

    .alert-error {
        background-color: rgba(255, 0, 0, 0.2);
        color: #ff0000;
    }

    </style>
    """

    st.markdown(css, unsafe_allow_html=True)
    st.session_state.global_css_injected = True
    _CSS_INJECTED = True


def is_css_injected() -> bool:
    """Check if global CSS has been injected"""
    return "global_css_injected" in st.session_state
