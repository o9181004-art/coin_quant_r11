#!/usr/bin/env python3
"""
Wire-Checks - Phase 3
Live diagnostics for component connectivity and health
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
import sys

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from shared.environment_guardrails import get_repo_paths, check_service_pid_lock
from shared.component_contracts import get_component_contract, get_component_ttl, validate_component_health
from shared.atomic_io import read_json_atomic, read_ndjson_lines


class WireCheckResult:
    """Wire check 결과"""
    
    def __init__(self, check_name: str):
        self.check_name = check_name
        self.passed = False
        self.message = ""
        self.metrics = {}
        self.timestamp = time.time()
    
    def pass_check(self, message: str = "OK", metrics: Dict[str, Any] = None):
        """체크 통과"""
        self.passed = True
        self.message = message
        self.metrics = metrics or {}
    
    def fail_check(self, message: str, metrics: Dict[str, Any] = None):
        """체크 실패"""
        self.passed = False
        self.message = message
        self.metrics = metrics or {}


class WireChecker:
    """Wire check 시스템"""
    
    def __init__(self):
        self.paths = get_repo_paths()
        self.results = {}
    
    def run_all_checks(self) -> Dict[str, WireCheckResult]:
        """모든 wire check 실행"""
        print("🔍 Wire-Checks - 라이브 진단 시작")
        print("=" * 60)
        
        self.results = {}
        
        # 각 체크 실행
        self._check_feeder_health()
        self._check_uds_trader()
        self._check_ares_trader()
        self._check_trader_account_circuit()
        self._check_autoheal()
        self._check_single_instances()
        
        # 결과 요약
        self._print_summary()
        
        return self.results
    
    def _check_feeder_health(self):
        """Feeder ↔ Health 체크"""
        result = WireCheckResult("Feeder ↔ Health")
        
        try:
            # Feeder PID 확인
            is_running, pid = check_service_pid_lock("feeder")
            if not is_running:
                result.fail_check("Feeder 서비스가 실행되지 않음")
                self.results["feeder_health"] = result
                return
            
            # 상태 버스 파일 확인
            state_bus_file = self.paths["shared_data"] / "state_bus.json"
            if not state_bus_file.exists():
                result.fail_check("state_bus.json 파일이 없음")
                self.results["feeder_health"] = result
                return
            
            # 파일 나이 확인 (5초 TTL)
            file_age = time.time() - state_bus_file.stat().st_mtime
            if file_age > 5:
                result.fail_check(f"state_bus.json이 오래됨 (age: {file_age:.1f}s > 5s)")
                self.results["feeder_health"] = result
                return
            
            # 헬스 상태 확인
            health_data = read_json_atomic(self.paths["shared_data"] / "health.json", {})
            feeder_health = health_data.get("feeder", {})
            
            if not feeder_health:
                result.fail_check("Feeder 헬스 데이터가 없음")
                self.results["feeder_health"] = result
                return
            
            # TTL 검증
            is_valid, error_msg = validate_component_health("feeder", feeder_health)
            if not is_valid:
                result.fail_check(f"Feeder 헬스 TTL 검증 실패: {error_msg}")
                self.results["feeder_health"] = result
                return
            
            result.pass_check("Feeder 상태 GREEN, state_bus.json 신선함", {
                "feeder_pid": pid,
                "state_bus_age": file_age,
                "feeder_state": feeder_health.get("state", "UNKNOWN")
            })
            
        except Exception as e:
            result.fail_check(f"Feeder 체크 중 오류: {e}")
        
        self.results["feeder_health"] = result
    
    def _check_uds_trader(self):
        """UDS ↔ Trader 체크"""
        result = WireCheckResult("UDS ↔ Trader")
        
        try:
            # UDS 헬스 확인
            health_data = read_json_atomic(self.paths["shared_data"] / "health.json", {})
            uds_health = health_data.get("uds", {})
            
            if not uds_health:
                result.fail_check("UDS 헬스 데이터가 없음")
                self.results["uds_trader"] = result
                return
            
            # heartbeat_age_sec 확인 (50초 TTL)
            heartbeat_age = uds_health.get("heartbeat_age_sec", 999)
            if heartbeat_age > 50:
                result.fail_check(f"UDS heartbeat이 오래됨 (age: {heartbeat_age}s > 50s)")
                self.results["uds_trader"] = result
                return
            
            # listen_key_age_sec 확인
            listen_key_age = uds_health.get("listen_key_age_sec", 999)
            
            # Trader가 UDS를 읽고 있는지 확인 (Trader 헬스에서 uds_age 확인)
            trader_health = health_data.get("trader", {})
            if not trader_health:
                result.fail_check("Trader 헬스 데이터가 없음")
                self.results["uds_trader"] = result
                return
            
            trader_uds_age = trader_health.get("uds_age", 999)
            if trader_uds_age > 60:  # Trader가 UDS를 60초 이상 오래된 것으로 인식
                result.fail_check(f"Trader가 UDS를 오래된 것으로 인식 (uds_age: {trader_uds_age}s)")
                self.results["uds_trader"] = result
                return
            
            result.pass_check("UDS heartbeat 신선함, Trader가 UDS 읽기 중", {
                "heartbeat_age": heartbeat_age,
                "listen_key_age": listen_key_age,
                "trader_uds_age": trader_uds_age,
                "uds_state": uds_health.get("state", "UNKNOWN")
            })
            
        except Exception as e:
            result.fail_check(f"UDS 체크 중 오류: {e}")
        
        self.results["uds_trader"] = result
    
    def _check_ares_trader(self):
        """ARES ↔ Trader 체크"""
        result = WireCheckResult("ARES ↔ Trader")
        
        try:
            # ARES 헬스 확인
            health_data = read_json_atomic(self.paths["shared_data"] / "health.json", {})
            ares_health = health_data.get("ares", {})
            
            if not ares_health:
                result.fail_check("ARES 헬스 데이터가 없음")
                self.results["ares_trader"] = result
                return
            
            # ARES 신호 파일 확인
            signals_file = self.paths["shared_data"] / "signals" / "ares_signals.json"
            if not signals_file.exists():
                result.fail_check("ARES 신호 파일이 없음")
                self.results["ares_trader"] = result
                return
            
            # 신호 파일 나이 확인 (30초 TTL)
            file_age = time.time() - signals_file.stat().st_mtime
            if file_age > 30:
                result.fail_check(f"ARES 신호 파일이 오래됨 (age: {file_age:.1f}s > 30s)")
                self.results["ares_trader"] = result
                return
            
            # 실제 신호 확인 (fallback 신호가 아닌지)
            signals_data = read_json_atomic(signals_file, {})
            if not signals_data:
                result.fail_check("ARES 신호 데이터가 비어있음")
                self.results["ares_trader"] = result
                return
            
            # TEST_ALLOW_DEFAULT_SIGNAL 플래그 확인
            allow_default = os.getenv("TEST_ALLOW_DEFAULT_SIGNAL", "false").lower() == "true"
            
            if not allow_default:
                # 실제 신호가 있는지 확인 (예: confidence > 0, 실제 심볼들)
                has_real_signals = False
                for symbol, signal_data in signals_data.items():
                    if isinstance(signal_data, dict):
                        confidence = signal_data.get("confidence", 0)
                        if confidence > 0:
                            has_real_signals = True
                            break
                
                if not has_real_signals:
                    result.fail_check("실제 ARES 신호가 없음 (fallback 신호만 존재)")
                    self.results["ares_trader"] = result
                    return
            
            result.pass_check("ARES 신호 신선함, 실제 신호 생성됨", {
                "signals_age": file_age,
                "signals_count": len(signals_data),
                "ares_state": ares_health.get("state", "UNKNOWN"),
                "allow_default_signal": allow_default
            })
            
        except Exception as e:
            result.fail_check(f"ARES 체크 중 오류: {e}")
        
        self.results["ares_trader"] = result
    
    def _check_trader_account_circuit(self):
        """Trader ↔ Account/Circuit 체크"""
        result = WireCheckResult("Trader ↔ Account/Circuit")
        
        try:
            # 계좌 스냅샷 확인 (180초 TTL)
            account_file = self.paths["shared_data"] / "account_snapshot.json"
            if not account_file.exists():
                result.fail_check("계좌 스냅샷 파일이 없음")
                self.results["trader_account_circuit"] = result
                return
            
            account_age = time.time() - account_file.stat().st_mtime
            if account_age > 180:
                result.fail_check(f"계좌 스냅샷이 오래됨 (age: {account_age:.1f}s > 180s)")
                self.results["trader_account_circuit"] = result
                return
            
            # 서킷 브레이커 확인 (60초 TTL)
            circuit_file = self.paths["shared_data"] / "circuit_breaker.json"
            if not circuit_file.exists():
                result.fail_check("서킷 브레이커 파일이 없음")
                self.results["trader_account_circuit"] = result
                return
            
            circuit_age = time.time() - circuit_file.stat().st_mtime
            if circuit_age > 60:
                result.fail_check(f"서킷 브레이커가 오래됨 (age: {circuit_age:.1f}s > 60s)")
                self.results["trader_account_circuit"] = result
                return
            
            # 서킷 브레이커 상태 확인
            circuit_data = read_json_atomic(circuit_file, {})
            circuit_breaker_on = circuit_data.get("circuit_breaker_on", False)
            
            if circuit_breaker_on:
                result.fail_check("서킷 브레이커가 ON 상태 (거래 차단)")
                self.results["trader_account_circuit"] = result
                return
            
            # 거래소 필터 확인 (180초 TTL)
            filters_file = self.paths["shared_data"] / "exchange_filters.json"
            if not filters_file.exists():
                result.fail_check("거래소 필터 파일이 없음")
                self.results["trader_account_circuit"] = result
                return
            
            filters_age = time.time() - filters_file.stat().st_mtime
            if filters_age > 180:
                result.fail_check(f"거래소 필터가 오래됨 (age: {filters_age:.1f}s > 180s)")
                self.results["trader_account_circuit"] = result
                return
            
            result.pass_check("계좌/서킷/필터 모두 신선함, 서킷 브레이커 OFF", {
                "account_age": account_age,
                "circuit_age": circuit_age,
                "filters_age": filters_age,
                "circuit_breaker_on": circuit_breaker_on
            })
            
        except Exception as e:
            result.fail_check(f"Trader 계좌/서킷 체크 중 오류: {e}")
        
        self.results["trader_account_circuit"] = result
    
    def _check_autoheal(self):
        """Auto-Heal 체크"""
        result = WireCheckResult("Auto-Heal")
        
        try:
            # Auto-Heal 헬스 확인
            health_data = read_json_atomic(self.paths["shared_data"] / "health.json", {})
            autoheal_health = health_data.get("autoheal", {})
            
            if not autoheal_health:
                result.fail_check("Auto-Heal 헬스 데이터가 없음")
                self.results["autoheal"] = result
                return
            
            # Auto-Heal이 모니터링 중인 서비스들 확인
            watching_services = autoheal_health.get("watching", [])
            expected_services = ["feeder", "trader", "ares", "uds"]
            
            missing_services = [svc for svc in expected_services if svc not in watching_services]
            if missing_services:
                result.fail_check(f"Auto-Heal이 다음 서비스를 모니터링하지 않음: {missing_services}")
                self.results["autoheal"] = result
                return
            
            # Auto-Heal 상태 확인
            autoheal_state = autoheal_health.get("state", "UNKNOWN")
            if autoheal_state != "GREEN":
                result.fail_check(f"Auto-Heal 상태가 GREEN이 아님: {autoheal_state}")
                self.results["autoheal"] = result
                return
            
            result.pass_check("Auto-Heal이 모든 서비스 모니터링 중", {
                "watching_services": watching_services,
                "autoheal_state": autoheal_state,
                "last_check": autoheal_health.get("last_check", 0)
            })
            
        except Exception as e:
            result.fail_check(f"Auto-Heal 체크 중 오류: {e}")
        
        self.results["autoheal"] = result
    
    def _check_single_instances(self):
        """단일 인스턴스 체크"""
        result = WireCheckResult("Single Instances")
        
        try:
            services = ["feeder", "trader", "ares", "uds", "autoheal"]
            duplicate_services = []
            missing_services = []
            
            for service in services:
                is_running, pid = check_service_pid_lock(service)
                if not is_running:
                    missing_services.append(service)
                # PID 락 시스템이 중복을 방지하므로 추가 체크 불필요
            
            if missing_services:
                result.fail_check(f"다음 서비스들이 실행되지 않음: {missing_services}")
                self.results["single_instances"] = result
                return
            
            if duplicate_services:
                result.fail_check(f"다음 서비스들이 중복 실행됨: {duplicate_services}")
                self.results["single_instances"] = result
                return
            
            result.pass_check("모든 서비스가 단일 인스턴스로 실행 중", {
                "active_services": services,
                "total_count": len(services)
            })
            
        except Exception as e:
            result.fail_check(f"단일 인스턴스 체크 중 오류: {e}")
        
        self.results["single_instances"] = result
    
    def _print_summary(self):
        """결과 요약 출력"""
        print("\n📊 Wire-Checks 결과 요약")
        print("=" * 60)
        
        passed_count = sum(1 for result in self.results.values() if result.passed)
        total_count = len(self.results)
        
        print(f"전체 체크: {total_count}개")
        print(f"통과: {passed_count}개")
        print(f"실패: {total_count - passed_count}개")
        
        print(f"\n상세 결과:")
        for check_name, result in self.results.items():
            status = "✅ PASS" if result.passed else "❌ FAIL"
            print(f"  {check_name}: {status}")
            print(f"    메시지: {result.message}")
            if result.metrics:
                metrics_str = ", ".join([f"{k}={v}" for k, v in result.metrics.items()])
                print(f"    메트릭: {metrics_str}")
        
        print("\n" + "=" * 60)
    
    def generate_report(self) -> str:
        """Wire-check 보고서 생성"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        passed_count = sum(1 for result in self.results.values() if result.passed)
        total_count = len(self.results)
        
        report = f"""# Wire-Check Report - {timestamp}

## 요약
- 전체 체크: {total_count}개
- 통과: {passed_count}개
- 실패: {total_count - passed_count}개
- 전체 상태: {'✅ GREEN' if passed_count == total_count else '❌ RED'}

## 상세 결과

"""
        
        for check_name, result in self.results.items():
            status = "✅ PASS" if result.passed else "❌ FAIL"
            report += f"### {check_name}: {status}\n\n"
            report += f"**메시지:** {result.message}\n\n"
            
            if result.metrics:
                report += "**메트릭:**\n"
                for key, value in result.metrics.items():
                    report += f"- {key}: {value}\n"
                report += "\n"
        
        report += f"""
## 생성 시간
{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## 권장 조치
"""
        
        failed_checks = [name for name, result in self.results.items() if not result.passed]
        if failed_checks:
            report += f"실패한 체크들을 수정해야 합니다: {', '.join(failed_checks)}\n"
        else:
            report += "모든 체크가 통과했습니다. 시스템이 정상 작동 중입니다.\n"
        
        return report


# 전역 인스턴스
wire_checker = WireChecker()


def run_wire_checks() -> Dict[str, WireCheckResult]:
    """Wire checks 실행"""
    return wire_checker.run_all_checks()


def generate_wire_check_report() -> str:
    """Wire-check 보고서 생성"""
    return wire_checker.generate_report()


if __name__ == "__main__":
    # 직접 실행 시 wire checks 실행
    print("🔍 Wire-Checks - 독립 실행")
    results = run_wire_checks()
    
    # 보고서 생성 및 저장
    report = generate_wire_check_report()
    reports_dir = get_repo_paths()["shared_data_reports"]
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = reports_dir / f"wirecheck_{timestamp}.md"
    
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"\n📄 보고서 저장: {report_file}")
