#!/usr/bin/env python3
"""
UI Safe Mode - Diagnostic mode to isolate layout issues
Set UI_SAFE_MODE=true in environment or session_state to enable

Phase 1 Emergency Hotfix:
- Disables AlertBar completely
- Bypasses all custom CSS except minimal reset
- Disables fixed/absolute positioned UI elements
- Ensures st.set_page_config is called unconditionally
"""

import os
import streamlit as st


def is_safe_mode_enabled() -> bool:
    """
    Check if UI Safe Mode is enabled.

    Safe mode can be enabled via:
    1. Environment variable: UI_SAFE_MODE=true (or legacy UI_FIX_SAFE_MODE=true)
    2. Session state: st.session_state.ui_safe_mode = True

    Returns:
        bool: True if safe mode is enabled
    """
    # Check environment variables (support both new and legacy names)
    env_safe_mode = (
        os.getenv("UI_SAFE_MODE", "false").lower() == "true" or
        os.getenv("UI_FIX_SAFE_MODE", "false").lower() == "true"
    )

    # Check session state
    session_safe_mode = st.session_state.get("ui_safe_mode", False)

    return env_safe_mode or session_safe_mode


def inject_safe_mode_css():
    """
    Inject minimal baseline CSS for safe mode.
    This bypasses all custom CSS and uses only essential styles.

    Phase 1 Requirements:
    - NO modifications to .block-container, .main, body paddings/margins/positions
    - NO fixed/absolute positioning
    - Minimal reset only
    """
    # Check if already injected
    if st.session_state.get("safe_mode_css_injected", False):
        return

    css = """
    <style id="safe-mode-css">
    /* ============================================
       SAFE MODE - MINIMAL CSS ONLY
       Phase 1 Emergency Hotfix
       ============================================ */

    /* Basic dark theme - colors only */
    .stApp {
        background-color: #0e1117 !important;
        color: #ffffff !important;
    }

    /* Sidebar basic styling - colors only */
    section[data-testid="stSidebar"] {
        background-color: #1e1e1e !important;
        color: #ffffff !important;
    }

    /* Text colors only - NO layout modifications */
    .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6 {
        color: #ffffff !important;
    }

    .stApp p, .stApp div, .stApp span {
        color: #ffffff !important;
    }

    /* NO modifications to:
       - .block-container
       - .main
       - body
       - paddings, margins, positions
       - overflow, width, height
    */

    </style>
    """

    st.markdown(css, unsafe_allow_html=True)
    st.session_state.safe_mode_css_injected = True


def render_safe_mode_banner():
    """Render a banner indicating safe mode is active"""
    st.warning(
        "⚠️ **UI Safe Mode Active (Phase 1 Emergency Hotfix)** - "
        "Custom CSS and Alert Bar are disabled for diagnostics. "
        "Layout is locked to wide mode. "
        "Set `UI_SAFE_MODE=false` or `st.session_state.ui_safe_mode = False` to disable.",
        icon="🔧"
    )


def should_disable_alert_bar() -> bool:
    """Check if Alert Bar should be disabled in safe mode"""
    return is_safe_mode_enabled()


def should_use_minimal_css() -> bool:
    """Check if only minimal CSS should be used"""
    return is_safe_mode_enabled()


def get_safe_mode_info() -> dict:
    """
    Get information about safe mode status.

    Returns:
        dict: Safe mode status information
    """
    return {
        "enabled": is_safe_mode_enabled(),
        "env_var": os.getenv("UI_FIX_SAFE_MODE", "false"),
        "session_state": st.session_state.get("ui_safe_mode", False),
        "alert_bar_disabled": should_disable_alert_bar(),
        "minimal_css": should_use_minimal_css(),
    }
