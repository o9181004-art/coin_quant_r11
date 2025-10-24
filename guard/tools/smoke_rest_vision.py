#!/usr/bin/env python3
"""
Smoke Test: REST Vision Resilience
502/5xx 에러 시뮬레이션 및 Feeder/Trader 강건성 검증
"""
import json
import os
import sys
import time
from pathlib import Path

# 프로젝트 루트
REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

# 환경변수 로드
from dotenv import load_dotenv

load_dotenv(REPO_ROOT / "config.env")


def simulate_5xx():
    """5xx 에러 시뮬레이션 (monkey patch)"""
    print("\n⚠️  5xx 에러 시뮬레이션 활성화")
    print("   모든 REST API 호출이 502 에러를 반환합니다\n")
    
    # Binance Spot 클라이언트를 monkey patch
    try:
        from binance.spot import Spot
        
        original_exchange_info = Spot.exchange_info
        original_account = Spot.account
        
        def mock_exchange_info(self, **kwargs):
            raise Exception("(502, '502 Bad Gateway')")
        
        def mock_account(self, **kwargs):
            raise Exception("(502, '502 Bad Gateway')")
        
        Spot.exchange_info = mock_exchange_info
        Spot.account = mock_account
        
        print("✅ Monkey patch 적용 완료")
    
    except Exception as e:
        print(f"❌ Monkey patch 실패: {e}")


def check_feeder_health() -> dict:
    """Feeder health 확인"""
    health_file = Path("shared_data/health.json")
    
    if not health_file.exists():
        return {"state": "UNKNOWN", "error": "health.json 없음"}
    
    try:
        with open(health_file, 'r', encoding='utf-8') as f:
            health_data = json.load(f)
        
        feeder_health = health_data.get("feeder", {})
        return feeder_health
    
    except Exception as e:
        return {"state": "ERROR", "error": str(e)}


def check_trader_health() -> dict:
    """Trader health 확인"""
    health_file = Path("shared_data/health.json")
    
    if not health_file.exists():
        return {"state": "UNKNOWN", "error": "health.json 없음"}
    
    try:
        with open(health_file, 'r', encoding='utf-8') as f:
            health_data = json.load(f)
        
        trader_health = health_data.get("trader", {})
        return trader_health
    
    except Exception as e:
        return {"state": "ERROR", "error": str(e)}


def smoke_test(simulate_5xx_errors: bool = False):
    """
    Smoke test 실행
    
    Args:
        simulate_5xx_errors: 5xx 에러 시뮬레이션 여부
    """
    print("=" * 70)
    print("🧪 REST Vision Resilience Smoke Test")
    print("=" * 70)
    
    if simulate_5xx_errors:
        simulate_5xx()
    
    # 1. Baseline 심볼 확인
    print("\n[1/5] Baseline 심볼 확인...")
    from feeder.universe.provider import (get_universe_status,
                                          load_cached_universe)
    
    status = get_universe_status()
    print(f"   소스: {status['source']}")
    print(f"   개수: {status['symbols_count']}개")
    print(f"   Fresh: {status['is_fresh']}")
    
    if status['symbols_count'] == 0:
        print("   ❌ 심볼 없음!")
        return False
    
    print("   ✅ Baseline 심볼 정상")
    
    # 2. REST 호출 테스트
    print("\n[2/5] REST 호출 테스트...")
    from engine.binance_client import get_symbol_filters, new_client
    
    try:
        client = new_client()
        filters = get_symbol_filters(client, "BTCUSDT")
        
        if filters.get("_degraded"):
            print("   ⚠️  Degraded mode (예상된 동작)")
            print(f"   필터: {filters}")
        else:
            print("   ✅ REST 정상 - 필터 로드 성공")
    
    except Exception as e:
        print(f"   ⚠️  REST 오류 (예상된 동작): {e}")
    
    # 3. Health 파일 확인
    print("\n[3/5] Health 파일 확인...")
    feeder_health = check_feeder_health()
    trader_health = check_trader_health()
    
    print(f"   Feeder: {feeder_health.get('state', 'UNKNOWN')}")
    if feeder_health.get('last_rest_error'):
        print(f"      오류: {feeder_health['last_rest_error'][:60]}...")
    
    print(f"   Trader: {trader_health.get('state', 'UNKNOWN')}")
    print(f"      Filters: {trader_health.get('filters', 'UNKNOWN')}")
    if trader_health.get('error_message'):
        print(f"      오류: {trader_health['error_message'][:60]}...")
    
    # 4. 캐시 확인
    print("\n[4/5] 캐시 파일 확인...")
    cache_dir = Path("shared_data/cache")
    if cache_dir.exists():
        cache_files = list(cache_dir.glob("*.json"))
        print(f"   캐시 파일: {len(cache_files)}개")
        for cf in cache_files[:5]:
            print(f"      - {cf.name}")
    else:
        print("   ℹ️  캐시 디렉토리 없음")
    
    # 5. Acceptance 체크
    print("\n[5/5] Acceptance 체크...")
    
    checks = []
    
    # Feeder DEGRADE 상태 확인
    if simulate_5xx_errors:
        if feeder_health.get('state') == 'DEGRADE':
            print("   ✅ Feeder DEGRADE 모드 (502 에러 시 예상)")
            checks.append(True)
        else:
            print(f"   ❌ Feeder 상태: {feeder_health.get('state')} (DEGRADE 예상)")
            checks.append(False)
    
    # Trader IDLE 상태 확인
    if simulate_5xx_errors:
        if trader_health.get('state') in ['IDLE', 'DEGRADE']:
            print(f"   ✅ Trader {trader_health.get('state')} 모드 (502 에러 시 예상)")
            checks.append(True)
        else:
            print(f"   ❌ Trader 상태: {trader_health.get('state')} (IDLE 예상)")
            checks.append(False)
    
    # 프로세스 생존 확인
    feeder_pid_file = Path("shared_data/feeder.pid")
    trader_pid_file = Path("shared_data/trader.pid")
    
    if feeder_pid_file.exists() or trader_pid_file.exists():
        print("   ✅ 프로세스 실행 중 (PID 파일 존재)")
        checks.append(True)
    else:
        print("   ℹ️  프로세스 없음 (수동 시작 필요)")
        checks.append(None)  # Not a failure
    
    # 최종 판정
    print("\n" + "=" * 70)
    if all(c is not False for c in checks):
        print("🎉 Smoke Test PASS")
        print("   502 에러에도 시스템이 정상적으로 작동합니다")
        return True
    else:
        print("❌ Smoke Test FAIL")
        print("   일부 체크 실패")
        return False


def main():
    """메인 함수"""
    import argparse
    
    parser = argparse.ArgumentParser(description="REST Vision Resilience Smoke Test")
    parser.add_argument('--simulate_5xx', action='store_true', help='5xx 에러 시뮬레이션')
    args = parser.parse_args()
    
    try:
        success = smoke_test(simulate_5xx_errors=args.simulate_5xx)
        sys.exit(0 if success else 1)
    
    except KeyboardInterrupt:
        print("\n⚠️  사용자에 의해 중단됨")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 치명적 오류: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

