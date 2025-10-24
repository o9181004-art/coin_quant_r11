#!/usr/bin/env python3
"""
Symbol Cards View for Coin Quant R11

Renders symbol cards with price, signal, and position information.
"""

import streamlit as st
from typing import Dict, Any, List
from ..widgets.common import (
    render_status_badge, render_age_pill, render_price_change, 
    render_pnl_badge, render_no_data_box, render_symbol_card_header,
    render_data_age_indicators, render_position_summary
)
from coin_quant.shared.data_access import get_data_bus


def render_symbol_card(symbol: str, symbol_data: Dict[str, Any], config: Any) -> None:
    """Render a single symbol card"""
    with st.container():
        # Card header
        render_symbol_card_header(
            symbol, 
            symbol_data.get("price"), 
            symbol_data.get("signal")
        )
        
        # Data age indicators
        render_data_age_indicators(
            symbol_data.get("price_age_seconds"),
            symbol_data.get("signal_age_seconds"),
            config.snapshot_age_warn,
            config.snapshot_age_halt
        )
        
        # Price information
        price_data = symbol_data.get("price")
        if price_data:
            col1, col2, col3 = st.columns(3)
            
            with col1:
                price = price_data.get("price", 0.0)
                st.metric("Current Price", f"${price:.4f}")
            
            with col2:
                change_24h = price_data.get("change_24h", 0.0)
                st.markdown(f"**24h Change:** {render_price_change(change_24h)}")
            
            with col3:
                volume = price_data.get("volume", 0.0)
                st.metric("Volume", f"{volume:.0f}")
        else:
            render_no_data_box("price", f"snapshots/prices_{symbol.lower()}.json")
        
        # Signal information
        signal_data = symbol_data.get("signal")
        if signal_data:
            col1, col2, col3 = st.columns(3)
            
            with col1:
                signal = signal_data.get("signal", "HOLD")
                st.markdown(f"**Signal:** {render_status_badge(signal)}")
            
            with col2:
                confidence = signal_data.get("confidence", 0.0)
                st.metric("Confidence", f"{confidence:.1f}%")
            
            with col3:
                reason = signal_data.get("reason", "No reason provided")
                st.markdown(f"**Reason:** {reason}")
        else:
            render_no_data_box("signal", "ares signals")
        
        # Position information
        position_data = symbol_data.get("position")
        if position_data:
            st.markdown("**Position:**")
            render_position_summary(position_data)
        else:
            # Show "No Position" instead of "No Data"
            st.info("📊 No active position")
        
        st.divider()


def render_symbol_cards_grid(symbols: List[str], config: Any) -> None:
    """Render a grid of symbol cards"""
    data_bus = get_data_bus()
    symbols_data = data_bus.get_all_symbols_data(symbols)
    
    # Filter symbols if filter is set
    symbol_filter = st.session_state.get("symbol_filter", "")
    if symbol_filter:
        filtered_symbols = [s for s in symbols if symbol_filter.lower() in s.lower()]
    else:
        filtered_symbols = symbols
    
    # Display filter
    col1, col2 = st.columns([3, 1])
    with col1:
        filter_input = st.text_input("Filter symbols:", value=symbol_filter, key="symbol_filter_input")
        st.session_state["symbol_filter"] = filter_input
    
    with col2:
        st.metric("Symbols", len(filtered_symbols))
    
    # Render cards
    for symbol in filtered_symbols:
        symbol_data = symbols_data.get(symbol, {})
        render_symbol_card(symbol, symbol_data, config)


def render_symbol_cards_only(config: Any) -> None:
    """Render only symbol cards (cards-only mode)"""
    st.title("📊 Symbol Cards")
    
    # Default symbols
    default_symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT", "SOLUSDT", "XRPUSDT"]
    
    # Get symbols from config or use defaults
    symbols = default_symbols  # TODO: Get from config
    
    render_symbol_cards_grid(symbols, config)


def render_multi_board(config: Any) -> None:
    """Render multi-board view with symbol cards"""
    st.title("📊 Multi Board")
    
    # Mode indicator
    mode_display = config.get_mode_display()
    mode_color = config.get_mode_color()
    
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        st.markdown(f"**Trading Mode:** {mode_display}")
    
    with col2:
        st.metric("Backend", config.monitoring_backend.title())
    
    with col3:
        auto_refresh = st.session_state.get("auto_refresh_enabled", True)
        st.metric("Auto Refresh", "ON" if auto_refresh else "OFF")
    
    # Symbol cards
    default_symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT", "SOLUSDT", "XRPUSDT"]
    render_symbol_cards_grid(default_symbols, config)
