#!/usr/bin/env python3
"""
E2E Start: Feeder → UDS → Trader 순차 시작
SSOT health gating으로 의존성 순서 보장
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent.resolve()
sys.path.insert(0, str(REPO_ROOT))

# 환경변수 로드
from dotenv import load_dotenv

load_dotenv(REPO_ROOT / "config.env")


def check_testnet_config() -> tuple:
    """
    Testnet 설정 확인
    
    Returns:
        (success: bool, message: str)
    """
    # 1. BINANCE_USE_TESTNET
    use_testnet = os.getenv("BINANCE_USE_TESTNET", "false").lower() == "true"
    if not use_testnet:
        return (False, "🚫 BINANCE_USE_TESTNET != true (프로덕션 보호)")
    
    # 2. DRY_RUN
    dry_run = os.getenv("DRY_RUN", "true").lower() == "true"
    if dry_run:
        return (False, "🚫 DRY_RUN != false (실제 주문 필요)")
    
    # 3. API Keys
    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_API_SECRET")
    if not api_key or not api_secret:
        return (False, "🚫 API Keys 없음")
    
    return (True, "✅ Testnet 설정 정상")


def wait_for_health_gate(
    component: str,
    expected_states: list,
    max_wait_sec: int = 30,
    check_interval: float = 1.0
) -> tuple:
    """
    Health gate 대기 (SSOT 기반)
    
    Args:
        component: "feeder" | "trader" | "uds"
        expected_states: 허용되는 상태 리스트
        max_wait_sec: 최대 대기 시간
        check_interval: 체크 간격
    
    Returns:
        (success: bool, state: str, message: str)
    """
    health_file = REPO_ROOT / "shared_data" / "health.json"
    start_time = time.time()
    
    while (time.time() - start_time) < max_wait_sec:
        try:
            if not health_file.exists():
                time.sleep(check_interval)
                continue
            
            with open(health_file, 'r', encoding='utf-8') as f:
                health_data = json.load(f)
            
            comp_health = health_data.get(component, {})
            state = comp_health.get("state", "UNKNOWN")
            
            if state in expected_states:
                elapsed = time.time() - start_time
                return (True, state, f"✅ {component}: {state} ({elapsed:.1f}초)")
            
            # 특별 케이스: Feeder WS age 체크
            if component == "feeder" and state in ["RUNNING", "DEGRADE"]:
                # WS age 체크 (health_stats)
                health_stats = health_data.get("health_stats", {})
                ws_age = health_stats.get("age_sec", 999)
                
                if ws_age <= 5.0:
                    elapsed = time.time() - start_time
                    return (True, state, f"✅ Feeder: {state}, WS age={ws_age:.1f}s ({elapsed:.1f}초)")
            
        except Exception as e:
            pass
        
        time.sleep(check_interval)
    
    # Timeout
    elapsed = time.time() - start_time
    return (False, "TIMEOUT", f"⏱️  {component} timeout ({elapsed:.1f}초)")


def start_feeder() -> tuple:
    """Feeder 시작"""
    print("\n[1/3] Feeder 시작...")
    
    try:
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "guard" / "tools" / "launch_feeder.py")],
            capture_output=True,
            text=True,
            timeout=20,
            cwd=str(REPO_ROOT)
        )
        
        if result.returncode == 0 or result.returncode == 2:  # 성공 or 이미 실행 중
            # Health gate 대기
            success, state, msg = wait_for_health_gate(
                "feeder",
                expected_states=["RUNNING", "DEGRADE"],
                max_wait_sec=30
            )
            
            print(f"   {msg}")
            return (success, msg)
        else:
            return (False, f"❌ Feeder 시작 실패 (exit code: {result.returncode})")
    
    except subprocess.TimeoutExpired:
        return (False, "❌ Feeder 시작 timeout")
    except Exception as e:
        return (False, f"❌ Feeder 시작 오류: {e}")


def start_trader() -> tuple:
    """Trader 시작"""
    print("\n[2/3] Trader 시작...")
    
    try:
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "guard" / "tools" / "launch_trader.py")],
            capture_output=True,
            text=True,
            timeout=20,
            cwd=str(REPO_ROOT)
        )
        
        if result.returncode == 0 or result.returncode == 2:
            # Health gate 대기
            success, state, msg = wait_for_health_gate(
                "trader",
                expected_states=["RUNNING", "IDLE"],
                max_wait_sec=30
            )
            
            print(f"   {msg}")
            return (success or state == "IDLE", msg)  # IDLE도 허용
        else:
            return (False, f"❌ Trader 시작 실패 (exit code: {result.returncode})")
    
    except subprocess.TimeoutExpired:
        return (False, "❌ Trader 시작 timeout")
    except Exception as e:
        return (False, f"❌ Trader 시작 오류: {e}")


def check_uds_heartbeat() -> tuple:
    """UDS heartbeat 확인"""
    print("\n[3/3] UDS heartbeat 확인...")
    
    # UDS는 Trader 내부에 포함되어 있음
    # Health에서 UDS 정보 확인
    health_file = REPO_ROOT / "shared_data" / "health.json"
    
    try:
        if not health_file.exists():
            return (True, "ℹ️  UDS: Health 파일 없음 (생성 대기)")
        
        with open(health_file, 'r', encoding='utf-8') as f:
            health_data = json.load(f)
        
        uds_health = health_data.get("uds", {})
        heartbeat_age = uds_health.get("heartbeat_age_sec", 999)
        
        if heartbeat_age <= 60:
            return (True, f"✅ UDS: Fresh (age={heartbeat_age:.1f}s)")
        else:
            # UDS fresh하지 않아도 허용 (Trader가 IDLE로 시작)
            return (True, f"⚠️  UDS: Stale (age={heartbeat_age:.1f}s) - Trader IDLE 허용")
    
    except Exception as e:
        return (True, f"ℹ️  UDS: 확인 불가 - {e}")


def e2e_start():
    """E2E 전체 시작"""
    print("=" * 70)
    print("🚀 E2E Start: Feeder → UDS → Trader")
    print("=" * 70)
    
    # 0. Testnet 설정 확인
    print("\n[0/3] Testnet 설정 확인...")
    config_ok, config_msg = check_testnet_config()
    print(f"   {config_msg}")
    
    if not config_ok:
        print("\n" + "=" * 70)
        print("❌ E2E 시작 거부: Testnet 설정 확인 필요")
        print("=" * 70)
        return 1
    
    # 1. Feeder 시작
    feeder_ok, feeder_msg = start_feeder()
    if not feeder_ok:
        print(f"\n❌ Feeder 시작 실패: {feeder_msg}")
        return 1
    
    # 2. Trader 시작
    trader_ok, trader_msg = start_trader()
    if not trader_ok:
        print(f"\n❌ Trader 시작 실패: {trader_msg}")
        return 1
    
    # 3. UDS 확인
    uds_ok, uds_msg = check_uds_heartbeat()
    print(f"   {uds_msg}")
    
    # 최종 결과
    print("\n" + "=" * 70)
    print("🎉 E2E 시작 완료!")
    print("=" * 70)
    print(f"Feeder: {feeder_msg}")
    print(f"Trader: {trader_msg}")
    print(f"UDS: {uds_msg}")
    print("\n다음 단계:")
    print("  1. E2E 신호 주입: python guard/tools/e2e_inject_signals.py")
    print("  2. 체결 검증: python guard/tools/e2e_verify.py")
    print("=" * 70)
    
    return 0


def main():
    try:
        exit_code = e2e_start()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⚠️  사용자에 의해 중단됨")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 오류: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

