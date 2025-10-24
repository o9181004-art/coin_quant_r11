#!/usr/bin/env python3
"""
Main Application Entry Point for Coin Quant R11 Dashboard

Orchestrates the Streamlit dashboard with proper path resolution and data access.
"""

import logging
import os
import sys
from pathlib import Path

import streamlit as st

# Add project root to path
def setup_paths():
    """Setup project paths and imports"""
    # Get project root
    current_file = Path(__file__).resolve()
    project_root = None
    
    # Walk up to find project root
    for path in [current_file.parent] + list(current_file.parents):
        if (path / "pyproject.toml").exists() or (path / "src" / "coin_quant").exists():
            project_root = path
            break
    
    if not project_root:
        project_root = current_file.parent.parent.parent.parent
    
    # Add src to Python path
    src_path = project_root / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    
    return project_root


def setup_logging():
    """Setup logging for Streamlit"""
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )


def setup_streamlit_config():
    """Setup Streamlit page configuration"""
    st.set_page_config(
        page_title="Coin Quant R11 - Dashboard",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded"
    )


def main():
    """Main application entry point"""
    # Setup paths and logging
    project_root = setup_paths()
    setup_logging()
    setup_streamlit_config()
    
    # Set environment variable for project root
    os.environ["COIN_QUANT_ROOT"] = str(project_root)
    
    # Initialize session state
    from .state import SessionState
    SessionState.initialize_defaults()
    
    # Load configuration
    from .config import UiConfig
    config = UiConfig.from_env()
    
    # Initialize data bus
    from coin_quant.shared.data_access import get_data_bus
    data_bus = get_data_bus()
    
    # Check backend configuration
    if config.monitoring_backend == "file":
        from coin_quant.shared.pathing import get_paths
        paths = get_paths()
        if not paths.health_dir.exists():
            st.warning(f"⚠️ Health directory not found: {paths.health_dir}. Dashboard will show warnings when services are down.")
    elif config.monitoring_backend == "http":
        if not config.monitoring_endpoint:
            st.warning("⚠️ MONITORING_ENDPOINT not set. Dashboard will show warnings when services are down.")
    
    # Render main layout
    from .layout import render_main_layout
    render_main_layout(config)
    
    # Auto-refresh logic
    if config.auto_refresh_enabled and st.session_state.get("auto_refresh_enabled", True):
        import time
        refresh_interval = st.session_state.get("refresh_interval", config.auto_refresh_seconds)
        
        # Simple auto-refresh implementation
        placeholder = st.empty()
        with placeholder.container():
            st.markdown(f"⏱️ Auto-refresh in {refresh_interval} seconds...")
        
        time.sleep(refresh_interval)
        st.rerun()


if __name__ == "__main__":
    main()
