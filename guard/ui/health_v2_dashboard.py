"""
HealthV2 Dashboard Integration
GREEN-by-Design gating for the main dashboard
"""
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import streamlit as st

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from shared.auto_trading_control import (disable_auto_trading, emergency_stop,
                                         enable_auto_trading,
                                         get_auto_trading_status)
from shared.health_v2 import (get_health_v2_summary,
                              is_system_ready_for_auto_trading,
                              validate_health_v2)


def render_health_v2_status():
    """Render HealthV2 status with GREEN-by-Design gating"""
    st.markdown("### 🏥 시스템 헬스 상태 (HealthV2)")
    
    # Get HealthV2 status
    try:
        health_status = validate_health_v2()
        
        # Overall status
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            if health_status.is_green:
                st.success(f"🟢 GREEN ({health_status.green_count}/7)")
            else:
                st.error(f"🔴 RED ({health_status.green_count}/7)")
        
        with col2:
            st.metric("Safe to Trade", "✅" if health_status.safe_to_trade else "❌")
        
        with col3:
            st.metric("Global Status", health_status.global_status)
        
        with col4:
            st.metric("Probe Count", f"{health_status.green_count}/7")
        
        # Detailed probe results
        st.markdown("#### 🔍 상세 프로브 결과")
        
        for probe in health_status.probe_results:
            col1, col2, col3, col4 = st.columns([2, 1, 1, 2])
            
            with col1:
                if probe.status:
                    st.success(f"✅ {probe.probe_name}")
                else:
                    st.error(f"❌ {probe.probe_name}")
            
            with col2:
                if probe.age_seconds > 0:
                    st.metric("Age", f"{probe.age_seconds:.1f}s")
                else:
                    st.metric("Age", "N/A")
            
            with col3:
                if probe.threshold_seconds > 0:
                    st.metric("Threshold", f"{probe.threshold_seconds:.1f}s")
                else:
                    st.metric("Threshold", "N/A")
            
            with col4:
                st.text(probe.message)
        
        # Summary
        if health_status.is_green:
            st.success("🎉 모든 시스템이 정상 작동 중입니다. 자동매매가 가능합니다.")
        else:
            failed_probes = [p.probe_name for p in health_status.probe_results if not p.status]
            st.error(f"⚠️ 다음 프로브가 실패했습니다: {', '.join(failed_probes)}")
        
        return health_status
        
    except Exception as e:
        st.error(f"HealthV2 상태 확인 중 오류: {e}")
        return None


def render_auto_trading_control():
    """Render auto trading control with GREEN gating"""
    st.markdown("### ⚡ 자동매매 제어")
    
    try:
        # Get current status
        auto_status = get_auto_trading_status()
        health_status = validate_health_v2()
        
        # Status display
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if auto_status.get("enabled", False):
                st.success("🟢 자동매매 활성")
            else:
                st.error("🔴 자동매매 비활성")
        
        with col2:
            st.metric("Health Status", health_status.global_status)
        
        with col3:
            st.metric("Green Count", f"{health_status.green_count}/7")
        
        # Control buttons
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("🚀 Start Auto-Trading", type="primary", use_container_width=True):
                if health_status.is_green:
                    result = enable_auto_trading("dashboard")
                    if result.get("success", False):
                        st.success("✅ 자동매매가 시작되었습니다!")
                        st.rerun()
                    else:
                        st.error(f"❌ 자동매매 시작 실패: {result.get('reason', 'Unknown error')}")
                else:
                    st.error("❌ 시스템이 GREEN 상태가 아닙니다. 모든 프로브가 통과해야 합니다.")
        
        with col2:
            if st.button("⏸️ Stop Auto-Trading", use_container_width=True):
                result = disable_auto_trading("dashboard", "Manual stop from dashboard")
                if result.get("success", False):
                    st.success("✅ 자동매매가 중지되었습니다!")
                    st.rerun()
                else:
                    st.error(f"❌ 자동매매 중지 실패: {result.get('reason', 'Unknown error')}")
        
        with col3:
            if st.button("🚨 Emergency Stop", type="secondary", use_container_width=True):
                result = emergency_stop("Emergency stop from dashboard")
                if result.get("success", False):
                    st.error("🚨 비상정지가 실행되었습니다!")
                    st.rerun()
                else:
                    st.error(f"❌ 비상정지 실패: {result.get('reason', 'Unknown error')}")
        
        # Status details
        if auto_status.get("enabled", False):
            st.info(f"💡 자동매매 활성화됨 (by {auto_status.get('enabled_by', 'unknown')})")
            if auto_status.get("last_enabled"):
                last_enabled = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(auto_status["last_enabled"]))
                st.text(f"마지막 활성화: {last_enabled}")
        else:
            st.warning("⚠️ 자동매매가 비활성화되어 있습니다.")
            if auto_status.get("reason"):
                st.text(f"사유: {auto_status['reason']}")
        
        return auto_status
        
    except Exception as e:
        st.error(f"자동매매 제어 상태 확인 중 오류: {e}")
        return None


def render_system_overview():
    """Render system overview with key metrics"""
    st.markdown("### 📊 시스템 개요")
    
    try:
        # Get statuses
        health_status = validate_health_v2()
        auto_status = get_auto_trading_status()
        
        # Key metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                "System Status",
                health_status.global_status,
                delta=f"{health_status.green_count}/7 probes"
            )
        
        with col2:
            st.metric(
                "Auto Trading",
                "ON" if auto_status.get("enabled", False) else "OFF",
                delta="Safe" if health_status.safe_to_trade else "Unsafe"
            )
        
        with col3:
            st.metric(
                "Health Score",
                f"{health_status.green_count}/7",
                delta="GREEN" if health_status.is_green else "RED"
            )
        
        with col4:
            st.metric(
                "Last Update",
                time.strftime("%H:%M:%S"),
                delta="Live"
            )
        
        # Status summary
        if health_status.is_green and auto_status.get("enabled", False):
            st.success("🎉 시스템이 정상 작동 중이며 자동매매가 활성화되어 있습니다.")
        elif health_status.is_green:
            st.info("✅ 시스템이 정상 작동 중입니다. 자동매매를 시작할 수 있습니다.")
        else:
            st.error("❌ 시스템에 문제가 있습니다. 자동매매를 시작할 수 없습니다.")
        
    except Exception as e:
        st.error(f"시스템 개요 확인 중 오류: {e}")


def render_health_v2_dashboard():
    """Main HealthV2 dashboard renderer"""
    st.markdown("## 🏥 HealthV2 Dashboard")
    st.markdown("---")
    
    # System overview
    render_system_overview()
    st.markdown("---")
    
    # HealthV2 status
    health_status = render_health_v2_status()
    st.markdown("---")
    
    # Auto trading control
    auto_status = render_auto_trading_control()
    st.markdown("---")
    
    # Refresh button
    if st.button("🔄 새로고침", use_container_width=True):
        st.rerun()
    
    # Auto refresh info
    st.info("💡 이 페이지는 30초마다 자동으로 새로고침됩니다.")
    
    return {
        "health_status": health_status,
        "auto_status": auto_status
    }


if __name__ == "__main__":
    # Test the dashboard
    st.set_page_config(
        page_title="HealthV2 Dashboard",
        page_icon="🏥",
        layout="wide"
    )
    
    render_health_v2_dashboard()
