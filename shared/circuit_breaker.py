#!/usr/bin/env python3
"""
Circuit Breaker & E-STOP - 글로벌 제어 평면
"""

import json
import logging
import time
import threading
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
from enum import Enum
from collections import deque

from shared.guardrails import get_guardrails
from shared.state_bus import get_state_bus, update_service_heartbeat


class CircuitBreakerState(Enum):
    """회로 차단기 상태"""
    CLOSED = "CLOSED"  # 정상 동작
    OPEN = "OPEN"  # 차단됨
    HALF_OPEN = "HALF_OPEN"  # 부분 복구 시도


class CircuitBreakerReason(Enum):
    """회로 차단기 트리거 이유"""
    FEEDER_LAG = "FEEDER_LAG"  # 피더 지연
    EXCHANGE_ERROR = "EXCHANGE_ERROR"  # 거래소 오류
    SCHEMA_VIOLATION = "SCHEMA_VIOLATION"  # 스키마 위반
    BALANCE_ANOMALY = "BALANCE_ANOMALY"  # 잔고 이상
    ORDER_FAILURE = "ORDER_FAILURE"  # 주문 실패
    DAILY_LOSS_LIMIT = "DAILY_LOSS_LIMIT"  # 일일 손실 한도
    MANUAL_TRIGGER = "MANUAL_TRIGGER"  # 수동 트리거
    SYSTEM_ERROR = "SYSTEM_ERROR"  # 시스템 오류


@dataclass
class CircuitBreakerConfig:
    """회로 차단기 설정"""
    # 피더 지연 임계값
    feeder_lag_threshold: float = 20.0  # 초
    
    # 주문 실패 임계값
    order_failure_threshold: int = 5  # 연속 실패 횟수
    order_failure_window: float = 300.0  # 5분 윈도우
    
    # 일일 손실 한도
    daily_loss_threshold: float = 1000.0  # USD
    
    # 복구 설정
    recovery_timeout: float = 60.0  # 복구 시도 시간 (초)
    max_recovery_attempts: int = 3  # 최대 복구 시도 횟수
    
    # 자동 리셋 설정
    auto_reset_enabled: bool = True
    auto_reset_interval: float = 3600.0  # 1시간


@dataclass
class CircuitBreakerStatus:
    """회로 차단기 상태"""
    state: CircuitBreakerState = CircuitBreakerState.CLOSED
    reason: Optional[CircuitBreakerReason] = None
    triggered_at: float = 0.0
    last_trigger_reason: str = ""
    
    # 통계
    trigger_count: int = 0
    recovery_attempts: int = 0
    last_recovery_attempt: float = 0.0
    
    # 활성 조건
    active_conditions: List[str] = None
    
    def __post_init__(self):
        if self.active_conditions is None:
            self.active_conditions = []


@dataclass
class EStopStatus:
    """E-STOP 상태"""
    active: bool = False
    triggered_at: float = 0.0
    triggered_by: str = ""
    reason: str = ""
    last_check: float = 0.0


class CircuitBreaker:
    """회로 차단기"""
    
    def __init__(self, config_path: str = "config/policy.yaml"):
        self.config_path = config_path
        self.logger = logging.getLogger(__name__)
        
        # 가드레일 및 상태 버스
        self.guardrails = get_guardrails()
        self.state_bus = get_state_bus()
        self.config = self.guardrails.get_config()
        
        # 회로 차단기 설정
        self.cb_config = CircuitBreakerConfig()
        
        # 상태
        self.cb_status = CircuitBreakerStatus()
        self.estop_status = EStopStatus()
        
        # 모니터링 데이터
        self._feeder_heartbeats: deque = deque(maxlen=100)
        self._order_failures: deque = deque(maxlen=100)
        self._exchange_errors: deque = deque(maxlen=100)
        
        # 락
        self._lock = threading.RLock()
        
        # 통계
        self._stats = {
            "circuit_breaker_trips": 0,
            "estop_activations": 0,
            "recovery_attempts": 0,
            "recovery_successes": 0,
            "last_trip_time": 0.0,
            "last_recovery_time": 0.0,
        }
        
        # 모니터링 스레드
        self._monitor_thread: Optional[threading.Thread] = None
        self._monitor_running = False
        
        # 복구 스레드
        self._recovery_thread: Optional[threading.Thread] = None
        self._recovery_running = False
    
    def start(self):
        """회로 차단기 시작"""
        try:
            # 모니터링 스레드 시작
            self._monitor_running = True
            self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self._monitor_thread.start()
            
            # 복구 스레드 시작
            self._recovery_running = True
            self._recovery_thread = threading.Thread(target=self._recovery_loop, daemon=True)
            self._recovery_thread.start()
            
            self.logger.info("Circuit Breaker started")
            
        except Exception as e:
            self.logger.error(f"Failed to start Circuit Breaker: {e}")
    
    def stop(self):
        """회로 차단기 중지"""
        try:
            self._monitor_running = False
            self._recovery_running = False
            
            if self._monitor_thread:
                self._monitor_thread.join(timeout=5.0)
            
            if self._recovery_thread:
                self._recovery_thread.join(timeout=5.0)
            
            self.logger.info("Circuit Breaker stopped")
            
        except Exception as e:
            self.logger.error(f"Failed to stop Circuit Breaker: {e}")
    
    def _monitor_loop(self):
        """모니터링 루프"""
        while self._monitor_running:
            try:
                current_time = time.time()
                
                # E-STOP 상태 확인
                self._check_estop_status()
                
                # 회로 차단기 상태 확인
                if self.cb_status.state == CircuitBreakerState.CLOSED:
                    self._check_circuit_breaker_conditions()
                
                # 상태 버스에 업데이트
                self._update_state_bus()
                
                # 5초마다 모니터링
                time.sleep(5.0)
                
            except Exception as e:
                self.logger.error(f"Circuit breaker monitor error: {e}")
                time.sleep(5.0)
    
    def _recovery_loop(self):
        """복구 루프"""
        while self._recovery_running:
            try:
                current_time = time.time()
                
                # 회로 차단기가 열려있고 복구 시도가 필요한 경우
                if (self.cb_status.state == CircuitBreakerState.OPEN and 
                    current_time - self.cb_status.triggered_at > self.cb_config.recovery_timeout):
                    
                    self._attempt_recovery()
                
                # 자동 리셋 확인
                if (self.cb_config.auto_reset_enabled and 
                    self.cb_status.state == CircuitBreakerState.OPEN and
                    current_time - self.cb_status.triggered_at > self.cb_config.auto_reset_interval):
                    
                    self._auto_reset()
                
                # 30초마다 복구 시도
                time.sleep(30.0)
                
            except Exception as e:
                self.logger.error(f"Circuit breaker recovery error: {e}")
                time.sleep(30.0)
    
    def _check_estop_status(self):
        """E-STOP 상태 확인"""
        try:
            # 가드레일에서 E-STOP 상태 확인
            estop_active = self.config.E_STOP
            
            if estop_active != self.estop_status.active:
                if estop_active:
                    # E-STOP 활성화
                    self.estop_status.active = True
                    self.estop_status.triggered_at = time.time()
                    self.estop_status.triggered_by = "system"
                    self.estop_status.reason = "E-STOP flag enabled"
                    
                    self._stats["estop_activations"] += 1
                    self.logger.warning("E-STOP ACTIVATED - All trading halted")
                else:
                    # E-STOP 비활성화
                    self.estop_status.active = False
                    self.logger.info("E-STOP DEACTIVATED - Trading resumed")
            
            self.estop_status.last_check = time.time()
            
        except Exception as e:
            self.logger.error(f"Failed to check E-STOP status: {e}")
    
    def _check_circuit_breaker_conditions(self):
        """회로 차단기 조건 확인"""
        try:
            current_time = time.time()
            active_conditions = []
            
            # 1. 피더 지연 확인
            if self._check_feeder_lag():
                active_conditions.append("feeder_lag")
            
            # 2. 주문 실패 확인
            if self._check_order_failures():
                active_conditions.append("order_failures")
            
            # 3. 거래소 오류 확인
            if self._check_exchange_errors():
                active_conditions.append("exchange_errors")
            
            # 4. 일일 손실 한도 확인
            if self._check_daily_loss_limit():
                active_conditions.append("daily_loss_limit")
            
            # 5. 스키마 위반 확인
            if self._check_schema_violations():
                active_conditions.append("schema_violations")
            
            # 조건이 활성화된 경우 회로 차단기 트리거
            if active_conditions:
                self._trigger_circuit_breaker(
                    reason=CircuitBreakerReason.SYSTEM_ERROR,
                    details=f"Active conditions: {', '.join(active_conditions)}"
                )
            
            # 활성 조건 업데이트
            self.cb_status.active_conditions = active_conditions
            
        except Exception as e:
            self.logger.error(f"Failed to check circuit breaker conditions: {e}")
    
    def _check_feeder_lag(self) -> bool:
        """피더 지연 확인"""
        try:
            # 상태 버스에서 피더 하트비트 확인
            feeder_heartbeat = self.state_bus.get_service_heartbeat("feeder")
            if not feeder_heartbeat:
                return True  # 피더 하트비트가 없으면 지연으로 간주
            
            current_time = time.time()
            last_heartbeat = feeder_heartbeat.get('ts', 0)
            lag = current_time - last_heartbeat
            
            if lag > self.cb_config.feeder_lag_threshold:
                self.logger.warning(f"Feeder lag detected: {lag:.1f}s > {self.cb_config.feeder_lag_threshold}s")
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Failed to check feeder lag: {e}")
            return True  # 오류 시 안전하게 차단
    
    def _check_order_failures(self) -> bool:
        """주문 실패 확인"""
        try:
            current_time = time.time()
            
            # 최근 주문 실패 확인
            recent_failures = [
                failure for failure in self._order_failures
                if current_time - failure['timestamp'] < self.cb_config.order_failure_window
            ]
            
            if len(recent_failures) >= self.cb_config.order_failure_threshold:
                self.logger.warning(f"Order failure threshold exceeded: {len(recent_failures)} failures in {self.cb_config.order_failure_window}s")
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Failed to check order failures: {e}")
            return False
    
    def _check_exchange_errors(self) -> bool:
        """거래소 오류 확인"""
        try:
            current_time = time.time()
            
            # 최근 거래소 오류 확인
            recent_errors = [
                error for error in self._exchange_errors
                if current_time - error['timestamp'] < 300.0  # 5분 윈도우
            ]
            
            if len(recent_errors) >= 3:  # 5분 내 3회 이상 오류
                self.logger.warning(f"Exchange error threshold exceeded: {len(recent_errors)} errors in 5 minutes")
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Failed to check exchange errors: {e}")
            return False
    
    def _check_daily_loss_limit(self) -> bool:
        """일일 손실 한도 확인"""
        try:
            # 상태 버스에서 리스크 데이터 확인
            risk_data = self.state_bus.get_risk_data()
            realized_pnl = risk_data.get('realized_pnl_today', 0.0)
            
            if realized_pnl < -self.cb_config.daily_loss_threshold:
                self.logger.warning(f"Daily loss limit exceeded: {realized_pnl} < -{self.cb_config.daily_loss_threshold}")
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Failed to check daily loss limit: {e}")
            return False
    
    def _check_schema_violations(self) -> bool:
        """스키마 위반 확인"""
        try:
            # 상태 버스에서 스키마 위반 확인
            state_data = self.state_bus.get_state()
            if state_data.get('schema_violations', 0) > 0:
                self.logger.warning("Schema violations detected")
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Failed to check schema violations: {e}")
            return False
    
    def _trigger_circuit_breaker(self, reason: CircuitBreakerReason, details: str = ""):
        """회로 차단기 트리거"""
        try:
            with self._lock:
                if self.cb_status.state == CircuitBreakerState.CLOSED:
                    self.cb_status.state = CircuitBreakerState.OPEN
                    self.cb_status.reason = reason
                    self.cb_status.triggered_at = time.time()
                    self.cb_status.last_trigger_reason = details
                    self.cb_status.trigger_count += 1
                    
                    self._stats["circuit_breaker_trips"] += 1
                    self._stats["last_trip_time"] = time.time()
                    
                    self.logger.error(f"CIRCUIT BREAKER TRIGGERED: {reason.value} - {details}")
                    
                    # 상태 버스에 업데이트
                    self.state_bus.update_circuit_breaker(
                        active=True,
                        reason=reason.value,
                        since_ts=self.cb_status.triggered_at,
                        details=details
                    )
            
        except Exception as e:
            self.logger.error(f"Failed to trigger circuit breaker: {e}")
    
    def _attempt_recovery(self):
        """복구 시도"""
        try:
            with self._lock:
                if self.cb_status.state == CircuitBreakerState.OPEN:
                    self.cb_status.state = CircuitBreakerState.HALF_OPEN
                    self.cb_status.recovery_attempts += 1
                    self.cb_status.last_recovery_attempt = time.time()
                    
                    self._stats["recovery_attempts"] += 1
                    self.logger.info(f"Circuit breaker recovery attempt {self.cb_status.recovery_attempts}")
                    
                    # 복구 조건 확인
                    if self._check_recovery_conditions():
                        self._reset_circuit_breaker()
                    else:
                        # 복구 실패, 다시 열림
                        self.cb_status.state = CircuitBreakerState.OPEN
                        self.cb_status.triggered_at = time.time()
                        self.logger.warning("Circuit breaker recovery failed, remaining open")
            
        except Exception as e:
            self.logger.error(f"Failed to attempt recovery: {e}")
    
    def _check_recovery_conditions(self) -> bool:
        """복구 조건 확인"""
        try:
            # 모든 조건이 정상인지 확인
            conditions_ok = True
            
            # 피더 지연 확인
            if self._check_feeder_lag():
                conditions_ok = False
            
            # 주문 실패 확인
            if self._check_order_failures():
                conditions_ok = False
            
            # 거래소 오류 확인
            if self._check_exchange_errors():
                conditions_ok = False
            
            # 일일 손실 한도 확인
            if self._check_daily_loss_limit():
                conditions_ok = False
            
            return conditions_ok
            
        except Exception as e:
            self.logger.error(f"Failed to check recovery conditions: {e}")
            return False
    
    def _reset_circuit_breaker(self):
        """회로 차단기 리셋"""
        try:
            with self._lock:
                self.cb_status.state = CircuitBreakerState.CLOSED
                self.cb_status.reason = None
                self.cb_status.last_trigger_reason = ""
                self.cb_status.active_conditions = []
                
                self._stats["recovery_successes"] += 1
                self._stats["last_recovery_time"] = time.time()
                
                self.logger.info("Circuit breaker reset - Trading resumed")
                
                # 상태 버스에 업데이트
                self.state_bus.update_circuit_breaker(
                    active=False,
                    reason="",
                    since_ts=0.0,
                    details=""
                )
            
        except Exception as e:
            self.logger.error(f"Failed to reset circuit breaker: {e}")
    
    def _auto_reset(self):
        """자동 리셋"""
        try:
            with self._lock:
                if self.cb_status.state == CircuitBreakerState.OPEN:
                    self.logger.info("Auto-resetting circuit breaker after timeout")
                    self._reset_circuit_breaker()
            
        except Exception as e:
            self.logger.error(f"Failed to auto-reset circuit breaker: {e}")
    
    def _update_state_bus(self):
        """상태 버스 업데이트"""
        try:
            # 회로 차단기 상태 업데이트
            self.state_bus.update_circuit_breaker(
                active=self.cb_status.state == CircuitBreakerState.OPEN,
                reason=self.cb_status.reason.value if self.cb_status.reason else "",
                since_ts=self.cb_status.triggered_at,
                details=self.cb_status.last_trigger_reason
            )
            
            # E-STOP 상태 업데이트
            self.state_bus.update_estop(
                active=self.estop_status.active,
                triggered_at=self.estop_status.triggered_at,
                triggered_by=self.estop_status.triggered_by,
                reason=self.estop_status.reason
            )
            
        except Exception as e:
            self.logger.error(f"Failed to update state bus: {e}")
    
    def record_order_failure(self, order_id: str, error: str):
        """주문 실패 기록"""
        try:
            with self._lock:
                self._order_failures.append({
                    'order_id': order_id,
                    'error': error,
                    'timestamp': time.time()
                })
            
        except Exception as e:
            self.logger.error(f"Failed to record order failure: {e}")
    
    def record_exchange_error(self, error: str, details: str = ""):
        """거래소 오류 기록"""
        try:
            with self._lock:
                self._exchange_errors.append({
                    'error': error,
                    'details': details,
                    'timestamp': time.time()
                })
            
        except Exception as e:
            self.logger.error(f"Failed to record exchange error: {e}")
    
    def manual_trigger(self, reason: str, details: str = ""):
        """수동 트리거"""
        try:
            self._trigger_circuit_breaker(
                reason=CircuitBreakerReason.MANUAL_TRIGGER,
                details=f"Manual trigger: {reason} - {details}"
            )
            
        except Exception as e:
            self.logger.error(f"Failed to manual trigger circuit breaker: {e}")
    
    def manual_reset(self):
        """수동 리셋"""
        try:
            self._reset_circuit_breaker()
            
        except Exception as e:
            self.logger.error(f"Failed to manual reset circuit breaker: {e}")
    
    def is_trading_allowed(self) -> bool:
        """거래 허용 여부 확인"""
        try:
            # E-STOP 확인
            if self.estop_status.active:
                return False
            
            # 회로 차단기 확인
            if self.cb_status.state == CircuitBreakerState.OPEN:
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to check trading allowed: {e}")
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """상태 반환"""
        try:
            return {
                "circuit_breaker": {
                    "state": self.cb_status.state.value,
                    "reason": self.cb_status.reason.value if self.cb_status.reason else None,
                    "triggered_at": self.cb_status.triggered_at,
                    "trigger_count": self.cb_status.trigger_count,
                    "recovery_attempts": self.cb_status.recovery_attempts,
                    "active_conditions": self.cb_status.active_conditions,
                },
                "estop": {
                    "active": self.estop_status.active,
                    "triggered_at": self.estop_status.triggered_at,
                    "triggered_by": self.estop_status.triggered_by,
                    "reason": self.estop_status.reason,
                },
                "stats": self._stats.copy(),
                "trading_allowed": self.is_trading_allowed(),
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get status: {e}")
            return {}


# 전역 인스턴스
_global_circuit_breaker: Optional[CircuitBreaker] = None


def get_circuit_breaker() -> CircuitBreaker:
    """전역 회로 차단기 반환"""
    global _global_circuit_breaker
    if _global_circuit_breaker is None:
        _global_circuit_breaker = CircuitBreaker()
        _global_circuit_breaker.start()
    return _global_circuit_breaker


def is_trading_allowed() -> bool:
    """거래 허용 여부 확인"""
    return get_circuit_breaker().is_trading_allowed()


def record_order_failure(order_id: str, error: str):
    """주문 실패 기록"""
    get_circuit_breaker().record_order_failure(order_id, error)


def record_exchange_error(error: str, details: str = ""):
    """거래소 오류 기록"""
    get_circuit_breaker().record_exchange_error(error, details)


def manual_trigger_circuit_breaker(reason: str, details: str = ""):
    """수동 회로 차단기 트리거"""
    get_circuit_breaker().manual_trigger(reason, details)


def manual_reset_circuit_breaker():
    """수동 회로 차단기 리셋"""
    get_circuit_breaker().manual_reset()


def get_circuit_breaker_status() -> Dict[str, Any]:
    """회로 차단기 상태 반환"""
    return get_circuit_breaker().get_status()
