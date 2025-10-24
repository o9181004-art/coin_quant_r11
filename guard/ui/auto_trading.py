"""
자동매매 제어 UI 모듈
"""

import json
from pathlib import Path

import streamlit as st


def save_auto_trading_state(active_state=None):
    """자동매매 상태 저장"""
    try:
        if active_state is not None:
            st.session_state.auto_trading_active = active_state
        
        state = {
            "auto_trading_active": st.session_state.get("auto_trading_active", False),
            "timestamp": st.session_state.get("timestamp", 0)
        }
        
        state_file = Path("shared_data/auto_trading_state.json")
        state_file.parent.mkdir(exist_ok=True)
        
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
            
    except Exception as e:
        print(f"자동매매 상태 저장 실패: {e}")

def load_auto_trading_state():
    """자동매매 상태 로드"""
    try:
        state_file = Path("shared_data/auto_trading_state.json")
        if state_file.exists():
            with open(state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
                return state.get("auto_trading_active", False)
    except Exception as e:
        print(f"자동매매 상태 로드 실패: {e}")
    
    return False

def clear_auto_trading_state():
    """자동매매 상태 초기화"""
    try:
        state_file = Path("shared_data/auto_trading_state.json")
        if state_file.exists():
            state_file.unlink()
        
        if "auto_trading_active" in st.session_state:
            del st.session_state.auto_trading_active
            
    except Exception as e:
        print(f"자동매매 상태 초기화 실패: {e}")

def render_auto_trading_controls():
    """자동매매 제어 UI 렌더링"""
    st.markdown("### 🤖 자동매매 제어")
    
    # 현재 상태 로드
    current_state = load_auto_trading_state()
    if "auto_trading_active" not in st.session_state:
        st.session_state.auto_trading_active = current_state
    
    # 상태 표시
    status_color = "🟢" if st.session_state.auto_trading_active else "🔴"
    status_text = "활성" if st.session_state.auto_trading_active else "비활성"
    
    st.markdown(f"**상태:** {status_color} {status_text}")
    
    # 제어 버튼
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("▶️ 시작", use_container_width=True, disabled=st.session_state.auto_trading_active):
            st.session_state.auto_trading_active = True
            save_auto_trading_state(True)
            st.success("자동매매가 시작되었습니다!")
            st.rerun()
    
    with col2:
        if st.button("⏹️ 중지", use_container_width=True, disabled=not st.session_state.auto_trading_active):
            st.session_state.auto_trading_active = False
            save_auto_trading_state(False)
            st.warning("자동매매가 중지되었습니다!")
            st.rerun()
    
    # 상태 초기화 버튼
    if st.button("🔄 상태 초기화", use_container_width=True):
        clear_auto_trading_state()
        st.session_state.auto_trading_active = False
        st.info("자동매매 상태가 초기화되었습니다!")
        st.rerun()
