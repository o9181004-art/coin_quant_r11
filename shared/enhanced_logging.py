#!/usr/bin/env python3
"""
Enhanced Logging & Telemetry - 로깅, 텔레메트리, 운영자 명확성 개선
"""

import json
import logging
import logging.handlers
import time
import threading
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
from enum import Enum
from collections import deque
import traceback

from shared.guardrails import get_guardrails
from shared.state_bus import get_state_bus


class LogLevel(Enum):
    """로그 레벨"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class EventType(Enum):
    """이벤트 타입"""
    ORDER_LIFECYCLE = "ORDER_LIFECYCLE"
    SIGNAL_GENERATED = "SIGNAL_GENERATED"
    CIRCUIT_BREAKER = "CIRCUIT_BREAKER"
    SERVICE_HEALTH = "SERVICE_HEALTH"
    RISK_EVENT = "RISK_EVENT"
    SYSTEM_ERROR = "SYSTEM_ERROR"
    PERFORMANCE = "PERFORMANCE"


@dataclass
class TelemetryEvent:
    """텔레메트리 이벤트"""
    timestamp: float
    event_type: EventType
    level: LogLevel
    message: str
    service: str
    data: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.data is None:
            self.data = {}


@dataclass
class OrderLifecycleEvent:
    """주문 생명주기 이벤트"""
    client_order_id: str
    symbol: str
    side: str
    status: str
    timestamp: float
    price: float = 0.0
    quantity: float = 0.0
    filled_quantity: float = 0.0
    average_price: float = 0.0
    error: str = ""
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class EnhancedLogger:
    """향상된 로거"""
    
    def __init__(self, config_path: str = "config/policy.yaml"):
        self.config_path = config_path
        self.logger = logging.getLogger(__name__)
        
        # 가드레일 및 상태 버스
        self.guardrails = get_guardrails()
        self.state_bus = get_state_bus()
        self.config = self.guardrails.get_config()
        
        # 로그 디렉토리
        self.log_dir = Path("logs")
        self.log_dir.mkdir(exist_ok=True)
        
        # 텔레메트리 이벤트 큐
        self._telemetry_events: deque = deque(maxlen=1000)
        self._telemetry_lock = threading.RLock()
        
        # 주문 생명주기 이벤트 큐
        self._order_events: deque = deque(maxlen=1000)
        self._order_lock = threading.RLock()
        
        # 통계
        self._stats = {
            "total_events": 0,
            "events_by_level": {},
            "events_by_type": {},
            "events_by_service": {},
            "last_event_time": 0.0,
        }
        
        # 로거 설정
        self._setup_loggers()
        
        # 텔레메트리 스레드
        self._telemetry_thread: Optional[threading.Thread] = None
        self._telemetry_running = False
    
    def _setup_loggers(self):
        """로거 설정"""
        try:
            # 루트 로거 설정
            root_logger = logging.getLogger()
            root_logger.setLevel(logging.DEBUG)
            
            # 기존 핸들러 제거
            for handler in root_logger.handlers[:]:
                root_logger.removeHandler(handler)
            
            # 콘솔 핸들러
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            console_handler.setFormatter(console_formatter)
            root_logger.addHandler(console_handler)
            
            # 파일 핸들러 (일반 로그)
            file_handler = logging.handlers.RotatingFileHandler(
                self.log_dir / "trading_system.log",
                maxBytes=10*1024*1024,  # 10MB
                backupCount=5
            )
            file_handler.setLevel(logging.DEBUG)
            file_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            file_handler.setFormatter(file_formatter)
            root_logger.addHandler(file_handler)
            
            # 오류 로그 핸들러
            error_handler = logging.handlers.RotatingFileHandler(
                self.log_dir / "errors.log",
                maxBytes=5*1024*1024,  # 5MB
                backupCount=3
            )
            error_handler.setLevel(logging.ERROR)
            error_handler.setFormatter(file_formatter)
            root_logger.addHandler(error_handler)
            
            # 주문 로그 핸들러
            order_handler = logging.handlers.RotatingFileHandler(
                self.log_dir / "orders.log",
                maxBytes=5*1024*1024,  # 5MB
                backupCount=3
            )
            order_handler.setLevel(logging.INFO)
            order_formatter = logging.Formatter(
                '%(asctime)s - %(message)s'
            )
            order_handler.setFormatter(order_formatter)
            
            # 주문 전용 로거
            order_logger = logging.getLogger("orders")
            order_logger.addHandler(order_handler)
            order_logger.setLevel(logging.INFO)
            order_logger.propagate = False
            
            # 텔레메트리 로그 핸들러
            telemetry_handler = logging.handlers.RotatingFileHandler(
                self.log_dir / "telemetry.log",
                maxBytes=5*1024*1024,  # 5MB
                backupCount=3
            )
            telemetry_handler.setLevel(logging.INFO)
            telemetry_formatter = logging.Formatter(
                '%(asctime)s - %(message)s'
            )
            telemetry_handler.setFormatter(telemetry_formatter)
            
            # 텔레메트리 전용 로거
            telemetry_logger = logging.getLogger("telemetry")
            telemetry_logger.addHandler(telemetry_handler)
            telemetry_logger.setLevel(logging.INFO)
            telemetry_logger.propagate = False
            
            self.logger.info("Enhanced logging system initialized")
            
        except Exception as e:
            print(f"Failed to setup loggers: {e}")
    
    def start(self):
        """향상된 로깅 시작"""
        try:
            # 텔레메트리 스레드 시작
            self._telemetry_running = True
            self._telemetry_thread = threading.Thread(target=self._telemetry_loop, daemon=True)
            self._telemetry_thread.start()
            
            self.logger.info("Enhanced logging started")
            
        except Exception as e:
            self.logger.error(f"Failed to start enhanced logging: {e}")
    
    def stop(self):
        """향상된 로깅 중지"""
        try:
            self._telemetry_running = False
            
            if self._telemetry_thread:
                self._telemetry_thread.join(timeout=5.0)
            
            self.logger.info("Enhanced logging stopped")
            
        except Exception as e:
            self.logger.error(f"Failed to stop enhanced logging: {e}")
    
    def _telemetry_loop(self):
        """텔레메트리 루프"""
        while self._telemetry_running:
            try:
                # 텔레메트리 이벤트 처리
                self._process_telemetry_events()
                
                # 주문 이벤트 처리
                self._process_order_events()
                
                # 통계 업데이트
                self._update_stats()
                
                # 5초마다 처리
                time.sleep(5.0)
                
            except Exception as e:
                self.logger.error(f"Telemetry loop error: {e}")
                time.sleep(5.0)
    
    def _process_telemetry_events(self):
        """텔레메트리 이벤트 처리"""
        try:
            with self._telemetry_lock:
                while self._telemetry_events:
                    event = self._telemetry_events.popleft()
                    self._log_telemetry_event(event)
                    
        except Exception as e:
            self.logger.error(f"Failed to process telemetry events: {e}")
    
    def _process_order_events(self):
        """주문 이벤트 처리"""
        try:
            with self._order_lock:
                while self._order_events:
                    event = self._order_events.popleft()
                    self._log_order_event(event)
                    
        except Exception as e:
            self.logger.error(f"Failed to process order events: {e}")
    
    def _log_telemetry_event(self, event: TelemetryEvent):
        """텔레메트리 이벤트 로깅"""
        try:
            # 텔레메트리 로거에 기록
            telemetry_logger = logging.getLogger("telemetry")
            
            # 이벤트 데이터를 JSON으로 직렬화
            event_data = {
                "timestamp": event.timestamp,
                "event_type": event.event_type.value,
                "level": event.level.value,
                "message": event.message,
                "service": event.service,
                "data": event.data
            }
            
            # 단일 라인으로 로깅
            telemetry_logger.info(json.dumps(event_data, ensure_ascii=False))
            
        except Exception as e:
            self.logger.error(f"Failed to log telemetry event: {e}")
    
    def _log_order_event(self, event: OrderLifecycleEvent):
        """주문 이벤트 로깅"""
        try:
            # 주문 로거에 기록
            order_logger = logging.getLogger("orders")
            
            # 주문 생명주기 로그 (단일 라인)
            log_message = (
                f"ORDER {event.status}: {event.client_order_id} "
                f"{event.symbol} {event.side} "
                f"{event.quantity}@{event.price} "
                f"filled:{event.filled_quantity}@{event.average_price}"
            )
            
            if event.error:
                log_message += f" error:{event.error}"
            
            order_logger.info(log_message)
            
        except Exception as e:
            self.logger.error(f"Failed to log order event: {e}")
    
    def _update_stats(self):
        """통계 업데이트"""
        try:
            # 통계는 별도 파일에 저장
            stats_file = self.log_dir / "logging_stats.json"
            
            stats_data = {
                "timestamp": time.time(),
                "stats": self._stats.copy(),
                "telemetry_queue_size": len(self._telemetry_events),
                "order_queue_size": len(self._order_events),
            }
            
            with open(stats_file, 'w', encoding='utf-8') as f:
                json.dump(stats_data, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            self.logger.error(f"Failed to update stats: {e}")
    
    def log_telemetry(self, event_type: EventType, level: LogLevel, message: str, 
                     service: str, data: Dict[str, Any] = None):
        """텔레메트리 이벤트 로깅"""
        try:
            event = TelemetryEvent(
                timestamp=time.time(),
                event_type=event_type,
                level=level,
                message=message,
                service=service,
                data=data or {}
            )
            
            with self._telemetry_lock:
                self._telemetry_events.append(event)
            
            # 통계 업데이트
            self._stats["total_events"] += 1
            self._stats["last_event_time"] = event.timestamp
            
            # 레벨별 통계
            level_key = level.value
            self._stats["events_by_level"][level_key] = self._stats["events_by_level"].get(level_key, 0) + 1
            
            # 타입별 통계
            type_key = event_type.value
            self._stats["events_by_type"][type_key] = self._stats["events_by_type"].get(type_key, 0) + 1
            
            # 서비스별 통계
            service_key = service
            self._stats["events_by_service"][service_key] = self._stats["events_by_service"].get(service_key, 0) + 1
            
        except Exception as e:
            self.logger.error(f"Failed to log telemetry: {e}")
    
    def log_order_lifecycle(self, client_order_id: str, symbol: str, side: str, 
                           status: str, price: float = 0.0, quantity: float = 0.0,
                           filled_quantity: float = 0.0, average_price: float = 0.0,
                           error: str = "", metadata: Dict[str, Any] = None):
        """주문 생명주기 로깅"""
        try:
            event = OrderLifecycleEvent(
                client_order_id=client_order_id,
                symbol=symbol,
                side=side,
                status=status,
                timestamp=time.time(),
                price=price,
                quantity=quantity,
                filled_quantity=filled_quantity,
                average_price=average_price,
                error=error,
                metadata=metadata or {}
            )
            
            with self._order_lock:
                self._order_events.append(event)
            
        except Exception as e:
            self.logger.error(f"Failed to log order lifecycle: {e}")
    
    def log_actionable_event(self, level: LogLevel, message: str, service: str, 
                           data: Dict[str, Any] = None):
        """실행 가능한 이벤트 로깅 (INFO/WARN 레벨)"""
        try:
            # 실행 가능한 이벤트만 INFO/WARN 레벨로 로깅
            if level in [LogLevel.INFO, LogLevel.WARNING, LogLevel.ERROR, LogLevel.CRITICAL]:
                self.log_telemetry(
                    event_type=EventType.SYSTEM_ERROR,
                    level=level,
                    message=message,
                    service=service,
                    data=data
                )
            
        except Exception as e:
            self.logger.error(f"Failed to log actionable event: {e}")
    
    def log_noisy_debug(self, message: str, service: str, data: Dict[str, Any] = None):
        """노이즈가 많은 디버그 로깅 (DEBUG 레벨)"""
        try:
            # 노이즈가 많은 로그는 DEBUG 레벨로만 로깅
            self.log_telemetry(
                event_type=EventType.PERFORMANCE,
                level=LogLevel.DEBUG,
                message=message,
                service=service,
                data=data
            )
            
        except Exception as e:
            self.logger.error(f"Failed to log noisy debug: {e}")
    
    def get_telemetry_footer_data(self) -> Dict[str, Any]:
        """텔레메트리 푸터 데이터 반환"""
        try:
            # 상태 버스에서 최신 데이터 가져오기
            state_data = self.state_bus.get_state()
            
            # 서비스 하트비트 확인
            service_heartbeats = state_data.get('service_heartbeats', {})
            
            # 회로 차단기 상태
            circuit_breaker = state_data.get('circuit_breaker', {})
            
            # E-STOP 상태
            estop = state_data.get('estop', {})
            
            # 최신 스냅샷 시간
            snapshot_time = state_data.get('last_snapshot_time', 0)
            snapshot_age = time.time() - snapshot_time if snapshot_time > 0 else 0
            
            # 피더 지연
            feeder_heartbeat = service_heartbeats.get('feeder', {})
            feeder_lag = time.time() - feeder_heartbeat.get('ts', 0) if feeder_heartbeat.get('ts') else 0
            
            # 활성 심볼 수
            symbols = state_data.get('symbols', {})
            active_symbols = len(symbols.get('active', []))
            expected_symbols = len(symbols.get('expected', []))
            
            return {
                "snapshot_time": time.strftime("%H:%M:%S", time.localtime(snapshot_time)) if snapshot_time > 0 else "N/A",
                "snapshot_age": f"{snapshot_age:.1f}s",
                "active_symbols": f"{active_symbols}/{expected_symbols}",
                "feeder_lag": f"{feeder_lag:.1f}s",
                "circuit_breaker": "ON" if circuit_breaker.get('active', False) else "OFF",
                "estop": "ON" if estop.get('active', False) else "OFF",
                "timestamp": time.time()
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get telemetry footer data: {e}")
            return {
                "snapshot_time": "N/A",
                "snapshot_age": "N/A",
                "active_symbols": "N/A",
                "feeder_lag": "N/A",
                "circuit_breaker": "UNKNOWN",
                "estop": "UNKNOWN",
                "timestamp": time.time()
            }
    
    def get_stats(self) -> Dict[str, Any]:
        """통계 반환"""
        return self._stats.copy()
    
    def get_recent_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        """최근 이벤트 반환"""
        try:
            events = []
            
            # 텔레메트리 이벤트
            with self._telemetry_lock:
                for event in list(self._telemetry_events)[-limit//2:]:
                    events.append({
                        "type": "telemetry",
                        "timestamp": event.timestamp,
                        "event_type": event.event_type.value,
                        "level": event.level.value,
                        "message": event.message,
                        "service": event.service,
                        "data": event.data
                    })
            
            # 주문 이벤트
            with self._order_lock:
                for event in list(self._order_events)[-limit//2:]:
                    events.append({
                        "type": "order",
                        "timestamp": event.timestamp,
                        "client_order_id": event.client_order_id,
                        "symbol": event.symbol,
                        "side": event.side,
                        "status": event.status,
                        "price": event.price,
                        "quantity": event.quantity,
                        "filled_quantity": event.filled_quantity,
                        "average_price": event.average_price,
                        "error": event.error
                    })
            
            # 타임스탬프로 정렬
            events.sort(key=lambda x: x['timestamp'], reverse=True)
            
            return events[:limit]
            
        except Exception as e:
            self.logger.error(f"Failed to get recent events: {e}")
            return []


# 전역 인스턴스
_global_enhanced_logger: Optional[EnhancedLogger] = None


def get_enhanced_logger() -> EnhancedLogger:
    """전역 향상된 로거 반환"""
    global _global_enhanced_logger
    if _global_enhanced_logger is None:
        _global_enhanced_logger = EnhancedLogger()
        _global_enhanced_logger.start()
    return _global_enhanced_logger


def log_telemetry(event_type: EventType, level: LogLevel, message: str, 
                 service: str, data: Dict[str, Any] = None):
    """텔레메트리 이벤트 로깅"""
    get_enhanced_logger().log_telemetry(event_type, level, message, service, data)


def log_order_lifecycle(client_order_id: str, symbol: str, side: str, 
                       status: str, price: float = 0.0, quantity: float = 0.0,
                       filled_quantity: float = 0.0, average_price: float = 0.0,
                       error: str = "", metadata: Dict[str, Any] = None):
    """주문 생명주기 로깅"""
    get_enhanced_logger().log_order_lifecycle(
        client_order_id, symbol, side, status, price, quantity,
        filled_quantity, average_price, error, metadata
    )


def log_actionable_event(level: LogLevel, message: str, service: str, 
                        data: Dict[str, Any] = None):
    """실행 가능한 이벤트 로깅"""
    get_enhanced_logger().log_actionable_event(level, message, service, data)


def log_noisy_debug(message: str, service: str, data: Dict[str, Any] = None):
    """노이즈가 많은 디버그 로깅"""
    get_enhanced_logger().log_noisy_debug(message, service, data)


def get_telemetry_footer_data() -> Dict[str, Any]:
    """텔레메트리 푸터 데이터 반환"""
    return get_enhanced_logger().get_telemetry_footer_data()


def get_logging_stats() -> Dict[str, Any]:
    """로깅 통계 반환"""
    return get_enhanced_logger().get_stats()


def get_recent_events(limit: int = 100) -> List[Dict[str, Any]]:
    """최근 이벤트 반환"""
    return get_enhanced_logger().get_recent_events(limit)
