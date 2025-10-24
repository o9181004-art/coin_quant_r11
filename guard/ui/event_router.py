#!/usr/bin/env python3
"""
Event Router - Event → Widget routing for partial UI updates
"""

import logging
import time
from typing import Dict, Any, Optional
from collections import defaultdict, deque

from shared.ui_event_bus import UIEvent, UIEventType, get_event_subscriber
from guard.ui.partial_renderer import get_partial_renderer


class EventRouter:
    """이벤트 라우터"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.partial_renderer = get_partial_renderer()
        self.event_subscriber = get_event_subscriber()
        
        # 이벤트 큐 관리
        self.event_queue = deque(maxlen=500)  # 백프레셔 방지
        self.last_processed_version = 0
        
        # 델타 추적
        self.last_values = {
            'balance_usdt': 0.0,
            'pnl_today': 0.0,
            'pnl_total': 0.0,
            'symbols': {},
            'status': {},
        }
        
        # 통계
        self._stats = {
            "events_routed": 0,
            "widgets_updated": 0,
            "events_coalesced": 0,
            "events_dropped": 0,
        }
        
        # 이벤트 핸들러 등록
        self._register_handlers()
    
    def _register_handlers(self):
        """이벤트 핸들러 등록"""
        self.event_subscriber.subscribe(UIEventType.TRADE_FILL, self._handle_trade_fill)
        self.event_subscriber.subscribe(UIEventType.ORDER_UPDATE, self._handle_order_update)
        self.event_subscriber.subscribe(UIEventType.BALANCE_UPDATE, self._handle_balance_update)
        self.event_subscriber.subscribe(UIEventType.PNL_UPDATE, self._handle_pnl_update)
        self.event_subscriber.subscribe(UIEventType.RISK_ALERT, self._handle_risk_alert)
        self.event_subscriber.subscribe(UIEventType.ERROR, self._handle_error)
        self.event_subscriber.subscribe(UIEventType.HEARTBEAT, self._handle_heartbeat)
    
    def _handle_trade_fill(self, event: UIEvent):
        """거래 체결 이벤트 처리"""
        try:
            # UI 상태 업데이트
            self.partial_renderer.update_ui_state(event)
            
            # 델타 계산
            symbol = event.symbol
            payload = event.payload
            
            if symbol:
                # 심볼별 델타
                symbol_delta = {
                    'position_size': payload.get('position_size', 0.0),
                    'avg_price': payload.get('avg_price', 0.0),
                    'price_change': 0.0,  # 가격 변화는 별도 이벤트에서 처리
                }
                
                # PnL 델타
                pnl_delta = payload.get('realized_pnl_delta', 0.0)
                
                # 위젯 업데이트
                self._update_symbol_card(symbol, symbol_delta)
                self._update_pnl_tiles(pnl_today_delta=pnl_delta)
                self._add_alert('success', f"Trade filled: {symbol} {pnl_delta:+.2f}")
                
                self._stats["widgets_updated"] += 3
            
            self._stats["events_routed"] += 1
            
        except Exception as e:
            self.logger.error(f"Trade fill handling error: {e}")
    
    def _handle_order_update(self, event: UIEvent):
        """주문 업데이트 이벤트 처리"""
        try:
            # UI 상태 업데이트
            self.partial_renderer.update_ui_state(event)
            
            # 델타 계산
            symbol = event.symbol
            payload = event.payload
            
            if symbol:
                # 심볼별 델타
                symbol_delta = {
                    'order_status': payload.get('status', 'N/A'),
                    'quantity': payload.get('quantity', 0.0),
                    'price': payload.get('price', 0.0),
                }
                
                # 위젯 업데이트
                self._update_symbol_card(symbol, symbol_delta)
                
                # 상태별 알림
                status = payload.get('status', '')
                if status == 'FILLED':
                    self._add_alert('success', f"Order filled: {symbol}")
                elif status == 'CANCELLED':
                    self._add_alert('warning', f"Order cancelled: {symbol}")
                elif status == 'FAILED':
                    self._add_alert('error', f"Order failed: {symbol}")
                
                self._stats["widgets_updated"] += 2
            
            self._stats["events_routed"] += 1
            
        except Exception as e:
            self.logger.error(f"Order update handling error: {e}")
    
    def _handle_balance_update(self, event: UIEvent):
        """잔고 업데이트 이벤트 처리"""
        try:
            # UI 상태 업데이트
            self.partial_renderer.update_ui_state(event)
            
            # 델타 계산
            payload = event.payload
            new_balance = payload.get('balance_usdt', 0.0)
            old_balance = self.last_values['balance_usdt']
            balance_delta = new_balance - old_balance
            
            # 위젯 업데이트
            self._update_balance_tile(balance_delta)
            
            # 값 업데이트
            self.last_values['balance_usdt'] = new_balance
            
            self._stats["widgets_updated"] += 1
            self._stats["events_routed"] += 1
            
        except Exception as e:
            self.logger.error(f"Balance update handling error: {e}")
    
    def _handle_pnl_update(self, event: UIEvent):
        """PnL 업데이트 이벤트 처리"""
        try:
            # UI 상태 업데이트
            self.partial_renderer.update_ui_state(event)
            
            # 델타 계산
            payload = event.payload
            new_pnl_today = payload.get('pnl_today', 0.0)
            new_pnl_total = payload.get('pnl_total', 0.0)
            
            old_pnl_today = self.last_values['pnl_today']
            old_pnl_total = self.last_values['pnl_total']
            
            pnl_today_delta = new_pnl_today - old_pnl_today
            pnl_total_delta = new_pnl_total - old_pnl_total
            
            # 위젯 업데이트
            self._update_pnl_tiles(pnl_today_delta, pnl_total_delta)
            
            # 값 업데이트
            self.last_values['pnl_today'] = new_pnl_today
            self.last_values['pnl_total'] = new_pnl_total
            
            self._stats["widgets_updated"] += 1
            self._stats["events_routed"] += 1
            
        except Exception as e:
            self.logger.error(f"PnL update handling error: {e}")
    
    def _handle_risk_alert(self, event: UIEvent):
        """리스크 알림 이벤트 처리"""
        try:
            # UI 상태 업데이트
            self.partial_renderer.update_ui_state(event)
            
            # 델타 계산
            payload = event.payload
            alert_code = payload.get('alert_code', '')
            message = payload.get('message', '')
            severity = payload.get('severity', 'warning')
            
            # 상태 스트립 업데이트
            status_delta = {}
            if alert_code == 'CIRCUIT_BREAKER':
                status_delta['circuit_breaker_active'] = True
            elif alert_code == 'E_STOP':
                status_delta['estop_active'] = True
            
            # 위젯 업데이트
            self._update_status_strip(status_delta)
            self._add_alert(severity, message)
            
            self._stats["widgets_updated"] += 2
            self._stats["events_routed"] += 1
            
        except Exception as e:
            self.logger.error(f"Risk alert handling error: {e}")
    
    def _handle_error(self, event: UIEvent):
        """오류 이벤트 처리"""
        try:
            # UI 상태 업데이트
            self.partial_renderer.update_ui_state(event)
            
            # 델타 계산
            payload = event.payload
            error_code = payload.get('error_code', '')
            message = payload.get('message', '')
            component = payload.get('component', 'unknown')
            
            # 상태 스트립 업데이트 (Degraded 상태)
            status_delta = {'degraded': True}
            
            # 위젯 업데이트
            self._update_status_strip(status_delta)
            self._add_alert('error', f"{component}: {message}")
            
            self._stats["widgets_updated"] += 2
            self._stats["events_routed"] += 1
            
        except Exception as e:
            self.logger.error(f"Error handling error: {e}")
    
    def _handle_heartbeat(self, event: UIEvent):
        """하트비트 이벤트 처리"""
        try:
            # UI 상태 업데이트
            self.partial_renderer.update_ui_state(event)
            
            # 델타 계산
            payload = event.payload
            snapshot_age = payload.get('snapshot_age', 0)
            feeder_lag = payload.get('feeder_lag', 0)
            active_symbols = payload.get('active_symbols', 0)
            
            # 상태 스트립 업데이트
            status_delta = {
                'snapshot_age': snapshot_age,
                'feeder_lag': feeder_lag,
                'active_symbols': active_symbols,
            }
            
            # 위젯 업데이트
            self._update_status_strip(status_delta)
            
            # 값 업데이트
            self.last_values['status'].update(status_delta)
            
            self._stats["widgets_updated"] += 1
            self._stats["events_routed"] += 1
            
        except Exception as e:
            self.logger.error(f"Heartbeat handling error: {e}")
    
    def _update_balance_tile(self, delta: float):
        """잔고 타일 업데이트"""
        try:
            self.partial_renderer.render_balance_tile(delta)
            self.logger.info(f"[UI] updated: balance (Δ{delta:+.2f})")
            
        except Exception as e:
            self.logger.error(f"Balance tile update error: {e}")
    
    def _update_pnl_tiles(self, pnl_today_delta: Optional[float] = None, 
                         pnl_total_delta: Optional[float] = None):
        """PnL 타일 업데이트"""
        try:
            self.partial_renderer.render_pnl_tiles(pnl_today_delta, pnl_total_delta)
            
            if pnl_today_delta is not None:
                self.logger.info(f"[UI] updated: pnl_today (Δ{pnl_today_delta:+.2f})")
            if pnl_total_delta is not None:
                self.logger.info(f"[UI] updated: pnl_total (Δ{pnl_total_delta:+.2f})")
            
        except Exception as e:
            self.logger.error(f"PnL tiles update error: {e}")
    
    def _update_status_strip(self, status_delta: Dict[str, Any]):
        """상태 스트립 업데이트"""
        try:
            self.partial_renderer.render_status_strip(status_delta)
            self.logger.info(f"[UI] updated: status_strip")
            
        except Exception as e:
            self.logger.error(f"Status strip update error: {e}")
    
    def _update_symbol_card(self, symbol: str, symbol_delta: Dict[str, Any]):
        """심볼 카드 업데이트"""
        try:
            # 심볼별 델타로 변환
            symbol_deltas = {symbol: symbol_delta}
            self.partial_renderer.render_symbol_cards(symbol_deltas)
            self.logger.info(f"[UI] updated: symbol_card ({symbol})")
            
        except Exception as e:
            self.logger.error(f"Symbol card update error: {e}")
    
    def _add_alert(self, alert_type: str, message: str):
        """알림 추가"""
        try:
            alert = {
                'type': alert_type,
                'message': message,
                'timestamp': time.time()
            }
            self.partial_renderer.render_alerts_bar(alert)
            self.logger.info(f"[UI] updated: alerts_bar ({alert_type})")
            
        except Exception as e:
            self.logger.error(f"Alert addition error: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """통계 반환"""
        return self._stats.copy()
    
    def get_last_values(self) -> Dict[str, Any]:
        """마지막 값 반환"""
        return self.last_values.copy()


# 전역 인스턴스
_global_event_router: Optional[EventRouter] = None


def get_event_router() -> EventRouter:
    """전역 이벤트 라우터 반환"""
    global _global_event_router
    if _global_event_router is None:
        _global_event_router = EventRouter()
    return _global_event_router


def start_event_routing():
    """이벤트 라우팅 시작"""
    get_event_router()


def get_routing_stats() -> Dict[str, Any]:
    """라우팅 통계 반환"""
    return get_event_router().get_stats()
