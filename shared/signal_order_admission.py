#!/usr/bin/env python3
"""
Signal→Order Admission, Dedupe, and Evidence
Production-grade signal processing with comprehensive drop tracking
"""

import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .centralized_path_registry import get_path_registry


class DropCode(Enum):
    """신호 드롭 코드"""
    # 기본 검증 실패
    INVALID_SYMBOL = "invalid_symbol"
    INVALID_SIDE = "invalid_side"
    INVALID_SIZE = "invalid_size"
    INVALID_PRICE = "invalid_price"
    
    # 리스크 관리
    INSUFFICIENT_BALANCE = "insufficient_balance"
    MIN_NOTIONAL = "min_notional"
    MAX_POSITION_SIZE = "max_position_size"
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    CIRCUIT_BREAKER = "circuit_breaker"
    
    # 신호 품질
    STALE_SIGNAL = "stale_signal"
    LOW_CONFIDENCE = "low_confidence"
    DUPLICATE_SIGNAL = "duplicate_signal"
    
    # 시스템 상태
    EXCHANGE_DOWN = "exchange_down"
    NETWORK_ERROR = "network_error"
    RATE_LIMIT = "rate_limit"
    MAINTENANCE = "maintenance"
    
    # 테스트/시뮬레이션
    SIMULATION_BLOCK = "simulation_block"
    TEST_FILTER_VIOLATION = "test_filter_violation"
    
    # 기타
    UNKNOWN_ERROR = "unknown_error"


@dataclass
class AdmissionResult:
    """신호 승인 결과"""
    accepted: bool
    trace_id: str
    drop_code: Optional[DropCode] = None
    drop_details: Optional[str] = None
    client_order_id: Optional[str] = None
    computed_qty: Optional[float] = None
    computed_price: Optional[float] = None
    timestamp: float = 0.0
    processing_time_ms: float = 0.0


@dataclass
class OrderEvidence:
    """주문 증거"""
    trace_id: str
    client_order_id: str
    symbol: str
    side: str
    qty: float
    price: float
    timestamp: float
    
    # 입력 신호
    input_signal: Dict[str, Any]
    
    # 처리 과정
    admission_result: Dict[str, Any]
    exchange_filters: Dict[str, Any]
    risk_checks: Dict[str, Any]
    
    # 주문 요청/응답
    order_request: Dict[str, Any]
    order_response: Optional[Dict[str, Any]] = None
    
    # 최종 상태
    final_status: str = "pending"
    error_message: Optional[str] = None


class SignalOrderAdmission:
    """신호→주문 승인 시스템"""
    
    def __init__(self, repo_root: Path):
        self.logger = logging.getLogger(__name__)
        self.repo_root = repo_root
        self.path_registry = get_path_registry(repo_root)
        
        # 증거 수집 디렉토리
        self.evidence_dir = self.repo_root / "logs" / "orders"
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        
        # 중복 방지 저장소 (최근 1000개 주문)
        self.recent_orders: Dict[str, float] = {}  # client_order_id -> timestamp
        self.max_recent_orders = 1000
        
        # 통계
        self.stats = {
            "signals_in": 0,
            "orders_sent": 0,
            "orders_filled": 0,
            "drops": 0,
            "retryable_errors": 0,
            "drop_codes": {}
        }
        
        # 시작 시간
        self.start_time = time.time()
        
        self.logger.info("SignalOrderAdmission initialized")
    
    def process_signal(self, signal: Any, risk_checks: Dict[str, Any], 
                      exchange_filters: Dict[str, Any]) -> AdmissionResult:
        """신호 처리 및 승인 결정"""
        start_time = time.time()
        
        # 통계 업데이트
        self.stats["signals_in"] += 1
        
        try:
            # 1. 신호 파라미터 추출
            signal_params = self._extract_signal_params(signal)
            if not signal_params:
                return self._create_drop_result(
                    DropCode.INVALID_SYMBOL, "Failed to extract signal parameters",
                    start_time
                )
            
            # 2. Trace ID 생성
            trace_id = self._generate_trace_id(signal_params)
            
            # 3. 기본 검증
            validation_result = self._validate_signal(signal_params)
            if not validation_result["valid"]:
                return self._create_drop_result(
                    validation_result["drop_code"], validation_result["reason"],
                    start_time, trace_id
                )
            
            # 4. 중복 검사
            client_order_id = self._generate_client_order_id(trace_id, signal_params)
            if self._is_duplicate_order(client_order_id):
                return self._create_drop_result(
                    DropCode.DUPLICATE_SIGNAL, f"Duplicate order: {client_order_id}",
                    start_time, trace_id
                )
            
            # 5. 리스크 체크 결과 검증
            if not risk_checks.get("can_trade", False):
                drop_code = self._map_risk_reason_to_drop_code(risk_checks.get("reason", "unknown"))
                return self._create_drop_result(
                    drop_code, risk_checks.get("reason", "Risk check failed"),
                    start_time, trace_id
                )
            
            # 6. 거래소 필터 검증
            if not exchange_filters.get("valid", False):
                drop_code = self._map_exchange_filter_to_drop_code(exchange_filters.get("reason", "unknown"))
                return self._create_drop_result(
                    drop_code, exchange_filters.get("reason", "Exchange filter failed"),
                    start_time, trace_id
                )
            
            # 7. 승인 성공
            processing_time = (time.time() - start_time) * 1000
            
            # 최근 주문에 추가
            self._add_recent_order(client_order_id)
            
            # 통계 업데이트
            self.stats["orders_sent"] += 1
            
            return AdmissionResult(
                accepted=True,
                trace_id=trace_id,
                client_order_id=client_order_id,
                computed_qty=signal_params["qty"],
                computed_price=signal_params["price"],
                timestamp=time.time(),
                processing_time_ms=processing_time
            )
            
        except Exception as e:
            self.logger.error(f"Signal processing error: {e}")
            return self._create_drop_result(
                DropCode.UNKNOWN_ERROR, f"Processing error: {str(e)}",
                start_time
            )
    
    def record_order_evidence(self, evidence: OrderEvidence) -> bool:
        """주문 증거 기록"""
        try:
            evidence_file = self.evidence_dir / "order_evidence.jsonl"
            
            # JSONL 형식으로 추가
            with open(evidence_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(asdict(evidence), ensure_ascii=False) + '\n')
            
            self.logger.debug(f"Order evidence recorded: {evidence.trace_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to record order evidence: {e}")
            return False
    
    def get_drop_code_histogram(self) -> Dict[str, int]:
        """드롭 코드 히스토그램 조회"""
        return self.stats["drop_codes"].copy()
    
    def get_live_counters(self) -> Dict[str, int]:
        """실시간 카운터 조회"""
        return {
            "signals_in": self.stats["signals_in"],
            "orders_sent": self.stats["orders_sent"],
            "orders_filled": self.stats["orders_filled"],
            "drops": self.stats["drops"],
            "retryable_errors": self.stats["retryable_errors"],
            "uptime_seconds": int(time.time() - self.start_time)
        }
    
    def _extract_signal_params(self, signal: Any) -> Optional[Dict[str, Any]]:
        """신호 파라미터 추출"""
        try:
            if hasattr(signal, "action"):  # ARESSignal
                return {
                    "symbol": getattr(signal, "sub", "").upper(),
                    "side": getattr(signal, "action", "").upper(),
                    "qty": getattr(signal, "size_quote", 0.0),
                    "price": getattr(signal, "px", 0.0),
                    "size_type": "usdt"
                }
            else:  # TradingSignal
                symbol = getattr(signal, "symbol", "").upper()
                side = getattr(signal, "side", "").upper()
                size = getattr(signal, "size", 0.0)
                size_type = getattr(signal, "size_type", "usdt").lower()
                price = (
                    getattr(signal, "price_hint", 0.0) or
                    getattr(signal, "target_price", 0.0) or
                    0.0
                )
                
                # size_type에 따른 수량 계산
                if size_type == "usdt" and price > 0:
                    qty = size / price
                else:
                    qty = size
                
                return {
                    "symbol": symbol,
                    "side": side,
                    "qty": qty,
                    "price": price,
                    "size_type": size_type
                }
                
        except Exception as e:
            self.logger.error(f"Failed to extract signal parameters: {e}")
            return None
    
    def _validate_signal(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """신호 기본 검증"""
        symbol = params.get("symbol", "")
        side = params.get("side", "")
        qty = params.get("qty", 0.0)
        price = params.get("price", 0.0)
        
        if not symbol or len(symbol) < 3:
            return {"valid": False, "drop_code": DropCode.INVALID_SYMBOL, "reason": f"Invalid symbol: {symbol}"}
        
        if side not in ["BUY", "SELL"]:
            return {"valid": False, "drop_code": DropCode.INVALID_SIDE, "reason": f"Invalid side: {side}"}
        
        if qty <= 0:
            return {"valid": False, "drop_code": DropCode.INVALID_SIZE, "reason": f"Invalid quantity: {qty}"}
        
        if price <= 0:
            return {"valid": False, "drop_code": DropCode.INVALID_PRICE, "reason": f"Invalid price: {price}"}
        
        return {"valid": True}
    
    def _generate_trace_id(self, params: Dict[str, Any]) -> str:
        """Trace ID 생성"""
        # 안정적인 trace_id 생성 (symbol + side + timestamp + engine)
        timestamp = int(time.time())
        engine = "ares"  # 기본값
        
        trace_string = f"{params['symbol']}|{params['side']}|{timestamp}|{engine}"
        return hashlib.md5(trace_string.encode()).hexdigest()[:16]
    
    def _generate_client_order_id(self, trace_id: str, params: Dict[str, Any]) -> str:
        """Client Order ID 생성 (idempotency)"""
        # 결정론적 client_order_id 생성
        coid_string = f"{trace_id}|{params['symbol']}|{params['side']}|{params['price']}|{params['qty']}"
        return hashlib.sha256(coid_string.encode()).hexdigest()[:32]
    
    def _is_duplicate_order(self, client_order_id: str) -> bool:
        """중복 주문 검사"""
        current_time = time.time()
        
        # 최근 주문에서 검사 (5분 이내)
        if client_order_id in self.recent_orders:
            last_time = self.recent_orders[client_order_id]
            if current_time - last_time < 300:  # 5분
                return True
        
        return False
    
    def _add_recent_order(self, client_order_id: str):
        """최근 주문에 추가"""
        current_time = time.time()
        
        # 오래된 주문 정리 (5분 이상)
        self.recent_orders = {
            coid: timestamp for coid, timestamp in self.recent_orders.items()
            if current_time - timestamp < 300
        }
        
        # 새 주문 추가
        self.recent_orders[client_order_id] = current_time
        
        # 최대 개수 제한
        if len(self.recent_orders) > self.max_recent_orders:
            # 가장 오래된 주문 제거
            oldest_coid = min(self.recent_orders.keys(), key=lambda k: self.recent_orders[k])
            del self.recent_orders[oldest_coid]
    
    def _create_drop_result(self, drop_code: DropCode, reason: str, 
                           start_time: float, trace_id: Optional[str] = None) -> AdmissionResult:
        """드롭 결과 생성"""
        processing_time = (time.time() - start_time) * 1000
        
        if not trace_id:
            trace_id = f"drop_{int(time.time())}"
        
        # 통계 업데이트
        self.stats["drops"] += 1
        self.stats["drop_codes"][drop_code.value] = self.stats["drop_codes"].get(drop_code.value, 0) + 1
        
        return AdmissionResult(
            accepted=False,
            trace_id=trace_id,
            drop_code=drop_code,
            drop_details=reason,
            timestamp=time.time(),
            processing_time_ms=processing_time
        )
    
    def _map_risk_reason_to_drop_code(self, reason: str) -> DropCode:
        """리스크 사유를 드롭 코드로 매핑"""
        reason_lower = reason.lower()
        
        if "balance" in reason_lower:
            return DropCode.INSUFFICIENT_BALANCE
        elif "notional" in reason_lower:
            return DropCode.MIN_NOTIONAL
        elif "position" in reason_lower:
            return DropCode.MAX_POSITION_SIZE
        elif "loss" in reason_lower:
            return DropCode.DAILY_LOSS_LIMIT
        elif "circuit" in reason_lower:
            return DropCode.CIRCUIT_BREAKER
        else:
            return DropCode.UNKNOWN_ERROR
    
    def _map_exchange_filter_to_drop_code(self, reason: str) -> DropCode:
        """거래소 필터를 드롭 코드로 매핑"""
        reason_lower = reason.lower()
        
        if "notional" in reason_lower:
            return DropCode.MIN_NOTIONAL
        elif "balance" in reason_lower:
            return DropCode.INSUFFICIENT_BALANCE
        elif "rate" in reason_lower:
            return DropCode.RATE_LIMIT
        elif "maintenance" in reason_lower:
            return DropCode.MAINTENANCE
        else:
            return DropCode.UNKNOWN_ERROR


def get_signal_order_admission(repo_root: Path) -> SignalOrderAdmission:
    """SignalOrderAdmission 인스턴스 획득"""
    return SignalOrderAdmission(repo_root)
