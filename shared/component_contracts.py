#!/usr/bin/env python3
"""
Component Contracts - Phase 1
Define inputs, outputs, TTLs, and invariants for each component
"""

import json
import time
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from shared.environment_guardrails import get_repo_paths


class ComponentState(Enum):
    """컴포넌트 상태"""
    GREEN = "GREEN"      # 정상 작동
    YELLOW = "YELLOW"    # 경고 상태 (제한적 기능)
    RED = "RED"          # 오류 상태 (기능 중단)


class ComponentStatus(Enum):
    """컴포넌트 상태 세부사항"""
    RUNNING = "RUNNING"
    IDLE = "IDLE"
    ERROR = "ERROR"
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    STOPPING = "STOPPING"


@dataclass
class ComponentHealth:
    """컴포넌트 헬스 정보"""
    name: str
    state: ComponentState
    status: ComponentStatus
    last_update: float
    error_message: str = ""
    metrics: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metrics is None:
            self.metrics = {}
    
    def is_fresh(self, ttl_seconds: float) -> bool:
        """TTL 기준 신선도 확인"""
        return (time.time() - self.last_update) <= ttl_seconds
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리 변환"""
        data = asdict(self)
        data['state'] = self.state.value
        data['status'] = self.status.value
        return data


class ComponentContracts:
    """컴포넌트 계약 정의"""
    
    def __init__(self):
        self.paths = get_repo_paths()
        self.contracts = self._define_contracts()
    
    def _define_contracts(self) -> Dict[str, Dict[str, Any]]:
        """컴포넌트 계약 정의"""
        return {
            "feeder": {
                "name": "Feeder",
                "description": "실시간 시장 데이터 수집 및 상태 버스 업데이트",
                "inputs": [],
                "outputs": {
                    "state_bus": {
                        "file": "shared_data/state_bus.json",
                        "ttl_seconds": 5,
                        "description": "시장 데이터 스냅샷 (심볼별 최신 가격, 볼륨 등)"
                    },
                    "health": {
                        "component": "feeder",
                        "ttl_seconds": 10,
                        "description": "Feeder 서비스 상태"
                    }
                },
                "invariants": [
                    "단일 작성자 (single writer)",
                    "Windows-safe atomic writes만 사용",
                    "WebSocket 연결 유지 (5초 이내 재연결)"
                ],
                "dependencies": [],
                "pid_file": "shared_data/pids/feeder.pid"
            },
            
            "uds": {
                "name": "User Data Stream",
                "description": "Binance 사용자 데이터 스트림 관리",
                "inputs": [],
                "outputs": {
                    "health": {
                        "component": "uds",
                        "ttl_seconds": 50,
                        "description": "UDS 서비스 상태 (heartbeat_age_sec, listen_key_age_sec)"
                    }
                },
                "invariants": [
                    "heartbeat 50초 이내",
                    "listen_key 갱신 (30일 이내)",
                    "연결 끊김 시 자동 재연결"
                ],
                "dependencies": [],
                "pid_file": "shared_data/pids/uds.pid"
            },
            
            "ares": {
                "name": "ARES Engine",
                "description": "적응형 레짐 전략 엔진",
                "inputs": {
                    "feeder_snapshot": {
                        "file": "shared_data/state_bus.json",
                        "ttl_seconds": 5,
                        "description": "Feeder에서 제공하는 시장 데이터"
                    }
                },
                "outputs": {
                    "signals": {
                        "file": "shared_data/signals/ares_signals.json",
                        "ttl_seconds": 30,
                        "description": "ARES 신호 출력"
                    },
                    "health": {
                        "component": "ares",
                        "ttl_seconds": 30,
                        "description": "ARES 엔진 상태 (latency metrics)"
                    }
                },
                "invariants": [
                    "실제 신호만 출력 (fallback/default 신호 금지, TEST_ALLOW_DEFAULT_SIGNAL=true 제외)",
                    "입력 데이터 신선도 확인",
                    "지연 시간 모니터링"
                ],
                "dependencies": ["feeder"],
                "pid_file": "shared_data/pids/ares.pid"
            },
            
            "trader": {
                "name": "Trader",
                "description": "자동매매 실행 엔진",
                "inputs": {
                    "ares_signals": {
                        "file": "shared_data/signals/ares_signals.json",
                        "ttl_seconds": 30,
                        "description": "ARES에서 제공하는 매매 신호"
                    },
                    "health": {
                        "file": "shared_data/health.json",
                        "ttl_seconds": 15,
                        "description": "전체 시스템 헬스 상태"
                    },
                    "account_snapshot": {
                        "file": "shared_data/account_snapshot.json",
                        "ttl_seconds": 180,
                        "description": "계좌 스냅샷"
                    },
                    "exchange_filters": {
                        "file": "shared_data/exchange_filters.json",
                        "ttl_seconds": 180,
                        "description": "거래소 필터 정보"
                    },
                    "circuit_breaker": {
                        "file": "shared_data/circuit_breaker.json",
                        "ttl_seconds": 60,
                        "description": "서킷 브레이커 상태"
                    }
                },
                "outputs": {
                    "orders": {
                        "file": "shared_data/orders/orders_log.ndjson",
                        "ttl_seconds": 300,
                        "description": "주문 로그"
                    },
                    "positions": {
                        "file": "shared_data/positions.json",
                        "ttl_seconds": 180,
                        "description": "포지션 정보"
                    },
                    "pnl_rollup": {
                        "file": "shared_data/pnl_rollup.ndjson",
                        "ttl_seconds": 300,
                        "description": "손익 롤업"
                    },
                    "health": {
                        "component": "trader",
                        "ttl_seconds": 15,
                        "description": "Trader 상태"
                    }
                },
                "invariants": [
                    "UDS 신선도 확인 (heartbeat_age_sec ≤ 50s)",
                    "헬스 신선도 확인 (≤ 15s)",
                    "서킷 브레이커 OFF 상태",
                    "필터 신선도 확인 (≤ 180s)",
                    "제한된 경고 (transition + ≤1/min while stale)"
                ],
                "dependencies": ["ares", "uds", "account_snapshot", "circuit_breaker"],
                "pid_file": "shared_data/pids/trader.pid"
            },
            
            "autoheal": {
                "name": "Auto-Heal",
                "description": "자동 복구 시스템",
                "inputs": {
                    "health": {
                        "file": "shared_data/health.json",
                        "ttl_seconds": 30,
                        "description": "전체 시스템 헬스 상태"
                    },
                    "pid_locks": {
                        "directory": "shared_data/pids",
                        "description": "서비스 PID 락 파일들"
                    }
                },
                "outputs": {
                    "health": {
                        "component": "autoheal",
                        "ttl_seconds": 30,
                        "description": "Auto-Heal 상태"
                    },
                    "alerts": {
                        "file": "shared_data/alerts.ndjson",
                        "description": "자동 복구 알림"
                    }
                },
                "invariants": [
                    "PID 락 존중",
                    "중복 프로세스 방지",
                    "복구 시도 제한 (백오프)"
                ],
                "dependencies": ["feeder", "trader", "ares", "uds"],
                "pid_file": "shared_data/pids/autoheal.pid"
            },
            
            "account_snapshot": {
                "name": "Account Snapshot Service",
                "description": "계좌 정보 스냅샷 서비스",
                "inputs": [],
                "outputs": {
                    "account_snapshot": {
                        "file": "shared_data/account_snapshot.json",
                        "ttl_seconds": 60,
                        "description": "계좌 스냅샷 (60초마다 갱신)"
                    },
                    "health": {
                        "component": "account_snapshot",
                        "ttl_seconds": 60,
                        "description": "계좌 스냅샷 서비스 상태"
                    }
                },
                "invariants": [
                    "60초마다 atomic write",
                    "단일 작성자"
                ],
                "dependencies": [],
                "pid_file": "shared_data/pids/account_snapshot.pid"
            },
            
            "circuit_breaker": {
                "name": "Circuit Breaker",
                "description": "서킷 브레이커 시스템",
                "inputs": [],
                "outputs": {
                    "circuit_breaker": {
                        "file": "shared_data/circuit_breaker.json",
                        "ttl_seconds": 60,
                        "description": "서킷 브레이커 상태 (atomic, 60s TTL)"
                    }
                },
                "invariants": [
                    "atomic write",
                    "60초 TTL"
                ],
                "dependencies": [],
                "pid_file": "shared_data/pids/circuit_breaker.pid"
            },
            
            "alerts": {
                "name": "Alerts System",
                "description": "알림 시스템",
                "inputs": [
                    "모든 컴포넌트의 오류/경고"
                ],
                "outputs": {
                    "alerts": {
                        "file": "shared_data/alerts.ndjson",
                        "description": "알림 로그 (append, daily rotation, 30d retention)"
                    }
                },
                "invariants": [
                    "append only",
                    "일일 회전",
                    "30일 보관"
                ],
                "dependencies": ["모든 컴포넌트"],
                "pid_file": None
            }
        }
    
    def get_contract(self, component_name: str) -> Dict[str, Any]:
        """컴포넌트 계약 조회"""
        if component_name not in self.contracts:
            raise ValueError(f"알 수 없는 컴포넌트: {component_name}")
        return self.contracts[component_name]
    
    def get_component_ttl(self, component_name: str, output_type: str = "health") -> Optional[float]:
        """컴포넌트 TTL 조회"""
        contract = self.get_contract(component_name)
        
        if output_type == "health":
            if "health" in contract["outputs"]:
                return contract["outputs"]["health"]["ttl_seconds"]
            else:
                return None
        elif output_type in contract["outputs"]:
            return contract["outputs"][output_type]["ttl_seconds"]
        else:
            raise ValueError(f"알 수 없는 출력 타입: {output_type}")
    
    def get_component_dependencies(self, component_name: str) -> List[str]:
        """컴포넌트 의존성 조회"""
        contract = self.get_contract(component_name)
        return contract["dependencies"]
    
    def validate_component_health(self, component_name: str, health_data: Dict[str, Any]) -> Tuple[bool, str]:
        """컴포넌트 헬스 검증"""
        try:
            contract = self.get_contract(component_name)
            ttl_seconds = contract["outputs"]["health"]["ttl_seconds"]
            
            # TTL 검증
            if not health_data.get("last_update"):
                return False, "last_update 누락"
            
            last_update = health_data["last_update"]
            if not isinstance(last_update, (int, float)):
                return False, "last_update 타입 오류"
            
            age = time.time() - last_update
            if age > ttl_seconds:
                return False, f"TTL 초과 (age: {age:.1f}s > {ttl_seconds}s)"
            
            # 상태 검증
            state = health_data.get("state")
            if state not in ["GREEN", "YELLOW", "RED"]:
                return False, f"잘못된 상태: {state}"
            
            return True, "OK"
            
        except Exception as e:
            return False, f"검증 오류: {e}"
    
    def get_all_components(self) -> List[str]:
        """모든 컴포넌트 목록 조회"""
        return list(self.contracts.keys())
    
    def get_components_by_dependency(self, target_component: str) -> List[str]:
        """특정 컴포넌트에 의존하는 컴포넌트들 조회"""
        dependents = []
        for component, contract in self.contracts.items():
            if target_component in contract["dependencies"]:
                dependents.append(component)
        return dependents
    
    def print_contracts_summary(self):
        """계약 요약 출력"""
        print("📋 Component Contracts Summary")
        print("=" * 60)
        
        for component, contract in self.contracts.items():
            print(f"\n🔧 {contract['name']} ({component})")
            print(f"   설명: {contract['description']}")
            
            # TTL 출력 (health가 있는 경우)
            if "health" in contract["outputs"]:
                print(f"   TTL: {contract['outputs']['health']['ttl_seconds']}s")
            else:
                print(f"   TTL: N/A (no health output)")
            
            print(f"   의존성: {', '.join(contract['dependencies']) if contract['dependencies'] else 'None'}")
            
            # 주요 출력 파일들
            outputs = []
            for output_name, output_info in contract["outputs"].items():
                if output_name != "health" and "file" in output_info:
                    outputs.append(f"{output_name}: {output_info['file']}")
            
            if outputs:
                print(f"   출력: {', '.join(outputs)}")
        
        print("\n" + "=" * 60)


# 전역 인스턴스
contracts = ComponentContracts()


def get_component_contract(component_name: str) -> Dict[str, Any]:
    """컴포넌트 계약 조회"""
    return contracts.get_contract(component_name)


def get_component_ttl(component_name: str, output_type: str = "health") -> Optional[float]:
    """컴포넌트 TTL 조회"""
    return contracts.get_component_ttl(component_name, output_type)


def validate_component_health(component_name: str, health_data: Dict[str, Any]) -> Tuple[bool, str]:
    """컴포넌트 헬스 검증"""
    return contracts.validate_component_health(component_name, health_data)


if __name__ == "__main__":
    # 직접 실행 시 계약 요약 출력
    print("📋 Component Contracts - 독립 실행")
    contracts.print_contracts_summary()
    
    # TTL 테스트
    print("\n⏱️ TTL 테스트:")
    for component in contracts.get_all_components():
        ttl = get_component_ttl(component)
        ttl_str = f"{ttl}s" if ttl is not None else "N/A"
        print(f"   {component}: {ttl_str}")
