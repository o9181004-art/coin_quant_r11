"""
Read-Only UI Components

This module provides read-only UI components that prevent unintended service
mutations during UI refreshes.
"""

import os
from typing import Any, Callable, Dict, Optional

import streamlit as st

from shared.command_queue import enqueue_command, get_command_queue


class ReadOnlyUI:
    """Read-only UI wrapper with mutation protection"""
    
    def __init__(self):
        self.allow_mutation = os.getenv('UI_ALLOW_SERVICE_MUTATION', 'false').lower() == 'true'
        self.command_queue = get_command_queue()
    
    def is_mutation_allowed(self) -> bool:
        """Check if service mutations are allowed"""
        return self.allow_mutation
    
    def show_readonly_banner(self):
        """Show read-only mode banner"""
        if not self.allow_mutation:
            # Get trading mode from SSOT for more accurate banner
            try:
                from shared.state_bus import get_trading_mode
                current_mode = get_trading_mode()
                
                if current_mode == "LIVE":
                    st.warning("🔴 **Live Trading Mode**: UI reruns won't affect services. Use explicit actions to modify services.")
                elif current_mode == "TESTNET":
                    st.info("🟡 **Testnet Mode**: UI reruns won't affect services. Use explicit actions to modify services.")
                else:
                    st.info("🔒 **Read-only Mode**: UI reruns won't affect services. Use explicit actions to modify services.")
            except Exception:
                # Fallback to original behavior
                st.info("🔒 **Read-only Mode**: UI reruns won't affect services. Use explicit actions to modify services.")
    
    def button_with_protection(self, label: str, action: str, args: Dict[str, Any] = None,
                             key: Optional[str] = None, help: Optional[str] = None,
                             disabled: bool = False, **kwargs) -> bool:
        """Button with read-only protection"""
        if args is None:
            args = {}
        
        if not self.allow_mutation:
            # Show disabled button with tooltip
            return st.button(
                f"🔒 {label}",
                disabled=True,
                key=key,
                help=f"Read-only mode: {help or 'Service mutations disabled'}"
            )
        
        # Normal button - enqueue command instead of direct execution
        clicked = st.button(label, key=key, help=help, disabled=disabled, **kwargs)
        
        if clicked:
            # Enqueue command
            result = enqueue_command(action, args, origin='ui')
            
            if result.startswith('duplicate_pending'):
                st.warning("⚠️ Command already pending")
            elif result.startswith('cooldown_active'):
                cooldown_remaining = result.split('_')[-1]
                st.warning(f"⏳ Command in cooldown: {cooldown_remaining} remaining")
            else:
                st.success(f"✅ Command queued: {result}")
                
            # Force rerun to show updated status
            st.rerun()
        
        return clicked
    
    def start_trader_button(self, key: str = "start_trader") -> bool:
        """Start trader button with protection"""
        return self.button_with_protection(
            "Start Trader",
            "start_trader",
            key=key,
            help="Start the trader service"
        )
    
    def stop_trader_button(self, key: str = "stop_trader") -> bool:
        """Stop trader button with protection"""
        return self.button_with_protection(
            "Stop Trader", 
            "stop_trader",
            key=key,
            help="Stop the trader service"
        )
    
    def restart_trader_button(self, key: str = "restart_trader") -> bool:
        """Restart trader button with protection"""
        return self.button_with_protection(
            "Restart Trader",
            "restart_trader", 
            key=key,
            help="Restart the trader service"
        )
    
    def start_feeder_button(self, key: str = "start_feeder") -> bool:
        """Start feeder button with protection"""
        return self.button_with_protection(
            "Start Feeder",
            "start_feeder",
            key=key,
            help="Start the feeder service"
        )
    
    def stop_feeder_button(self, key: str = "stop_feeder") -> bool:
        """Stop feeder button with protection"""
        return self.button_with_protection(
            "Stop Feeder",
            "stop_feeder", 
            key=key,
            help="Stop the feeder service"
        )
    
    def restart_feeder_button(self, key: str = "restart_feeder") -> bool:
        """Restart feeder button with protection"""
        return self.button_with_protection(
            "Restart Feeder",
            "restart_feeder",
            key=key,
            help="Restart the feeder service"
        )
    
    def reconcile_env_button(self, key: str = "reconcile_env") -> bool:
        """Reconcile environment button with protection"""
        return self.button_with_protection(
            "Reconcile Environment",
            "reconcile_env",
            key=key,
            help="Reconcile environment without restarting services"
        )
    
    def apply_ssot_button(self, targets: list = None, key: str = "apply_ssot") -> bool:
        """Apply SSOT button with protection"""
        if targets is None:
            targets = ['trader', 'feeder']
            
        return self.button_with_protection(
            "Apply SSOT to Services",
            "apply_ssot",
            args={'targets': targets},
            key=key,
            help="Apply SSOT and restart specified services"
        )
    
    def show_command_queue_status(self):
        """Show command queue status in sidebar"""
        with st.sidebar:
            st.markdown("### 📋 Command Queue")
            
            try:
                status = self.command_queue.get_status()
                
                st.metric("Pending", status['pending_commands'])
                st.metric("Processing", status['processing_commands'])
                st.metric("Completed", status['completed_commands'])
                st.metric("Failed", status['failed_commands'])
                st.metric("Active Cooldowns", status['active_cooldowns'])
                
                if status['pending_commands'] > 0:
                    st.info("Commands pending processing")
                    
            except Exception as e:
                st.error(f"Queue status error: {e}")
    
    def show_service_status(self):
        """Show service status with mutation protection info"""
        with st.sidebar:
            st.markdown("### 🔧 Service Status")
            
            # Service running status (read-only info)
            try:
                from pathlib import Path

                import psutil
                
                services = ['trader', 'feeder', 'ares', 'health_emitter']
                
                for service in services:
                    pid_file = Path(f"shared_data/pids/{service}.pid")
                    running = False
                    
                    if pid_file.exists():
                        try:
                            with open(pid_file, 'r') as f:
                                pid = int(f.read().strip())
                            running = psutil.pid_exists(pid)
                        except Exception:
                            pass
                    
                    status_icon = "🟢" if running else "🔴"
                    st.text(f"{status_icon} {service.title()}")
                    
            except ImportError:
                st.text("Service status unavailable")
            
            # Mutation mode
            mode_icon = "🔓" if self.allow_mutation else "🔒"
            mode_text = "Mutable" if self.allow_mutation else "Read-only"
            st.text(f"{mode_icon} Mode: {mode_text}")


# Global read-only UI instance
_readonly_ui = None

def get_readonly_ui() -> ReadOnlyUI:
    """Get global read-only UI instance"""
    global _readonly_ui
    if _readonly_ui is None:
        _readonly_ui = ReadOnlyUI()
    return _readonly_ui


def show_readonly_banner():
    """Show read-only banner if needed"""
    ui = get_readonly_ui()
    ui.show_readonly_banner()


def button_with_protection(label: str, action: str, args: Dict[str, Any] = None,
                         key: Optional[str] = None, help: Optional[str] = None,
                         disabled: bool = False, **kwargs) -> bool:
    """Convenience function for protected buttons"""
    ui = get_readonly_ui()
    return ui.button_with_protection(label, action, args, key, help, disabled, **kwargs)
