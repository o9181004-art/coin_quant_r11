#!/usr/bin/env python3
"""
Worker Status Component - Show action dispatcher status
"""

import time
from pathlib import Path

import streamlit as st

try:
    from shared.action_dispatcher import get_dispatcher
    from shared.action_queue import get_action_queue
    DISPATCHER_AVAILABLE = True
except ImportError:
    DISPATCHER_AVAILABLE = False


def render_worker_status():
    """Render worker status badge"""
    if not DISPATCHER_AVAILABLE:
        st.error("⚠️ Worker: UNAVAILABLE")
        return
    
    try:
        dispatcher = get_dispatcher()
        status = dispatcher.get_status()
        
        worker_status = status.get("status", "UNKNOWN")
        last_tick = status.get("last_tick_ts", 0)
        
        # Calculate age
        if last_tick > 0:
            age = time.time() - last_tick
        else:
            age = float('inf')
        
        # Determine color
        if worker_status == "RUNNING" and age < 10:
            color = "#4CAF50"  # Green
            icon = "🟢"
        elif worker_status == "RUNNING" and age < 60:
            color = "#FF9800"  # Orange
            icon = "🟡"
        else:
            color = "#F44336"  # Red
            icon = "🔴"
        
        # Display badge
        st.markdown(
            f"""
            <div style="
                background-color: {color}15;
                border: 1px solid {color};
                border-radius: 4px;
                padding: 4px 8px;
                display: inline-block;
                font-size: 11px;
                font-weight: 600;
            ">
                {icon} Worker: {worker_status}
                <span style="color: #888; margin-left: 8px;">
                    {f'tick {age:.0f}s ago' if age < float('inf') else 'never'}
                </span>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        # Red banner if stopped
        if worker_status != "RUNNING" or age >= 60:
            st.error(
                "🚨 **Action Worker is STOPPED or STALE** - "
                "Start/Stop buttons will not execute. "
                "Restart the dashboard to fix."
            )
    
    except Exception as e:
        st.error(f"⚠️ Worker status error: {e}")


def render_latest_command_status():
    """Render latest command status"""
    if not DISPATCHER_AVAILABLE:
        return
    
    try:
        queue = get_action_queue()
        latest = queue.get_latest_command()
        
        if latest is None:
            return
        
        # Determine status color and icon
        status_icons = {
            "pending": "⏳",
            "running": "🔄",
            "succeeded": "✅",
            "failed": "❌",
            "timeout": "⏱️"
        }
        
        status_colors = {
            "pending": "#FFC107",
            "running": "#2196F3",
            "succeeded": "#4CAF50",
            "failed": "#F44336",
            "timeout": "#FF9800"
        }
        
        icon = status_icons.get(latest.status, "❓")
        color = status_colors.get(latest.status, "#888")
        
        # Calculate elapsed time
        if latest.started_ts:
            if latest.finished_ts:
                elapsed = latest.finished_ts - latest.started_ts
                elapsed_str = f"{elapsed:.1f}s"
            else:
                elapsed = time.time() - latest.started_ts
                elapsed_str = f"{elapsed:.1f}s (running)"
        else:
            elapsed_str = "pending"
        
        # Display command status
        st.markdown(
            f"""
            <div style="
                background-color: {color}15;
                border-left: 4px solid {color};
                padding: 8px 12px;
                margin: 8px 0;
                border-radius: 4px;
            ">
                <div style="font-size: 12px; font-weight: 600; color: {color};">
                    {icon} {latest.verb.upper()} {latest.target.upper()}
                    <span style="color: #888; font-weight: normal; margin-left: 8px;">
                        {latest.status.upper()}
                    </span>
                </div>
                <div style="font-size: 11px; color: #aaa; margin-top: 4px;">
                    Elapsed: {elapsed_str}
                    {f' | Error: {latest.error_code}' if latest.error_code else ''}
                </div>
                {f'<div style="font-size: 10px; color: #F44336; margin-top: 4px; font-family: monospace;">{latest.error_detail}</div>' if latest.error_detail else ''}
            </div>
            """,
            unsafe_allow_html=True
        )
    
    except Exception as e:
        st.caption(f"⚠️ Command status error: {e}")

