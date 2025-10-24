#!/usr/bin/env python3
"""
REST API Resilience Layer
Binance REST 502/5xx 에러에 대한 강건한 처리
"""
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, Optional, Tuple

logger = logging.getLogger(__name__)

# 설정
ALLOW_DEGRADE = os.getenv("ALLOW_DEGRADE", "1") == "1"
FAIL_FAST = os.getenv("FAIL_FAST", "0") == "1"

# 캐시 디렉토리
CACHE_DIR = Path("shared_data/cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def exponential_backoff_retry(
    func: Callable,
    max_retries: int = 5,
    base_delay: float = 2.0,
    max_delay: float = 60.0,
    operation_name: str = "API call"
) -> Tuple[bool, Any, Optional[str]]:
    """
    지수 백오프 재시도
    
    Args:
        func: 실행할 함수
        max_retries: 최대 재시도 횟수
        base_delay: 기본 지연 시간 (초)
        max_delay: 최대 지연 시간 (초)
        operation_name: 작업 이름 (로깅용)
    
    Returns:
        (success: bool, result: Any, error: Optional[str])
    """
    last_error = None
    
    for attempt in range(max_retries):
        try:
            result = func()
            
            if attempt > 0:
                logger.info(f"✅ {operation_name} 성공 (시도 {attempt + 1}/{max_retries})")
            
            return (True, result, None)
        
        except Exception as e:
            last_error = str(e)
            error_code = getattr(e, 'code', None) if hasattr(e, 'code') else None
            
            # 5xx 에러인지 확인
            is_5xx = False
            if error_code:
                is_5xx = 500 <= error_code < 600
            elif "502" in last_error or "503" in last_error or "504" in last_error:
                is_5xx = True
            
            # 마지막 시도가 아니면 재시도
            if attempt < max_retries - 1:
                delay = min(base_delay * (2 ** attempt), max_delay)
                
                logger.warning(
                    f"⚠️  {operation_name} 실패 (시도 {attempt + 1}/{max_retries}): {last_error}"
                )
                logger.info(f"   {delay:.1f}초 후 재시도...")
                
                time.sleep(delay)
            else:
                # 마지막 시도 실패
                logger.error(
                    f"❌ {operation_name} 최종 실패 ({max_retries}회 시도): {last_error}"
                )
    
    return (False, None, last_error)


def load_cached_data(cache_file: str, default: Any = None) -> Any:
    """
    캐시된 데이터 로드
    
    Args:
        cache_file: 캐시 파일명
        default: 기본값
    
    Returns:
        캐시된 데이터 또는 기본값
    """
    cache_path = CACHE_DIR / cache_file
    
    if not cache_path.exists():
        return default
    
    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 캐시 나이 확인
        cached_at = data.get('cached_at', 0)
        age = time.time() - cached_at
        
        logger.info(f"📦 캐시 데이터 로드: {cache_file} (age: {age:.0f}초)")
        
        return data.get('data')
    
    except Exception as e:
        logger.error(f"❌ 캐시 로드 실패: {cache_file} - {e}")
        return default


def save_cached_data(cache_file: str, data: Any) -> bool:
    """
    데이터 캐싱
    
    Args:
        cache_file: 캐시 파일명
        data: 저장할 데이터
    
    Returns:
        성공 여부
    """
    cache_path = CACHE_DIR / cache_file
    
    try:
        cache_data = {
            'data': data,
            'cached_at': time.time()
        }
        
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
        
        logger.debug(f"💾 캐시 저장: {cache_file}")
        return True
    
    except Exception as e:
        logger.error(f"❌ 캐시 저장 실패: {cache_file} - {e}")
        return False


def safe_rest_call(
    func: Callable,
    operation_name: str,
    cache_file: Optional[str] = None,
    default_on_error: Any = None
) -> Tuple[bool, Any]:
    """
    안전한 REST 호출 (재시도 + 캐시 fallback)
    
    Args:
        func: 실행할 함수
        operation_name: 작업 이름
        cache_file: 캐시 파일명 (선택)
        default_on_error: 에러 시 기본값
    
    Returns:
        (success: bool, result: Any)
    """
    # 1. 재시도 로직으로 실행
    success, result, error = exponential_backoff_retry(
        func,
        max_retries=5,
        base_delay=2.0,
        max_delay=60.0,
        operation_name=operation_name
    )
    
    if success:
        # 성공 시 캐시 저장
        if cache_file and result:
            save_cached_data(cache_file, result)
        
        return (True, result)
    
    # 2. 실패 시 처리
    if FAIL_FAST:
        # Fail-fast 모드: 즉시 실패
        logger.critical(f"💥 FAIL_FAST 모드: {operation_name} 실패로 종료")
        raise RuntimeError(f"{operation_name} failed: {error}")
    
    if ALLOW_DEGRADE:
        # Degraded 모드: 캐시 또는 기본값 사용
        logger.warning(f"⚠️  DEGRADE 모드: {operation_name} 실패, fallback 사용")
        
        if cache_file:
            cached_data = load_cached_data(cache_file, default_on_error)
            if cached_data is not None:
                logger.info(f"📦 캐시된 데이터 사용: {cache_file}")
                return (False, cached_data)
        
        # 캐시 없으면 기본값
        logger.warning(f"🔧 기본값 사용: {default_on_error}")
        return (False, default_on_error)
    
    # 3. 둘 다 아니면 에러
    logger.error(f"❌ {operation_name} 실패")
    return (False, default_on_error)


def update_degraded_health(
    component: str,
    status: str,
    error_message: str = ""
):
    """
    Degraded 상태를 health.json에 기록
    
    Args:
        component: "feeder" | "trader"
        status: "RUNNING" | "DEGRADE" | "IDLE" | "ERROR"
        error_message: 에러 메시지
    """
    try:
        health_file = Path("shared_data/health.json")
        
        # 기존 health 데이터 로드
        if health_file.exists():
            with open(health_file, 'r', encoding='utf-8') as f:
                health_data = json.load(f)
        else:
            health_data = {}
        
        # 업데이트
        health_data[component] = {
            "status": status,
            "last_update": time.time(),
            "error_message": error_message if error_message else ""
        }
        
        if status == "DEGRADE":
            health_data[f"{component}_last_rest_error"] = time.time()
        
        # 저장
        with open(health_file, 'w', encoding='utf-8') as f:
            json.dump(health_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"🩺 Health 업데이트: {component} = {status}")
    
    except Exception as e:
        logger.error(f"❌ Health 업데이트 실패: {e}")


def get_empty_account_snapshot():
    """
    빈 계좌 스냅샷 (API 실패 시 사용)
    
    Returns:
        dict: 빈 계좌 데이터
    """
    return {
        "balances": [],
        "makerCommission": 10,
        "takerCommission": 10,
        "buyerCommission": 0,
        "sellerCommission": 0,
        "canTrade": False,
        "canWithdraw": False,
        "canDeposit": False,
        "updateTime": int(time.time() * 1000),
        "_degraded": True,
        "_error": "Account snapshot unavailable (REST API error)"
    }


def get_empty_exchange_info():
    """
    빈 거래소 정보 (API 실패 시 사용)
    
    Returns:
        dict: 최소한의 거래소 정보
    """
    return {
        "timezone": "UTC",
        "serverTime": int(time.time() * 1000),
        "symbols": [],
        "_degraded": True,
        "_error": "ExchangeInfo unavailable (REST API error)"
    }


# 환경변수 출력 (디버깅용)
if __name__ == "__main__":
    print("=" * 70)
    print("REST Resilience Configuration")
    print("=" * 70)
    print(f"ALLOW_DEGRADE: {ALLOW_DEGRADE}")
    print(f"FAIL_FAST: {FAIL_FAST}")
    print(f"CACHE_DIR: {CACHE_DIR}")
    print("=" * 70)

