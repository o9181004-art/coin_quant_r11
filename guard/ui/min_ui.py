#!/usr/bin/env python3
"""
Minimal Read-Only Operations UI
Safe, no side effects, no CSS/JS, no trading module imports

Features:
- Read-only SSOT snapshot display
- Quarantine mode support
- Graceful degradation for missing/stale data
- No custom CSS/JS injection
- No writes, no API calls
"""

import os
import time
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
import streamlit as st

from guard.ui.readonly_data_loader import get_data_loader


# ============================================
# Safety Flags
# ============================================

def is_quarantine_mode() -> bool:
    """Check if UI_QUARANTINE_MODE is enabled"""
    return os.getenv("UI_QUARANTINE_MODE", "false").lower() == "true"


def is_readonly_mode() -> bool:
    """Check if UI_READONLY is enabled (default: true)"""
    return os.getenv("UI_READONLY", "true").lower() == "true"


# ============================================
# Quarantine Mode Rendering
# ============================================

def render_quarantine_mode():
    """Render minimal quarantine message (no CSS/JS)"""
    st.title("🔒 Quarantined UI")
    st.warning(
        "**UI_QUARANTINE_MODE is enabled**\n\n"
        "Read-only operations UI is disabled for safety.\n\n"
        "To enable, set `UI_QUARANTINE_MODE=false` in environment."
    )
    st.info(
        "**Current Status:**\n"
        f"- UI_QUARANTINE_MODE: `{os.getenv('UI_QUARANTINE_MODE', 'false')}`\n"
        f"- UI_READONLY: `{os.getenv('UI_READONLY', 'true')}`"
    )


# ============================================
# Header Row - Badges & Global Health
# ============================================

def render_header_row():
    """Render header with badges and global health (no CSS)"""
    st.title("📊 Read-Only Operations Dashboard")

    # Badges row
    col1, col2, col3 = st.columns([2, 2, 3])

    with col1:
        st.subheader("Environment")
        try:
            render_env_badges()
        except Exception as e:
            st.caption(f":gray[Env badges unavailable]")

    with col2:
        st.subheader("Modes")
        try:
            render_mode_badges()
        except Exception as e:
            st.caption(f":gray[Mode badges unavailable]")

    with col3:
        st.subheader("Global Health")
        try:
            render_global_health()
        except Exception as e:
            st.caption(f":gray[Health unavailable]")

    st.divider()


def render_env_badges():
    """Render environment badges"""
    # ENV badge
    is_testnet = os.getenv("BINANCE_USE_TESTNET", "true").lower() == "true"
    env_label = "TESTNET" if is_testnet else "🔴 LIVE"
    env_color = "orange" if is_testnet else "red"

    st.markdown(f"**ENV:** :{env_color}[{env_label}]")

    # DRY_RUN badge
    is_dry_run = os.getenv("DRY_RUN", "false").lower() == "true"
    if is_dry_run:
        st.markdown("**DRY_RUN:** :green[ON]")

    # RISK_PROFILE badge
    risk_profile = os.getenv("RISK_PROFILE", "").upper()
    if risk_profile:
        st.markdown(f"**RISK:** :blue[{risk_profile}]")


def render_mode_badges():
    """Render mode badges"""
    loader = get_data_loader()

    # CANARY_MODE badge
    canary_mode = os.getenv("CANARY_MODE", "false").lower() == "true"
    canary_label = "ON" if canary_mode else "OFF"
    canary_color = "orange" if canary_mode else "gray"
    st.markdown(f"**CANARY:** :{canary_color}[{canary_label}]")

    # Circuit Breaker badge
    cb_data, _, cb_stale = loader.get_circuit_breaker()
    if cb_data is not None and not cb_stale:
        cb_enabled = cb_data.get("enabled", False)
        cb_label = "ON" if cb_enabled else "OFF"
        cb_color = "red" if cb_enabled else "green"
        st.markdown(f"**CB:** :{cb_color}[{cb_label}]")


def render_global_health():
    """Render global health status"""
    loader = get_data_loader()

    health_data, age_sec, is_stale = loader.get_health()
    status, color = loader.get_global_health_status()

    # Status badge
    st.markdown(f"**Status:** :{color}[{status}]")

    # Updated timestamp
    if health_data is not None and age_sec is not None:
        updated_time = datetime.fromtimestamp(time.time() - age_sec).strftime("%H:%M:%S")
        st.markdown(f"**Updated:** {updated_time}")

        # STALE chip
        if is_stale:
            st.markdown(":orange[⚠️ STALE]")
    else:
        st.markdown("**Updated:** :gray[Unavailable]")


# ============================================
# KPI Row - Key Metrics
# ============================================

def render_kpi_row():
    """Render KPI metrics row (no CSS)"""
    loader = get_data_loader()

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        try:
            render_equity_kpi(loader)
        except Exception:
            st.metric(label="Equity (USDT)", value="–")
            st.caption(":gray[Unavailable]")

    with col2:
        try:
            render_free_usdt_kpi(loader)
        except Exception:
            st.metric(label="Free USDT", value="–")
            st.caption(":gray[Unavailable]")

    with col3:
        try:
            render_positions_kpi(loader)
        except Exception:
            st.metric(label="Open Positions", value="–")
            st.caption(":gray[Unavailable]")

    with col4:
        try:
            render_pnl_kpi(loader)
        except Exception:
            st.metric(label="Today PnL", value="–")
            st.caption(":gray[Unavailable]")

    st.divider()


def render_equity_kpi(loader):
    """Render equity KPI"""
    equity, free_usdt, is_stale = loader.get_equity_usdt()

    st.metric(
        label="Equity (USDT)",
        value=f"${equity:,.2f}" if equity is not None else "Unavailable",
        delta="STALE" if is_stale else None,
        delta_color="off" if is_stale else "normal"
    )


def render_free_usdt_kpi(loader):
    """Render free USDT KPI"""
    equity, free_usdt, is_stale = loader.get_equity_usdt()

    st.metric(
        label="Free USDT",
        value=f"${free_usdt:,.2f}" if free_usdt is not None else "Unavailable",
        delta="STALE" if is_stale else None,
        delta_color="off" if is_stale else "normal"
    )


def render_positions_kpi(loader):
    """Render open positions count KPI"""
    count = loader.get_open_positions_count()

    st.metric(
        label="Open Positions",
        value=count
    )


def render_pnl_kpi(loader):
    """Render today's PnL KPI"""
    pnl, is_stale = loader.get_today_pnl()

    if pnl is not None:
        st.metric(
            label="Today PnL",
            value=f"${pnl:,.2f}",
            delta="STALE" if is_stale else None,
            delta_color="off" if is_stale else "normal"
        )
    else:
        st.metric(
            label="Today PnL",
            value="–"
        )


# ============================================
# Tables - Positions, Health, Fills
# ============================================

def render_tables():
    """Render data tables"""
    tab1, tab2, tab3, tab4 = st.tabs(["Positions", "Health Components", "Recent Fills", "Balances"])

    with tab1:
        try:
            render_positions_table()
        except Exception as e:
            st.error(f"⚠️ Positions section failed to load")
            st.caption(f":gray[Error: {str(e)[:100]}]")

    with tab2:
        try:
            render_health_components_table()
        except Exception as e:
            st.error(f"⚠️ Health section failed to load")
            st.caption(f":gray[Error: {str(e)[:100]}]")

    with tab3:
        try:
            render_recent_fills_table()
        except Exception as e:
            st.error(f"⚠️ Fills section failed to load")
            st.caption(f":gray[Error: {str(e)[:100]}]")

    with tab4:
        try:
            render_balances_table()
        except Exception as e:
            st.error(f"⚠️ Balances section failed to load")
            st.caption(f":gray[Error: {str(e)[:100]}]")


def render_positions_table():
    """Render positions table with per-section error isolation"""
    st.subheader("Open Positions")

    try:
        loader = get_data_loader()
        positions_data, age_sec, is_stale = loader.get_positions()

        # Show STALE chip only for this section
        if is_stale:
            st.warning("⚠️ Position data is STALE (>180s)")

        if positions_data is None:
            st.info("Position data unavailable")
            return

        # Build table data
        rows = []
        for symbol, pos_data in positions_data.items():
            if isinstance(pos_data, dict):
                qty = pos_data.get("qty", 0)
                if qty > 0:
                    rows.append({
                        "Symbol": symbol,
                        "Side": "LONG",  # Spot positions are always long
                        "Qty": f"{qty:.8f}",
                        "Entry": f"${pos_data.get('avg_px', 0):.2f}",
                        "uPnL": f"${pos_data.get('unrealized_pnl', 0):.2f}"
                    })

        if rows:
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("No open positions")

    except Exception as e:
        st.error(f"⚠️ Failed to load positions")
        st.caption(f":gray[{str(e)[:100]}]")


def render_health_components_table():
    """Render health components table with per-section error isolation"""
    st.subheader("Health Components")

    try:
        loader = get_data_loader()
        health_data, age_sec, is_stale = loader.get_health()

        # Show STALE chip only for this section
        if is_stale:
            st.warning("⚠️ Health data is STALE (>15s)")

        if health_data is None:
            st.info("Health data unavailable")
            return

        components = health_data.get("components", {})

        # Core components to display
        core_components = ["feeder", "ares", "trader", "uds", "autoheal"]

        rows = []
        for comp in core_components:
            comp_data = components.get(comp, {})

            status = comp_data.get("status", "UNKNOWN")
            comp_age = comp_data.get("age_sec", 0)
            notes = comp_data.get("notes", "")

            rows.append({
                "Component": comp.upper(),
                "Status": status,
                "Age (sec)": f"{comp_age:.1f}",
                "Notes": notes
            })

        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

    except Exception as e:
        st.error(f"⚠️ Failed to load health components")
        st.caption(f":gray[{str(e)[:100]}]")


def render_recent_fills_table():
    """Render recent fills table with per-section error isolation (optional)"""
    st.subheader("Recent Fills (Last 10)")

    try:
        loader = get_data_loader()
        fills_data, age_sec, is_stale = loader.get_pnl_rollup(max_lines=10)

        if fills_data is None:
            st.info("Recent fills data unavailable")
            return

        if not fills_data:
            st.info("No recent fills")
            return

        rows = []
        for fill in fills_data:
            timestamp = fill.get("timestamp", 0)
            dt = datetime.fromtimestamp(timestamp).strftime("%H:%M:%S") if timestamp > 0 else "N/A"

            rows.append({
                "Time": dt,
                "Symbol": fill.get("symbol", ""),
                "Side": fill.get("side", ""),
                "Qty": f"{fill.get('qty', 0):.8f}",
                "Price": f"${fill.get('price', 0):.2f}",
                "PnL": f"${fill.get('pnl', 0):.2f}"
            })

        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

    except Exception as e:
        st.error(f"⚠️ Failed to load recent fills")
        st.caption(f":gray[{str(e)[:100]}]")


def render_balances_table():
    """Render top balances table with per-section error isolation"""
    st.subheader("Top Balances (Non-Zero)")

    try:
        loader = get_data_loader()
        balances = loader.get_top_balances(max_count=8)

        _, _, is_stale = loader.get_account_snapshot()

        # Show STALE chip only for this section
        if is_stale:
            st.warning("⚠️ Balance data is STALE (>180s)")

        if not balances:
            st.info("Balance data unavailable")
            return

        rows = []
        for balance in balances:
            rows.append({
                "Asset": balance["asset"],
                "Free": f"{balance['free']:.8f}",
                "Locked": f"{balance['locked']:.8f}",
                "Est. USDT": f"${balance['est_usdt']:.2f}"
            })

        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

    except Exception as e:
        st.error(f"⚠️ Failed to load balances")
        st.caption(f":gray[{str(e)[:100]}]")


# ============================================
# Main Render Function
# ============================================

def render_readonly_ui():
    """
    Main render function for read-only operations UI.

    This is the entry point called by the dashboard script.
    """
    # Check quarantine mode first
    if is_quarantine_mode():
        render_quarantine_mode()
        return

    # Verify readonly mode
    if not is_readonly_mode():
        st.warning(
            "⚠️ **UI_READONLY is disabled**\n\n"
            "This UI is designed for read-only operations only.\n"
            "Set `UI_READONLY=true` for safety."
        )

    # Render main UI
    render_header_row()
    render_kpi_row()
    render_tables()

    # Footer
    st.divider()
    st.caption(
        f"Read-Only Operations UI | "
        f"UI_READONLY: {os.getenv('UI_READONLY', 'true')} | "
        f"Last Update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
