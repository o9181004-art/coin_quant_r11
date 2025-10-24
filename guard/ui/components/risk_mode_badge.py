#!/usr/bin/env python3
"""
Risk Mode Badge Component
Displays current risk mode (AGGRESSIVE/SAFE) in UI header
"""

import streamlit as st
from typing import Dict, Any

from shared.state.risk_mode_store import get_risk_mode_store


def render_risk_mode_badge() -> None:
    """
    Render risk mode badge in UI header

    Shows:
    - AGGRESSIVE (red outline) or SAFE (green outline)
    - Tooltip with last switch reason and timestamp
    """
    try:
        # Get risk mode state
        store = get_risk_mode_store()
        state = store.get_risk_state()

        mode = state.current_mode

        # Determine badge style
        if mode == "SAFE":
            badge_color = "#28a745"  # Green
            badge_icon = "🛡️"
            badge_text = "SAFE MODE"
        else:  # AGGRESSIVE
            badge_color = "#dc3545"  # Red
            badge_icon = "⚡"
            badge_text = "AGGRESSIVE MODE"

        # Build tooltip
        tooltip = f"Current Mode: {mode}"
        if state.last_switch_reason:
            tooltip += f"\nLast Switch: {state.last_switch_reason}"
        if state.last_switch_ts:
            tooltip += f"\nTime: {state.last_switch_ts}"

        # Render badge with custom CSS
        st.markdown(
            f"""
            <div style="
                display: inline-block;
                padding: 6px 12px;
                border: 2px solid {badge_color};
                border-radius: 6px;
                background-color: rgba(0, 0, 0, 0.05);
                color: {badge_color};
                font-weight: bold;
                font-size: 14px;
                margin-left: 10px;
                cursor: help;
            " title="{tooltip}">
                {badge_icon} {badge_text}
            </div>
            """,
            unsafe_allow_html=True
        )

    except Exception as e:
        st.error(f"Failed to render risk mode badge: {e}")


def render_risk_mode_badge_compact() -> str:
    """
    Render compact risk mode badge (returns HTML string)

    For use in tight spaces or inline displays
    """
    try:
        store = get_risk_mode_store()
        state = store.get_risk_state()

        mode = state.current_mode

        if mode == "SAFE":
            badge_color = "#28a745"
            badge_icon = "🛡️"
        else:
            badge_color = "#dc3545"
            badge_icon = "⚡"

        return f'<span style="color: {badge_color}; font-weight: bold;">{badge_icon} {mode}</span>'

    except Exception as e:
        return f'<span style="color: #999;">ERROR</span>'
