#!/usr/bin/env python3
"""
Environment Guardrails - Phase 0
One-true interpreter & CWD validation, absolute paths centralization, PID-lock discipline
"""

import os
import sys
import time
import uuid
from pathlib import Path
from typing import Dict, Optional, Tuple


class EnvironmentGuardrails:
    """환경 가드레일 시스템"""
    
    def __init__(self):
        self.repo_root = Path(__file__).parent.parent.absolute()
        self.venv_python = self.repo_root / "venv" / "Scripts" / "python.exe"
        
        # 중앙화된 절대 경로들
        self.paths = {
            "repo_root": self.repo_root,
            "venv_python": self.venv_python,
            "shared_data": self.repo_root / "shared_data",
            "logs": self.repo_root / "logs",
            "shared_data_pids": self.repo_root / "shared_data" / "pids",
            "shared_data_ops": self.repo_root / "shared_data" / "ops",
            "shared_data_alerts": self.repo_root / "shared_data" / "alerts",
            "shared_data_reports": self.repo_root / "shared_data" / "reports",
            "config": self.repo_root / "config",
        }
        
        # 필수 디렉토리들
        self.required_dirs = [
            "shared_data", "logs", "shared_data_pids", 
            "shared_data_ops", "shared_data_alerts", "shared_data_reports"
        ]
        
        self._validate_and_setup()
    
    def _validate_and_setup(self):
        """환경 검증 및 설정"""
        print("🔒 Environment Guardrails - 검증 시작")
        print("=" * 60)
        
        # 1. One-true interpreter 검증
        self._validate_python_interpreter()
        
        # 2. CWD 검증
        self._validate_working_directory()
        
        # 3. 절대 경로 출력
        self._print_absolute_paths()
        
        # 4. 필수 디렉토리 생성
        self._ensure_required_directories()
        
        print("✅ Environment Guardrails 검증 완료")
        print("=" * 60)
    
    def _validate_python_interpreter(self):
        """Python 인터프리터 검증"""
        current_python = sys.executable
        expected_python = str(self.venv_python)
        
        print(f"🐍 Python 인터프리터 검증:")
        print(f"   현재: {current_python}")
        print(f"   기대: {expected_python}")
        
        if current_python.lower() != expected_python.lower():
            error_msg = (
                f"❌ 잘못된 Python 인터프리터!\n"
                f"   현재: {current_python}\n"
                f"   기대: {expected_python}\n"
                f"   해결방법: 프로젝트 venv를 활성화하세요\n"
                f"   Windows: venv\\Scripts\\activate.bat"
            )
            print(error_msg)
            sys.exit(1)
        
        if not self.venv_python.exists():
            error_msg = (
                f"❌ 가상환경 Python을 찾을 수 없습니다!\n"
                f"   경로: {expected_python}\n"
                f"   해결방법: venv를 다시 생성하세요\n"
                f"   python -m venv venv"
            )
            print(error_msg)
            sys.exit(1)
        
        print("   ✅ 올바른 Python 인터프리터 확인")
    
    def _validate_working_directory(self):
        """작업 디렉토리 검증"""
        current_cwd = Path.cwd().absolute()
        expected_cwd = self.repo_root
        
        print(f"📁 작업 디렉토리 검증:")
        print(f"   현재: {current_cwd}")
        print(f"   기대: {expected_cwd}")
        
        if current_cwd != expected_cwd:
            error_msg = (
                f"❌ 잘못된 작업 디렉토리!\n"
                f"   현재: {current_cwd}\n"
                f"   기대: {expected_cwd}\n"
                f"   해결방법: 프로젝트 루트로 이동하세요\n"
                f"   cd {expected_cwd}"
            )
            print(error_msg)
            sys.exit(1)
        
        print("   ✅ 올바른 작업 디렉토리 확인")
    
    def _print_absolute_paths(self):
        """절대 경로들 출력"""
        print(f"📂 중앙화된 절대 경로들:")
        for name, path in self.paths.items():
            status = "✅" if path.exists() else "❌"
            print(f"   {name}: {path} {status}")
    
    def _ensure_required_directories(self):
        """필수 디렉토리 생성"""
        print(f"📁 필수 디렉토리 확인/생성:")
        
        for dir_name in self.required_dirs:
            dir_path = self.paths[dir_name]
            try:
                dir_path.mkdir(parents=True, exist_ok=True)
                print(f"   {dir_name}: {dir_path} ✅")
            except Exception as e:
                error_msg = (
                    f"❌ 디렉토리 생성 실패!\n"
                    f"   디렉토리: {dir_path}\n"
                    f"   오류: {e}"
                )
                print(error_msg)
                sys.exit(1)
    
    def get_path(self, name: str) -> Path:
        """경로 조회"""
        if name not in self.paths:
            raise ValueError(f"알 수 없는 경로: {name}")
        return self.paths[name]
    
    def get_pid_file_path(self, service_name: str) -> Path:
        """서비스 PID 파일 경로 조회"""
        return self.paths["shared_data_pids"] / f"{service_name}.pid"
    
    def check_pid_lock(self, service_name: str) -> Tuple[bool, Optional[int]]:
        """PID 락 확인"""
        pid_file = self.get_pid_file_path(service_name)
        
        if not pid_file.exists():
            return False, None
        
        try:
            pid = int(pid_file.read_text().strip())
            
            # Windows에서 프로세스 존재 확인
            try:
                import psutil
                if psutil.pid_exists(pid):
                    # 프로세스가 실제로 해당 서비스인지 확인
                    try:
                        process = psutil.Process(pid)
                        cmdline = " ".join(process.cmdline())
                        if service_name in cmdline:
                            return True, pid
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                
                # 스테일 PID 파일 정리
                pid_file.unlink(missing_ok=True)
                return False, None
                
            except ImportError:
                # psutil이 없으면 PID 파일만으로 판단 (Windows 기본)
                try:
                    os.kill(pid, 0)  # 프로세스 존재 확인
                    return True, pid
                except (OSError, ProcessLookupError):
                    # 스테일 PID 파일 정리
                    pid_file.unlink(missing_ok=True)
                    return False, None
                    
        except (ValueError, FileNotFoundError):
            return False, None
    
    def create_pid_lock(self, service_name: str) -> bool:
        """PID 락 생성"""
        pid_file = self.get_pid_file_path(service_name)
        
        # 기존 PID 락 확인
        is_locked, existing_pid = self.check_pid_lock(service_name)
        if is_locked:
            print(f"❌ {service_name} 서비스가 이미 실행 중입니다 (PID: {existing_pid})")
            return False
        
        try:
            # PID 파일 생성
            pid_file.write_text(str(os.getpid()))
            print(f"✅ {service_name} PID 락 생성: {pid_file}")
            return True
        except Exception as e:
            print(f"❌ {service_name} PID 락 생성 실패: {e}")
            return False
    
    def remove_pid_lock(self, service_name: str):
        """PID 락 제거"""
        pid_file = self.get_pid_file_path(service_name)
        try:
            pid_file.unlink(missing_ok=True)
            print(f"✅ {service_name} PID 락 제거: {pid_file}")
        except Exception as e:
            print(f"⚠️ {service_name} PID 락 제거 실패: {e}")


# 전역 인스턴스
guardrails = EnvironmentGuardrails()


def validate_environment():
    """환경 검증 (다른 모듈에서 import 시 자동 실행)"""
    return guardrails


def get_repo_paths() -> Dict[str, Path]:
    """중앙화된 경로들 조회"""
    return guardrails.paths.copy()


def get_pid_file_path(service_name: str) -> Path:
    """서비스 PID 파일 경로 조회"""
    return guardrails.get_pid_file_path(service_name)


def check_service_pid_lock(service_name: str) -> Tuple[bool, Optional[int]]:
    """서비스 PID 락 확인"""
    return guardrails.check_pid_lock(service_name)


def create_service_pid_lock(service_name: str) -> bool:
    """서비스 PID 락 생성"""
    return guardrails.create_pid_lock(service_name)


def remove_service_pid_lock(service_name: str):
    """서비스 PID 락 제거"""
    guardrails.remove_pid_lock(service_name)


if __name__ == "__main__":
    # 직접 실행 시 환경 검증만 수행
    print("🔒 Environment Guardrails - 독립 실행")
    guardrails = EnvironmentGuardrails()
    
    # PID 락 테스트
    print("\n🔒 PID 락 테스트:")
    test_services = ["feeder", "trader", "autoheal"]
    
    for service in test_services:
        is_locked, pid = check_service_pid_lock(service)
        status = f"실행 중 (PID: {pid})" if is_locked else "중지됨"
        print(f"   {service}: {status}")
