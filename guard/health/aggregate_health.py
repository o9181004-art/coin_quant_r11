#!/usr/bin/env python3
"""
Health Aggregator
주기적으로 health/*.json 파일들을 읽어 통합 health.json 생성
"""

import json
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict

# 프로젝트 루트를 경로에 추가
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from shared.ssot_path_resolver import (get_component_health_path,
                                       get_health_dir, get_health_path,
                                       log_resolved_paths)


class HealthAggregator:
    """Health 파일 통합 관리자"""
    
    def __init__(self, interval_sec: float = 3.0):
        """
        Args:
            interval_sec: 통합 주기 (기본 3초)
        """
        self.interval_sec = interval_sec
        self.running = False
        self.thread = None
        self.logger = self._setup_logging()
        
        # SSOT 경로
        self.health_file = get_health_path()
        self.health_dir = get_health_dir()
        
        # 컴포넌트 목록
        self.components = ["feeder", "trader", "uds", "ares", "autoheal"]
        
        # 시작 시 경로 로그
        log_resolved_paths()
        
    def _setup_logging(self) -> logging.Logger:
        """로거 설정"""
        logger = logging.getLogger("health_aggregator")
        logger.setLevel(logging.INFO)
        
        # 콘솔 핸들러
        if not logger.handlers:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)
        
        return logger
    
    def start(self):
        """Aggregator 시작"""
        if self.running:
            self.logger.warning("Aggregator already running")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._aggregation_loop, daemon=True)
        self.thread.start()
        self.logger.info(f"Health Aggregator started (interval: {self.interval_sec}s)")
        self.logger.info(f"Aggregated health file: {self.health_file}")
        self.logger.info(f"Component health dir: {self.health_dir}")
    
    def stop(self):
        """Aggregator 중지"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        self.logger.info("Health Aggregator stopped")
    
    def _aggregation_loop(self):
        """통합 루프"""
        last_log_time = 0
        log_interval = 30  # 30초마다 로그
        
        while self.running:
            try:
                current_time = time.time()
                
                # Health 통합 실행
                aggregated = self._aggregate_health_files()
                
                # Atomic write: .tmp -> rename
                self._write_health_atomic(aggregated)
                
                # 주기적 로그 (30초마다)
                if current_time - last_log_time >= log_interval:
                    self._log_health_status(aggregated)
                    last_log_time = current_time
                
                # 대기
                time.sleep(self.interval_sec)
                
            except Exception as e:
                self.logger.error(f"Aggregation loop error: {e}")
                time.sleep(self.interval_sec)
    
    def _aggregate_health_files(self) -> Dict[str, Any]:
        """
        개별 health 파일들을 읽어 통합
        
        Returns:
            통합된 health 데이터
        """
        current_time = time.time()
        
        # 통합 데이터 초기화
        aggregated = {
            "ts": current_time,
            "components": {},
            "global_status": "GREEN",
            "aggregator_version": "1.0",
        }
        
        # 각 컴포넌트 health 파일 읽기
        for component in self.components:
            component_path = get_component_health_path(component)
            
             try:
                if component_path.exists():
                    # UTF-8 BOM 처리
                    with open(component_path, "r", encoding="utf-8-sig") as f:
                        component_data = json.load(f)
                    
                    # 파일 수정 시간 확인
                    mtime = component_path.stat().st_mtime
                    age_sec = current_time - mtime
                    
                    # 컴포넌트 데이터 추가
                    aggregated["components"][component] = {
                        "status": component_data.get("status", "UNKNOWN"),
                        "last_ts": component_data.get("ts", mtime),
                        "age_sec": age_sec,
                        "data": component_data
                    }
                    
                    # Global status 결정 (가장 안 좋은 상태 우선)
                    component_status = component_data.get("status", "UNKNOWN")
                    if component_status == "RED" or component_status == "ERROR":
                        aggregated["global_status"] = "RED"
                    elif component_status == "YELLOW" and aggregated["global_status"] != "RED":
                        aggregated["global_status"] = "YELLOW"
                    
                else:
                    # 파일이 없으면 MISSING 상태
                    aggregated["components"][component] = {
                        "status": "MISSING",
                        "last_ts": 0,
                        "age_sec": float('inf'),
                        "data": {}
                    }
                    if aggregated["global_status"] == "GREEN":
                        aggregated["global_status"] = "YELLOW"
                    
            except Exception as e:
                self.logger.error(f"Failed to read {component} health: {e}")
                aggregated["components"][component] = {
                    "status": "ERROR",
                    "last_ts": 0,
                    "age_sec": float('inf'),
                    "data": {"error": str(e)}
                }
                aggregated["global_status"] = "RED"
        
        return aggregated
    
    def _write_health_atomic(self, data: Dict[str, Any]):
        """
        Health 파일을 atomic하게 쓰기
        
        .tmp 파일에 먼저 쓰고 rename으로 교체
        """
        try:
            # 임시 파일 경로
            tmp_file = self.health_file.with_suffix(".json.tmp")
            
            # 1. .tmp 파일에 쓰기
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # 2. rename으로 atomic 교체 (Windows에서도 가능)
            tmp_file.replace(self.health_file)
            
        except Exception as e:
            self.logger.error(f"Failed to write health file: {e}")
    
    def _log_health_status(self, aggregated: Dict[str, Any]):
        """
        Health 상태 로그 (30초마다)
        """
        try:
            # 파일 수정 시간
            if self.health_file.exists():
                mtime = self.health_file.stat().st_mtime
                age_sec = time.time() - mtime
                mtime_iso = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))
            else:
                mtime_iso = "N/A"
                age_sec = float('inf')
            
            global_status = aggregated.get("global_status", "UNKNOWN")
            
            # 컴포넌트 요약
            components_summary = []
            for comp, comp_data in aggregated.get("components", {}).items():
                status = comp_data.get("status", "UNKNOWN")
                age = comp_data.get("age_sec", float('inf'))
                components_summary.append(f"{comp}={status}({age:.1f}s)")
            
            # 한 줄 로그
            self.logger.info(
                f"[HealthUI] reading from {self.health_file}, "
                f"mtime={mtime_iso}, age={age_sec:.1f}s, global={global_status}, "
                f"components=[{', '.join(components_summary)}]"
            )
            
        except Exception as e:
            self.logger.error(f"Failed to log health status: {e}")


def main():
    """메인 함수 - Aggregator 실행"""
    aggregator = HealthAggregator(interval_sec=3.0)
    
    try:
        aggregator.start()
        
        # 계속 실행
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n[HealthAggregator] Stopping...")
        aggregator.stop()


if __name__ == "__main__":
    main()

