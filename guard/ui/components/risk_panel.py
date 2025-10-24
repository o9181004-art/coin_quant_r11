#!/usr/bin/env python3
"""
Risk Panel Component
Displays detailed risk mode information and controls
"""

import streamlit as st
from typing import Dict, Any, Optional

from shared.state.risk_mode_store import get_risk_mode_store
from guard.risk.risk_mode_manager import get_risk_mode_manager
from guard.risk.risk_profiles import get_profile_manager


def render_risk_panel(is_admin: bool = False) -> None:
    """
    Render risk panel with current mode, metrics, and controls

    Args:
        is_admin: Whether current user has admin privileges
    """
    try:
        st.subheader("🛡️ Risk Mode Control")

        # Get state
        store = get_risk_mode_store()
        manager = get_risk_mode_manager()
        profile_mgr = get_profile_manager()

        state = store.get_risk_state()
        status = manager.get_status()
        profile = profile_mgr.get_current_profile()

        # Create columns for layout
        col1, col2, col3 = st.columns([2, 2, 1])

        with col1:
            # Current mode
            mode = state.current_mode
            if mode == "SAFE":
                st.success(f"🛡️ **Current Mode:** SAFE")
            else:
                st.error(f"⚡ **Current Mode:** AGGRESSIVE")

            # Last switch info
            if state.last_switch_reason:
                st.caption(f"**Last Switch:** {state.last_switch_reason}")
                if state.last_switch_ts:
                    st.caption(f"**Time:** {state.last_switch_ts}")

        with col2:
            # Metrics
            st.metric("Intraday PnL", f"{state.intraday_pnl_pct:.2f}%")
            st.metric("Consecutive Losses", state.consecutive_losses)

        with col3:
            # Profile info
            if profile:
                st.caption(f"**Profile:** {profile.name}")
                st.caption(f"**Daily Limit:** {profile.daily_loss_limit_pct}%")
                st.caption(f"**Max Positions:** {profile.max_concurrent_positions}")

        # Separator
        st.divider()

        # Detailed metrics
        col_a, col_b, col_c = st.columns(3)

        with col_a:
            st.metric("Day Open Equity", f"${state.day_open_equity:,.2f}")

        with col_b:
            st.metric("Today Realized PnL", f"${state.today_realized_pnl:,.2f}")

        with col_c:
            st.metric("Peak Equity", f"${state.drawdown_peak_equity:,.2f}")

        # Trigger thresholds
        st.caption("**Trigger Thresholds:**")
        triggers = status.get('triggers', {})
        st.caption(
            f"Consecutive Losses: {triggers.get('consecutive_loss_trigger', 'N/A')} | "
            f"Intraday DD: {triggers.get('intraday_drawdown_trigger_pct', 'N/A')}% | "
            f"Hard Cutoff: {triggers.get('hard_cutoff_daily_loss_pct', 'N/A')}%"
        )

        # Admin controls
        if is_admin:
            st.divider()
            st.caption("**Admin Controls**")

            col_btn1, col_btn2 = st.columns(2)

            with col_btn1:
                # Resume Aggressive button
                if state.current_mode == "SAFE":
                    if status.get('return_policy') == "MANUAL":
                        if st.button("▶️ Resume Aggressive", type="primary", use_container_width=True):
                            success = manager.resume_aggressive(auto=False)
                            if success:
                                st.success("✅ Resumed AGGRESSIVE mode")
                                st.rerun()
                            else:
                                st.error("❌ Failed to resume AGGRESSIVE mode")
                    else:
                        st.button(
                            "▶️ Resume Aggressive (AUTO policy)",
                            disabled=True,
                            use_container_width=True,
                            help="Manual resume not allowed with AUTO return policy"
                        )

            with col_btn2:
                # Force SAFE button
                if state.current_mode == "AGGRESSIVE":
                    if st.button("⏸️ Force SAFE Mode", type="secondary", use_container_width=True):
                        success = store.switch_mode("SAFE", "manual_admin_ui", manual_override=True)
                        if success:
                            from guard.risk.risk_profiles import apply_profile_safe
                            apply_profile_safe()
                            st.warning("⚠️ Switched to SAFE mode")
                            st.rerun()
                        else:
                            st.error("❌ Failed to switch to SAFE mode")
        else:
            st.caption("*Admin privileges required for controls*")

        # Recent triggers
        recent_triggers = status.get('recent_triggers', [])
        if recent_triggers:
            st.divider()
            st.caption("**Recent Triggers:**")
            for trigger in recent_triggers[-3:]:
                st.caption(
                    f"• {trigger.get('timestamp', 'N/A')} - "
                    f"{trigger.get('trigger_type', 'N/A')} "
                    f"(value: {trigger.get('value', 'N/A')}, threshold: {trigger.get('threshold', 'N/A')})"
                )

    except Exception as e:
        st.error(f"Failed to render risk panel: {e}")


def render_risk_panel_compact() -> None:
    """Render compact risk panel (for sidebar or small spaces)"""
    try:
        store = get_risk_mode_store()
        state = store.get_risk_state()

        # Mode badge
        mode = state.current_mode
        if mode == "SAFE":
            st.success(f"🛡️ SAFE MODE", icon="✅")
        else:
            st.error(f"⚡ AGGRESSIVE MODE", icon="⚠️")

        # Key metrics
        st.metric("Intraday PnL", f"{state.intraday_pnl_pct:.2f}%", delta=None)
        st.metric("Loss Streak", state.consecutive_losses, delta=None)

        # Last switch
        if state.last_switch_reason:
            st.caption(f"Last: {state.last_switch_reason}")

    except Exception as e:
        st.error(f"Error: {e}")
