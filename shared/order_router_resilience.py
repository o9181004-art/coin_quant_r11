#!/usr/bin/env python3
"""
Order Router Resilience
Production-grade order routing with retry logic and error handling
"""

import json
import logging
import time
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import requests


class RetryableError(Enum):
    """재시도 가능한 오류"""
    NETWORK_ERROR = "network_error"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    SERVER_ERROR_5XX = "server_error_5xx"
    TEMPORARY_UNAVAILABLE = "temporary_unavailable"


class NonRetryableError(Enum):
    """재시도 불가능한 오류"""
    INVALID_SYMBOL = "invalid_symbol"
    INSUFFICIENT_BALANCE = "insufficient_balance"
    INVALID_ORDER_PARAMS = "invalid_order_params"
    ACCOUNT_RESTRICTED = "account_restricted"
    SYMBOL_NOT_TRADING = "symbol_not_trading"


@dataclass
class RetryConfig:
    """재시도 설정"""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    backoff_multiplier: float = 2.0
    jitter: bool = True


@dataclass
class OrderRequest:
    """주문 요청"""
    symbol: str
    side: str
    qty: float
    price: float
    order_type: str = "MARKET"
    client_order_id: str = ""
    timestamp: int = 0


@dataclass
class OrderResponse:
    """주문 응답"""
    success: bool
    order_id: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    http_status: Optional[int] = None
    retry_after: Optional[int] = None
    raw_response: Optional[Dict[str, Any]] = None


@dataclass
class RetryAttempt:
    """재시도 시도"""
    attempt: int
    delay: float
    error: str
    timestamp: float


class OrderRouterResilience:
    """주문 라우터 복원력 관리"""
    
    def __init__(self, retry_config: Optional[RetryConfig] = None):
        self.logger = logging.getLogger(__name__)
        self.retry_config = retry_config or RetryConfig()
        
        # 통계
        self.stats = {
            "orders_sent": 0,
            "orders_success": 0,
            "orders_failed": 0,
            "retryable_errors": 0,
            "non_retryable_errors": 0,
            "total_retries": 0
        }
        
        # 재시도 히스토리
        self.retry_history: List[RetryAttempt] = []
        self.max_retry_history = 1000
        
        self.logger.info("OrderRouterResilience initialized")
    
    def route_order(self, order_request: OrderRequest, 
                   exchange_client: Any) -> Tuple[OrderResponse, List[RetryAttempt]]:
        """주문 라우팅 (재시도 로직 포함)"""
        self.stats["orders_sent"] += 1
        
        retry_attempts = []
        last_error = None
        
        for attempt in range(self.retry_config.max_retries + 1):
            try:
                # 주문 실행
                response = self._execute_order(order_request, exchange_client)
                
                if response.success:
                    self.stats["orders_success"] += 1
                    self.logger.info(f"ROUTE status=sent code=200 trace_id={order_request.client_order_id} coid={order_request.client_order_id}")
                    return response, retry_attempts
                
                # 오류 분석
                is_retryable, retry_after = self._analyze_error(response)
                
                if not is_retryable or attempt >= self.retry_config.max_retries:
                    # 재시도 불가능하거나 최대 재시도 횟수 초과
                    if is_retryable:
                        self.stats["retryable_errors"] += 1
                    else:
                        self.stats["non_retryable_errors"] += 1
                    
                    self.stats["orders_failed"] += 1
                    self.logger.error(f"ROUTE status=drop code={response.error_code} trace_id={order_request.client_order_id} coid={order_request.client_order_id}")
                    return response, retry_attempts
                
                # 재시도 가능한 오류
                self.stats["retryable_errors"] += 1
                self.stats["total_retries"] += 1
                
                # 재시도 지연 계산
                delay = self._calculate_retry_delay(attempt, retry_after)
                
                # 재시도 기록
                retry_attempt = RetryAttempt(
                    attempt=attempt + 1,
                    delay=delay,
                    error=response.error_message or "Unknown error",
                    timestamp=time.time()
                )
                retry_attempts.append(retry_attempt)
                self._add_retry_history(retry_attempt)
                
                self.logger.warning(f"ROUTE status=retry code={response.error_code} trace_id={order_request.client_order_id} coid={order_request.client_order_id} attempt={attempt + 1} delay={delay:.1f}s")
                
                # 재시도 대기
                time.sleep(delay)
                last_error = response
                
            except Exception as e:
                self.logger.error(f"Order routing exception: {e}")
                last_error = OrderResponse(
                    success=False,
                    error_code="EXCEPTION",
                    error_message=str(e)
                )
                break
        
        # 모든 재시도 실패
        self.stats["orders_failed"] += 1
        self.logger.error(f"ROUTE status=drop code={last_error.error_code if last_error else 'UNKNOWN'} trace_id={order_request.client_order_id} coid={order_request.client_order_id}")
        
        return last_error or OrderResponse(success=False, error_code="UNKNOWN"), retry_attempts
    
    def _execute_order(self, order_request: OrderRequest, exchange_client: Any) -> OrderResponse:
        """주문 실행"""
        try:
            # 거래소 클라이언트를 통한 주문 실행
            # 실제 구현은 거래소별로 다름
            if hasattr(exchange_client, 'new_order'):
                # Binance 스타일
                result = exchange_client.new_order(
                    symbol=order_request.symbol,
                    side=order_request.side,
                    type=order_request.order_type,
                    quantity=order_request.qty,
                    price=order_request.price,
                    newClientOrderId=order_request.client_order_id
                )
                
                return OrderResponse(
                    success=True,
                    order_id=result.get('orderId'),
                    raw_response=result
                )
            
            elif hasattr(exchange_client, 'place_order'):
                # 일반적인 place_order 메서드
                result = exchange_client.place_order(
                    symbol=order_request.symbol,
                    side=order_request.side,
                    order_type=order_request.order_type,
                    qty=order_request.qty,
                    price=order_request.price,
                    client_order_id=order_request.client_order_id
                )
                
                return OrderResponse(
                    success=True,
                    order_id=result.get('order_id'),
                    raw_response=result
                )
            
            else:
                return OrderResponse(
                    success=False,
                    error_code="UNSUPPORTED_CLIENT",
                    error_message="Exchange client does not support order placement"
                )
                
        except requests.exceptions.Timeout as e:
            return OrderResponse(
                success=False,
                error_code="TIMEOUT",
                error_message=str(e)
            )
        
        except requests.exceptions.ConnectionError as e:
            return OrderResponse(
                success=False,
                error_code="NETWORK_ERROR",
                error_message=str(e)
            )
        
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response else 0
            
            # Retry-After 헤더 확인
            retry_after = None
            if e.response and 'Retry-After' in e.response.headers:
                try:
                    retry_after = int(e.response.headers['Retry-After'])
                except ValueError:
                    pass
            
            return OrderResponse(
                success=False,
                error_code=f"HTTP_{status_code}",
                error_message=str(e),
                http_status=status_code,
                retry_after=retry_after
            )
        
        except Exception as e:
            return OrderResponse(
                success=False,
                error_code="UNKNOWN_ERROR",
                error_message=str(e)
            )
    
    def _analyze_error(self, response: OrderResponse) -> Tuple[bool, Optional[int]]:
        """오류 분석 (재시도 가능 여부 판단)"""
        if not response.error_code:
            return False, None
        
        error_code = response.error_code.upper()
        
        # 재시도 가능한 오류
        if error_code in ["TIMEOUT", "NETWORK_ERROR"]:
            return True, None
        
        if error_code.startswith("HTTP_5"):
            return True, response.retry_after
        
        if error_code == "HTTP_429":  # Rate limit
            return True, response.retry_after or 60
        
        if error_code == "HTTP_503":  # Service unavailable
            return True, response.retry_after or 30
        
        # 재시도 불가능한 오류
        if error_code in ["INVALID_SYMBOL", "INSUFFICIENT_BALANCE", "INVALID_ORDER_PARAMS"]:
            return False, None
        
        if error_code.startswith("HTTP_4") and error_code != "HTTP_429":
            return False, None
        
        # 기본값: 재시도 불가능
        return False, None
    
    def _calculate_retry_delay(self, attempt: int, retry_after: Optional[int] = None) -> float:
        """재시도 지연 시간 계산"""
        if retry_after:
            # Retry-After 헤더 값 사용
            return float(retry_after)
        
        # 지수 백오프
        delay = self.retry_config.base_delay * (self.retry_config.backoff_multiplier ** attempt)
        delay = min(delay, self.retry_config.max_delay)
        
        # 지터 추가 (선택적)
        if self.retry_config.jitter:
            import random
            jitter = random.uniform(0.1, 0.3) * delay
            delay += jitter
        
        return delay
    
    def _add_retry_history(self, retry_attempt: RetryAttempt):
        """재시도 히스토리 추가"""
        self.retry_history.append(retry_attempt)
        
        # 히스토리 크기 제한
        if len(self.retry_history) > self.max_retry_history:
            self.retry_history = self.retry_history[-self.max_retry_history:]
    
    def get_stats(self) -> Dict[str, Any]:
        """통계 조회"""
        return {
            **self.stats,
            "retry_history_count": len(self.retry_history),
            "success_rate": (
                self.stats["orders_success"] / max(self.stats["orders_sent"], 1) * 100
            ),
            "retry_rate": (
                self.stats["total_retries"] / max(self.stats["orders_sent"], 1) * 100
            )
        }
    
    def get_recent_retry_attempts(self, limit: int = 10) -> List[RetryAttempt]:
        """최근 재시도 시도 조회"""
        return self.retry_history[-limit:] if self.retry_history else []


def get_order_router_resilience(retry_config: Optional[RetryConfig] = None) -> OrderRouterResilience:
    """OrderRouterResilience 인스턴스 획득"""
    return OrderRouterResilience(retry_config)
