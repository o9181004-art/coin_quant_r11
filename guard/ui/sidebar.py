"""
사이드바 UI 모듈
"""

import time

import streamlit as st

from guard.ui.auto_trading import render_auto_trading_controls
from guard.ui.health_monitor import render_health_status
from guard.ui.watchlist import render_watchlist_controls


def render_sidebar():
    """사이드바 렌더링"""
    
    with st.sidebar:
        st.title("🎛️ 제어판")
        
        # Auto Trading 섹션
        auto_trading_status = st.session_state.get("auto_trading_active", False)
        status_text = "ON" if auto_trading_status else "OFF"
        
        # Auto Trading 제목과 상태를 한 줄에 표시
        if auto_trading_status:
            st.markdown(
                """
                <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem;">
                    <h3 style="font-size: 1.1rem; font-weight: 700; color: #fff; margin: 0;">Auto Trading</h3>
                    <span style="color: #4CAF50; font-weight: 600; font-size: 0.9rem;">ON</span>
                    <div style="width: 8px; height: 8px; background-color: #4CAF50; border-radius: 50%;"></div>
                </div>
                """,
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                """
                <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem;">
                    <h3 style="font-size: 1.1rem; font-weight: 700; color: #fff; margin: 0;">Auto Trading</h3>
                    <span style="color: #f44336; font-weight: 600; font-size: 0.9rem;">OFF</span>
                    <div style="width: 8px; height: 8px; background-color: #f44336; border-radius: 50%;"></div>
                </div>
                """,
                unsafe_allow_html=True
            )
        
        # Auto Trading 버튼들
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Start Auto Trading", use_container_width=True):
                st.session_state.auto_trading_active = True
                st.success("자동매매 시작됨!")
                # st.rerun() 제거 - 상태 변경만으로 UI 업데이트
        
        with col2:
            if st.button("TESTNET", use_container_width=True):
                st.info("TESTNET 모드")
        
        st.markdown("---")
        
        # Manual Trading 섹션
        st.markdown("### Manual Trading")
        
        # Symbol 선택
        symbol = st.selectbox(
            "Symbol",
            options=["btcusdt", "ethusdt", "adausdt", "dotusdt", "linkusdt"],
            index=0
        )
        
        # Amount 입력
        amount = st.number_input(
            "Amount (USDT)",
            min_value=0.0,
            value=100.0,
            step=10.0
        )
        
        # BUY 버튼
        if st.button("BUY", use_container_width=True):
            st.success(f"{symbol.upper()} {amount} USDT 매수 주문!")
        
        # Position Check 버튼
        if st.button("Position Check", use_container_width=True):
            st.info("포지션 확인 기능은 추후 구현 예정입니다.")
        
        st.markdown("---")
        
        # 잔고 섹션
        st.markdown("### 잔고")
        
        # 잔고 표시
        st.markdown(
            """
            <div style="text-align: center; padding: 1rem; background-color: #2d2d2d; border-radius: 0.5rem; margin-bottom: 0.5rem;">
                <div style="font-size: 1.5rem; font-weight: bold; color: #4CAF50; margin-bottom: 0.5rem;">6,828.25 USDT</div>
                <div style="font-size: 0.8rem; color: #888;">실시간 업데이트</div>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        # 보유 코인 조회 버튼
        if st.button("보유 코인 조회", use_container_width=True):
            st.info("보유 코인 조회 기능은 추후 구현 예정입니다.")
        
        st.markdown("---")
        
        # 새로고침 버튼 제거됨 (중복 제거)
        
        # 메모리 사용량 표시
        try:
            from shared.memory_utils import get_memory_usage
            memory_usage = get_memory_usage()
            st.metric("💾 메모리 사용량", f"{memory_usage:.1f} MB")
        except:
            pass
