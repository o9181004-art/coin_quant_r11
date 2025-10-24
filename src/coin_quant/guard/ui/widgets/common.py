#!/usr/bin/env python3
"""
Common UI Widgets for Coin Quant R11

Reusable UI components like badges, status chips, and warning boxes.
"""

import streamlit as st
from datetime import datetime, timedelta
from typing import Optional, Dict, Any


def render_status_badge(status: str, size: str = "normal") -> str:
    """Render a status badge with appropriate color"""
    status_colors = {
        "ok": "🟢",
        "green": "🟢",
        "healthy": "🟢",
        "active": "🟢",
        "warning": "🟡",
        "yellow": "🟡",
        "degraded": "🟡",
        "error": "🔴",
        "red": "🔴",
        "down": "🔴",
        "offline": "🔴",
        "unknown": "⚪",
        "none": "⚪",
        "hold": "⚪",
        "buy": "🟢",
        "sell": "🔴"
    }
    
    emoji = status_colors.get(status.lower(), "⚪")
    return f"{emoji} {status.upper()}"


def render_age_pill(age_seconds: Optional[float], warn_threshold: int = 300, halt_threshold: int = 900) -> str:
    """Render an age indicator with appropriate color based on thresholds"""
    if age_seconds is None:
        return "❓ NO DATA"
    
    if age_seconds < warn_threshold:
        return f"🟢 {format_age(age_seconds)}"
    elif age_seconds < halt_threshold:
        return f"🟡 {format_age(age_seconds)}"
    else:
        return f"🔴 {format_age(age_seconds)}"


def format_age(age_seconds: float) -> str:
    """Format age in seconds to human-readable string"""
    if age_seconds < 60:
        return f"{age_seconds:.0f}s"
    elif age_seconds < 3600:
        return f"{age_seconds/60:.1f}m"
    else:
        return f"{age_seconds/3600:.1f}h"


def render_price_change(change_24h: float) -> str:
    """Render price change with appropriate color"""
    if change_24h > 0:
        return f"🟢 +{change_24h:.2f}%"
    elif change_24h < 0:
        return f"🔴 {change_24h:.2f}%"
    else:
        return f"⚪ {change_24h:.2f}%"


def render_pnl_badge(pnl: float) -> str:
    """Render PnL with appropriate color"""
    if pnl > 0:
        return f"🟢 +${pnl:.2f}"
    elif pnl < 0:
        return f"🔴 ${pnl:.2f}"
    else:
        return f"⚪ ${pnl:.2f}"


def render_mode_badge(mode: str) -> str:
    """Render trading mode badge"""
    mode_colors = {
        "mainnet": "🔴",
        "testnet": "🟡", 
        "simulation": "🟢",
        "paper": "🟢"
    }
    
    emoji = mode_colors.get(mode.lower(), "⚪")
    return f"{emoji} {mode.upper()}"


def render_warning_box(message: str, warning_type: str = "warning") -> None:
    """Render a warning box with appropriate styling"""
    if warning_type == "error":
        st.error(f"❌ {message}")
    elif warning_type == "warning":
        st.warning(f"⚠️ {message}")
    elif warning_type == "info":
        st.info(f"ℹ️ {message}")
    else:
        st.info(message)


def render_no_data_box(data_type: str, source_file: Optional[str] = None) -> None:
    """Render a 'no data' box with source information"""
    message = f"No {data_type} data available"
    if source_file:
        message += f" (Source: {source_file})"
    render_warning_box(message, "info")


def render_symbol_card_header(symbol: str, price_data: Optional[Dict[str, Any]], 
                            signal_data: Optional[Dict[str, Any]]) -> None:
    """Render header for symbol card"""
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        st.markdown(f"### {symbol.upper()}")
    
    with col2:
        if price_data:
            price = price_data.get("price", 0.0)
            st.metric("Price", f"${price:.4f}")
        else:
            st.metric("Price", "NO DATA")
    
    with col3:
        if signal_data:
            signal = signal_data.get("signal", "HOLD")
            st.markdown(f"**Signal:** {render_status_badge(signal)}")
        else:
            st.markdown("**Signal:** NO DATA")


def render_data_age_indicators(price_age: Optional[float], signal_age: Optional[float],
                             warn_threshold: int = 300, halt_threshold: int = 900) -> None:
    """Render data age indicators"""
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown(f"**Price Age:** {render_age_pill(price_age, warn_threshold, halt_threshold)}")
    
    with col2:
        st.markdown(f"**Signal Age:** {render_age_pill(signal_age, warn_threshold, halt_threshold)}")


def render_position_summary(position_data: Optional[Dict[str, Any]]) -> None:
    """Render position summary"""
    if not position_data:
        render_no_data_box("position")
        return
    
    side = position_data.get("side", "NONE")
    size = position_data.get("size", 0.0)
    entry_price = position_data.get("entry_price", 0.0)
    current_price = position_data.get("current_price", 0.0)
    unrealized_pnl = position_data.get("unrealized_pnl", 0.0)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Side", side)
    
    with col2:
        st.metric("Size", f"{size:.4f}")
    
    with col3:
        st.metric("Unrealized PnL", render_pnl_badge(unrealized_pnl))


def render_health_status(health_data: Optional[Dict[str, Any]]) -> None:
    """Render health status"""
    if not health_data:
        render_no_data_box("health")
        return
    
    status = health_data.get("status", "unknown")
    last_update = health_data.get("last_update_ts", 0)
    updated_within_sec = health_data.get("updated_within_sec", 0)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown(f"**Status:** {render_status_badge(status)}")
    
    with col2:
        st.markdown(f"**Last Update:** {render_age_pill(updated_within_sec)}")


def render_timestamp(timestamp: float) -> str:
    """Render timestamp in readable format"""
    try:
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OSError):
        return "Invalid timestamp"


def render_compact_metric(label: str, value: Any, delta: Optional[Any] = None) -> None:
    """Render a compact metric"""
    if isinstance(value, (int, float)):
        if isinstance(value, float):
            formatted_value = f"{value:.2f}"
        else:
            formatted_value = str(value)
    else:
        formatted_value = str(value)
    
    if delta is not None:
        st.metric(label, formatted_value, delta)
    else:
        st.metric(label, formatted_value)
