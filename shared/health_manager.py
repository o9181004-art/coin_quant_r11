#!/usr/bin/env python3
"""
중앙 헬스 상태 관리자
모든 컴포넌트의 상태를 shared_data/health.json에 원자적으로 기록
Phase 1: Uses Windows-safe atomic writer
"""

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

# Phase 1: Import atomic writer
from shared.atomic_writer import atomic_write_json, safe_read_json


class HealthManager:
    """헬스 상태 관리자 - 원자적 쓰기 보장"""
    
    def __init__(self, health_file: str = "shared_data/health.json"):
        self.health_file = Path(health_file)
        self.health_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 상태 정의
        self.STATES = {
            "GREEN": "정상",
            "YELLOW": "경고", 
            "RED": "오류"
        }
        
        # 컴포넌트별 메트릭 스키마
        self.COMPONENT_SCHEMAS = {
            "feeder": {
                "ws_age": float,  # WebSocket 연결 나이 (초)
                "symbols_count": int,  # 모니터링 중인 심볼 수
                "rest_state": str,  # REST API 상태
                "last_heartbeat": float  # 마지막 하트비트 시간
            },
            "trader": {
                "state": str,  # IDLE, RUNNING, PAUSED
                "filters_state": str,  # FRESH, STALE
                "uds_age": float,  # UDS 연결 나이 (초)
                "account_snapshot_age": float,  # 계좌 스냅샷 나이 (초)
                "orders_count": int,  # 주문 시도 횟수
                "fills_count": int,  # 체결 횟수
                "last_order_time": float  # 마지막 주문 시간
            },
            "uds": {
                "listen_key_age_sec": float,  # ListenKey 나이 (초) - 표준 메트릭명
                "heartbeat_age_sec": float,  # 하트비트 나이 (초) - 표준 메트릭명
                "state": str,  # 연결 상태
                "last_heartbeat": float  # 마지막 하트비트 시간
            },
            "ares": {
                "signal_count": int,  # 신호 생성 횟수
                "latency_ms_p50": float,  # 지연시간 (밀리초)
                "state": str,  # 신호 생성 상태
                "last_signal_time": float  # 마지막 신호 시간
            },
            "autoheal": {
                "last_action": float,  # 마지막 액션 시간
                "restart_count": int,  # 재시작 횟수
                "state": str,  # 모니터링 상태
                "watchdog_active": bool  # 워치독 활성 상태
            },
            "account": {
                "equity_usdt": float,  # 총 자산 가치 (USDT)
                "balances_count": int,  # 잔고 자산 수
                "last_update_ts": float,  # 마지막 업데이트 시간
                "rest_api_enabled": bool,  # REST API 사용 여부
                "testnet_mode": bool  # TESTNET 모드 여부
            }
        }
    
    def _load_health_data(self) -> Dict[str, Any]:
        """헬스 데이터 로드 - Phase 1: Use safe reader"""
        data = safe_read_json(self.health_file)
        
        # 기본 구조가 없으면 추가
        if not data or "components" not in data:
            data = {
                "timestamp": time.time(),
                "components": {}
            }
        
        return data
    
    def _save_health_data(self, data: Dict[str, Any]) -> bool:
        """헬스 데이터 원자적 저장 - Phase 1: Use atomic writer"""
        try:
            # 기존 데이터 로드
            existing_data = self._load_health_data()
            
            # 새 데이터로 병합 (기존 필드 보존)
            existing_data.update(data)
            
            # Phase 1: Use Windows-safe atomic writer
            return atomic_write_json(self.health_file, existing_data)
            
        except Exception as e:
            print(f"[HealthManager] 헬스 데이터 저장 실패: {e}")
            return False
    
    def update_component(self, name: str, state: str, metrics: Dict[str, Any]) -> bool:
        """
        컴포넌트 상태 업데이트
        
        Args:
            name: 컴포넌트 이름 (feeder, trader, uds, autoheal)
            state: 상태 (GREEN, YELLOW, RED)
            metrics: 메트릭 딕셔너리
        
        Returns:
            bool: 성공 여부
        """
        if state not in self.STATES:
            print(f"[HealthManager] 잘못된 상태: {state}")
            return False
        
        if name not in self.COMPONENT_SCHEMAS:
            print(f"[HealthManager] 알 수 없는 컴포넌트: {name}")
            return False
        
        # 현재 데이터 로드
        health_data = self._load_health_data()
        
        # 컴포넌트 데이터 업데이트
        if "components" not in health_data:
            health_data["components"] = {}
        
        # 메트릭 검증 및 정규화
        validated_metrics = {}
        schema = self.COMPONENT_SCHEMAS[name]
        
        for key, value in metrics.items():
            if key in schema:
                expected_type = schema[key]
                try:
                    if expected_type == float:
                        validated_metrics[key] = float(value)
                    elif expected_type == int:
                        validated_metrics[key] = int(value)
                    elif expected_type == bool:
                        validated_metrics[key] = bool(value)
                    else:
                        validated_metrics[key] = str(value)
                except (ValueError, TypeError):
                    print(f"[HealthManager] 메트릭 타입 변환 실패: {key}={value}")
                    continue
            else:
                print(f"[HealthManager] 알 수 없는 메트릭: {key}")
        
        # 컴포넌트 상태 업데이트 (표준 스키마)
        health_data["components"][name] = {
            "status": state,  # 표준 스키마: status
            "last_ts": time.time(),  # 표준 스키마: last_ts
            "metrics": validated_metrics,
            "last_updated": time.time(),  # 하위 호환성
            "status_text": self.STATES[state]  # 하위 호환성
        }
        
        # 타임스탬프 업데이트
        health_data["timestamp"] = time.time()
        
        # 하위 호환성을 위한 top-level booleans 계산
        self._update_compatibility_flags(health_data)
        
        # 저장
        return self._save_health_data(health_data)
    
    def _update_compatibility_flags(self, health_data: Dict[str, Any]) -> None:
        """하위 호환성을 위한 top-level booleans 업데이트"""
        components = health_data.get("components", {})
        current_time = time.time()
        
        # TTLs for freshness (seconds)
        FEEDER_TTL = 5
        UDS_TTL = 50
        TRADER_TTL = 60
        ARES_TTL = 300
        AUTOHEAL_TTL = 300
        
        # Feeder 상태 계산
        feeder_status = components.get("feeder", {})
        if feeder_status.get("status") == "GREEN" and (current_time - feeder_status.get("last_ts", 0)) <= FEEDER_TTL:
            health_data["feeder_ok"] = True
        else:
            health_data["feeder_ok"] = False
        
        # UDS 상태 계산
        uds_status = components.get("uds", {})
        if uds_status.get("status") == "GREEN" and (current_time - uds_status.get("last_ts", 0)) <= UDS_TTL:
            health_data["uds_ok"] = True
        else:
            health_data["uds_ok"] = False
        
        # Trader 상태 계산
        trader_status = components.get("trader", {})
        if trader_status.get("status") == "GREEN" and (current_time - trader_status.get("last_ts", 0)) <= TRADER_TTL:
            health_data["trader_ok"] = True
        else:
            health_data["trader_ok"] = False
        
        # ARES 상태 계산
        ares_status = components.get("ares", {})
        if ares_status.get("status") == "GREEN" and (current_time - ares_status.get("last_ts", 0)) <= ARES_TTL:
            health_data["ares_ok"] = True
        else:
            health_data["ares_ok"] = False
        
        # Auto-Heal 상태 계산
        autoheal_status = components.get("autoheal", {})
        if autoheal_status.get("status") == "GREEN" and (current_time - autoheal_status.get("last_ts", 0)) <= AUTOHEAL_TTL:
            health_data["autoheal_ok"] = True
        else:
            health_data["autoheal_ok"] = False
        
        # History 상태 (기존 로직 유지)
        health_data["history_ok"] = True  # 기본값
    
    def get_component_status(self, name: str) -> Optional[Dict[str, Any]]:
        """컴포넌트 상태 조회"""
        health_data = self._load_health_data()
        return health_data.get("components", {}).get(name)
    
    def get_all_status(self) -> Dict[str, Any]:
        """전체 헬스 상태 조회"""
        return self._load_health_data()
    
    def is_component_healthy(self, name: str, max_age: float = 300.0) -> bool:
        """
        컴포넌트가 건강한지 확인
        
        Args:
            name: 컴포넌트 이름
            max_age: 최대 허용 나이 (초)
        
        Returns:
            bool: 건강 여부
        """
        status = self.get_component_status(name)
        if not status:
            return False
        
        # 상태가 GREEN이고 최근에 업데이트되었는지 확인
        if status.get("state") != "GREEN":
            return False
        
        last_updated = status.get("last_updated", 0)
        return (time.time() - last_updated) <= max_age
    
    def get_component_age(self, name: str) -> float:
        """컴포넌트 마지막 업데이트 나이 반환"""
        status = self.get_component_status(name)
        if not status:
            return float('inf')
        
        last_updated = status.get("last_updated", 0)
        return time.time() - last_updated


# 전역 인스턴스
_health_manager = None

def get_health_manager() -> HealthManager:
    """헬스 매니저 싱글톤 인스턴스 반환"""
    global _health_manager
    if _health_manager is None:
        _health_manager = HealthManager()
    return _health_manager

def update_component(name: str, state: str, metrics: Dict[str, Any]) -> bool:
    """컴포넌트 상태 업데이트 (편의 함수)"""
    return get_health_manager().update_component(name, state, metrics)

def get_component_status(name: str) -> Optional[Dict[str, Any]]:
    """컴포넌트 상태 조회 (편의 함수)"""
    return get_health_manager().get_component_status(name)

def get_all_status() -> Dict[str, Any]:
    """전체 헬스 상태 조회 (편의 함수)"""
    return get_health_manager().get_all_status()

def is_component_healthy(name: str, max_age: float = 300.0) -> bool:
    """컴포넌트 건강 여부 확인 (편의 함수)"""
    return get_health_manager().is_component_healthy(name, max_age)

def get_component_age(name: str) -> float:
    """컴포넌트 나이 조회 (편의 함수)"""
    return get_health_manager().get_component_age(name)

def set_component(name: str, status: str, metrics_dict: Dict[str, Any]) -> bool:
    """경량 헬퍼 - 컴포넌트 상태 설정 (편의 함수)"""
    return get_health_manager().update_component(name, status, metrics_dict)


# 테스트 함수
def test_health_manager():
    """헬스 매니저 테스트"""
    print("[HealthManager] 테스트 시작")
    
    # Feeder 상태 업데이트
    success = update_component("feeder", "GREEN", {
        "ws_age": 2.5,
        "symbols_count": 10,
        "rest_state": "OK",
        "last_heartbeat": time.time()
    })
    print(f"Feeder 업데이트: {'성공' if success else '실패'}")
    
    # Trader 상태 업데이트
    success = update_component("trader", "YELLOW", {
        "state": "IDLE",
        "filters_state": "STALE",
        "uds_age": 45.0,
        "account_snapshot_age": 120.0,
        "orders_count": 0,
        "fills_count": 0,
        "last_order_time": 0
    })
    print(f"Trader 업데이트: {'성공' if success else '실패'}")
    
    # 전체 상태 조회
    all_status = get_all_status()
    print(f"전체 상태: {json.dumps(all_status, indent=2, ensure_ascii=False)}")
    
    print("[HealthManager] 테스트 완료")


if __name__ == "__main__":
    test_health_manager()
