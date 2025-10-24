#!/usr/bin/env python3
"""
Layout Components for Coin Quant R11

Handles page layout, sidebar, and tab structure.
"""

import streamlit as st
from typing import Any


def render_sidebar(config: Any) -> None:
    """Render sidebar with controls"""
    with st.sidebar:
        st.title("🎛️ Controls")
        
        # Auto-refresh controls
        st.subheader("Auto Refresh")
        auto_refresh = st.checkbox(
            "Enable Auto Refresh", 
            value=st.session_state.get("auto_refresh_enabled", True),
            key="auto_refresh_checkbox"
        )
        st.session_state["auto_refresh_enabled"] = auto_refresh
        
        if auto_refresh:
            refresh_interval = st.slider(
                "Refresh Interval (seconds)",
                min_value=1,
                max_value=60,
                value=st.session_state.get("refresh_interval", 5),
                key="refresh_interval_slider"
            )
            st.session_state["refresh_interval"] = refresh_interval
        
        # Manual refresh button
        if st.button("🔄 Refresh Now"):
            st.rerun()
        
        st.divider()
        
        # View controls
        st.subheader("View Settings")
        
        view_mode = st.selectbox(
            "View Mode",
            ["overview", "detailed", "compact"],
            index=0,
            key="view_mode_select"
        )
        st.session_state["view_mode"] = view_mode
        
        show_debug = st.checkbox(
            "Show Debug Info",
            value=st.session_state.get("show_debug", False),
            key="show_debug_checkbox"
        )
        st.session_state["show_debug"] = show_debug
        
        st.divider()
        
        # System info
        st.subheader("System Info")
        st.metric("Backend", config.monitoring_backend.title())
        st.metric("Mode", config.get_mode_display())
        
        # Health status
        from ...shared.data_access import get_data_bus
        data_bus = get_data_bus()
        health_summary = data_bus.get_health_summary()
        
        st.subheader("Health Status")
        components = health_summary.get("components", {})
        
        for component_name, component_data in components.items():
            if component_data:
                status = component_data.get("status", "unknown")
                age = component_data.get("updated_within_sec", 0)
                
                if age < 60:
                    age_display = f"{age:.0f}s"
                else:
                    age_display = f"{age/60:.1f}m"
                
                st.metric(component_name.title(), status, age_display)
            else:
                st.metric(component_name.title(), "NO DATA")


def render_header(config: Any) -> None:
    """Render page header"""
    col1, col2, col3 = st.columns([3, 1, 1])
    
    with col1:
        st.title("📊 Coin Quant R11 Dashboard")
        st.markdown("Real-time trading system monitoring")
    
    with col2:
        mode_display = config.get_mode_display()
        st.metric("Mode", mode_display)
    
    with col3:
        auto_refresh = st.session_state.get("auto_refresh_enabled", True)
        refresh_interval = st.session_state.get("refresh_interval", 5)
        if auto_refresh:
            st.metric("Refresh", f"{refresh_interval}s")
        else:
            st.metric("Refresh", "OFF")


def render_tabs(config: Any) -> None:
    """Render main tabs"""
    if config.cards_only:
        # Cards-only mode
        from .views.symbol_cards import render_symbol_cards_only
        render_symbol_cards_only(config)
    else:
        # Full mode with tabs
        tab1, tab2, tab3, tab4 = st.tabs([
            "📊 Multi Board",
            "📈 Detail", 
            "🔍 Advanced Monitoring",
            "⚡ 매매 현황"
        ])
        
        with tab1:
            from .views.symbol_cards import render_multi_board
            render_multi_board(config)
        
        with tab2:
            render_detail_tab(config)
        
        with tab3:
            render_advanced_monitoring_tab(config)
        
        with tab4:
            render_trading_status_tab(config)


def render_detail_tab(config: Any) -> None:
    """Render detail tab"""
    st.title("📈 Detail View")
    
    # Symbol selector
    selected_symbol = st.selectbox(
        "Select Symbol",
        ["BTCUSDT", "ETHUSDT", "ADAUSDT", "SOLUSDT", "XRPUSDT"],
        key="detail_symbol_select"
    )
    
    if selected_symbol:
        from ...shared.data_access import get_data_bus
        data_bus = get_data_bus()
        symbol_data = data_bus.get_symbol_data(selected_symbol)
        
        # Detailed symbol information
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Price Information")
            price_data = symbol_data.get("price")
            if price_data:
                st.json(price_data)
            else:
                st.info("No price data available")
        
        with col2:
            st.subheader("Signal Information")
            signal_data = symbol_data.get("signal")
            if signal_data:
                st.json(signal_data)
            else:
                st.info("No signal data available")


def render_advanced_monitoring_tab(config: Any) -> None:
    """Render advanced monitoring tab"""
    st.title("🔍 Advanced Monitoring")
    
    # Health monitoring
    st.subheader("Health Monitoring")
    from ...shared.data_access import get_data_bus
    data_bus = get_data_bus()
    health_summary = data_bus.get_health_summary()
    
    if health_summary:
        st.json(health_summary)
    else:
        st.info("No health data available")
    
    # Metrics monitoring
    st.subheader("Metrics")
    metrics_summary = data_bus.get_metrics_summary()
    
    if metrics_summary:
        st.json(metrics_summary)
    else:
        st.info("No metrics data available")


def render_trading_status_tab(config: Any) -> None:
    """Render trading status tab"""
    st.title("⚡ 매매 현황")
    
    # Positions summary
    st.subheader("Positions")
    from ...shared.data_access import get_data_bus
    data_bus = get_data_bus()
    positions_summary = data_bus.get_positions_summary()
    
    if positions_summary:
        st.json(positions_summary)
    else:
        st.info("No position data available")


def render_main_layout(config: Any) -> None:
    """Render main layout"""
    # Header
    render_header(config)
    
    # Sidebar
    render_sidebar(config)
    
    # Main content
    render_tabs(config)
