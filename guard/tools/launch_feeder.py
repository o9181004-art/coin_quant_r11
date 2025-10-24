#!/usr/bin/env python3
"""
Feeder Detached Launcher
완전 독립적인 백그라운드 프로세스로 Feeder 실행
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
FEEDER_PID_FILE = SHARED_DATA_DIR / "feeder.pid"
FEEDER_LOG_FILE = LOGS_DIR / "feeder.log"

# Cooldown 시간 (초)
LAUNCH_COOLDOWN = 5


def check_venv_python() -> Optional[str]:
    """프로젝트 venv Python 경로 확인"""
    venv_python_paths = [
        REPO_ROOT / "venv" / "Scripts" / "python.exe",
        REPO_ROOT / ".venv" / "Scripts" / "python.exe",
        REPO_ROOT / "venv" / "bin" / "python",
        REPO_ROOT / ".venv" / "bin" / "python",
    ]
    
    for path in venv_python_paths:
        if path.exists():
            return str(path)
    
    return None


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


def check_existing_feeder() -> Optional[dict]:
    """기존 Feeder 프로세스 확인"""
    if not FEEDER_PID_FILE.exists():
        return None
    
    try:
        with open(FEEDER_PID_FILE, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            # JSON 또는 plain text 지원
            try:
                pid_data = json.loads(content)
                pid = pid_data.get('pid') if isinstance(pid_data, dict) else int(content)
            except json.JSONDecodeError:
                pid = int(content)
        
        if is_pid_alive(pid):
            return {
                "status": "running",
                "pid": pid
            }
        else:
            # Stale PID
            FEEDER_PID_FILE.unlink()
            return None
    
    except Exception:
        return None


def launch_feeder() -> int:
    """Feeder를 Detached 프로세스로 실행"""
    print("=" * 70)
    print("🚀 Feeder 런처")
    print("=" * 70)
    
    # 1. 기존 Feeder 확인
    existing = check_existing_feeder()
    if existing:
        print(f"\n✅ Feeder 이미 실행 중 (PID: {existing['pid']})")
        return 2
    
    # 2. venv Python 확인
    venv_python = check_venv_python()
    if not venv_python:
        print("\n❌ venv Python을 찾을 수 없습니다.")
        return 1
    
    # 3. Feeder 스크립트
    feeder_script = REPO_ROOT / "services" / "feeder_service.py"
    if not feeder_script.exists():
        print(f"\n❌ Feeder 스크립트 없음: {feeder_script}")
        return 1
    
    # 4. 실행
    print(f"\n▶️  Feeder 시작 중...")
    print(f"   Python: {venv_python}")
    print(f"   Script: {feeder_script}")
    
    try:
        # Windows flags
        CREATE_NO_WINDOW = 0x08000000
        DETACHED_PROCESS = 0x00000008
        
        # 로그 파일
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        log_handle = open(FEEDER_LOG_FILE, 'a', encoding='utf-8')
        
        # Detached 실행
        process = subprocess.Popen(
            [venv_python, str(feeder_script)],
            cwd=str(REPO_ROOT),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS if sys.platform == 'win32' else 0,
            start_new_session=True if sys.platform != 'win32' else False,
        )
        
        pid = process.pid
        
        # PID 파일 생성 (plain text)
        SHARED_DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(FEEDER_PID_FILE, 'w') as f:
            f.write(str(pid))
        
        log_handle.close()
        
        print(f"\n✅ Feeder 시작 완료!")
        print(f"   PID: {pid}")
        print(f"\n📊 상태 확인: python guard/tools/healthcheck_recover.py")
        
        return 0
    
    except Exception as e:
        print(f"\n❌ 오류: {e}")
        return 1


def main():
    try:
        exit_code = launch_feeder()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⚠️  중단됨")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 오류: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
