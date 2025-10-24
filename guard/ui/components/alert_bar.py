#!/usr/bin/env python3
"""
Alert Bar Component
Displays sticky alerts for risk mode changes and critical events
"""

import json
import streamlit as st
from pathlib import Path
from typing import Optional, Dict, Any


def render_alert_bar() -> None:
    """
    Render alert bar at top of page (Non-intrusive, fixed position)

    Reads alerts from:
    1. shared_data/alerts/ui_alert.json (risk mode alerts)
    2. shared_data/health_v2.json (DOR status)

    Displays sticky alerts that persist until dismissed or cleared.
    Uses fixed positioning with reserved spacer to prevent layout shift.
    """
    try:
        # Reserve space at top to prevent layout shift
        st.markdown(
            """
            <div style="height: 0px; margin-bottom: 0px;"></div>
            """,
            unsafe_allow_html=True
        )

        # Check health_v2.json for DOR status
        health_file = Path("shared_data/health_v2.json")
        dor = True
        failing_components = []

        if health_file.exists():
            try:
                with open(health_file, 'r', encoding='utf-8') as f:
                    health = json.load(f)
                dor = health.get("dor", True)
                failing_components = health.get("failing_components", [])
            except:
                pass

        # Check for risk mode alert
        alert_file = Path("shared_data/alerts/ui_alert.json")
        has_risk_alert = False
        risk_message = ""
        risk_mode = ""
        risk_timestamp = ""

        if alert_file.exists():
            try:
                with open(alert_file, 'r', encoding='utf-8') as f:
                    alert = json.load(f)

                if alert.get("message"):
                    has_risk_alert = True
                    risk_mode = alert.get("mode", "UNKNOWN")
                    risk_message = alert.get("message", "")
                    risk_timestamp = alert.get("timestamp", "")
            except:
                pass

        # Render alerts
        alerts_html = ""

        # DOR Status Alert (if not ready)
        if not dor:
            failing_str = ", ".join(failing_components) if failing_components else "Unknown"
            alerts_html += f"""
            <div style="
                position: relative;
                padding: 10px 16px;
                margin-bottom: 8px;
                border-left: 4px solid #dc3545;
                background-color: #f8d7da;
                border-radius: 4px;
                font-size: 13px;
                line-height: 1.4;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            ">
                <strong>⚠️ System Not Ready (DOR=false)</strong><br>
                <span style="font-size: 12px;">Failing: {failing_str}</span>
            </div>
            """

        # Risk Mode Alert
        if has_risk_alert:
            if risk_mode == "SAFE":
                alert_color = "#ff9800"
                bg_color = "#fff3cd"
                icon = "⚠️"
            elif risk_mode == "AGGRESSIVE":
                alert_color = "#28a745"
                bg_color = "#d4edda"
                icon = "✅"
            else:
                alert_color = "#17a2b8"
                bg_color = "#d1ecf1"
                icon = "ℹ️"

            alerts_html += f"""
            <div style="
                position: relative;
                padding: 10px 16px;
                margin-bottom: 8px;
                border-left: 4px solid {alert_color};
                background-color: {bg_color};
                border-radius: 4px;
                font-size: 13px;
                line-height: 1.4;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            ">
                <strong>{icon} Risk Mode Alert</strong><br>
                {risk_message.replace(chr(10), '<br>')}
                <div style="font-size: 11px; color: #666; margin-top: 4px;">
                    {risk_timestamp}
                </div>
            </div>
            """

        # Render all alerts
        if alerts_html:
            st.markdown(
                f"""
                <div style="
                    position: relative;
                    width: 100%;
                    z-index: 100;
                    margin-bottom: 16px;
                ">
                    {alerts_html}
                </div>
                """,
                unsafe_allow_html=True
            )

            # Dismiss button (only for risk alerts)
            if has_risk_alert:
                if st.button("✖ Dismiss Risk Alert", key="dismiss_alert"):
                    # Clear alert file
                    alert_file.unlink()
                    st.rerun()

    except Exception as e:
        # Silently fail - don't disrupt UI
        pass


def render_alert_bar_compact(max_width: int = 800) -> None:
    """
    Render compact alert bar (for sidebar or narrow spaces)

    Args:
        max_width: Maximum width in pixels
    """
    try:
        alert_file = Path("shared_data/alerts/ui_alert.json")

        if not alert_file.exists():
            return

        with open(alert_file, 'r', encoding='utf-8') as f:
            alert = json.load(f)

        if not alert.get("message"):
            return

        mode = alert.get("mode", "UNKNOWN")
        message = alert.get("message", "")

        # Truncate message for compact display
        if len(message) > 100:
            message = message[:97] + "..."

        # Determine color
        if mode == "SAFE":
            color = "#ff9800"
            icon = "⚠️"
        elif mode == "AGGRESSIVE":
            color = "#28a745"
            icon = "✅"
        else:
            color = "#17a2b8"
            icon = "ℹ️"

        st.markdown(
            f"""
            <div style="
                padding: 8px 12px;
                margin-bottom: 12px;
                border-left: 3px solid {color};
                background-color: rgba(0,0,0,0.05);
                border-radius: 3px;
                font-size: 13px;
                max-width: {max_width}px;
            ">
                <strong>{icon}</strong> {message}
            </div>
            """,
            unsafe_allow_html=True
        )

    except Exception as e:
        pass


def clear_alert() -> bool:
    """Clear current alert"""
    try:
        alert_file = Path("shared_data/alerts/ui_alert.json")
        if alert_file.exists():
            alert_file.unlink()
            return True
        return False
    except Exception as e:
        return False


def create_alert(mode: str, reason: str, message: str) -> bool:
    """
    Create a new alert

    Args:
        mode: Risk mode (SAFE or AGGRESSIVE)
        reason: Reason for alert
        message: Alert message

    Returns:
        True if successful
    """
    try:
        from shared.state.risk_mode_store import to_iso8601_kst

        alert_file = Path("shared_data/alerts/ui_alert.json")
        alert_file.parent.mkdir(parents=True, exist_ok=True)

        alert = {
            "timestamp": to_iso8601_kst(),
            "mode": mode,
            "reason": reason,
            "message": message,
            "sticky": True
        }

        with open(alert_file, 'w', encoding='utf-8') as f:
            json.dump(alert, f, indent=2)

        return True

    except Exception as e:
        return False
