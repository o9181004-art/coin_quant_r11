#!/usr/bin/env python3
"""
Account Cache Manager
잔고/포지션 캐시 관리 (5xx 에러 대응)
"""
import json
import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 캐시 경로
CACHE_DIR = Path("shared_data/cache")
ACCOUNT_CACHE_FILE = CACHE_DIR / "account_cache.json"


def save_account_snapshot(balances: dict, positions: dict = None) -> bool:
    """
    계좌 스냅샷 저장
    
    Args:
        balances: 잔고 정보 dict
        positions: 포지션 정보 dict (선택)
    
    Returns:
        성공 여부
    """
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        
        snapshot = {
            "balances": balances,
            "positions": positions or {},
            "cached_at": time.time(),
            "server_time": int(time.time() * 1000)
        }
        
        with open(ACCOUNT_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
        
        logger.debug(f"💾 계좌 캐시 저장: {ACCOUNT_CACHE_FILE}")
        return True
    
    except Exception as e:
        logger.error(f"❌ 계좌 캐시 저장 실패: {e}")
        return False


def load_account_snapshot() -> Optional[dict]:
    """
    계좌 스냅샷 로드
    
    Returns:
        dict: {
            "balances": dict,
            "positions": dict,
            "cached_at": float,
            "age_sec": float,
            "is_fresh": bool
        }
        또는 None
    """
    if not ACCOUNT_CACHE_FILE.exists():
        return None
    
    try:
        with open(ACCOUNT_CACHE_FILE, 'r', encoding='utf-8') as f:
            snapshot = json.load(f)
        
        cached_at = snapshot.get('cached_at', 0)
        age_sec = time.time() - cached_at
        is_fresh = age_sec < 60  # 60초 이내면 fresh
        
        snapshot['age_sec'] = age_sec
        snapshot['is_fresh'] = is_fresh
        
        logger.debug(f"📦 계좌 캐시 로드: age={age_sec:.0f}초, fresh={is_fresh}")
        
        return snapshot
    
    except Exception as e:
        logger.error(f"❌ 계좌 캐시 로드 실패: {e}")
        return None


def get_account_with_fallback(fetch_func, default_balances: dict = None) -> tuple:
    """
    계좌 정보 조회 (fallback 포함)
    
    Args:
        fetch_func: 실제 API 호출 함수
        default_balances: 기본값
    
    Returns:
        (success: bool, data: dict, cache_age: float)
    """
    # 1차 시도: 실제 API
    try:
        data = fetch_func()
        
        # 성공 시 캐시 저장
        save_account_snapshot(data)
        
        return (True, data, 0.0)
    
    except Exception as e:
        logger.warning(f"⚠️  계좌 조회 실패: {e}")
        
        # 2차 시도: 캐시
        snapshot = load_account_snapshot()
        if snapshot:
            age_sec = snapshot.get('age_sec', 999)
            balances = snapshot.get('balances', {})
            
            logger.info(f"📦 캐시 사용: age={age_sec:.0f}초")
            return (False, balances, age_sec)
        
        # 3차 시도: 기본값
        if default_balances:
            logger.warning(f"🔧 기본값 사용")
            return (False, default_balances, 999.0)
        
        # 실패
        return (False, {}, 999.0)


if __name__ == "__main__":
    # 테스트
    print("=" * 70)
    print("Account Cache Manager Test")
    print("=" * 70)
    
    # 테스트 데이터
    test_balances = {
        "USDT": 10000.0,
        "BTC": 0.0,
        "ETH": 0.0
    }
    
    # 저장
    print("\n[1/2] 캐시 저장...")
    success = save_account_snapshot(test_balances)
    print(f"   {'✅' if success else '❌'} 저장 {' 성공' if success else '실패'}")
    
    # 로드
    print("\n[2/2] 캐시 로드...")
    snapshot = load_account_snapshot()
    if snapshot:
        print(f"   ✅ 로드 성공")
        print(f"   Age: {snapshot['age_sec']:.1f}초")
        print(f"   Fresh: {snapshot['is_fresh']}")
        print(f"   Balances: {snapshot['balances']}")
    else:
        print(f"   ❌ 로드 실패")

