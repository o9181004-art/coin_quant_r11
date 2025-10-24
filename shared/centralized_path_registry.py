#!/usr/bin/env python3
"""
Centralized Path Registry
Single source of truth for all file paths in the system
"""

import os
import sys
import time
from pathlib import Path
from typing import Dict, Optional


class CentralizedPathRegistry:
    """중앙화된 경로 레지스트리"""
    
    def __init__(self, repo_root: Optional[Path] = None):
        if repo_root is None:
            # 현재 파일에서 프로젝트 루트 자동 감지
            current_file = Path(__file__).resolve()
            for parent in current_file.parents:
                if (parent / "shared").exists() and (parent / "guard").exists():
                    repo_root = parent
                    break
        
        self.repo_root = repo_root.resolve()
        self._paths = self._initialize_paths()
    
    def _initialize_paths(self) -> Dict[str, Path]:
        """경로 초기화"""
        return {
            # 기본 경로
            'repo_root': self.repo_root,
            'shared_data': self.repo_root / 'shared_data',
            'shared_data_health': self.repo_root / 'shared_data' / 'health',
            'runtime': self.repo_root / '.runtime',
            
            # 헬스 파일들
            'health_feeder': self.repo_root / 'shared_data' / 'health' / 'feeder.json',
            'health_trader': self.repo_root / 'shared_data' / 'health' / 'trader.json',
            'health_ares': self.repo_root / 'shared_data' / 'health' / 'ares.json',
            'health_positions': self.repo_root / 'shared_data' / 'health' / 'positions.json',
            'health_autoheal': self.repo_root / 'shared_data' / 'health' / 'autoheal.json',
            
            # SSOT 파일들
            'ssot_env': self.repo_root / 'shared_data' / 'ssot' / 'env.json',
            
            # 데이터 파일들
            'state_bus': self.repo_root / 'shared_data' / 'state_bus.json',
            'candidates_ndjson': self.repo_root / 'shared_data' / 'candidates.ndjson',
            'positions_json': self.repo_root / 'shared_data' / 'positions.json',
            
            # UI 락 파일들
            'ui_lock': self.repo_root / '.runtime' / 'ui.lock',
            'ui_pid': self.repo_root / '.runtime' / 'ui.pid',
            'ui_port': self.repo_root / '.runtime' / 'ui.port',
        }
    
    def get(self, key: str) -> Path:
        """경로 조회"""
        if key not in self._paths:
            raise KeyError(f"Unknown path key: {key}")
        return self._paths[key]
    
    def get_all_paths(self) -> Dict[str, Path]:
        """모든 경로 조회"""
        return self._paths.copy()
    
    def get_health_paths(self) -> Dict[str, Path]:
        """헬스 관련 경로만 조회"""
        health_keys = [k for k in self._paths.keys() if k.startswith('health_')]
        return {k: self._paths[k] for k in health_keys}
    
    def get_absolute_path(self, key: str) -> str:
        """절대 경로 문자열 반환"""
        return str(self.get(key))
    
    def validate_paths(self) -> Dict[str, bool]:
        """경로 유효성 검증"""
        results = {}
        for key, path in self._paths.items():
            results[key] = path.exists()
        return results
    
    def get_path_info(self, key: str) -> Dict:
        """경로 정보 조회"""
        path = self.get(key)
        info = {
            'key': key,
            'path': str(path),
            'exists': path.exists(),
            'is_file': path.is_file() if path.exists() else False,
            'is_dir': path.is_dir() if path.exists() else False,
        }
        
        if path.exists() and path.is_file():
            try:
                stat = path.stat()
                info.update({
                    'size': stat.st_size,
                    'mtime': stat.st_mtime,
                    'mtime_human': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stat.st_mtime))
                })
            except Exception:
                pass
        
        return info


# 전역 인스턴스
_path_registry: Optional[CentralizedPathRegistry] = None


def get_path_registry(repo_root: Optional[Path] = None) -> CentralizedPathRegistry:
    """경로 레지스트리 인스턴스 획득"""
    global _path_registry
    if _path_registry is None:
        _path_registry = CentralizedPathRegistry(repo_root)
    return _path_registry


def get_absolute_path(key: str) -> str:
    """절대 경로 조회 (기존 API 호환성)"""
    return get_path_registry().get_absolute_path(key)
