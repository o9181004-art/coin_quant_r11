#!/usr/bin/env python3
"""
Single-Root Service Launcher
Starts all services bound to the same root as the Enhanced Dashboard
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import psutil

from .centralized_path_registry import get_path_registry


class ServiceLauncher:
    """단일 루트 서비스 런처"""
    
    def __init__(self, repo_root: Path, venv_python: Path):
        self.repo_root = repo_root.resolve()
        self.venv_python = venv_python.resolve()
        self.path_registry = get_path_registry(self.repo_root)
        self.runtime_dir = self.repo_root / ".runtime"
        self.runtime_dir.mkdir(exist_ok=True)
        
        # 서비스 정의
        self.services = {
            "feeder": {
                "module": "guard.feeder",
                "health_file": "health_feeder",
                "heartbeat_interval": 30,
                "threshold": 60
            },
            "trader": {
                "module": "guard.trader", 
                "health_file": "health_trader",
                "heartbeat_interval": 60,
                "threshold": 300
            },
            "ares": {
                "module": "guard.ares",
                "health_file": "health_ares", 
                "heartbeat_interval": 30,
                "threshold": 75
            },
            "autoheal": {
                "module": "guard.autoheal",
                "health_file": "health_autoheal",
                "heartbeat_interval": 120,
                "threshold": 300
            }
        }
        
        self.running_services: Dict[str, subprocess.Popen] = {}
    
    def print_banner(self):
        """시작 배너 출력"""
        print("=" * 80)
        print("🚀 코인퀀트 Single-Root Service Launcher")
        print("=" * 80)
        print(f"REPO_ROOT: {self.repo_root}")
        print(f"VENV_PY: {self.venv_python}")
        print(f"RUNTIME_DIR: {self.runtime_dir}")
        print("=" * 80)
    
    def check_existing_services(self) -> Dict[str, bool]:
        """기존 서비스 확인"""
        existing = {}
        for service_name in self.services.keys():
            pid_file = self.runtime_dir / f"{service_name}.pid"
            if pid_file.exists():
                try:
                    with open(pid_file, 'r') as f:
                        pid = int(f.read().strip())
                    
                    if psutil.pid_exists(pid):
                        existing[service_name] = True
                        print(f"⚠️  {service_name} already running (PID: {pid})")
                    else:
                        # 죽은 PID 파일 정리
                        pid_file.unlink()
                        existing[service_name] = False
                except Exception:
                    # 손상된 PID 파일 정리
                    pid_file.unlink()
                    existing[service_name] = False
            else:
                existing[service_name] = False
        
        return existing
    
    def start_service(self, service_name: str, force: bool = False) -> Tuple[bool, str]:
        """개별 서비스 시작"""
        if service_name not in self.services:
            return False, f"Unknown service: {service_name}"
        
        service_config = self.services[service_name]
        pid_file = self.runtime_dir / f"{service_name}.pid"
        
        # 기존 서비스 확인
        if pid_file.exists() and not force:
            try:
                with open(pid_file, 'r') as f:
                    pid = int(f.read().strip())
                if psutil.pid_exists(pid):
                    return False, f"Service {service_name} already running (PID: {pid})"
            except Exception:
                pass
        
        # 서비스 시작
        try:
            cmd = [
                str(self.venv_python),
                "-m", service_config["module"],
                "--mode", "TESTNET"
            ]
            
            # 환경 변수 설정
            env = os.environ.copy()
            env['COIN_QUANT_REPO_ROOT'] = str(self.repo_root)
            env['SERVICE_NAME'] = service_name
            
            # 서비스 시작
            process = subprocess.Popen(
                cmd,
                cwd=str(self.repo_root),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # PID 파일 작성
            with open(pid_file, 'w') as f:
                f.write(str(process.pid))
            
            # 헬스 파일 경로 출력
            health_path = self.path_registry.get(service_config["health_file"])
            print(f"SERVICE={service_name} ROOT={self.repo_root} VENV_PY={self.venv_python} OUT={health_path}")
            
            self.running_services[service_name] = process
            return True, f"Service {service_name} started (PID: {process.pid})"
            
        except Exception as e:
            return False, f"Failed to start {service_name}: {e}"
    
    def stop_service(self, service_name: str) -> Tuple[bool, str]:
        """개별 서비스 중지"""
        if service_name in self.running_services:
            process = self.running_services[service_name]
            try:
                process.terminate()
                process.wait(timeout=5)
                del self.running_services[service_name]
                
                # PID 파일 정리
                pid_file = self.runtime_dir / f"{service_name}.pid"
                if pid_file.exists():
                    pid_file.unlink()
                
                return True, f"Service {service_name} stopped"
            except Exception as e:
                return False, f"Failed to stop {service_name}: {e}"
        else:
            return False, f"Service {service_name} not running"
    
    def start_all_services(self, force: bool = False) -> Dict[str, Tuple[bool, str]]:
        """모든 서비스 시작"""
        results = {}
        existing = self.check_existing_services()
        
        for service_name in self.services.keys():
            if existing.get(service_name, False) and not force:
                results[service_name] = (False, f"Already running")
                continue
            
            success, message = self.start_service(service_name, force)
            results[service_name] = (success, message)
            
            if success:
                print(f"✅ {message}")
            else:
                print(f"❌ {message}")
        
        return results
    
    def stop_all_services(self) -> Dict[str, Tuple[bool, str]]:
        """모든 서비스 중지"""
        results = {}
        
        for service_name in list(self.running_services.keys()):
            success, message = self.stop_service(service_name)
            results[service_name] = (success, message)
            
            if success:
                print(f"✅ {message}")
            else:
                print(f"❌ {message}")
        
        return results
    
    def get_service_status(self) -> Dict[str, Dict]:
        """서비스 상태 조회"""
        status = {}
        
        for service_name in self.services.keys():
            pid_file = self.runtime_dir / f"{service_name}.pid"
            health_file = self.path_registry.get(self.services[service_name]["health_file"])
            
            service_status = {
                "name": service_name,
                "pid_file": str(pid_file),
                "health_file": str(health_file),
                "running": False,
                "pid": None,
                "health_exists": health_file.exists(),
                "health_age": None
            }
            
            if pid_file.exists():
                try:
                    with open(pid_file, 'r') as f:
                        pid = int(f.read().strip())
                    
                    if psutil.pid_exists(pid):
                        service_status["running"] = True
                        service_status["pid"] = pid
                        
                        # 헬스 파일 나이 계산
                        if health_file.exists():
                            mtime = health_file.stat().st_mtime
                            service_status["health_age"] = time.time() - mtime
                except Exception:
                    pass
            
            status[service_name] = service_status
        
        return status
    
    def cleanup(self):
        """정리 작업"""
        self.stop_all_services()
        
        # PID 파일 정리
        for service_name in self.services.keys():
            pid_file = self.runtime_dir / f"{service_name}.pid"
            if pid_file.exists():
                try:
                    pid_file.unlink()
                except Exception:
                    pass


def main():
    """메인 함수"""
    import argparse
    
    parser = argparse.ArgumentParser(description="코인퀀트 서비스 런처")
    parser.add_argument("--start", action="store_true", help="모든 서비스 시작")
    parser.add_argument("--stop", action="store_true", help="모든 서비스 중지")
    parser.add_argument("--status", action="store_true", help="서비스 상태 확인")
    parser.add_argument("--force", action="store_true", help="강제 시작")
    parser.add_argument("--service", help="특정 서비스만 시작/중지")
    
    args = parser.parse_args()
    
    # 프로젝트 루트 및 가상환경 확인
    project_root = Path(__file__).parent.parent
    venv_python = project_root / "venv_fixed" / "Scripts" / "python.exe"
    
    if not venv_python.exists():
        print(f"❌ Virtual environment not found: {venv_python}")
        return 1
    
    launcher = ServiceLauncher(project_root, venv_python)
    launcher.print_banner()
    
    try:
        if args.status:
            status = launcher.get_service_status()
            print("\n📊 Service Status:")
            for service_name, info in status.items():
                status_icon = "🟢" if info["running"] else "🔴"
                age_info = f" (age: {info['health_age']:.1f}s)" if info["health_age"] else ""
                print(f"  {status_icon} {service_name}: PID={info['pid']}, Health={info['health_exists']}{age_info}")
        
        elif args.start:
            if args.service:
                success, message = launcher.start_service(args.service, args.force)
                print(f"{'✅' if success else '❌'} {message}")
            else:
                results = launcher.start_all_services(args.force)
                print(f"\n📊 Start Results:")
                for service_name, (success, message) in results.items():
                    print(f"  {'✅' if success else '❌'} {service_name}: {message}")
        
        elif args.stop:
            if args.service:
                success, message = launcher.stop_service(args.service)
                print(f"{'✅' if success else '❌'} {message}")
            else:
                results = launcher.stop_all_services()
                print(f"\n📊 Stop Results:")
                for service_name, (success, message) in results.items():
                    print(f"  {'✅' if success else '❌'} {service_name}: {message}")
        
        else:
            parser.print_help()
    
    except KeyboardInterrupt:
        print("\n🛑 사용자에 의해 중지됨")
        launcher.cleanup()
    
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
