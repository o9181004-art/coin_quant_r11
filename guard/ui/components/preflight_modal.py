#!/usr/bin/env python3
"""
Preflight Modal - Show blocking flags with Resolve & Start option
"""

from datetime import datetime

import streamlit as st

try:
    from shared.preflight_guard import get_preflight_guard
    GUARD_AVAILABLE = True
except ImportError:
    GUARD_AVAILABLE = False


def show_preflight_modal() -> bool:
    """
    Show preflight modal if blocking flags exist
    
    Returns:
        True if user clicked Resolve & Start, False otherwise
    """
    if not GUARD_AVAILABLE:
        return False
    
    guard = get_preflight_guard()
    is_blocked, flags = guard.check_blocking_flags()
    
    if not is_blocked:
        return False
    
    # Show modal
    st.error("🚨 **System Blocked - Manual Intervention Required**")
    
    st.markdown("---")
    st.markdown("### Blocking Flags Detected")
    
    for flag in flags:
        severity_color = "#F44336" if flag.severity == "critical" else "#FF9800"
        severity_emoji = "🔴" if flag.severity == "critical" else "🟡"
        
        created_time = datetime.fromtimestamp(flag.created_ts).strftime("%Y-%m-%d %H:%M:%S")
        
        st.markdown(
            f"""
            <div style="
                background-color: {severity_color}15;
                border-left: 4px solid {severity_color};
                padding: 12px;
                margin: 8px 0;
                border-radius: 4px;
            ">
                <div style="font-weight: 600; font-size: 14px;">
                    {severity_emoji} {flag.file_path.name}
                </div>
                <div style="color: #aaa; font-size: 12px; margin-top: 4px;">
                    {flag.reason}
                </div>
                <div style="color: #888; font-size: 11px; margin-top: 4px;">
                    Created: {created_time}
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
    
    st.markdown("---")
    
    # Resolution options
    st.markdown("### Resolution Options")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.info(
            "**Option 1: Resolve & Start** (Recommended)\n\n"
            "- Removes all blocking flags\n"
            "- Sets 10-minute manual override\n"
            "- Prevents auto-recreation of flags\n"
            "- Starts services normally"
        )
        
        resolve_and_start = st.button(
            "🔓 Resolve & Start",
            type="primary",
            use_container_width=True,
            key="btn_resolve_and_start"
        )
    
    with col2:
        st.warning(
            "**Option 2: Manual Resolution**\n\n"
            "- Manually delete flag files\n"
            "- Check logs for root cause\n"
            "- Fix underlying issues\n"
            "- Then click Start normally"
        )
        
        if st.button(
            "📋 Copy Commands",
            use_container_width=True,
            key="btn_copy_commands"
        ):
            commands = "\n".join([
                f"Remove-Item '{flag.file_path}' -Force"
                for flag in flags
            ])
            st.code(commands, language="powershell")
    
    # Handle Resolve & Start
    if resolve_and_start:
        with st.spinner("🔄 Resolving flags..."):
            success = guard.resolve_flags_and_set_override(flags)
            
            if success:
                st.success("✅ All flags resolved! Manual override active for 10 minutes.")
                st.info("🚀 Click 'Start Auto Trading' button to proceed.")
                return True
            else:
                st.error("❌ Failed to resolve some flags. Try manual resolution.")
                return False
    
    return False

