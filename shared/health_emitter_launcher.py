#!/usr/bin/env python3
"""
HealthEmitter Launcher with Single Instance Guard
"""

import os
import sys
import time
from pathlib import Path

import psutil

from .health_emitter import HealthEmitter


class HealthEmitterLauncher:
    """HealthEmitter 런처"""
    
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root.resolve()
        self.runtime_dir = self.repo_root / ".runtime"
        self.runtime_dir.mkdir(exist_ok=True)
        self.pid_file = self.runtime_dir / "health_emitter.pid"
    
    def check_existing_instance(self) -> bool:
        """기존 인스턴스 확인"""
        if not self.pid_file.exists():
            return False
        
        try:
            with open(self.pid_file, 'r') as f:
                pid = int(f.read().strip())
            
            if psutil.pid_exists(pid):
                print(f"❌ HealthEmitter already running (PID: {pid})")
                return True
            else:
                # 죽은 PID 파일 정리
                self.pid_file.unlink()
                return False
                
        except Exception:
            # 손상된 PID 파일 정리
            self.pid_file.unlink()
            return False
    
    def start_health_emitter(self, dry_run: bool = False) -> bool:
        """HealthEmitter 시작"""
        if self.check_existing_instance():
            return False
        
        try:
            # HealthEmitter 실행
            emitter = HealthEmitter(self.repo_root, dry_run)
            return emitter.run() == 0
            
        except Exception as e:
            print(f"❌ Failed to start HealthEmitter: {e}")
            return False
    
    def stop_health_emitter(self) -> bool:
        """HealthEmitter 중지"""
        if not self.pid_file.exists():
            print("⚠️ HealthEmitter PID file not found")
            return False
        
        try:
            with open(self.pid_file, 'r') as f:
                pid = int(f.read().strip())
            
            if psutil.pid_exists(pid):
                process = psutil.Process(pid)
                process.terminate()
                
                # 프로세스 종료 대기
                try:
                    process.wait(timeout=5)
                except psutil.TimeoutExpired:
                    process.kill()
                
                print(f"✅ HealthEmitter stopped (PID: {pid})")
                return True
            else:
                print("⚠️ HealthEmitter process not running")
                self.pid_file.unlink()
                return False
                
        except Exception as e:
            print(f"❌ Failed to stop HealthEmitter: {e}")
            return False
    
    def get_status(self) -> dict:
        """상태 조회"""
        status = {
            "running": False,
            "pid": None,
            "pid_file_exists": self.pid_file.exists()
        }
        
        if self.pid_file.exists():
            try:
                with open(self.pid_file, 'r') as f:
                    pid = int(f.read().strip())
                
                if psutil.pid_exists(pid):
                    status["running"] = True
                    status["pid"] = pid
                else:
                    # 죽은 PID 파일 정리
                    self.pid_file.unlink()
                    
            except Exception:
                # 손상된 PID 파일 정리
                self.pid_file.unlink()
        
        return status


def main():
    """메인 함수"""
    import argparse
    
    parser = argparse.ArgumentParser(description="HealthEmitter Launcher")
    parser.add_argument("--start", action="store_true", help="Start HealthEmitter")
    parser.add_argument("--stop", action="store_true", help="Stop HealthEmitter")
    parser.add_argument("--status", action="store_true", help="Check status")
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode")
    
    args = parser.parse_args()
    
    # 프로젝트 루트 자동 감지
    current_file = Path(__file__).resolve()
    for parent in current_file.parents:
        if (parent / "shared").exists() and (parent / "guard").exists():
            repo_root = parent
            break
    else:
        print("❌ Could not find project root")
        return 1
    
    launcher = HealthEmitterLauncher(repo_root)
    
    if args.status:
        status = launcher.get_status()
        if status["running"]:
            print(f"🟢 HealthEmitter is running (PID: {status['pid']})")
        else:
            print("🔴 HealthEmitter is not running")
        return 0
    
    elif args.start:
        if launcher.start_health_emitter(args.dry_run):
            print("✅ HealthEmitter started successfully")
            return 0
        else:
            print("❌ Failed to start HealthEmitter")
            return 1
    
    elif args.stop:
        if launcher.stop_health_emitter():
            return 0
        else:
            return 1
    
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
