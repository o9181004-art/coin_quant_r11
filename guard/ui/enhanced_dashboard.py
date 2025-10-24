#!/usr/bin/env python3
"""
Enhanced Dashboard with Single Instance Guard and Debug Panel
"""

import os
import sys
import time
from pathlib import Path

import streamlit as st

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from shared.centralized_path_registry import get_path_registry
from shared.health_debug_panel import render_health_debug_panel
from shared.ui_instance_guard import get_ui_guard
from shared.ui_signal_order_panel import \
    render_comprehensive_signal_order_panel


def main():
    """메인 대시보드 함수"""
    # 페이지 설정
    st.set_page_config(
        page_title="코인퀀트 Enhanced Dashboard",
        page_icon="🚀",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # UI 인스턴스 가드 초기화
    ui_guard = get_ui_guard(project_root, port=8502)
    
    # 부트 배너 출력
    boot_banner = ui_guard.get_boot_banner()
    print(boot_banner)
    
    # 단일 인스턴스 체크
    success, error_msg = ui_guard.acquire_lock()
    
    if not success:
        # 다중 루트 감지
        multiple_roots = ui_guard.detect_multiple_roots()
        
        st.error("🚫 Multiple UI Instance Detected")
        st.write(f"**Error:** {error_msg}")
        
        if multiple_roots:
            st.warning("⚠️ Multiple repository roots detected:")
            for root in multiple_roots:
                st.write(f"- {root}")
            st.write(f"**This UI is bound to:** {project_root}")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Force Takeover", type="primary"):
                takeover_success, takeover_msg = ui_guard.force_takeover()
                if takeover_success:
                    st.success("✅ Successfully took over!")
                    st.rerun()
                else:
                    st.error(f"❌ Takeover failed: {takeover_msg}")
        
        with col2:
            if st.button("❌ Exit"):
                st.stop()
        
        return
    
    # 정상 실행
    try:
        # 헤더
        st.title("🚀 코인퀀트 Enhanced Dashboard")
        st.write(f"**Repository Root:** `{project_root}`")
        st.write(f"**PID:** {os.getpid()} | **Port:** 8502")
        
        # 다중 루트 경고
        multiple_roots = ui_guard.detect_multiple_roots()
        if multiple_roots:
            st.warning("⚠️ Multiple repository roots detected. This UI is bound to the current root.")
        
        # Auto-heal 상태 표시
        autoheal_enabled = os.environ.get("AUTOHEAL_ENABLED", "false").lower() == "true"
        if not autoheal_enabled:
            st.warning("⚠️ Auto-Heal is disabled (skipping recovery).")
        
        # 디버그 패널
        render_health_debug_panel()
        
        # Signal→Order 패널
        render_comprehensive_signal_order_panel(path_registry)
        
        # 기존 대시보드 내용
        st.markdown("---")
        st.subheader("📊 System Status")
        
        # 경로 레지스트리 정보
        path_registry = get_path_registry(project_root)
        path_validation = path_registry.validate_paths()
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Valid Paths", sum(path_validation.values()))
        
        with col2:
            st.metric("Total Paths", len(path_validation))
        
        with col3:
            st.metric("Health Files", sum(1 for k, v in path_validation.items() if k.startswith('health_') and v))
        
        # 경로 상태 테이블
        st.subheader("📁 Path Status")
        path_data = []
        for key, exists in path_validation.items():
            path_info = path_registry.get_path_info(key)
            path_data.append({
                "Key": key,
                "Path": path_info['path'],
                "Exists": "✅" if exists else "❌",
                "Type": "File" if path_info.get('is_file') else "Directory" if path_info.get('is_dir') else "Unknown"
            })
        
        st.dataframe(path_data, use_container_width=True)
        
        # 자동 새로고침
        if st.button("🔄 Refresh Dashboard"):
            st.rerun()
        
        # 사이드바
        with st.sidebar:
            st.header("🎛️ Controls")
            
            if st.button("🔄 Reload All"):
                st.rerun()
            
            if st.button("📊 Show Path Registry"):
                st.json(path_registry.get_all_paths())
            
            st.markdown("---")
            st.write("**Instance Info:**")
            st.write(f"PID: {os.getpid()}")
            st.write(f"Root: {project_root}")
            st.write(f"Port: 8502")
            
            if st.button("🚪 Exit Dashboard"):
                ui_guard.release_lock()
                st.stop()
    
    except Exception as e:
        st.error(f"Dashboard error: {e}")
        st.exception(e)
    
    finally:
        # 정리 작업은 Streamlit의 on_shutdown에서 처리
        pass


if __name__ == "__main__":
    main()
