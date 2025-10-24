#!/usr/bin/env python3
"""
중앙화된 런처 시스템
서비스 실행, 모니터링, 오류 복구 통합 관리
"""

import json
import os
import platform
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .environment_manager import get_environment_manager
from .port_manager import get_port_manager


class ServiceLauncher:
    """서비스 런처 클래스"""
    
    def __init__(self, name: str, command: List[str], working_dir: Optional[Path] = None):
        self.name = name
        self.command = command
        self.working_dir = working_dir or Path.cwd()
        self.process = None
        self.status = "stopped"
        self.start_time = None
        self.port = None
        
    def start(self, background: bool = True) -> bool:
        """서비스 시작"""
        try:
            if self.status == "running":
                return True
                
            self.process = subprocess.Popen(
                self.command,
                cwd=self.working_dir,
                stdout=subprocess.PIPE if background else None,
                stderr=subprocess.PIPE if background else None,
                creationflags=subprocess.CREATE_NEW_CONSOLE if background and os.name == 'nt' else 0
            )
            
            self.status = "running"
            self.start_time = time.time()
            
            if background:
                # 백그라운드 프로세스 모니터링 스레드 시작
                monitor_thread = threading.Thread(target=self._monitor_process, daemon=True)
                monitor_thread.start()
            
            return True
            
        except Exception as e:
            print(f"서비스 {self.name} 시작 실패: {e}")
            self.status = "failed"
            return False
    
    def stop(self) -> bool:
        """서비스 중지"""
        try:
            if self.process and self.process.poll() is None:
                self.process.terminate()
                time.sleep(2)
                if self.process.poll() is None:
                    self.process.kill()
            
            self.status = "stopped"
            self.process = None
            return True
            
        except Exception as e:
            print(f"서비스 {self.name} 중지 실패: {e}")
            return False
    
    def _monitor_process(self):
        """프로세스 모니터링"""
        while self.process and self.process.poll() is None:
            time.sleep(1)
        
        if self.process:
            return_code = self.process.poll()
            if return_code != 0:
                self.status = "failed"
                print(f"서비스 {self.name} 비정상 종료 (코드: {return_code})")
            else:
                self.status = "stopped"
                print(f"서비스 {self.name} 정상 종료")


class LauncherSystem:
    """중앙화된 런처 시스템"""
    
    def __init__(self):
        self.env_manager = get_environment_manager()
        self.port_manager = get_port_manager()
        self.services: Dict[str, ServiceLauncher] = {}
        self.project_root = self.env_manager.project_root
        
    def validate_environment(self) -> Tuple[bool, List[str]]:
        """환경 유효성 검사"""
        return self.env_manager.validate_environment()
    
    def setup_environment(self):
        """환경 설정"""
        self.env_manager.setup_environment_variables()
        self.port_manager.cleanup_stale_ports()
    
    def create_service_launcher(self, service_name: str, config: Dict) -> ServiceLauncher:
        """서비스 런처 생성"""
        # 포트 할당
        port = self.port_manager.allocate_port(service_name, force_kill=True)
        
        # 명령어 구성
        command = config["command"].copy()
        
        # 포트가 명령어에 포함되어 있으면 교체
        for i, arg in enumerate(command):
            if "--server.port" in arg and i + 1 < len(command):
                command[i + 1] = str(port)
            elif ":8501" in arg or ":8502" in arg:
                command[i] = arg.replace(":8501", f":{port}").replace(":8502", f":{port}")
        
        # 가상환경 활성화 명령어 추가
        venv_info = self.env_manager.get_optimal_venv()
        if venv_info and platform.system() == "Windows":
            venv_name, venv_path = venv_info
            activate_script = venv_path / "Scripts" / "activate.bat"
            if activate_script.exists():
                command = [str(activate_script), "&&"] + command
        
        working_dir = self.project_root / config.get("working_dir", "")
        
        launcher = ServiceLauncher(service_name, command, working_dir)
        launcher.port = port
        
        return launcher
    
    def start_service(self, service_name: str, config: Dict, background: bool = True) -> bool:
        """서비스 시작"""
        try:
            if service_name in self.services:
                return self.services[service_name].start(background)
            
            launcher = self.create_service_launcher(service_name, config)
            self.services[service_name] = launcher
            
            success = launcher.start(background)
            if success:
                print(f"✅ 서비스 {service_name} 시작됨 (포트: {launcher.port})")
            else:
                print(f"❌ 서비스 {service_name} 시작 실패")
            
            return success
            
        except Exception as e:
            print(f"서비스 {service_name} 시작 중 오류: {e}")
            return False
    
    def stop_service(self, service_name: str) -> bool:
        """서비스 중지"""
        if service_name in self.services:
            success = self.services[service_name].stop()
            if success:
                self.port_manager.release_port(service_name)
                print(f"✅ 서비스 {service_name} 중지됨")
            return success
        return False
    
    def get_service_status(self, service_name: str) -> Dict:
        """서비스 상태 조회"""
        if service_name in self.services:
            launcher = self.services[service_name]
            return {
                "status": launcher.status,
                "port": launcher.port,
                "start_time": launcher.start_time,
                "url": f"http://localhost:{launcher.port}" if launcher.port else None
            }
        return {"status": "not_found"}
    
    def get_all_services_status(self) -> Dict[str, Dict]:
        """모든 서비스 상태 조회"""
        return {name: self.get_service_status(name) for name in self.services.keys()}
    
    def stop_all_services(self):
        """모든 서비스 중지"""
        for service_name in list(self.services.keys()):
            self.stop_service(service_name)
    
    def launch_dashboard_system(self, mode: str = "full") -> bool:
        """대시보드 시스템 전체 실행"""
        try:
            # 환경 검증
            is_valid, errors = self.validate_environment()
            if not is_valid:
                print("❌ 환경 검증 실패:")
                for error in errors:
                    print(f"  - {error}")
                return False
            
            # 환경 설정
            self.setup_environment()
            
            # 서비스 설정
            services_config = {
                "feeder": {
                    "command": ["python", "services/feeder_service.py"],
                    "working_dir": ""
                },
                "dashboard": {
                    "command": ["python", "-m", "streamlit", "run", "working_dashboard.py", "--server.port", "8502", "--server.headless", "false"],
                    "working_dir": ""
                }
            }
            
            if mode == "simple":
                services_config = {"dashboard": services_config["dashboard"]}
            
            # 서비스 시작
            for service_name, config in services_config.items():
                if not self.start_service(service_name, config, background=True):
                    print(f"❌ {service_name} 서비스 시작 실패")
                    return False
            
            # 브라우저 열기
            dashboard_status = self.get_service_status("dashboard")
            if dashboard_status.get("url"):
                self._open_browser(dashboard_status["url"])
            
            print("✅ 대시보드 시스템 시작 완료")
            return True
            
        except Exception as e:
            print(f"❌ 대시보드 시스템 시작 실패: {e}")
            return False
    
    def _open_browser(self, url: str):
        """브라우저 열기"""
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            print(f"브라우저 자동 열기 실패. 수동으로 {url} 접속하세요.")
    
    def cleanup(self):
        """정리 작업"""
        self.stop_all_services()
        for service_name in list(self.services.keys()):
            self.port_manager.release_port(service_name)


# 전역 인스턴스
launcher_system = LauncherSystem()


def get_launcher_system() -> LauncherSystem:
    """런처 시스템 싱글톤 반환"""
    return launcher_system
