#!/usr/bin/env python3
"""
Single Source of Truth (SSOT) & State Contracts
중앙화된 런타임 상태 관리 시스템
"""

import json
import logging
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import threading
from datetime import datetime

from .guardrails import get_guardrails


@dataclass
class ServiceHeartbeat:
    """서비스 하트비트"""
    ts: float  # 타임스탬프
    status: str  # healthy, warning, critical, down
    last_error: str = ""
    metrics: Dict[str, Any] = None


@dataclass
class ARESState:
    """ARES 상태"""
    regime: str = "unknown"  # bull, bear, sideways, unknown
    strategies_active: List[str] = None  # 활성 전략 목록
    min_confidence: float = 0.2
    last_signal_ts: float = 0.0
    signals_generated_today: int = 0
    errors_today: int = 0


@dataclass
class RiskState:
    """리스크 상태"""
    max_daily_loss_usd: float = 100.0
    realized_pnl_today: float = 0.0
    unrealized_pnl: float = 0.0
    est_margin_usage: float = 0.0
    daily_loss_pct: float = 0.0
    position_count: int = 0
    total_exposure_usd: float = 0.0


@dataclass
class OrderState:
    """주문 상태"""
    pending: List[Dict[str, Any]] = None  # 대기 중인 주문
    last_error: str = ""
    last_fill_ts: float = 0.0
    orders_today: int = 0
    fills_today: int = 0
    errors_today: int = 0
    total_volume_usd: float = 0.0


@dataclass
class CircuitBreakerState:
    """서킷 브레이커 상태"""
    active: bool = False
    reason: str = ""
    since_ts: float = 0.0
    auto_reset_ts: float = 0.0
    trigger_count: int = 0
    last_trigger_reason: str = ""


@dataclass
class SystemState:
    """시스템 전체 상태"""
    # 환경 정보
    env: Dict[str, Any] = None  # mode, use_testnet
    
    # 서비스 하트비트
    service_heartbeats: Dict[str, ServiceHeartbeat] = None
    
    # 심볼 정보
    symbols: Dict[str, Any] = None  # active list, universe_version
    
    # ARES 상태
    ares: ARESState = None
    
    # 리스크 상태
    risk: RiskState = None
    
    # 주문 상태
    orders: OrderState = None
    
    # 서킷 브레이커
    circuit_breaker: CircuitBreakerState = None
    
    # 긴급 정지
    estop: bool = False
    
    # 메타데이터
    version: str = "1.0.0"
    last_updated: float = 0.0
    schema_version: str = "1.0.0"


class StateBus:
    """상태 버스 - 중앙화된 상태 관리"""
    
    def __init__(self, state_file: str = "shared_data/state_bus.json"):
        self.state_file = Path(state_file)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        
        self.logger = logging.getLogger(__name__)
        self._lock = threading.RLock()
        self._state: Optional[SystemState] = None
        self._last_save_time = 0.0
        
        # 가드레일 설정
        self.guardrails = get_guardrails()
        
        # 초기 상태 로드
        self.load_state()
    
    def load_state(self) -> SystemState:
        """상태 로드"""
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 스키마 검증
                if not self._validate_schema(data):
                    self.logger.error("Invalid state schema, creating new state")
                    self._state = self._create_default_state()
                else:
                    self._state = self._deserialize_state(data)
            else:
                self._state = self._create_default_state()
            
            self.logger.info("State loaded successfully")
            return self._state
            
        except Exception as e:
            self.logger.error(f"Failed to load state: {e}")
            self._state = self._create_default_state()
            return self._state
    
    def _create_default_state(self) -> SystemState:
        """기본 상태 생성"""
        config = self.guardrails.get_config()
        
        return SystemState(
            env={
                'mode': 'SIMULATION' if config.SIMULATION_MODE else 'PRODUCTION',
                'use_testnet': config.BINANCE_USE_TESTNET,
                'trading_enabled': config.TRADING_ENABLED,
            },
            service_heartbeats={
                'feeder': ServiceHeartbeat(ts=0, status='down'),
                'ares': ServiceHeartbeat(ts=0, status='down'),
                'trader': ServiceHeartbeat(ts=0, status='down'),
            },
            symbols={
                'active': [],
                'universe_version': '1.0.0',
                'last_universe_update': 0.0,
            },
            ares=ARESState(),
            risk=RiskState(
                max_daily_loss_usd=config.MAX_DAILY_LOSS_USD,
            ),
            orders=OrderState(),
            circuit_breaker=CircuitBreakerState(),
            estop=config.E_STOP,
            last_updated=time.time(),
        )
    
    def _validate_schema(self, data: Dict[str, Any]) -> bool:
        """스키마 검증"""
        try:
            # 필수 키 확인
            required_keys = [
                'env', 'service_heartbeats', 'symbols', 'ares', 
                'risk', 'orders', 'circuit_breaker', 'version'
            ]
            
            for key in required_keys:
                if key not in data:
                    self.logger.error(f"Missing required key: {key}")
                    return False
            
            # 버전 호환성 확인
            if data.get('version') != '1.0.0':
                self.logger.warning(f"Schema version mismatch: {data.get('version')}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Schema validation error: {e}")
            return False
    
    def _deserialize_state(self, data: Dict[str, Any]) -> SystemState:
        """데이터에서 상태 객체 생성"""
        try:
            # 서비스 하트비트
            service_heartbeats = {}
            for service, heartbeat_data in data.get('service_heartbeats', {}).items():
                service_heartbeats[service] = ServiceHeartbeat(**heartbeat_data)
            
            # ARES 상태
            ares_data = data.get('ares', {})
            ares = ARESState(**ares_data)
            
            # 리스크 상태
            risk_data = data.get('risk', {})
            risk = RiskState(**risk_data)
            
            # 주문 상태
            orders_data = data.get('orders', {})
            orders = OrderState(**orders_data)
            
            # 서킷 브레이커
            cb_data = data.get('circuit_breaker', {})
            circuit_breaker = CircuitBreakerState(**cb_data)
            
            return SystemState(
                env=data.get('env', {}),
                service_heartbeats=service_heartbeats,
                symbols=data.get('symbols', {}),
                ares=ares,
                risk=risk,
                orders=orders,
                circuit_breaker=circuit_breaker,
                estop=data.get('estop', False),
                version=data.get('version', '1.0.0'),
                last_updated=data.get('last_updated', time.time()),
                schema_version=data.get('schema_version', '1.0.0'),
            )
            
        except Exception as e:
            self.logger.error(f"State deserialization error: {e}")
            raise
    
    def save_state(self) -> bool:
        """상태 저장 (Atomic write with schema validation)"""
        try:
            with self._lock:
                if self._state is None:
                    self.logger.error("No state to save")
                    return False

                # 메타데이터 업데이트
                self._state.last_updated = time.time()

                # 직렬화
                state_dict = self._serialize_state()

                # Schema validation before write
                if not self._validate_schema(state_dict):
                    self.logger.error("State schema validation failed - rejecting write")
                    # Alert on invalid write attempt
                    try:
                        alert_file = Path("shared_data/alerts/state_bus_invalid.json")
                        alert_file.parent.mkdir(parents=True, exist_ok=True)
                        alert_file.write_text(json.dumps({
                            "timestamp": time.time(),
                            "error": "Invalid state schema",
                            "state_keys": list(state_dict.keys())
                        }, indent=2))
                    except:
                        pass
                    return False

                # 원자적 저장 (temp file + atomic replace, UTF-8 no BOM)
                temp_file = self.state_file.with_suffix('.tmp')
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(state_dict, f, indent=2, ensure_ascii=False)

                # Atomic move (prevents partial writes)
                temp_file.replace(self.state_file)

                self._last_save_time = time.time()
                return True

        except Exception as e:
            self.logger.error(f"Failed to save state: {e}")
            return False
    
    def _serialize_state(self) -> Dict[str, Any]:
        """상태 객체를 딕셔너리로 변환"""
        try:
            state_dict = asdict(self._state)
            
            # 서비스 하트비트 직렬화
            if self._state.service_heartbeats:
                state_dict['service_heartbeats'] = {
                    service: asdict(heartbeat) 
                    for service, heartbeat in self._state.service_heartbeats.items()
                }
            
            return state_dict
            
        except Exception as e:
            self.logger.error(f"State serialization error: {e}")
            raise
    
    def get_state(self) -> SystemState:
        """현재 상태 반환"""
        with self._lock:
            if self._state is None:
                self.load_state()
            return self._state
    
    def update_service_heartbeat(self, service: str, status: str, 
                                last_error: str = "", metrics: Dict[str, Any] = None) -> bool:
        """서비스 하트비트 업데이트"""
        try:
            with self._lock:
                if self._state is None:
                    self.load_state()
                
                if self._state.service_heartbeats is None:
                    self._state.service_heartbeats = {}
                
                self._state.service_heartbeats[service] = ServiceHeartbeat(
                    ts=time.time(),
                    status=status,
                    last_error=last_error,
                    metrics=metrics or {}
                )
                
                return self.save_state()
                
        except Exception as e:
            self.logger.error(f"Failed to update service heartbeat: {e}")
            return False
    
    def update_symbols(self, active_symbols: List[str], universe_version: str = None) -> bool:
        """심볼 정보 업데이트"""
        try:
            with self._lock:
                if self._state is None:
                    self.load_state()
                
                if self._state.symbols is None:
                    self._state.symbols = {}
                
                self._state.symbols['active'] = active_symbols
                if universe_version:
                    self._state.symbols['universe_version'] = universe_version
                self._state.symbols['last_universe_update'] = time.time()
                
                return self.save_state()
                
        except Exception as e:
            self.logger.error(f"Failed to update symbols: {e}")
            return False
    
    def update_ares_state(self, **kwargs) -> bool:
        """ARES 상태 업데이트"""
        try:
            with self._lock:
                if self._state is None:
                    self.load_state()
                
                if self._state.ares is None:
                    self._state.ares = ARESState()
                
                # 업데이트할 필드만 변경
                for key, value in kwargs.items():
                    if hasattr(self._state.ares, key):
                        setattr(self._state.ares, key, value)
                
                return self.save_state()
                
        except Exception as e:
            self.logger.error(f"Failed to update ARES state: {e}")
            return False
    
    def update_risk_state(self, **kwargs) -> bool:
        """리스크 상태 업데이트"""
        try:
            with self._lock:
                if self._state is None:
                    self.load_state()
                
                if self._state.risk is None:
                    self._state.risk = RiskState()
                
                # 업데이트할 필드만 변경
                for key, value in kwargs.items():
                    if hasattr(self._state.risk, key):
                        setattr(self._state.risk, key, value)
                
                return self.save_state()
                
        except Exception as e:
            self.logger.error(f"Failed to update risk state: {e}")
            return False
    
    def update_orders_state(self, **kwargs) -> bool:
        """주문 상태 업데이트"""
        try:
            with self._lock:
                if self._state is None:
                    self.load_state()
                
                if self._state.orders is None:
                    self._state.orders = OrderState()
                
                # 업데이트할 필드만 변경
                for key, value in kwargs.items():
                    if hasattr(self._state.orders, key):
                        setattr(self._state.orders, key, value)
                
                return self.save_state()
                
        except Exception as e:
            self.logger.error(f"Failed to update orders state: {e}")
            return False
    
    def set_circuit_breaker(self, active: bool, reason: str = "") -> bool:
        """서킷 브레이커 설정"""
        try:
            with self._lock:
                if self._state is None:
                    self.load_state()
                
                if self._state.circuit_breaker is None:
                    self._state.circuit_breaker = CircuitBreakerState()
                
                self._state.circuit_breaker.active = active
                self._state.circuit_breaker.reason = reason
                self._state.circuit_breaker.since_ts = time.time()
                
                if active:
                    self._state.circuit_breaker.trigger_count += 1
                    self._state.circuit_breaker.last_trigger_reason = reason
                    # 자동 리셋 시간 설정 (5분 후)
                    self._state.circuit_breaker.auto_reset_ts = time.time() + 300
                else:
                    self._state.circuit_breaker.auto_reset_ts = 0.0
                
                return self.save_state()
                
        except Exception as e:
            self.logger.error(f"Failed to set circuit breaker: {e}")
            return False
    
    def set_estop(self, active: bool) -> bool:
        """긴급 정지 설정"""
        try:
            with self._lock:
                if self._state is None:
                    self.load_state()
                
                self._state.estop = active
                
                # 가드레일 설정도 업데이트
                self.guardrails.update_config({'E_STOP': active})
                
                return self.save_state()
                
        except Exception as e:
            self.logger.error(f"Failed to set E-STOP: {e}")
            return False
    
    def is_trading_allowed(self) -> bool:
        """거래 허용 여부 확인"""
        try:
            state = self.get_state()
            
            # E-STOP 확인
            if state.estop:
                self.logger.warning("E-STOP is active - trading blocked")
                return False
            
            # 서킷 브레이커 확인
            if state.circuit_breaker and state.circuit_breaker.active:
                self.logger.warning(f"Circuit breaker is active - trading blocked: {state.circuit_breaker.reason}")
                return False
            
            # 가드레일 확인
            if not self.guardrails.is_safe_to_trade():
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to check trading allowed: {e}")
            return False
    
    def get_service_status(self, service: str) -> Optional[ServiceHeartbeat]:
        """서비스 상태 반환"""
        try:
            state = self.get_state()
            return state.service_heartbeats.get(service) if state.service_heartbeats else None
        except Exception as e:
            self.logger.error(f"Failed to get service status: {e}")
            return None
    
    def get_health_summary(self) -> Dict[str, Any]:
        """헬스 요약 반환"""
        try:
            state = self.get_state()
            
            summary = {
                'overall_status': 'healthy',
                'services': {},
                'circuit_breaker': {
                    'active': state.circuit_breaker.active if state.circuit_breaker else False,
                    'reason': state.circuit_breaker.reason if state.circuit_breaker else '',
                },
                'estop': state.estop,
                'trading_allowed': self.is_trading_allowed(),
                'last_updated': state.last_updated,
            }
            
            # 서비스 상태 요약
            if state.service_heartbeats:
                for service, heartbeat in state.service_heartbeats.items():
                    summary['services'][service] = {
                        'status': heartbeat.status,
                        'last_seen': heartbeat.ts,
                        'age_sec': time.time() - heartbeat.ts,
                        'last_error': heartbeat.last_error,
                    }
            
            # 전체 상태 결정
            if state.estop:
                summary['overall_status'] = 'estop'
            elif state.circuit_breaker and state.circuit_breaker.active:
                summary['overall_status'] = 'circuit_breaker'
            elif any(s['status'] in ['critical', 'down'] for s in summary['services'].values()):
                summary['overall_status'] = 'critical'
            elif any(s['status'] == 'warning' for s in summary['services'].values()):
                summary['overall_status'] = 'warning'
            
            return summary
            
        except Exception as e:
            self.logger.error(f"Failed to get health summary: {e}")
            return {'overall_status': 'error', 'error': str(e)}


# 전역 인스턴스
_global_state_bus: Optional[StateBus] = None


def get_state_bus() -> StateBus:
    """전역 상태 버스 반환"""
    global _global_state_bus
    if _global_state_bus is None:
        _global_state_bus = StateBus()
    return _global_state_bus


def get_system_state() -> SystemState:
    """시스템 상태 반환"""
    return get_state_bus().get_state()


def is_trading_allowed() -> bool:
    """거래 허용 여부 확인"""
    return get_state_bus().is_trading_allowed()


def update_service_heartbeat(service: str, status: str, 
                           last_error: str = "", metrics: Dict[str, Any] = None) -> bool:
    """서비스 하트비트 업데이트"""
    return get_state_bus().update_service_heartbeat(service, status, last_error, metrics)


def set_circuit_breaker(active: bool, reason: str = "") -> bool:
    """서킷 브레이커 설정"""
    return get_state_bus().set_circuit_breaker(active, reason)


def set_estop(active: bool) -> bool:
    """긴급 정지 설정"""
    return get_state_bus().set_estop(active)


def get_health_summary() -> Dict[str, Any]:
    """헬스 요약 반환"""
    return get_state_bus().get_health_summary()
