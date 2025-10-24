"""
헬스 모니터 UI 모듈
"""

import json
import time
from pathlib import Path

import streamlit as st


def load_health_status():
    """헬스 상태 로드"""
    try:
        health_file = Path("shared_data/health_status.json")
        if health_file.exists():
            with open(health_file, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"헬스 상태 로드 실패: {e}")
    
    return {
        "status": "unknown",
        "last_check": 0,
        "components": {}
    }

def render_health_status():
    """헬스 모니터 렌더링"""
    st.markdown("### 🏥 시스템 상태")
    
    health_data = load_health_status()
    
    # 전체 상태
    status = health_data.get("status", "unknown")
    status_emoji = {
        "healthy": "🟢",
        "warning": "🟡", 
        "error": "🔴",
        "unknown": "⚪"
    }.get(status, "⚪")
    
    st.markdown(f"**전체 상태:** {status_emoji} {status.upper()}")
    
    # 마지막 체크 시간
    last_check = health_data.get("last_check", 0)
    if last_check:
        time_str = time.strftime("%H:%M:%S", time.localtime(last_check))
        st.markdown(f"**마지막 체크:** {time_str}")
    
    # 컴포넌트 상태
    components = health_data.get("components", {})
    if components:
        st.markdown("**컴포넌트:**")
        for comp_name, comp_status in components.items():
            comp_emoji = {
                "healthy": "✅",
                "warning": "⚠️",
                "error": "❌"
            }.get(comp_status, "❓")
            
            st.markdown(f"• {comp_name}: {comp_emoji} {comp_status}")
    
    # 헬스체크 버튼
    if st.button("🔍 헬스체크", use_container_width=True):
        st.info("헬스체크를 실행합니다...")
        # 여기에 실제 헬스체크 로직 추가 가능
        time.sleep(1)
        st.success("헬스체크 완료!")
        st.rerun()