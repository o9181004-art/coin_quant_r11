#!/usr/bin/env python3
"""
Trader Graceful Shutdown
Trader 프로세스를 안전하게 종료
"""
import json
import os
import pathlib
import sys
import time
from typing import Optional

# 프로젝트 루트 경로
REPO_ROOT = pathlib.Path(__file__).parent.parent.parent.resolve()

# SSOT 경로
SHARED_DATA_DIR = REPO_ROOT / "shared_data"
TRADER_PID_FILE = SHARED_DATA_DIR / "trader.pid"


def is_pid_alive(pid: int) -> bool:
    """PID가 살아있는지 확인"""
    try:
        import psutil
        return psutil.pid_exists(pid) and psutil.Process(pid).is_running()
    except:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False


def get_trader_pid() -> Optional[int]:
    """Trader PID 가져오기"""
    if not TRADER_PID_FILE.exists():
        return None
    
    try:
        with open(TRADER_PID_FILE, 'r', encoding='utf-8') as f:
            pid_data = json.load(f)
        
        pid = pid_data.get('pid')
        if pid and is_pid_alive(pid):
            return pid
        else:
            # Stale PID 정리
            TRADER_PID_FILE.unlink()
            return None
            
    except Exception:
        return None


def stop_trader(force: bool = False) -> int:
    """
    Trader 종료
    
    Args:
        force: True면 강제 종료 (SIGKILL)
    
    Returns:
        0: 성공
        1: 실행 중이 아님
        2: 종료 실패
    """
    print("=" * 70)
    print("🛑 Trader Stop")
    print("=" * 70)
    
    # 1. PID 확인
    print("\n[1/3] Trader PID 확인...")
    pid = get_trader_pid()
    
    if not pid:
        print("ℹ️  실행 중인 Trader가 없습니다.")
        return 1
    
    print(f"✅ Trader PID: {pid}")
    
    # 2. Graceful 종료 시도
    print("\n[2/3] Graceful 종료 시도...")
    
    try:
        import psutil
        process = psutil.Process(pid)
        
        if not force:
            # SIGTERM (graceful)
            process.terminate()
            print(f"   SIGTERM 전송됨 (PID {pid})")
            
            # 최대 5초 대기
            print("   프로세스 종료 대기 중 (최대 5초)...")
            try:
                process.wait(timeout=5)
                print(f"✅ Trader 정상 종료됨 (PID {pid})")
                
                # PID 파일 정리
                if TRADER_PID_FILE.exists():
                    TRADER_PID_FILE.unlink()
                
                return 0
                
            except psutil.TimeoutExpired:
                print(f"⚠️  5초 내 종료 안 됨")
                
                if not force:
                    print("\n강제 종료가 필요합니다.")
                    print("실행: python guard/tools/stop_trader.py --force")
                    return 2
        
        # 3. 강제 종료 (SIGKILL)
        if force:
            print("\n[3/3] 강제 종료 시도...")
            process.kill()
            print(f"   SIGKILL 전송됨 (PID {pid})")
            
            # 2초 대기
            try:
                process.wait(timeout=2)
                print(f"✅ Trader 강제 종료됨 (PID {pid})")
                
                # PID 파일 정리
                if TRADER_PID_FILE.exists():
                    TRADER_PID_FILE.unlink()
                
                return 0
                
            except psutil.TimeoutExpired:
                print(f"❌ 강제 종료 실패 (PID {pid})")
                print("   수동으로 종료가 필요합니다.")
                return 2
        
    except psutil.NoSuchProcess:
        print(f"ℹ️  프로세스가 이미 종료됨 (PID {pid})")
        
        # PID 파일 정리
        if TRADER_PID_FILE.exists():
            TRADER_PID_FILE.unlink()
        
        return 0
        
    except Exception as e:
        print(f"❌ 오류: {e}")
        return 2


def main():
    """메인 함수"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Trader 종료")
    parser.add_argument('--force', action='store_true', help='강제 종료 (SIGKILL)')
    args = parser.parse_args()
    
    try:
        exit_code = stop_trader(force=args.force)
        sys.exit(exit_code)
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

