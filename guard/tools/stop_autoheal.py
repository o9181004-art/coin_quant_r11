#!/usr/bin/env python3
"""
Auto-Heal Graceful Stop
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent.resolve()
SHARED_DATA_DIR = REPO_ROOT / "shared_data"
AUTOHEAL_PID_FILE = SHARED_DATA_DIR / "autoheal.pid"


def stop_autoheal():
    """Auto-Heal 종료"""
    print("=" * 70)
    print("🛑 Auto-Heal Stop")
    print("=" * 70)
    
    if not AUTOHEAL_PID_FILE.exists():
        print("\nℹ️  실행 중인 Auto-Heal이 없습니다.")
        return 1
    
    try:
        pid = int(AUTOHEAL_PID_FILE.read_text().strip())
        
        import psutil
        if not psutil.pid_exists(pid):
            print(f"\nℹ️  Auto-Heal 이미 종료됨 (PID: {pid})")
            AUTOHEAL_PID_FILE.unlink()
            return 0
        
        process = psutil.Process(pid)
        process.terminate()
        print(f"\nSIGTERM 전송 (PID: {pid})")
        
        try:
            process.wait(timeout=5)
            print("✅ Auto-Heal 정상 종료")
        except psutil.TimeoutExpired:
            process.kill()
            print("✅ Auto-Heal 강제 종료")
        
        AUTOHEAL_PID_FILE.unlink()
        return 0
    
    except Exception as e:
        print(f"\n❌ 오류: {e}")
        return 1


def main():
    try:
        exit_code = stop_autoheal()
        sys.exit(exit_code)
    except Exception as e:
        print(f"❌ 오류: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

