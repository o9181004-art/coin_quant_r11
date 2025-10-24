#!/usr/bin/env python3
"""
Trader Detached Launcher
완전 독립적인 백그라운드 프로세스로 Trader 실행
"""
import json
import os
import pathlib
import subprocess
import sys
import time
from typing import Optional

# 프로젝트 루트 경로
REPO_ROOT = pathlib.Path(__file__).parent.parent.parent.resolve()

# SSOT 경로
SHARED_DATA_DIR = REPO_ROOT / "shared_data"
LOGS_DIR = REPO_ROOT / "logs"

# PID 및 로그 파일
TRADER_PID_FILE = SHARED_DATA_DIR / "trader.pid"
TRADER_LOG_FILE = LOGS_DIR / "trader.log"
TRADER_HEALTH_FILE = SHARED_DATA_DIR / "trader_healthbeat.json"

# Cooldown 시간 (초)
LAUNCH_COOLDOWN = 5


def check_venv_python() -> Optional[str]:
    """
    프로젝트 venv Python 경로 확인 (통일된 우선순위)
    
    Priority: .venv → venv → current
    
    Returns:
        Python 경로
    """
    venv_python_paths = [
        REPO_ROOT / ".venv" / "Scripts" / "python.exe",     # Windows (.venv) - 우선
        REPO_ROOT / "venv" / "Scripts" / "python.exe",      # Windows (venv)
        REPO_ROOT / ".venv" / "bin" / "python",             # Unix (.venv)
        REPO_ROOT / "venv" / "bin" / "python",              # Unix (venv)
    ]
    
    for path in venv_python_paths:
        if path.exists():
            print(f"   Python 발견: {path}")
            return str(path)
    
    # Fallback: current Python
    import sys
    current_python = sys.executable
    print(f"   Fallback: {current_python}")
    return current_python


def is_pid_alive(pid: int) -> bool:
    """PID가 살아있는지 확인"""
    try:
        import psutil
        return psutil.pid_exists(pid) and psutil.Process(pid).is_running()
    except:
        # psutil 없으면 기본 체크
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False


def check_existing_trader() -> Optional[dict]:
    """
    기존 Trader 프로세스 확인
    
    Returns:
        dict: 이미 실행 중이면 PID 정보 반환
        None: 실행 중이 아님
    """
    if not TRADER_PID_FILE.exists():
        return None
    
    try:
        with open(TRADER_PID_FILE, 'r', encoding='utf-8') as f:
            pid_data = json.load(f)
        
        pid = pid_data.get('pid')
        if not pid:
            # 잘못된 PID 파일
            TRADER_PID_FILE.unlink()
            return None
        
        # PID 살아있는지 확인
        if is_pid_alive(pid):
            # Cooldown 체크
            started_at = pid_data.get('started_at', 0)
            age = time.time() - started_at
            
            if age < LAUNCH_COOLDOWN:
                return {
                    "status": "cooldown",
                    "pid": pid,
                    "remaining": LAUNCH_COOLDOWN - age
                }
            
            return {
                "status": "running",
                "pid": pid,
                "started_at": started_at,
                "cmdline": pid_data.get('cmdline', '')
            }
        else:
            # Stale PID - 정리
            print(f"[Cleanup] Stale PID {pid} 제거")
            TRADER_PID_FILE.unlink()
            return None
            
    except Exception as e:
        print(f"[Error] PID 파일 읽기 실패: {e}")
        return None


def launch_trader() -> int:
    """
    Trader를 Detached 프로세스로 실행
    
    Returns:
        0: 성공
        1: 실패
        2: 이미 실행 중
    """
    print("=" * 70)
    print("🚀 Trader Detached Launcher")
    print("=" * 70)
    
    # 1. 기존 Trader 확인
    existing = check_existing_trader()
    if existing:
        if existing['status'] == 'cooldown':
            print(f"⏱️  Cooldown 중: {existing['remaining']:.1f}초 남음")
            return 2
        elif existing['status'] == 'running':
            print(f"✅ Trader 이미 실행 중 (PID: {existing['pid']})")
            return 2
    
    # 2. venv Python 확인
    print("\n[1/5] venv Python 확인...")
    venv_python = check_venv_python()
    
    if not venv_python:
        print("❌ 오류: venv Python을 찾을 수 없습니다.")
        print(f"   확인: {REPO_ROOT}/venv/Scripts/python.exe")
        return 1
    
    print(f"✅ venv Python: {venv_python}")
    
    # 3. Trader 스크립트 확인
    print("\n[2/5] Trader 스크립트 확인...")
    trader_script = REPO_ROOT / "services" / "trader_service.py"
    
    if not trader_script.exists():
        print(f"❌ 오류: Trader 스크립트를 찾을 수 없습니다.")
        print(f"   확인: {trader_script}")
        return 1
    
    print(f"✅ Trader 스크립트: {trader_script}")
    
    # 4. 로그 디렉토리 생성
    print("\n[3/5] 로그 디렉토리 생성...")
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    SHARED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"✅ 로그: {TRADER_LOG_FILE}")
    
    # 5. Detached 프로세스로 실행
    print("\n[4/5] Trader 시작...")
    
    try:
        # Windows 전용 플래그
        CREATE_NO_WINDOW = 0x08000000
        DETACHED_PROCESS = 0x00000008
        
        # 로그 파일 열기 (append)
        log_handle = open(TRADER_LOG_FILE, 'a', encoding='utf-8')
        
        # Init banner 작성
        log_handle.write("\n" + "=" * 70 + "\n")
        log_handle.write(f"Trader 시작: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        log_handle.write(f"PID: [launching...]\n")
        log_handle.write("=" * 70 + "\n")
        log_handle.flush()
        
        # Detached 프로세스 실행
        process = subprocess.Popen(
            [venv_python, str(trader_script)],
            cwd=str(REPO_ROOT),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS if sys.platform == 'win32' else 0,
            start_new_session=True if sys.platform != 'win32' else False,
        )
        
        pid = process.pid
        
        # PID 파일 생성
        pid_data = {
            "pid": pid,
            "started_at": time.time(),
            "cmdline": f"{venv_python} {trader_script}",
            "python_path": venv_python,  # Python 경로 저장
            "cwd": str(REPO_ROOT),
            "log_file": str(TRADER_LOG_FILE)
        }
        
        with open(TRADER_PID_FILE, 'w', encoding='utf-8') as f:
            json.dump(pid_data, f, ensure_ascii=False, indent=2)
        
        # PID를 로그에 기록
        log_handle.write(f"PID: {pid}\n")
        log_handle.write(f"Detached: True\n")
        log_handle.flush()
        log_handle.close()
        
        print(f"✅ Trader 시작 성공!")
        print(f"   PID: {pid}")
        print(f"   로그: {TRADER_LOG_FILE}")
        print(f"   상태: {TRADER_PID_FILE}")
        
        # 5. 초기 health 파일 생성
        print("\n[5/5] Health 파일 생성...")
        health_data = {
            "pid": pid,
            "started_at": time.time(),
            "last_heartbeat": time.time(),
            "status": "STARTING"
        }
        
        with open(TRADER_HEALTH_FILE, 'w', encoding='utf-8') as f:
            json.dump(health_data, f, ensure_ascii=False, indent=2)
        
        print(f"✅ Health: {TRADER_HEALTH_FILE}")
        
        print("\n" + "=" * 70)
        print("🎉 Trader 실행 완료!")
        print(f"   PID {pid}가 백그라운드에서 실행 중입니다.")
        print(f"   로그 확인: tail -f {TRADER_LOG_FILE}")
        print("=" * 70)
        
        return 0
        
    except Exception as e:
        print(f"\n❌ 오류: Trader 실행 실패")
        print(f"   상세: {e}")
        
        # 로그에 오류 기록
        try:
            with open(TRADER_LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(f"\n[ERROR] Trader 실행 실패: {e}\n")
        except:
            pass
        
        return 1


def main():
    """메인 함수"""
    try:
        exit_code = launch_trader()
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

