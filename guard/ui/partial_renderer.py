#!/usr/bin/env python3
"""
Partial Renderer - Stable, keyed placeholders for partial UI updates
"""

import streamlit as st
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass
import logging

from shared.ui_event_bus import UIEvent, UIEventType


@dataclass
class UIState:
    """UI 상태"""
    balance_usdt: float = 0.0
    pnl_today: float = 0.0
    pnl_total: float = 0.0
    unrealized_pnl: float = 0.0
    symbols: Dict[str, Dict[str, Any]] = None
    status: Dict[str, Any] = None
    alerts: list = None
    last_update: float = 0.0
    
    def __post_init__(self):
        if self.symbols is None:
            self.symbols = {}
        if self.status is None:
            self.status = {}
        if self.alerts is None:
            self.alerts = []


class PartialRenderer:
    """부분 렌더러"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # UI 상태 초기화
        if 'ui_state' not in st.session_state:
            st.session_state.ui_state = UIState()
        
        # 버전 관리
        if 'ui_versions' not in st.session_state:
            st.session_state.ui_versions = {
                'balance': 0,
                'pnl_today': 0,
                'pnl_total': 0,
                'symbols': 0,
                'status': 0,
                'alerts': 0,
            }
        
        # CSS는 shared.ui_styles.inject_global_css()에서 중앙 관리됨
        # 중복 CSS 주입 방지
    
    def render_balance_tile(self, delta: Optional[float] = None):
        """잔고 타일 렌더링"""
        try:
            ui_state = st.session_state.ui_state
            
            # 값 변경 확인
            if delta is not None and abs(delta) > 0.01:
                # 펄스 애니메이션 추가
                pulse_class = "pulse"
            else:
                pulse_class = ""
            
            # 색상 결정
            if delta is not None and delta > 0:
                color_class = "positive"
            elif delta is not None and delta < 0:
                color_class = "negative"
            else:
                color_class = "neutral"
            
            # 타일 렌더링
            with st.container():
                st.markdown(f"""
                <div class="ui-tile {color_class} {pulse_class}" id="bal_tile">
                    <div style="font-size: 24px; font-weight: bold;">
                        ${ui_state.balance_usdt:,.2f}
                    </div>
                    <div style="font-size: 12px; opacity: 0.8;">
                        Available Balance
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            # 버전 업데이트
            st.session_state.ui_versions['balance'] += 1
            
        except Exception as e:
            self.logger.error(f"Balance tile rendering error: {e}")
    
    def render_pnl_tiles(self, pnl_today_delta: Optional[float] = None, 
                        pnl_total_delta: Optional[float] = None):
        """PnL 타일 렌더링"""
        try:
            ui_state = st.session_state.ui_state
            
            # 오늘 PnL 타일
            if pnl_today_delta is not None and abs(pnl_today_delta) > 0.01:
                today_pulse = "pulse"
            else:
                today_pulse = ""
            
            if pnl_today_delta is not None and pnl_today_delta > 0:
                today_color = "positive"
            elif pnl_today_delta is not None and pnl_today_delta < 0:
                today_color = "negative"
            else:
                today_color = "neutral"
            
            # 총 PnL 타일
            if pnl_total_delta is not None and abs(pnl_total_delta) > 0.01:
                total_pulse = "pulse"
            else:
                total_pulse = ""
            
            if pnl_total_delta is not None and pnl_total_delta > 0:
                total_color = "positive"
            elif pnl_total_delta is not None and pnl_total_delta < 0:
                total_color = "negative"
            else:
                total_color = "neutral"
            
            # 타일 렌더링
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown(f"""
                <div class="ui-tile {today_color} {today_pulse}" id="pnl_today_tile">
                    <div style="font-size: 20px; font-weight: bold;">
                        ${ui_state.pnl_today:+,.2f}
                    </div>
                    <div style="font-size: 12px; opacity: 0.8;">
                        Today's PnL
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            with col2:
                st.markdown(f"""
                <div class="ui-tile {total_color} {total_pulse}" id="pnl_total_tile">
                    <div style="font-size: 20px; font-weight: bold;">
                        ${ui_state.pnl_total:+,.2f}
                    </div>
                    <div style="font-size: 12px; opacity: 0.8;">
                        Total PnL
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            # 버전 업데이트
            st.session_state.ui_versions['pnl_today'] += 1
            st.session_state.ui_versions['pnl_total'] += 1
            
        except Exception as e:
            self.logger.error(f"PnL tiles rendering error: {e}")
    
    def render_status_strip(self, status_delta: Optional[Dict[str, Any]] = None):
        """상태 스트립 렌더링"""
        try:
            ui_state = st.session_state.ui_state
            status = ui_state.status
            
            # 상태 정보
            cb_active = status.get('circuit_breaker_active', False)
            estop_active = status.get('estop_active', False)
            snapshot_age = status.get('snapshot_age', 0)
            feeder_lag = status.get('feeder_lag', 0)
            active_symbols = status.get('active_symbols', 0)
            
            # 색상 결정
            if snapshot_age > 15 or feeder_lag > 20:
                health_color = "stale"
            else:
                health_color = "neutral"
            
            # 상태 스트립 렌더링
            st.markdown(f"""
            <div class="status-strip {health_color}" id="status_strip">
                <div style="display: flex; gap: 10px; align-items: center;">
                    <span class="status-badge {'on' if cb_active else 'off'}">CB</span>
                    <span class="status-badge {'on' if estop_active else 'off'}">E-STOP</span>
                    <span style="font-size: 12px;">Symbols: {active_symbols}</span>
                </div>
                <div style="font-size: 12px; opacity: 0.8;">
                    Snapshot: {snapshot_age:.1f}s | Feeder: {feeder_lag:.1f}s
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # 버전 업데이트
            st.session_state.ui_versions['status'] += 1
            
        except Exception as e:
            self.logger.error(f"Status strip rendering error: {e}")
    
    def render_symbol_cards(self, symbol_deltas: Optional[Dict[str, Dict[str, Any]]] = None):
        """심볼 카드 렌더링"""
        try:
            ui_state = st.session_state.ui_state
            symbols = ui_state.symbols
            
            if not symbols:
                return
            
            # 심볼 카드 그리드 시작
            st.markdown('<div class="symbol-card-grid" id="symbol_cards_grid">', unsafe_allow_html=True)
            
            for symbol, data in symbols.items():
                # 델타 확인
                delta = symbol_deltas.get(symbol, {}) if symbol_deltas else {}
                
                # 색상 결정
                if delta.get('price_change', 0) > 0:
                    color_class = "positive"
                elif delta.get('price_change', 0) < 0:
                    color_class = "negative"
                else:
                    color_class = "neutral"
                
                # 펄스 확인
                if delta.get('price_change', 0) != 0:
                    pulse_class = "pulse"
                else:
                    pulse_class = ""
                
                # 심볼 카드 렌더링
                st.markdown(f"""
                <div class="symbol-card {color_class} {pulse_class}">
                    <div style="font-size: 16px; font-weight: bold; margin-bottom: 5px;">
                        {symbol}
                    </div>
                    <div style="font-size: 14px; margin-bottom: 3px;">
                        Price: ${data.get('last_price', 0):,.4f}
                    </div>
                    <div style="font-size: 12px; margin-bottom: 3px;">
                        Size: {data.get('position_size', 0):.6f}
                    </div>
                    <div style="font-size: 12px; opacity: 0.8;">
                        Status: {data.get('order_status', 'N/A')}
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            st.markdown('</div>', unsafe_allow_html=True)
            
            # 버전 업데이트
            st.session_state.ui_versions['symbols'] += 1
            
        except Exception as e:
            self.logger.error(f"Symbol cards rendering error: {e}")
    
    def render_alerts_bar(self, new_alert: Optional[Dict[str, Any]] = None):
        """알림 바 렌더링"""
        try:
            ui_state = st.session_state.ui_state
            alerts = ui_state.alerts
            
            # 최근 5개 알림만 표시
            recent_alerts = alerts[-5:] if len(alerts) > 5 else alerts
            
            # 알림 바 렌더링
            st.markdown('<div class="alerts-bar" id="alerts_bar">', unsafe_allow_html=True)
            
            for alert in recent_alerts:
                # 알림 타입별 색상
                alert_type = alert.get('type', 'info')
                if alert_type == 'success':
                    alert_class = "alert-success"
                elif alert_type == 'warning':
                    alert_class = "alert-warning"
                elif alert_type == 'error':
                    alert_class = "alert-error"
                else:
                    alert_class = "alert-info"
                
                # 알림 렌더링
                st.markdown(f"""
                <div class="alert-item {alert_class}">
                    {alert.get('message', 'Unknown alert')}
                </div>
                """, unsafe_allow_html=True)
            
            st.markdown('</div>', unsafe_allow_html=True)
            
            # 버전 업데이트
            st.session_state.ui_versions['alerts'] += 1
            
        except Exception as e:
            self.logger.error(f"Alerts bar rendering error: {e}")
    
    def update_ui_state(self, event: UIEvent):
        """UI 상태 업데이트"""
        try:
            ui_state = st.session_state.ui_state
            payload = event.payload
            
            if event.type == UIEventType.BALANCE_UPDATE:
                ui_state.balance_usdt = payload.get('balance_usdt', 0.0)
                
            elif event.type == UIEventType.PNL_UPDATE:
                ui_state.pnl_today = payload.get('pnl_today', 0.0)
                ui_state.pnl_total = payload.get('pnl_total', 0.0)
                ui_state.unrealized_pnl = payload.get('unrealized_pnl', 0.0)
                
            elif event.type == UIEventType.TRADE_FILL:
                symbol = event.symbol
                if symbol:
                    if symbol not in ui_state.symbols:
                        ui_state.symbols[symbol] = {}
                    
                    ui_state.symbols[symbol]['position_size'] = payload.get('position_size', 0.0)
                    ui_state.symbols[symbol]['avg_price'] = payload.get('avg_price', 0.0)
                
            elif event.type == UIEventType.ORDER_UPDATE:
                symbol = event.symbol
                if symbol:
                    if symbol not in ui_state.symbols:
                        ui_state.symbols[symbol] = {}
                    
                    ui_state.symbols[symbol]['order_status'] = payload.get('status', 'N/A')
                
            elif event.type == UIEventType.RISK_ALERT:
                alert = {
                    'type': payload.get('severity', 'warning'),
                    'message': payload.get('message', 'Risk alert'),
                    'timestamp': event.ts
                }
                ui_state.alerts.append(alert)
                
            elif event.type == UIEventType.HEARTBEAT:
                ui_state.status.update({
                    'snapshot_age': payload.get('snapshot_age', 0),
                    'feeder_lag': payload.get('feeder_lag', 0),
                    'active_symbols': payload.get('active_symbols', 0)
                })
            
            ui_state.last_update = time.time()
            
        except Exception as e:
            self.logger.error(f"UI state update error: {e}")
    
    def get_ui_state(self) -> UIState:
        """UI 상태 반환"""
        return st.session_state.ui_state
    
    def get_versions(self) -> Dict[str, int]:
        """버전 정보 반환"""
        return st.session_state.ui_versions.copy()


# 전역 인스턴스
_global_partial_renderer: Optional[PartialRenderer] = None


def get_partial_renderer() -> PartialRenderer:
    """전역 부분 렌더러 반환"""
    global _global_partial_renderer
    if _global_partial_renderer is None:
        _global_partial_renderer = PartialRenderer()
    return _global_partial_renderer


def render_balance_tile(delta: Optional[float] = None):
    """잔고 타일 렌더링"""
    get_partial_renderer().render_balance_tile(delta)


def render_pnl_tiles(pnl_today_delta: Optional[float] = None, 
                    pnl_total_delta: Optional[float] = None):
    """PnL 타일 렌더링"""
    get_partial_renderer().render_pnl_tiles(pnl_today_delta, pnl_total_delta)


def render_status_strip(status_delta: Optional[Dict[str, Any]] = None):
    """상태 스트립 렌더링"""
    get_partial_renderer().render_status_strip(status_delta)


def render_symbol_cards(symbol_deltas: Optional[Dict[str, Dict[str, Any]]] = None):
    """심볼 카드 렌더링"""
    get_partial_renderer().render_symbol_cards(symbol_deltas)


def render_alerts_bar(new_alert: Optional[Dict[str, Any]] = None):
    """알림 바 렌더링"""
    get_partial_renderer().render_alerts_bar(new_alert)
