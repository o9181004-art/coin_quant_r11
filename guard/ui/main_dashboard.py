"""
메인 대시보드 UI 모듈 - 원본 app.py와 동일한 구조
"""

import streamlit as st

from guard.ui.advanced_monitoring import render_advanced_monitoring
from guard.ui.detail_tab import render_detail
from guard.ui.health_dashboard import render_health_dashboard
from guard.ui.multi_board import render_multi_board
from guard.ui.trade_history import render_trades_clean


def render_main_dashboard():
    """메인 대시보드 렌더링 - 원본과 동일한 탭 구조 (5개 탭)"""
    
    # 원본과 동일한 6개 탭 구조 (헬스 대시보드 추가)
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📊 Multi Board", 
        "📈 Detail", 
        "🔍 Advanced Monitoring", 
        "⚡ 매매 현황",
        "🔔 Alerts",
        "🏥 Health"
    ])
    
    with tab1:
        # Multi Board - 수익률 현황과 Symbol Cards
        render_multi_board()
    
    with tab2:
        # Detail - 차트와 상세 정보
        render_detail()
    
    with tab3:
        # Advanced Monitoring - KPI 대시보드와 진단 패널
        render_advanced_monitoring()
    
    with tab4:
        # 매매 현황 - 거래 내역
        render_trades_clean()
    
    with tab5:
        # 알림 탭 (원본과 동일)
        try:
            from guard.ui.notifications import render_alerts_tab
            render_alerts_tab(st.session_state.get("all_alerts", []))
        except ImportError:
            st.info("알림 시스템을 사용할 수 없습니다.")
    
    with tab6:
        # 헬스 대시보드 탭
        render_health_dashboard()
