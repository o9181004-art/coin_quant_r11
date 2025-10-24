#!/usr/bin/env python3
"""
포트 관리 시스템
포트 충돌 감지, 동적 포트 할당, 서비스 상태 모니터링
"""

import json
import socket
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class PortManager:
    """포트 관리 시스템"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.port_config_file = self.project_root / "shared_data" / "port_config.json"
        self.default_ports = {
            "dashboard": 8502,
            "main_app": 8501,
            "readonly_ui": 8503,
            "feeder_service": 8504
        }
    
    def is_port_available(self, port: int) -> bool:
        """포트 사용 가능 여부 확인"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                result = sock.connect_ex(('localhost', port))
                return result != 0
        except Exception:
            return False
    
    def find_process_using_port(self, port: int) -> Optional[int]:
        """포트를 사용하는 프로세스 PID 찾기"""
        try:
            if hasattr(subprocess, 'run'):
                # Windows
                result = subprocess.run(
                    f'netstat -ano | findstr :{port}',
                    shell=True, capture_output=True, text=True
                )
                if result.returncode == 0 and result.stdout:
                    lines = result.stdout.strip().split('\n')
                    for line in lines:
                        if f':{port}' in line:
                            parts = line.split()
                            if len(parts) >= 5:
                                return int(parts[-1])
            return None
        except Exception:
            return None
    
    def kill_process_on_port(self, port: int) -> bool:
        """포트를 사용하는 프로세스 종료"""
        try:
            pid = self.find_process_using_port(port)
            if pid:
                subprocess.run(f'taskkill /PID {pid} /F', shell=True, capture_output=True)
                time.sleep(1)  # 프로세스 종료 대기
                return True
            return False
        except Exception:
            return False
    
    def get_available_port(self, preferred_port: int, max_attempts: int = 10) -> int:
        """사용 가능한 포트 찾기 (선호 포트부터 시작)"""
        for port in range(preferred_port, preferred_port + max_attempts):
            if self.is_port_available(port):
                return port
        
        # 선호 포트 범위에서 찾지 못하면 다른 범위에서 찾기
        for port in range(8500, 8600):
            if self.is_port_available(port):
                return port
        
        raise RuntimeError(f"사용 가능한 포트를 찾을 수 없습니다 (시도 범위: {preferred_port}-{preferred_port + max_attempts})")
    
    def allocate_port(self, service_name: str, force_kill: bool = False) -> int:
        """서비스용 포트 할당"""
        preferred_port = self.default_ports.get(service_name, 8500)
        
        # 기존 포트 사용 중인지 확인
        if not self.is_port_available(preferred_port):
            if force_kill:
                self.kill_process_on_port(preferred_port)
                time.sleep(1)
            else:
                # 다른 포트 찾기
                preferred_port = self.get_available_port(preferred_port + 1)
        
        # 포트 할당 정보 저장
        self._save_port_allocation(service_name, preferred_port)
        return preferred_port
    
    def _save_port_allocation(self, service_name: str, port: int):
        """포트 할당 정보 저장"""
        try:
            # shared_data 디렉토리 생성
            self.port_config_file.parent.mkdir(exist_ok=True)
            
            # 기존 설정 로드
            port_config = {}
            if self.port_config_file.exists():
                with open(self.port_config_file, 'r', encoding='utf-8') as f:
                    port_config = json.load(f)
            
            # 새 포트 정보 추가
            port_config[service_name] = {
                "port": port,
                "allocated_at": time.time(),
                "status": "allocated"
            }
            
            # 설정 저장
            with open(self.port_config_file, 'w', encoding='utf-8') as f:
                json.dump(port_config, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            print(f"포트 설정 저장 실패: {e}")
    
    def release_port(self, service_name: str):
        """포트 할당 해제"""
        try:
            if self.port_config_file.exists():
                with open(self.port_config_file, 'r', encoding='utf-8') as f:
                    port_config = json.load(f)
                
                if service_name in port_config:
                    port_config[service_name]["status"] = "released"
                    
                    with open(self.port_config_file, 'w', encoding='utf-8') as f:
                        json.dump(port_config, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
    
    def get_port_status(self) -> Dict[str, Dict]:
        """모든 포트 상태 조회"""
        try:
            if self.port_config_file.exists():
                with open(self.port_config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception:
            return {}
    
    def cleanup_stale_ports(self):
        """사용하지 않는 포트 정리"""
        try:
            port_status = self.get_port_status()
            current_time = time.time()
            
            for service_name, info in port_status.items():
                if info.get("status") == "allocated":
                    port = info.get("port")
                    allocated_at = info.get("allocated_at", 0)
                    
                    # 30분 이상 할당된 포트 중 사용하지 않는 것 정리
                    if current_time - allocated_at > 1800 and self.is_port_available(port):
                        self.release_port(service_name)
                        print(f"사용하지 않는 포트 정리: {service_name}:{port}")
        except Exception as e:
            print(f"포트 정리 실패: {e}")
    
    def get_service_url(self, service_name: str) -> str:
        """서비스 URL 반환"""
        port_status = self.get_port_status()
        if service_name in port_status:
            port = port_status[service_name].get("port")
            if port and not self.is_port_available(port):
                return f"http://localhost:{port}"
        return ""


# 전역 인스턴스
port_manager = PortManager()


def get_port_manager() -> PortManager:
    """포트 관리자 싱글톤 반환"""
    return port_manager

