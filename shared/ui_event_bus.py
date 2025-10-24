#!/usr/bin/env python3
"""
UI Event Bus - JSONL-based event streaming for partial UI updates
"""

import json
import logging
import os
import time
import threading
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from enum import Enum
import queue
from collections import defaultdict

from shared.guardrails import get_guardrails
from shared.state_bus import get_state_bus


class UIEventType(Enum):
    """UI 이벤트 타입"""
    TRADE_FILL = "trade_fill"
    ORDER_UPDATE = "order_update"
    BALANCE_UPDATE = "balance_update"
    PNL_UPDATE = "pnl_update"
    RISK_ALERT = "risk_alert"
    ERROR = "error"
    HEARTBEAT = "heartbeat"


@dataclass
class UIEvent:
    """UI 이벤트"""
    type: UIEventType
    ts: int  # unix ms
    symbol: Optional[str] = None
    payload: Dict[str, Any] = None
    version: int = 0
    
    def __post_init__(self):
        if self.payload is None:
            self.payload = {}


class UIEventProducer:
    """UI 이벤트 생산자"""
    
    def __init__(self, producer_name: str):
        self.producer_name = producer_name
        self.logger = logging.getLogger(__name__)
        self.guardrails = get_guardrails()
        self.config = self.guardrails.get_config()
        self.state_bus = get_state_bus()
        
        # 이벤트 파일 경로
        self.events_file = Path("shared_data/ui_events.jsonl")
        self.events_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 버전 관리
        self._version_lock = threading.Lock()
        self._current_version = 0
        
        # 통계
        self._stats = {
            "events_emitted": 0,
            "events_by_type": defaultdict(int),
            "last_emit_time": 0.0,
        }
    
    def _get_next_version(self) -> int:
        """다음 버전 번호 가져오기"""
        with self._version_lock:
            self._current_version += 1
            return self._current_version
    
    def _emit_event(self, event: UIEvent) -> bool:
        """이벤트 방출"""
        try:
            # 이벤트를 JSONL 파일에 추가
            event_dict = asdict(event)
            event_dict['type'] = event.type.value
            event_dict['producer'] = self.producer_name
            
            with open(self.events_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(event_dict, ensure_ascii=False) + '\n')
            
            # 상태 버스 카운터 업데이트
            self._update_counters(event)
            
            # 통계 업데이트
            self._stats["events_emitted"] += 1
            self._stats["events_by_type"][event.type.value] += 1
            self._stats["last_emit_time"] = time.time()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to emit event: {e}")
            return False
    
    def _update_counters(self, event: UIEvent):
        """상태 버스 카운터 업데이트"""
        try:
            # 카운터 업데이트
            counters = {
                'balance': 0,
                'pnl': 0,
                'errors': 0,
                'fills': 0,
                'orders': 0,
                'alerts': 0,
                'heartbeats': 0,
            }
            
            # 이벤트 타입별 카운터 증가
            if event.type == UIEventType.BALANCE_UPDATE:
                counters['balance'] = 1
            elif event.type == UIEventType.PNL_UPDATE:
                counters['pnl'] = 1
            elif event.type == UIEventType.ERROR:
                counters['errors'] = 1
            elif event.type == UIEventType.TRADE_FILL:
                counters['fills'] = 1
            elif event.type == UIEventType.ORDER_UPDATE:
                counters['orders'] = 1
            elif event.type == UIEventType.RISK_ALERT:
                counters['alerts'] = 1
            elif event.type == UIEventType.HEARTBEAT:
                counters['heartbeats'] = 1
            
            # 상태 버스에 카운터 업데이트
            self.state_bus.update_counters(counters)
            
        except Exception as e:
            self.logger.error(f"Failed to update counters: {e}")
    
    def emit_trade_fill(self, symbol: str, realized_pnl_delta: float, 
                       position_size: float, avg_price: float):
        """거래 체결 이벤트"""
        event = UIEvent(
            type=UIEventType.TRADE_FILL,
            ts=int(time.time() * 1000),
            symbol=symbol,
            payload={
                'realized_pnl_delta': realized_pnl_delta,
                'position_size': position_size,
                'avg_price': avg_price,
            },
            version=self._get_next_version()
        )
        return self._emit_event(event)
    
    def emit_order_update(self, symbol: str, status: str, 
                         order_id: str, quantity: float, price: float):
        """주문 업데이트 이벤트"""
        event = UIEvent(
            type=UIEventType.ORDER_UPDATE,
            ts=int(time.time() * 1000),
            symbol=symbol,
            payload={
                'status': status,
                'order_id': order_id,
                'quantity': quantity,
                'price': price,
            },
            version=self._get_next_version()
        )
        return self._emit_event(event)
    
    def emit_balance_update(self, balance_usdt: float, available_balance: float):
        """잔고 업데이트 이벤트"""
        event = UIEvent(
            type=UIEventType.BALANCE_UPDATE,
            ts=int(time.time() * 1000),
            payload={
                'balance_usdt': balance_usdt,
                'available_balance': available_balance,
            },
            version=self._get_next_version()
        )
        return self._emit_event(event)
    
    def emit_pnl_update(self, pnl_today: float, pnl_total: float, 
                       unrealized_pnl: float):
        """PnL 업데이트 이벤트"""
        event = UIEvent(
            type=UIEventType.PNL_UPDATE,
            ts=int(time.time() * 1000),
            payload={
                'pnl_today': pnl_today,
                'pnl_total': pnl_total,
                'unrealized_pnl': unrealized_pnl,
            },
            version=self._get_next_version()
        )
        return self._emit_event(event)
    
    def emit_risk_alert(self, alert_code: str, message: str, 
                       severity: str = "warning"):
        """리스크 알림 이벤트"""
        event = UIEvent(
            type=UIEventType.RISK_ALERT,
            ts=int(time.time() * 1000),
            payload={
                'alert_code': alert_code,
                'message': message,
                'severity': severity,
            },
            version=self._get_next_version()
        )
        return self._emit_event(event)
    
    def emit_error(self, error_code: str, message: str, 
                  component: str = "unknown"):
        """오류 이벤트"""
        event = UIEvent(
            type=UIEventType.ERROR,
            ts=int(time.time() * 1000),
            payload={
                'error_code': error_code,
                'message': message,
                'component': component,
            },
            version=self._get_next_version()
        )
        return self._emit_event(event)
    
    def emit_heartbeat(self, component: str, snapshot_age: float, 
                      feeder_lag: float, active_symbols: int):
        """하트비트 이벤트"""
        event = UIEvent(
            type=UIEventType.HEARTBEAT,
            ts=int(time.time() * 1000),
            payload={
                'component': component,
                'snapshot_age': snapshot_age,
                'feeder_lag': feeder_lag,
                'active_symbols': active_symbols,
            },
            version=self._get_next_version()
        )
        return self._emit_event(event)
    
    def get_stats(self) -> Dict[str, Any]:
        """통계 반환"""
        stats = self._stats.copy()
        stats['events_by_type'] = dict(stats['events_by_type'])
        return stats


class UIEventSubscriber:
    """UI 이벤트 구독자"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.guardrails = get_guardrails()
        self.config = self.guardrails.get_config()
        
        # 이벤트 파일 경로
        self.events_file = Path("shared_data/ui_events.jsonl")
        
        # 이벤트 큐
        self.event_queue = queue.Queue(maxsize=1000)
        
        # 구독자 스레드
        self._subscriber_thread: Optional[threading.Thread] = None
        self._subscriber_running = False
        
        # 파일 모니터링
        self._last_file_size = 0
        self._last_inode = None
        
        # 이벤트 처리
        self._event_handlers: Dict[UIEventType, List[callable]] = defaultdict(list)
        
        # 통계
        self._stats = {
            "events_received": 0,
            "events_processed": 0,
            "events_dropped": 0,
            "last_event_time": 0.0,
        }
    
    def start(self):
        """구독자 시작"""
        try:
            self._subscriber_running = True
            self._subscriber_thread = threading.Thread(
                target=self._subscriber_loop, 
                daemon=True
            )
            self._subscriber_thread.start()
            
            self.logger.info("UI Event Subscriber started")
            
        except Exception as e:
            self.logger.error(f"Failed to start UI Event Subscriber: {e}")
    
    def stop(self):
        """구독자 중지"""
        try:
            self._subscriber_running = False
            
            if self._subscriber_thread:
                self._subscriber_thread.join(timeout=5.0)
            
            self.logger.info("UI Event Subscriber stopped")
            
        except Exception as e:
            self.logger.error(f"Failed to stop UI Event Subscriber: {e}")
    
    def _subscriber_loop(self):
        """구독자 루프"""
        while self._subscriber_running:
            try:
                # 파일 모니터링
                if self._should_reopen_file():
                    self._reopen_file()
                
                # 새 이벤트 읽기
                self._read_new_events()
                
                # 이벤트 처리
                self._process_events()
                
                # 100ms 대기
                time.sleep(0.1)
                
            except Exception as e:
                self.logger.error(f"Subscriber loop error: {e}")
                time.sleep(1.0)
    
    def _should_reopen_file(self) -> bool:
        """파일 재오픈 필요 여부 확인"""
        try:
            if not self.events_file.exists():
                return True
            
            # 파일 크기 확인
            current_size = self.events_file.stat().st_size
            if current_size < self._last_file_size:
                return True  # 파일이 축소됨 (로테이션)
            
            # inode 확인
            current_inode = self.events_file.stat().st_ino
            if self._last_inode is not None and current_inode != self._last_inode:
                return True  # inode 변경됨 (로테이션)
            
            return False
            
        except Exception as e:
            self.logger.error(f"File check error: {e}")
            return True
    
    def _reopen_file(self):
        """파일 재오픈"""
        try:
            if self.events_file.exists():
                self._last_file_size = self.events_file.stat().st_size
                self._last_inode = self.events_file.stat().st_ino
            else:
                self._last_file_size = 0
                self._last_inode = None
            
            self.logger.info("UI events file reopened")
            
        except Exception as e:
            self.logger.error(f"File reopen error: {e}")
    
    def _read_new_events(self):
        """새 이벤트 읽기"""
        try:
            if not self.events_file.exists():
                return
            
            with open(self.events_file, 'r', encoding='utf-8') as f:
                # 마지막 위치로 이동
                f.seek(self._last_file_size)
                
                # 새 라인 읽기
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        event_dict = json.loads(line)
                        event = self._parse_event(event_dict)
                        
                        if event:
                            # 큐에 추가 (백프레셔 처리)
                            try:
                                self.event_queue.put_nowait(event)
                                self._stats["events_received"] += 1
                            except queue.Full:
                                self._stats["events_dropped"] += 1
                                self.logger.warning("Event queue full, dropping event")
                        
                    except json.JSONDecodeError as e:
                        self.logger.warning(f"Invalid JSON in events file: {e}")
                        continue
                
                # 파일 크기 업데이트
                self._last_file_size = f.tell()
                
        except Exception as e:
            self.logger.error(f"Event reading error: {e}")
    
    def _parse_event(self, event_dict: Dict[str, Any]) -> Optional[UIEvent]:
        """이벤트 파싱"""
        try:
            event_type = UIEventType(event_dict.get('type'))
            
            event = UIEvent(
                type=event_type,
                ts=event_dict.get('ts', 0),
                symbol=event_dict.get('symbol'),
                payload=event_dict.get('payload', {}),
                version=event_dict.get('version', 0)
            )
            
            return event
            
        except (ValueError, KeyError) as e:
            self.logger.warning(f"Invalid event format: {e}")
            return None
    
    def _process_events(self):
        """이벤트 처리"""
        try:
            # 큐에서 이벤트 처리
            while not self.event_queue.empty():
                try:
                    event = self.event_queue.get_nowait()
                    
                    # 이벤트 핸들러 호출
                    handlers = self._event_handlers.get(event.type, [])
                    for handler in handlers:
                        try:
                            handler(event)
                        except Exception as e:
                            self.logger.error(f"Event handler error: {e}")
                    
                    self._stats["events_processed"] += 1
                    self._stats["last_event_time"] = time.time()
                    
                except queue.Empty:
                    break
                    
        except Exception as e:
            self.logger.error(f"Event processing error: {e}")
    
    def subscribe(self, event_type: UIEventType, handler: callable):
        """이벤트 구독"""
        self._event_handlers[event_type].append(handler)
    
    def unsubscribe(self, event_type: UIEventType, handler: callable):
        """이벤트 구독 해제"""
        if handler in self._event_handlers[event_type]:
            self._event_handlers[event_type].remove(handler)
    
    def get_stats(self) -> Dict[str, Any]:
        """통계 반환"""
        return self._stats.copy()


# 전역 인스턴스
_global_event_producer: Optional[UIEventProducer] = None
_global_event_subscriber: Optional[UIEventSubscriber] = None


def get_event_producer(producer_name: str = "default") -> UIEventProducer:
    """전역 이벤트 생산자 반환"""
    global _global_event_producer
    if _global_event_producer is None:
        _global_event_producer = UIEventProducer(producer_name)
    return _global_event_producer


def get_event_subscriber() -> UIEventSubscriber:
    """전역 이벤트 구독자 반환"""
    global _global_event_subscriber
    if _global_event_subscriber is None:
        _global_event_subscriber = UIEventSubscriber()
        _global_event_subscriber.start()
    return _global_event_subscriber


def emit_trade_fill(symbol: str, realized_pnl_delta: float, 
                   position_size: float, avg_price: float):
    """거래 체결 이벤트 방출"""
    get_event_producer().emit_trade_fill(symbol, realized_pnl_delta, position_size, avg_price)


def emit_order_update(symbol: str, status: str, order_id: str, 
                     quantity: float, price: float):
    """주문 업데이트 이벤트 방출"""
    get_event_producer().emit_order_update(symbol, status, order_id, quantity, price)


def emit_balance_update(balance_usdt: float, available_balance: float):
    """잔고 업데이트 이벤트 방출"""
    get_event_producer().emit_balance_update(balance_usdt, available_balance)


def emit_pnl_update(pnl_today: float, pnl_total: float, unrealized_pnl: float):
    """PnL 업데이트 이벤트 방출"""
    get_event_producer().emit_pnl_update(pnl_today, pnl_total, unrealized_pnl)


def emit_risk_alert(alert_code: str, message: str, severity: str = "warning"):
    """리스크 알림 이벤트 방출"""
    get_event_producer().emit_risk_alert(alert_code, message, severity)


def emit_error(error_code: str, message: str, component: str = "unknown"):
    """오류 이벤트 방출"""
    get_event_producer().emit_error(error_code, message, component)


def emit_heartbeat(component: str, snapshot_age: float, 
                  feeder_lag: float, active_symbols: int):
    """하트비트 이벤트 방출"""
    get_event_producer().emit_heartbeat(component, snapshot_age, feeder_lag, active_symbols)
