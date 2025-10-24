#!/usr/bin/env python3
"""
Observability Dashboard for Coin Quant R11

Real-time monitoring dashboard with metrics visualization,
health status, and system observability.
"""

import sys
import time
import json
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import pandas as pd
import requests

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from coin_quant.shared.monitoring import MetricsCollector, MonitoringEndpoint
from coin_quant.shared.health import health_manager
from coin_quant.shared.paths import get_data_dir

class ObservabilityDashboard:
    """Real-time observability dashboard"""
    
    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or get_data_dir()
        self.metrics_collector = MetricsCollector(self.data_dir)
        self.monitoring_endpoint: Optional[MonitoringEndpoint] = None
        
        # Dashboard state
        self.auto_refresh = True
        self.refresh_interval = 10  # seconds
        self.last_refresh = 0
        
    def start_monitoring(self):
        """Start monitoring services"""
        if not self.monitoring_endpoint:
            self.monitoring_endpoint = MonitoringEndpoint(port=8080, data_dir=self.data_dir)
            self.monitoring_endpoint.start()
    
    def stop_monitoring(self):
        """Stop monitoring services"""
        if self.monitoring_endpoint:
            self.monitoring_endpoint.stop()
            self.monitoring_endpoint = None
    
    def get_health_data(self) -> Dict[str, Any]:
        """Get current health data"""
        try:
            health_data = health_manager._load_health_data()
            overall_status = health_manager.get_overall_status()
            
            return {
                "overall_status": overall_status,
                "components": health_data.get("components", {}),
                "timestamp": health_data.get("timestamp", time.time())
            }
        except Exception as e:
            return {"error": str(e)}
    
    def get_metrics_data(self, hours_back: int = 1) -> Dict[str, Any]:
        """Get metrics data"""
        try:
            return self.metrics_collector.get_metrics_summary(hours_back)
        except Exception as e:
            return {"error": str(e)}
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get system status via monitoring endpoint"""
        try:
            if not self.monitoring_endpoint:
                return {"error": "Monitoring endpoint not started"}
            
            response = requests.get("http://localhost:8080/status", timeout=5)
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"error": str(e)}

def render_health_status(dashboard: ObservabilityDashboard):
    """Render health status section"""
    st.subheader("🏥 Health Status")
    
    health_data = dashboard.get_health_data()
    
    if "error" in health_data:
        st.error(f"Health data error: {health_data['error']}")
        return
    
    overall_status = health_data.get("overall_status", "UNKNOWN")
    components = health_data.get("components", {})
    
    # Overall status
    if overall_status == "GREEN":
        st.success(f"🟢 Overall Status: {overall_status}")
    elif overall_status == "YELLOW":
        st.warning(f"🟡 Overall Status: {overall_status}")
    else:
        st.error(f"🔴 Overall Status: {overall_status}")
    
    # Component status
    if components:
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Service Components:**")
            for service_name, health_info in components.items():
                status = health_info.get("status", "UNKNOWN")
                last_update = health_info.get("last_update_ts", 0)
                freshness = health_info.get("updated_within_sec", 0)
                
                if status == "GREEN":
                    st.success(f"✅ {service_name}: {status}")
                elif status == "YELLOW":
                    st.warning(f"⚠️ {service_name}: {status}")
                else:
                    st.error(f"❌ {service_name}: {status}")
                
                st.caption(f"Last update: {freshness:.1f}s ago")
        
        with col2:
            st.write("**Health Details:**")
            for service_name, health_info in components.items():
                with st.expander(f"{service_name} Details"):
                    st.json(health_info)
    else:
        st.warning("No component health data available")

def render_metrics_charts(dashboard: ObservabilityDashboard):
    """Render metrics charts"""
    st.subheader("📊 System Metrics")
    
    # Get metrics data
    metrics_data = dashboard.get_metrics_data(hours_back=1)
    
    if "error" in metrics_data:
        st.error(f"Metrics error: {metrics_data['error']}")
        return
    
    if not metrics_data.get("data_points", 0):
        st.warning("No metrics data available")
        return
    
    # System metrics
    system_metrics = metrics_data.get("system", {})
    if system_metrics:
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric(
                "CPU Usage",
                f"{system_metrics.get('avg_cpu_percent', 0):.1f}%",
                delta=f"Peak: {system_metrics.get('peak_cpu_percent', 0):.1f}%"
            )
        
        with col2:
            st.metric(
                "Memory Usage",
                f"{system_metrics.get('avg_memory_percent', 0):.1f}%",
                delta=f"Peak: {system_metrics.get('peak_memory_percent', 0):.1f}%"
            )
        
        with col3:
            st.metric(
                "Disk Usage",
                f"{system_metrics.get('avg_disk_percent', 0):.1f}%"
            )
    
    # Service metrics
    services_metrics = metrics_data.get("services", {})
    if services_metrics:
        st.write("**Service Metrics:**")
        
        # Create service metrics table
        service_data = []
        for service_name, service_metrics in services_metrics.items():
            service_data.append({
                "Service": service_name,
                "Avg CPU %": f"{service_metrics.get('avg_cpu_percent', 0):.1f}",
                "Avg Memory MB": f"{service_metrics.get('avg_memory_mb', 0):.1f}",
                "Uptime Hours": f"{service_metrics.get('uptime_hours', 0):.1f}",
                "Data Points": service_metrics.get('data_points', 0)
            })
        
        if service_data:
            df = pd.DataFrame(service_data)
            st.dataframe(df, use_container_width=True)

def render_system_status(dashboard: ObservabilityDashboard):
    """Render system status section"""
    st.subheader("🖥️ System Status")
    
    system_status = dashboard.get_system_status()
    
    if "error" in system_status:
        st.error(f"System status error: {system_status['error']}")
        return
    
    # System information
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**System Overview:**")
        st.metric("Overall Status", system_status.get("overall_status", "UNKNOWN"))
        st.metric("CPU Usage", f"{system_status.get('system', {}).get('cpu_percent', 0):.1f}%")
        st.metric("Memory Usage", f"{system_status.get('system', {}).get('memory_percent', 0):.1f}%")
        st.metric("Disk Usage", f"{system_status.get('system', {}).get('disk_percent', 0):.1f}%")
    
    with col2:
        st.write("**Uptime:**")
        uptime_seconds = system_status.get("uptime", 0)
        uptime_hours = uptime_seconds / 3600
        st.metric("System Uptime", f"{uptime_hours:.1f} hours")
        
        st.write("**Services:**")
        services = system_status.get("services", {})
        for service_name, service_info in services.items():
            status = service_info.get("status", "UNKNOWN")
            if status == "GREEN":
                st.success(f"✅ {service_name}")
            elif status == "YELLOW":
                st.warning(f"⚠️ {service_name}")
            else:
                st.error(f"❌ {service_name}")

def render_debug_info(dashboard: ObservabilityDashboard):
    """Render debug information"""
    st.subheader("🔍 Debug Information")
    
    try:
        # Get debug info via monitoring endpoint
        if dashboard.monitoring_endpoint:
            response = requests.get("http://localhost:8080/debug", timeout=5)
            if response.status_code == 200:
                debug_info = response.json()
                st.json(debug_info)
            else:
                st.error(f"Debug info HTTP {response.status_code}")
        else:
            st.warning("Monitoring endpoint not started")
    
    except Exception as e:
        st.error(f"Debug info error: {e}")

def render_alerts_and_logs(dashboard: ObservabilityDashboard):
    """Render alerts and logs section"""
    st.subheader("🚨 Alerts & Logs")
    
    # Check for recent errors in health data
    health_data = dashboard.get_health_data()
    components = health_data.get("components", {})
    
    alerts = []
    for service_name, health_info in components.items():
        status = health_info.get("status", "UNKNOWN")
        if status == "RED":
            alerts.append({
                "service": service_name,
                "level": "ERROR",
                "message": f"{service_name} service is in RED status",
                "timestamp": health_info.get("last_update_ts", 0)
            })
        elif status == "YELLOW":
            alerts.append({
                "service": service_name,
                "level": "WARNING",
                "message": f"{service_name} service is in YELLOW status",
                "timestamp": health_info.get("last_update_ts", 0)
            })
    
    if alerts:
        st.write("**Active Alerts:**")
        for alert in alerts:
            if alert["level"] == "ERROR":
                st.error(f"🔴 {alert['service']}: {alert['message']}")
            else:
                st.warning(f"🟡 {alert['service']}: {alert['message']}")
    else:
        st.success("✅ No active alerts")
    
    # Log files section
    st.write("**Recent Logs:**")
    logs_dir = dashboard.data_dir / "logs"
    if logs_dir.exists():
        log_files = list(logs_dir.glob("*.log"))
        if log_files:
            selected_log = st.selectbox("Select log file:", [f.name for f in log_files])
            if selected_log:
                log_file = logs_dir / selected_log
                try:
                    with open(log_file, 'r') as f:
                        lines = f.readlines()
                        recent_lines = lines[-50:]  # Last 50 lines
                        st.text_area("Recent log entries:", value=''.join(recent_lines), height=300)
                except Exception as e:
                    st.error(f"Failed to read log file: {e}")
        else:
            st.info("No log files found")
    else:
        st.info("Logs directory not found")

def main():
    """Main dashboard application"""
    st.set_page_config(
        page_title="Coin Quant R11 - Observability Dashboard",
        page_icon="📊",
        layout="wide"
    )
    
    st.title("📊 Coin Quant R11 - Observability Dashboard")
    st.markdown("Real-time monitoring and observability for Coin Quant R11 trading system")
    
    # Initialize dashboard
    dashboard = ObservabilityDashboard()
    
    # Sidebar controls
    st.sidebar.title("Dashboard Controls")
    
    # Auto-refresh control
    auto_refresh = st.sidebar.checkbox("Auto Refresh", value=True)
    refresh_interval = st.sidebar.slider("Refresh Interval (seconds)", 5, 60, 10)
    
    # Monitoring control
    if st.sidebar.button("Start Monitoring"):
        dashboard.start_monitoring()
        st.sidebar.success("Monitoring started")
    
    if st.sidebar.button("Stop Monitoring"):
        dashboard.stop_monitoring()
        st.sidebar.success("Monitoring stopped")
    
    # Manual refresh
    if st.sidebar.button("Refresh Now"):
        st.rerun()
    
    # Main dashboard content
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🏥 Health Status",
        "📊 Metrics",
        "🖥️ System Status", 
        "🚨 Alerts & Logs",
        "🔍 Debug Info"
    ])
    
    with tab1:
        render_health_status(dashboard)
    
    with tab2:
        render_metrics_charts(dashboard)
    
    with tab3:
        render_system_status(dashboard)
    
    with tab4:
        render_alerts_and_logs(dashboard)
    
    with tab5:
        render_debug_info(dashboard)
    
    # Auto-refresh logic
    if auto_refresh:
        current_time = time.time()
        if current_time - dashboard.last_refresh >= refresh_interval:
            dashboard.last_refresh = current_time
            time.sleep(refresh_interval)
            st.rerun()

if __name__ == "__main__":
    main()
