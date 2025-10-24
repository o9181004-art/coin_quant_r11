#!/usr/bin/env python3
"""
UI Single Instance Guard
Prevents multiple Streamlit instances and enforces single root
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

import psutil


class UIInstanceGuard:
    """UI 단일 인스턴스 가드"""
    
    def __init__(self, repo_root: Path, port: int = 8502):
        self.repo_root = repo_root.resolve()
        self.port = port
        self.lock_file = self.repo_root / ".runtime" / "ui.lock"
        self.pid_file = self.repo_root / ".runtime" / "ui.pid"
        self.port_file = self.repo_root / ".runtime" / "ui.port"
        
        # .runtime 디렉토리 생성
        self.lock_file.parent.mkdir(exist_ok=True)
    
    def get_current_instance_info(self) -> Optional[Dict]:
        """현재 실행 중인 인스턴스 정보 조회"""
        if not self.lock_file.exists():
            return None
        
        try:
            with open(self.lock_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # PID가 살아있는지 확인
            if psutil.pid_exists(data.get('pid')):
                return data
            else:
                # 죽은 PID의 락 파일 정리
                self._cleanup_stale_lock()
                return None
                
        except Exception:
            self._cleanup_stale_lock()
            return None
    
    def acquire_lock(self) -> Tuple[bool, Optional[str]]:
        """락 획득 시도"""
        existing = self.get_current_instance_info()
        
        if existing:
            return False, f"Another UI is running at {existing['root']} (PID={existing['pid']})"
        
        # 새 락 생성
        lock_data = {
            'pid': os.getpid(),
            'started_at': time.time(),
            'root': str(self.repo_root),
            'port': self.port
        }
        
        try:
            with open(self.lock_file, 'w', encoding='utf-8') as f:
                json.dump(lock_data, f, indent=2)
            
            # PID와 포트 파일도 생성
            with open(self.pid_file, 'w', encoding='utf-8') as f:
                f.write(str(os.getpid()))
            
            with open(self.port_file, 'w', encoding='utf-8') as f:
                f.write(str(self.port))
            
            return True, None
            
        except Exception as e:
            return False, f"Failed to acquire lock: {e}"
    
    def force_takeover(self) -> Tuple[bool, Optional[str]]:
        """강제 인수"""
        existing = self.get_current_instance_info()
        
        if not existing:
            return self.acquire_lock()
        
        try:
            # 기존 프로세스 종료
            pid = existing['pid']
            if psutil.pid_exists(pid):
                process = psutil.Process(pid)
                process.terminate()
                
                # 종료 대기 (최대 5초)
                try:
                    process.wait(timeout=5)
                except psutil.TimeoutExpired:
                    process.kill()
            
            # 락 파일 정리
            self._cleanup_stale_lock()
            
            # 새 락 획득
            return self.acquire_lock()
            
        except Exception as e:
            return False, f"Failed to takeover: {e}"
    
    def release_lock(self):
        """락 해제"""
        try:
            if self.lock_file.exists():
                self.lock_file.unlink()
            if self.pid_file.exists():
                self.pid_file.unlink()
            if self.port_file.exists():
                self.port_file.unlink()
        except Exception:
            pass
    
    def _cleanup_stale_lock(self):
        """오래된 락 파일 정리"""
        try:
            if self.lock_file.exists():
                self.lock_file.unlink()
            if self.pid_file.exists():
                self.pid_file.unlink()
            if self.port_file.exists():
                self.port_file.unlink()
        except Exception:
            pass
    
    def detect_multiple_roots(self) -> list:
        """다중 루트 감지"""
        possible_roots = []
        
        # 일반적인 루트 경로들 확인
        common_paths = [
            Path.home() / "Desktop" / "coin_quant",
            Path.home() / "Documents" / "coin_quant",
            Path("C:/Users") / "Gil" / "Desktop" / "coin_quant",
            Path("C:/Users") / "LeeSG" / "Desktop" / "coin_quant",
        ]
        
        for path in common_paths:
            if path.exists() and path != self.repo_root:
                # coin_quant 프로젝트인지 확인
                if (path / "shared").exists() and (path / "guard").exists():
                    possible_roots.append(str(path))
        
        return possible_roots
    
    def get_boot_banner(self) -> str:
        """부트 배너 생성"""
        python_path = Path(sys.executable).resolve()
        return f"BOOT: PID={os.getpid()} PORT={self.port} HEALTH_ROOT={self.repo_root} PY={python_path}"


# 전역 인스턴스
_guard_instance: Optional[UIInstanceGuard] = None


def get_ui_guard(repo_root: Path, port: int = 8502) -> UIInstanceGuard:
    """UI 가드 인스턴스 획득"""
    global _guard_instance
    if _guard_instance is None:
        _guard_instance = UIInstanceGuard(repo_root, port)
    return _guard_instance
