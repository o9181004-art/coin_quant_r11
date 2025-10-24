#!/usr/bin/env python3
"""
SSOT (Single Source of Truth) 경로 해결
모든 서비스에서 동일한 SSOT 파일 경로 사용 보장
"""

import os
from pathlib import Path
from typing import Optional


class SSOTPathResolver:
    """SSOT 경로 해결 클래스"""
    
    _instance = None
    _resolved_root: Optional[Path] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def get_root_dir(self) -> Path:
        """
        프로젝트 루트 디렉토리 해결
        
        우선순위:
        1. CQ_ROOT 환경변수
        2. __file__ 기반 자동 감지
        
        Returns:
            Path: 해결된 절대 경로
        """
        if self._resolved_root is not None:
            return self._resolved_root
        
        # 1. CQ_ROOT 환경변수 확인
        cq_root = os.getenv("CQ_ROOT")
        if cq_root:
            root_path = Path(cq_root).resolve()
            if root_path.exists():
                self._resolved_root = root_path
                print(f"[SSOT] 프로젝트 루트 (CQ_ROOT): {root_path}", flush=True)
                return root_path
        
        # 2. __file__ 기반 자동 감지
        # __file__이 shared/ssot_path_resolver.py이므로 parent.parent가 루트
        root_path = Path(__file__).resolve().parent.parent
        self._resolved_root = root_path
        print(f"[SSOT] 프로젝트 루트 (자동 감지): {root_path}", flush=True)
        return root_path
    
    def get_health_path(self) -> Path:
        """
        health.json (통합 파일) 절대 경로
        
        Returns:
            Path: 해결된 절대 경로
        """
        root = self.get_root_dir()
        health_path = root / "shared_data" / "health.json"
        self._ensure_dir(health_path.parent)
        return health_path
    
    def get_health_dir(self) -> Path:
        """
        health 서브 디렉토리 (per-service health files)
        
        Returns:
            Path: shared_data/health/
        """
        root = self.get_root_dir()
        health_dir = root / "shared_data" / "health"
        self._ensure_dir(health_dir)
        return health_dir
    
    def get_component_health_path(self, component: str) -> Path:
        """
        개별 컴포넌트 health 파일 경로
        
        Args:
            component: feeder, trader, uds, ares, autoheal 등
        
        Returns:
            Path: shared_data/health/{component}.json
        """
        health_dir = self.get_health_dir()
        return health_dir / f"{component}.json"
    
    def get_databus_snapshot_path(self) -> Path:
        """
        DataBus 스냅샷 절대 경로
        
        Returns:
            Path: shared_data/databus_snapshot.json
        """
        root = self.get_root_dir()
        snapshot_path = root / "shared_data" / "databus_snapshot.json"
        self._ensure_dir(snapshot_path.parent)
        return snapshot_path
    
    def get_feeder_heartbeat_path(self) -> Path:
        """Feeder 하트비트 파일 경로"""
        health_path = self.get_health_path()
        return health_path.parent / "feeder.heartbeat.json"
    
    def get_trader_heartbeat_path(self) -> Path:
        """Trader 하트비트 파일 경로"""
        health_path = self.get_health_path()
        return health_path.parent / "health" / "trader.heartbeat.json"
    
    def get_feeder_pid_path(self) -> Path:
        """Feeder PID 파일 경로"""
        health_path = self.get_health_path()
        return health_path.parent / "feeder.pid"
    
    def get_trader_pid_path(self) -> Path:
        """Trader PID 파일 경로"""
        health_path = self.get_health_path()
        return health_path.parent / "trader.pid"
    
    def get_shared_data_dir(self) -> Path:
        """shared_data 디렉토리 경로"""
        return self.get_health_path().parent
    
    def _ensure_dir(self, path: Path) -> bool:
        """디렉토리 생성 시도"""
        try:
            path.mkdir(parents=True, exist_ok=True)
            return True
        except Exception as e:
            print(f"[SSOT] 디렉토리 생성 실패 {path}: {e}", flush=True)
            return False
    
    def reset(self):
        """해결된 경로 초기화 (테스트용)"""
        self._resolved_path = None


# 전역 인스턴스
_resolver = SSOTPathResolver()


def get_health_path() -> Path:
    """health.json 경로 가져오기"""
    return _resolver.get_health_path()


def get_feeder_heartbeat_path() -> Path:
    """Feeder 하트비트 경로 가져오기"""
    return _resolver.get_feeder_heartbeat_path()


def get_trader_heartbeat_path() -> Path:
    """Trader 하트비트 경로 가져오기"""
    return _resolver.get_trader_heartbeat_path()


def get_feeder_pid_path() -> Path:
    """Feeder PID 경로 가져오기"""
    return _resolver.get_feeder_pid_path()


def get_trader_pid_path() -> Path:
    """Trader PID 경로 가져오기"""
    return _resolver.get_trader_pid_path()


def get_shared_data_dir() -> Path:
    """shared_data 디렉토리 경로 가져오기"""
    return _resolver.get_shared_data_dir()


def get_root_dir() -> Path:
    """프로젝트 루트 디렉토리 가져오기"""
    return _resolver.get_root_dir()


def get_health_dir() -> Path:
    """health 서브 디렉토리 가져오기"""
    return _resolver.get_health_dir()


def get_component_health_path(component: str) -> Path:
    """개별 컴포넌트 health 파일 경로 가져오기"""
    return _resolver.get_component_health_path(component)


def get_databus_snapshot_path() -> Path:
    """DataBus 스냅샷 절대 경로 가져오기"""
    return _resolver.get_databus_snapshot_path()


def log_resolved_paths():
    """해결된 모든 경로를 로그로 출력 (시작 시 호출)"""
    print("=" * 80, flush=True)
    print("[SSOT] Resolved Absolute Paths", flush=True)
    print("=" * 80, flush=True)
    print(f"  Root Dir:          {get_root_dir()}", flush=True)
    print(f"  shared_data:       {get_shared_data_dir()}", flush=True)
    print(f"  health.json:       {get_health_path()}", flush=True)
    print(f"  health/ dir:       {get_health_dir()}", flush=True)
    print(f"  health/feeder:     {get_component_health_path('feeder')}", flush=True)
    print(f"  health/trader:     {get_component_health_path('trader')}", flush=True)
    print(f"  health/uds:        {get_component_health_path('uds')}", flush=True)
    print(f"  databus_snapshot:  {get_databus_snapshot_path()}", flush=True)
    print("=" * 80, flush=True)


if __name__ == "__main__":
    # 테스트
    log_resolved_paths()
    print(f"\nfeeder.heartbeat.json: {get_feeder_heartbeat_path()}")
    print(f"trader.heartbeat.json: {get_trader_heartbeat_path()}")
    print(f"feeder.pid: {get_feeder_pid_path()}")
    print(f"trader.pid: {get_trader_pid_path()}")
