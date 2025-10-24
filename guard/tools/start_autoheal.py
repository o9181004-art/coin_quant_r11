#!/usr/bin/env python3
"""
Auto-Heal Service Launcher
자동 복구 서비스를 독립 프로세스로 실행
"""
import json
import os
import pathlib
import subprocess
import sys
import time

REPO_ROOT = pathlib.Path(__file__).parent.parent.parent.resolve()
SHARED_DATA_DIR = REPO_ROOT / "shared_data"
LOGS_DIR = REPO_ROOT / "logs"

AUTOHEAL_PID_FILE = SHARED_DATA_DIR / "autoheal.pid"
AUTOHEAL_LOG_FILE = LOGS_DIR / "autoheal.log"

# 헬스 매니저 import
sys.path.insert(0, str(REPO_ROOT))

# Phase 0: Environment validation
from shared.env_guards import get_absolute_path, validate_environment
from shared.health_manager import update_component
# Phase 1: PID lock enforcement
from shared.pid_lock import PIDLock


def check_venv_python():
    """venv Python 경로 확인"""
    venv_paths = [
        REPO_ROOT / "venv" / "Scripts" / "python.exe",
        REPO_ROOT / ".venv" / "Scripts" / "python.exe",
    ]
    
    for path in venv_paths:
        if path.exists():
            return str(path)
    
    return None


def is_pid_alive(pid: int) -> bool:
    """PID 생존 확인"""
    try:
        import psutil
        return psutil.pid_exists(pid) and psutil.Process(pid).is_running()
    except:
        return False


def check_existing_autoheal():
    """기존 Auto-Heal 프로세스 확인"""
    if not AUTOHEAL_PID_FILE.exists():
        return None
    
    try:
        pid = int(AUTOHEAL_PID_FILE.read_text().strip())
        if is_pid_alive(pid):
            return pid
        else:
            AUTOHEAL_PID_FILE.unlink()
            return None
    except:
        return None


def launch_autoheal():
    """Auto-Heal 시작"""
    print("=" * 70)
    print("🔧 Auto-Heal Launcher")
    print("=" * 70)
    
    # 1. 기존 프로세스 확인
    existing_pid = check_existing_autoheal()
    if existing_pid:
        print(f"\n✅ Auto-Heal 이미 실행 중 (PID: {existing_pid})")
        return 2
    
    # 2. venv Python 확인
    venv_python = check_venv_python()
    if not venv_python:
        print("\n❌ venv Python을 찾을 수 없습니다.")
        return 1
    
    # 3. Auto-Heal 스크립트 확인
    autoheal_script = REPO_ROOT / "services" / "auto_heal_service.py"
    if not autoheal_script.exists():
        print(f"\n❌ Auto-Heal 스크립트 없음: {autoheal_script}")
        return 1
    
    # 4. 실행
    print(f"\n▶️  Auto-Heal 시작...")
    print(f"   Python: {venv_python}")
    print(f"   Script: {autoheal_script}")
    
    try:
        # Windows flags
        CREATE_NO_WINDOW = 0x08000000
        DETACHED_PROCESS = 0x00000008
        
        # 로그 파일
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        log_handle = open(AUTOHEAL_LOG_FILE, 'a', encoding='utf-8')
        
        # Init banner
        log_handle.write("\n" + "=" * 70 + "\n")
        log_handle.write(f"Auto-Heal 시작: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        log_handle.write("=" * 70 + "\n")
        log_handle.flush()
        
        # Detached 실행
        process = subprocess.Popen(
            [venv_python, str(autoheal_script)],
            cwd=str(REPO_ROOT),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS if sys.platform == 'win32' else 0,
            start_new_session=True if sys.platform != 'win32' else False,
        )
        
        pid = process.pid
        
        # PID 파일 저장
        AUTOHEAL_PID_FILE.write_text(str(pid))
        
        log_handle.write(f"PID: {pid}\n")
        log_handle.flush()
        log_handle.close()
        
        print(f"\n✅ Auto-Heal 시작 완료!")
        print(f"   PID: {pid}")
        print(f"   로그: {AUTOHEAL_LOG_FILE}")
        
        # 헬스 상태 업데이트 (GREEN)
        update_component("autoheal", "GREEN", {
            "last_action": time.time(),
            "restart_count": 0,
            "state": "MONITORING",
            "watchdog_active": True
        })
        
        return 0
    
    except Exception as e:
        print(f"\n❌ 오류: {e}")
        
        # 헬스 상태 업데이트 (RED)
        update_component("autoheal", "RED", {
            "last_action": time.time(),
            "restart_count": 0,
            "state": "ERROR",
            "watchdog_active": False
        })
        
        return 1


def main():
    # Phase 0: Environment validation
    validate_environment("autoheal")
    
    # Phase 1: PID lock enforcement
    with PIDLock("autoheal"):
        try:
            exit_code = launch_autoheal()
            sys.exit(exit_code)
        except Exception as e:
            print(f"❌ 오류: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()

