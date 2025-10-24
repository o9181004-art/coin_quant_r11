#!/usr/bin/env python3
"""
Autopilot Toggle Component
Enqueues commands instead of acting inline
"""

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import streamlit as st


class AutopilotToggle:
    """Autopilot toggle that enqueues commands"""
    
    def __init__(self):
        self.queue_path = Path("shared_data/ops/command_queue.jsonl")
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Rate limiting
        self.last_command_ts = 0
        self.min_interval = 5.0  # 5 seconds between commands
    
    def get_autopilot_state(self) -> Dict[str, Any]:
        """Get autopilot state from SSOT"""
        try:
            from shared.control_plane import get_control_plane
            control_plane = get_control_plane()
            state = control_plane.get_state()
            
            return {
                "enabled": state.get("auto_trading_enabled", False),
                "since": state.get("since", 0),
                "last_reason": state.get("reason", "unknown"),
                "timestamp": state.get("timestamp", 0)
            }
        except Exception as e:
            st.error(f"Failed to get autopilot state: {e}")
            return {
                "enabled": False,
                "since": 0,
                "last_reason": "error",
                "timestamp": time.time()
            }
    
    def enqueue_command(self, action: str, reason: str = "UI command") -> bool:
        """Enqueue autopilot command"""
        try:
            # Rate limiting
            current_time = time.time()
            if current_time - self.last_command_ts < self.min_interval:
                remaining = self.min_interval - (current_time - self.last_command_ts)
                st.warning(f"Rate limited. Please wait {remaining:.1f} seconds.")
                return False
            
            # Generate idempotency key
            idempotency_key = f"{action}_{int(current_time)}_{uuid.uuid4().hex[:8]}"
            
            # Create command
            command = {
                "timestamp": current_time,
                "action": action,
                "idempotency_key": idempotency_key,
                "reason": reason,
                "ttl": 300,  # 5 minutes
                "origin": "ui_toggle"
            }
            
            # Write to queue
            with open(self.queue_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(command) + '\n')
            
            # Update rate limit
            self.last_command_ts = current_time
            
            # Log command
            self._log_command(command)
            
            return True
            
        except Exception as e:
            st.error(f"Failed to enqueue command: {e}")
            return False
    
    def _log_command(self, command: Dict[str, Any]):
        """Log command for audit"""
        try:
            audit_file = Path("shared_data/logs/autopilot_commands.jsonl")
            audit_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(audit_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(command) + '\n')
        except Exception:
            pass  # Don't fail on audit logging
    
    def render_toggle(self):
        """Render autopilot toggle"""
        # Get current state
        state = self.get_autopilot_state()
        enabled = state["enabled"]
        
        # Display current state
        col1, col2 = st.columns([2, 1])
        
        with col1:
            if enabled:
                st.success("🟢 **Autopilot Enabled**")
                st.caption(f"Since: {time.strftime('%H:%M:%S', time.localtime(state['since']))}")
                st.caption(f"Reason: {state['last_reason']}")
            else:
                st.error("🔴 **Autopilot Disabled**")
                st.caption(f"Last reason: {state['last_reason']}")
        
        with col2:
            # Toggle button
            if enabled:
                if st.button("🛑 Disable", key="autopilot_disable", use_container_width=True):
                    if self.enqueue_command("autopilot_disable", "UI toggle"):
                        st.success("Command enqueued!")
                        st.rerun()
            else:
                if st.button("🚀 Enable", key="autopilot_enable", use_container_width=True):
                    if self.enqueue_command("autopilot_enable", "UI toggle"):
                        st.success("Command enqueued!")
                        st.rerun()
        
        # Show queue status
        self._show_queue_status()
    
    def _show_queue_status(self):
        """Show command queue status"""
        try:
            if self.queue_path.exists():
                with open(self.queue_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                if lines:
                    st.info(f"📋 {len(lines)} command(s) in queue")
                    
                    # Show recent commands
                    recent_commands = []
                    for line in lines[-3:]:  # Last 3 commands
                        try:
                            cmd = json.loads(line.strip())
                            recent_commands.append(cmd)
                        except:
                            continue
                    
                    if recent_commands:
                        st.caption("Recent commands:")
                        for cmd in recent_commands:
                            action = cmd.get("action", "unknown")
                            reason = cmd.get("reason", "no reason")
                            st.caption(f"  • {action}: {reason}")
                else:
                    st.caption("📋 Queue empty")
            else:
                st.caption("📋 No queue file")
                
        except Exception as e:
            st.caption(f"📋 Queue status error: {e}")


def render_autopilot_toggle():
    """Render autopilot toggle component"""
    toggle = AutopilotToggle()
    toggle.render_toggle()
