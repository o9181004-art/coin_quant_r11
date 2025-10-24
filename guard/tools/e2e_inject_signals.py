#!/usr/bin/env python3
"""
E2E Inject Signals
TestnetMarketPoke 전략에서 ARES 호환 신호 생성 및 주입
"""
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent.resolve()
sys.path.insert(0, str(REPO_ROOT))

# 환경변수 로드
from dotenv import load_dotenv

load_dotenv(REPO_ROOT / "config.env")


def check_e2e_preconditions() -> tuple:
    """E2E 실행 조건 확인"""
    # 1. Testnet
    if os.getenv("BINANCE_USE_TESTNET", "false").lower() != "true":
        return (False, "🚫 BINANCE_USE_TESTNET != true")
    
    # 2. DRY_RUN
    if os.getenv("DRY_RUN", "true").lower() == "true":
        return (False, "🚫 DRY_RUN != false")
    
    # 3. E2E_FLAG
    if os.getenv("E2E_FLAG", "0") != "1":
        return (False, "🚫 E2E_FLAG != 1")
    
    return (True, "✅ E2E 조건 충족")


def inject_signals():
    """E2E 신호 주입"""
    print("=" * 70)
    print("📤 E2E Inject Signals")
    print("=" * 70)
    
    # 1. 조건 확인
    print("\n[1/3] E2E 조건 확인...")
    precond_ok, precond_msg = check_e2e_preconditions()
    print(f"   {precond_msg}")
    
    if not precond_ok:
        print("\n" + "=" * 70)
        print("❌ E2E 실행 조건 미충족")
        print("=" * 70)
        print("활성화 방법:")
        print("  1. config.env 수정:")
        print("     BINANCE_USE_TESTNET=true")
        print("     DRY_RUN=false")
        print("     E2E_FLAG=1")
        print("  2. 서비스 재시작")
        return 1
    
    # 2. TestnetMarketPoke 전략 생성
    print("\n[2/3] TestnetMarketPoke 전략 생성...")
    
    try:
        from strategies.testnet_market_poke import create_e2e_strategy
        
        strategy = create_e2e_strategy()
        if not strategy:
            print("   ❌ 전략 생성 실패")
            return 1
        
        print(f"   ✅ Trace ID: {strategy.trace_id}")
        print(f"   심볼: {strategy.symbols}")
        print(f"   최대 주문: {strategy.max_orders}개")
    
    except Exception as e:
        print(f"   ❌ 전략 생성 오류: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # 3. 신호 생성 및 저장
    print(f"\n[3/3] 신호 생성 중 ({strategy.max_orders}개)...")
    
    signals_dir = REPO_ROOT / "shared_data" / "ares"
    signals_dir.mkdir(parents=True, exist_ok=True)
    
    signals_file = signals_dir / f"e2e_signals_{strategy.trace_id}.jsonl"
    
    signals_generated = 0
    
    with open(signals_file, 'w', encoding='utf-8') as f:
        for i in range(strategy.max_orders):
            signal = strategy.generate_signal()
            
            if not signal:
                break
            
            # JSONL 형식으로 저장
            f.write(json.dumps(signal, ensure_ascii=False) + "\n")
            f.flush()
            
            signals_generated += 1
            print(f"   {i+1}. {signal['action'].upper()} {signal['symbol']} @ {signal['notional_usdt']} USDT")
            
            # Timeout
            if i < strategy.max_orders - 1:
                time.sleep(strategy.timeout_sec)
    
    # 최종 결과
    print("\n" + "=" * 70)
    print(f"🎉 E2E 신호 주입 완료!")
    print("=" * 70)
    print(f"Trace ID: {strategy.trace_id}")
    print(f"신호 개수: {signals_generated}개")
    print(f"파일: {signals_file.name}")
    print("\n다음 단계:")
    print(f"  python guard/tools/e2e_verify.py --trace_id {strategy.trace_id}")
    print("=" * 70)
    
    return 0


def main():
    try:
        exit_code = inject_signals()
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

