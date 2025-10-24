#!/usr/bin/env python3
"""
UDS Graceful Stop
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent.resolve()
SHARED_DATA_DIR = REPO_ROOT / "shared_data"
UDS_PID_FILE = SHARED_DATA_DIR / "uds.pid"


def stop_uds():
    """UDS 종료"""
    print("=" * 70)
    print("🛑 UDS Stop")
    print("=" * 70)
    
    if not UDS_PID_FILE.exists():
        print("\nℹ️  실행 중인 UDS가 없습니다.")
        return 1
    
    try:
        pid = int(UDS_PID_FILE.read_text().strip())
        
        import psutil
        if not psutil.pid_exists(pid):
            print(f"\nℹ️  UDS 이미 종료됨 (PID: {pid})")
            UDS_PID_FILE.unlink()
            return 0
        
        process = psutil.Process(pid)
        process.terminate()
        print(f"\nSIGTERM 전송 (PID: {pid})")
        
        try:
            process.wait(timeout=5)
            print("✅ UDS 정상 종료")
        except psutil.TimeoutExpired:
            process.kill()
            print("✅ UDS 강제 종료")
        
        UDS_PID_FILE.unlink()
        return 0
    
    except Exception as e:
        print(f"\n❌ 오류: {e}")
        return 1


def main():
    try:
        exit_code = stop_uds()
        sys.exit(exit_code)
    except Exception as e:
        print(f"❌ 오류: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

