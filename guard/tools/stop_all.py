#!/usr/bin/env python3
"""
Stop All Services
Trader, Feeder 순서로 Graceful 종료
"""
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent.resolve()


def stop_trader() -> tuple:
    """Trader 종료"""
    print("\n[1/2] Trader 종료...")
    
    try:
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "guard" / "tools" / "stop_trader.py")],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(REPO_ROOT)
        )
        
        if result.returncode == 0:
            print("   ✅ Trader 정상 종료")
            return (True, "Trader 종료 완료")
        elif result.returncode == 1:
            print("   ℹ️  Trader 실행 중이 아님")
            return (True, "Trader 없음")
        else:
            print(f"   ⚠️  Trader 종료 부분 실패 (exit code: {result.returncode})")
            return (False, "Trader 종료 실패")
    
    except subprocess.TimeoutExpired:
        print("   ❌ Trader 종료 timeout")
        return (False, "Trader timeout")
    except Exception as e:
        print(f"   ❌ Trader 종료 오류: {e}")
        return (False, str(e))


def stop_feeder() -> tuple:
    """Feeder 종료"""
    print("\n[2/2] Feeder 종료...")
    
    # Feeder stop 스크립트 확인
    stop_feeder_script = REPO_ROOT / "guard" / "tools" / "stop_feeder.py"
    
    if not stop_feeder_script.exists():
        # 대체: PID로 종료
        try:
            import json

            import psutil
            
            pid_file = REPO_ROOT / "shared_data" / "feeder.pid"
            if not pid_file.exists():
                print("   ℹ️  Feeder 실행 중이 아님")
                return (True, "Feeder 없음")
            
            with open(pid_file, 'r', encoding='utf-8') as f:
                try:
                    pid_data = json.load(f)
                    pid = pid_data.get('pid') if isinstance(pid_data, dict) else int(pid_data)
                except:
                    pid = int(f.read().strip())
            
            if psutil.pid_exists(pid):
                proc = psutil.Process(pid)
                proc.terminate()
                print(f"   SIGTERM 전송 (PID {pid})")
                
                # 5초 대기
                try:
                    proc.wait(timeout=5)
                    print("   ✅ Feeder 정상 종료")
                except psutil.TimeoutExpired:
                    proc.kill()
                    print("   ✅ Feeder 강제 종료")
                
                # PID 파일 삭제
                pid_file.unlink()
                return (True, "Feeder 종료 완료")
            else:
                print("   ℹ️  Feeder 이미 종료됨")
                pid_file.unlink()
                return (True, "Feeder 없음")
        
        except Exception as e:
            print(f"   ❌ Feeder 종료 오류: {e}")
            return (False, str(e))
    
    else:
        # stop_feeder.py 사용
        try:
            result = subprocess.run(
                [sys.executable, str(stop_feeder_script)],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=str(REPO_ROOT)
            )
            
            if result.returncode == 0:
                print("   ✅ Feeder 정상 종료")
                return (True, "Feeder 종료 완료")
            else:
                print(f"   ⚠️  Feeder 종료 실패 (exit code: {result.returncode})")
                return (False, "Feeder 종료 실패")
        
        except subprocess.TimeoutExpired:
            print("   ❌ Feeder 종료 timeout")
            return (False, "Feeder timeout")
        except Exception as e:
            print(f"   ❌ Feeder 종료 오류: {e}")
            return (False, str(e))


def clear_e2e_flag():
    """E2E_FLAG 초기화"""
    print("\n[Cleanup] E2E_FLAG 초기화...")
    
    # 환경변수 파일 업데이트는 하지 않음 (수동으로 설정)
    # 대신 임시 플래그 파일 삭제
    e2e_flag_file = REPO_ROOT / "shared_data" / "E2E_ACTIVE.flag"
    if e2e_flag_file.exists():
        e2e_flag_file.unlink()
        print("   ✅ E2E flag 파일 삭제")


def stop_all():
    """모든 서비스 종료"""
    print("=" * 70)
    print("🛑 Stop All Services")
    print("=" * 70)
    
    # 1. Trader 종료
    trader_ok, trader_msg = stop_trader()
    
    # 2초 대기
    time.sleep(2)
    
    # 2. Feeder 종료
    feeder_ok, feeder_msg = stop_feeder()
    
    # 3. E2E flag 초기화
    clear_e2e_flag()
    
    # 최종 결과
    print("\n" + "=" * 70)
    if trader_ok and feeder_ok:
        print("✅ 모든 서비스 종료 완료")
        print("=" * 70)
        return 0
    else:
        print("⚠️  일부 서비스 종료 실패")
        print("=" * 70)
        print(f"Trader: {trader_msg}")
        print(f"Feeder: {feeder_msg}")
        return 1


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Stop All Services")
    parser.add_argument('--force', action='store_true', help='강제 종료')
    args = parser.parse_args()
    
    try:
        exit_code = stop_all()
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

