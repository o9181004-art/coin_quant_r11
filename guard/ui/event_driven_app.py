#!/usr/bin/env python3
"""
Event-Driven App - Main application with partial updates and fallback
"""

import streamlit as st
import time
import logging
from typing import Dict, Any, Optional
from pathlib import Path

from shared.guardrails import get_guardrails
from shared.state_bus import get_state_bus
from guard.ui.partial_renderer import get_partial_renderer
from guard.ui.event_router import get_event_router, start_event_routing
from shared.ui_event_bus import get_event_subscriber


class EventDrivenApp:
    """이벤트 기반 앱"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.guardrails = get_guardrails()
        self.config = self.guardrails.get_config()
        self.state_bus = get_state_bus()
        
        # UI 컴포넌트
        self.partial_renderer = get_partial_renderer()
        self.event_router = get_event_router()
        self.event_subscriber = get_event_subscriber()
        
        # 설정
        self.event_ui_enabled = getattr(self.config, 'EVENT_UI_ENABLED', True)
        self.fallback_refresh_sec = getattr(self.config, 'UI_FALLBACK_REFRESH_SEC', 0)
        
        # 상태
        self.last_fallback_refresh = 0
        self.app_initialized = False
        
        # 통계
        self._stats = {
            "app_starts": 0,
            "fallback_refreshes": 0,
            "event_updates": 0,
            "last_update_time": 0.0,
        }
    
    def initialize_app(self):
        """앱 초기화"""
        try:
            if self.app_initialized:
                return
            
            # 페이지 설정
            st.set_page_config(
                page_title="Trading Dashboard",
                page_icon="📊",
                layout="wide",
                initial_sidebar_state="expanded"
            )
            
            # 이벤트 기반 UI 활성화 확인
            if self.event_ui_enabled:
                # 이벤트 라우팅 시작
                start_event_routing()
                self.logger.info("Event-driven UI enabled")
            else:
                self.logger.info("Event-driven UI disabled, using fallback")
            
            # 초기 UI 상태 부트스트랩
            self._bootstrap_ui_state()
            
            # 앱 초기화 완료
            self.app_initialized = True
            self._stats["app_starts"] += 1
            
        except Exception as e:
            self.logger.error(f"App initialization error: {e}")
    
    def _bootstrap_ui_state(self):
        """UI 상태 부트스트랩"""
        try:
            # 상태 버스에서 초기 데이터 로드
            state = self.state_bus.get_state()
            
            # UI 상태 초기화
            ui_state = self.partial_renderer.get_ui_state()
            
            # 잔고 정보
            risk_data = state.get('risk', {})
            ui_state.balance_usdt = risk_data.get('available_balance', 0.0)
            ui_state.pnl_today = risk_data.get('realized_pnl_today', 0.0)
            ui_state.pnl_total = risk_data.get('realized_pnl_total', 0.0)
            ui_state.unrealized_pnl = risk_data.get('unrealized_pnl', 0.0)
            
            # 상태 정보
            circuit_breaker = state.get('circuit_breaker', {})
            estop = state.get('estop', {})
            
            ui_state.status = {
                'circuit_breaker_active': circuit_breaker.get('active', False),
                'estop_active': estop.get('active', False),
                'snapshot_age': 0,
                'feeder_lag': 0,
                'active_symbols': 0,
            }
            
            # 심볼 정보
            symbols_data = state.get('symbols', {})
            for symbol, data in symbols_data.items():
                ui_state.symbols[symbol] = {
                    'last_price': data.get('last_price', 0.0),
                    'position_size': data.get('position_size', 0.0),
                    'order_status': 'N/A',
                }
            
            self.logger.info("UI state bootstrapped from state_bus")
            
        except Exception as e:
            self.logger.error(f"UI state bootstrap error: {e}")
    
    def render_dashboard(self):
        """대시보드 렌더링"""
        try:
            # 이벤트 기반 UI가 활성화된 경우
            if self.event_ui_enabled:
                self._render_event_driven_dashboard()
            else:
                self._render_fallback_dashboard()
            
            # 폴백 새로고침 확인
            self._check_fallback_refresh()
            
        except Exception as e:
            self.logger.error(f"Dashboard rendering error: {e}")
    
    def _render_event_driven_dashboard(self):
        """이벤트 기반 대시보드 렌더링"""
        try:
            # 제목
            st.title("📊 Trading Dashboard (Event-Driven)")
            
            # 상태 스트립
            self.partial_renderer.render_status_strip()
            
            # 메인 메트릭스
            col1, col2, col3 = st.columns(3)
            
            with col1:
                self.partial_renderer.render_balance_tile()
            
            with col2:
                self.partial_renderer.render_pnl_tiles()
            
            with col3:
                # 추가 메트릭스 (예: 거래 수, 승률 등)
                st.metric("Active Orders", "0")
                st.metric("Today's Trades", "0")
            
            # 심볼 카드 그리드
            st.subheader("Symbol Positions")
            self.partial_renderer.render_symbol_cards()
            
            # 알림 바
            st.subheader("Alerts")
            self.partial_renderer.render_alerts_bar()
            
            # 사이드바 정보
            with st.sidebar:
                st.header("System Status")
                
                # 이벤트 통계
                event_stats = self.event_subscriber.get_stats()
                st.metric("Events Received", event_stats.get('events_received', 0))
                st.metric("Events Processed", event_stats.get('events_processed', 0))
                
                # 라우팅 통계
                routing_stats = self.event_router.get_stats()
                st.metric("Widgets Updated", routing_stats.get('widgets_updated', 0))
                
                # 버전 정보
                versions = self.partial_renderer.get_versions()
                st.json(versions)
            
        except Exception as e:
            self.logger.error(f"Event-driven dashboard rendering error: {e}")
    
    def _render_fallback_dashboard(self):
        """폴백 대시보드 렌더링"""
        try:
            # 제목
            st.title("📊 Trading Dashboard (Fallback)")
            
            # 상태 정보
            state = self.state_bus.get_state()
            
            # 메인 메트릭스
            col1, col2, col3 = st.columns(3)
            
            with col1:
                risk_data = state.get('risk', {})
                balance = risk_data.get('available_balance', 0.0)
                st.metric("Balance", f"${balance:,.2f}")
            
            with col2:
                pnl_today = risk_data.get('realized_pnl_today', 0.0)
                st.metric("Today's PnL", f"${pnl_today:+,.2f}")
            
            with col3:
                pnl_total = risk_data.get('realized_pnl_total', 0.0)
                st.metric("Total PnL", f"${pnl_total:+,.2f}")
            
            # 상태 정보
            st.subheader("System Status")
            
            circuit_breaker = state.get('circuit_breaker', {})
            estop = state.get('estop', {})
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Circuit Breaker", "ON" if circuit_breaker.get('active') else "OFF")
            with col2:
                st.metric("E-STOP", "ON" if estop.get('active') else "OFF")
            
            # 심볼 정보
            st.subheader("Symbol Positions")
            symbols_data = state.get('symbols', {})
            
            if symbols_data:
                for symbol, data in symbols_data.items():
                    with st.expander(symbol):
                        st.write(f"Price: ${data.get('last_price', 0):,.4f}")
                        st.write(f"Position: {data.get('position_size', 0):.6f}")
            else:
                st.info("No symbol data available")
            
            # 사이드바
            with st.sidebar:
                st.header("Fallback Mode")
                st.info("Event-driven UI is disabled. Using fallback refresh.")
                
                if st.button("Manual Refresh"):
                    st.rerun()
            
        except Exception as e:
            self.logger.error(f"Fallback dashboard rendering error: {e}")
    
    def _check_fallback_refresh(self):
        """폴백 새로고침 확인"""
        try:
            # 폴백 새로고침이 비활성화된 경우
            if self.fallback_refresh_sec <= 0:
                return
            
            current_time = time.time()
            
            # 폴백 새로고침 시간 확인
            if current_time - self.last_fallback_refresh >= self.fallback_refresh_sec:
                self.logger.info(f"Fallback refresh triggered ({self.fallback_refresh_sec}s)")
                
                # 폴백 새로고침 실행
                st.rerun()
                
                self.last_fallback_refresh = current_time
                self._stats["fallback_refreshes"] += 1
            
        except Exception as e:
            self.logger.error(f"Fallback refresh check error: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """통계 반환"""
        stats = self._stats.copy()
        
        # 이벤트 통계 추가
        if self.event_ui_enabled:
            event_stats = self.event_subscriber.get_stats()
            routing_stats = self.event_router.get_stats()
            
            stats.update({
                'event_ui_enabled': True,
                'events_received': event_stats.get('events_received', 0),
                'events_processed': event_stats.get('events_processed', 0),
                'widgets_updated': routing_stats.get('widgets_updated', 0),
            })
        else:
            stats.update({
                'event_ui_enabled': False,
                'fallback_refresh_sec': self.fallback_refresh_sec,
            })
        
        return stats


def main():
    """메인 함수"""
    try:
        # 앱 초기화
        app = EventDrivenApp()
        app.initialize_app()
        
        # 대시보드 렌더링
        app.render_dashboard()
        
        # 통계 로깅 (디버그 모드에서만)
        if app.logger.isEnabledFor(logging.DEBUG):
            stats = app.get_stats()
            app.logger.debug(f"App stats: {stats}")
        
    except Exception as e:
        st.error(f"Application error: {e}")
        logging.error(f"Main application error: {e}")


if __name__ == "__main__":
    main()
