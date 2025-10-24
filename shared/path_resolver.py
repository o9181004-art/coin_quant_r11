#!/usr/bin/env python3
"""
Path Resolver - 중앙집중식 경로 관리
SSOT_ROOT 기반 경로 정규화 및 보안 검증
"""

import os
from pathlib import Path
from typing import Optional


class PATH_VIOLATION(Exception):
    """경로 보안 위반 예외"""
    pass


class PathResolver:
    """경로 해결자 - SSOT_ROOT 기반 중앙집중식 경로 관리"""
    
    def __init__(self, ssot_root: Optional[Path] = None):
        """
        PathResolver 초기화
        
        Args:
            ssot_root: SSOT 루트 경로 (기본값: SSOT_ROOT 환경변수 또는 현재 작업 디렉토리)
        """
        self.ssot_root = ssot_root or Path(os.getenv("SSOT_ROOT", Path.cwd()))
        self._validate_root()
    
    def _validate_root(self):
        """SSOT_ROOT 유효성 검증"""
        if not self.ssot_root.exists():
            raise PATH_VIOLATION(f"SSOT_ROOT not found: {self.ssot_root}")
        
        if not self.ssot_root.is_dir():
            raise PATH_VIOLATION(f"SSOT_ROOT is not a directory: {self.ssot_root}")
    
    def resolve(self, path: str) -> Path:
        """
        경로 해결 및 보안 검증
        
        Args:
            path: 해결할 경로 (상대 또는 절대)
            
        Returns:
            정규화된 Path 객체
            
        Raises:
            PATH_VIOLATION: 경로가 SSOT_ROOT 밖으로 나가는 경우
        """
        resolved = Path(path).resolve()
        
        # SSOT_ROOT 밖으로 나가는지 검증
        try:
            resolved.relative_to(self.ssot_root)
        except ValueError:
            raise PATH_VIOLATION(f"Path outside SSOT_ROOT: {resolved} (root: {self.ssot_root})")
        
        return resolved
    
    def data_dir(self) -> Path:
        """shared_data 디렉토리"""
        return self.ssot_root / "shared_data"
    
    def log_dir(self) -> Path:
        """logs 디렉토리"""
        return self.ssot_root / "logs"
    
    def history_dir(self) -> Path:
        """history 디렉토리"""
        return self.data_dir() / "history"
    
    def snapshots_dir(self) -> Path:
        """snapshots 디렉토리"""
        return self.data_dir() / "snapshots"
    
    def signals_dir(self) -> Path:
        """signals 디렉토리"""
        return self.data_dir() / "signals"
    
    def trades_dir(self) -> Path:
        """trades 디렉토리"""
        return self.ssot_root / "trades"
    
    def runtime_dir(self) -> Path:
        """runtime 디렉토리"""
        return self.ssot_root / "runtime"
    
    def config_dir(self) -> Path:
        """config 디렉토리"""
        return self.ssot_root / "config"
    
    def ensure_dirs(self):
        """필수 디렉토리 생성"""
        dirs = [
            self.data_dir(),
            self.log_dir(),
            self.history_dir(),
            self.snapshots_dir(),
            self.signals_dir(),
            self.trades_dir(),
            self.runtime_dir()
        ]
        
        for dir_path in dirs:
            dir_path.mkdir(parents=True, exist_ok=True)


# 전역 PathResolver 인스턴스
_path_resolver = None


def get_path_resolver() -> PathResolver:
    """전역 PathResolver 인스턴스 반환"""
    global _path_resolver
    if _path_resolver is None:
        _path_resolver = PathResolver()
    return _path_resolver


def resolve_path(path: str) -> Path:
    """경로 해결 편의 함수"""
    return get_path_resolver().resolve(path)


if __name__ == "__main__":
    # 테스트
    resolver = PathResolver()
    print(f"SSOT_ROOT: {resolver.ssot_root}")
    print(f"Data dir: {resolver.data_dir()}")
    print(f"Log dir: {resolver.log_dir()}")
    
    # 경로 해결 테스트
    try:
        data_path = resolver.resolve("shared_data/health.json")
        print(f"Resolved: {data_path}")
    except PATH_VIOLATION as e:
        print(f"Path violation: {e}")
    
    # 디렉토리 생성 테스트
    resolver.ensure_dirs()
    print("✅ All directories created")
