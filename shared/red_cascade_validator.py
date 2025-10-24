#!/usr/bin/env python3
"""
RED Cascade Validator - Phase 5
Fault injection & propagation validation
"""

import json
import os
import time
import signal
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import sys

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from shared.environment_guardrails import get_repo_paths, check_service_pid_lock, remove_service_pid_lock
from shared.atomic_io import read_json_atomic, write_json_atomic, append_alert_atomic
from shared.wire_checks import WireChecker


class RedCascadeValidator:
    """RED Cascade 검증 시스템"""
    
    def __init__(self):
        self.paths = get_repo_paths()
        self.wire_checker = WireChecker()
        self.fault_scenarios = self._define_fault_scenarios()
        self.test_results = {}
        
    def _define_fault_scenarios(self) -> Dict[str, Dict[str, Any]]:
        """결함 시나리오 정의"""
        return {
            "feeder_crash": {
                "name": "Feeder Crash",
                "description": "Feeder 프로세스 강제 종료",
                "injection": self._inject_feeder_crash,
                "recovery": self._recover_feeder,
                "expected_effects": [
                    "Health feeder=RED within ≤10s",
                    "Trader halts entries",
                    "Auto-Heal restarts Feeder",
                    "System back to GREEN"
                ]
            },
            
            "uds_lapse": {
                "name": "UDS Heartbeat Lapse",
                "description": "UDS heartbeat 중단",
                "injection": self._inject_uds_lapse,
                "recovery": self._recover_uds,
                "expected_effects": [
                    "heartbeat_age_sec > 50s",
                    "Trader YELLOW (throttled)",
                    "Trader blocks entries",
                    "Restart UDS → GREEN"
                ]
            },
            
            "account_snapshot_stale": {
                "name": "Account Snapshot Stale",
                "description": "계좌 스냅샷 갱신 중단",
                "injection": self._inject_account_snapshot_stale,
                "recovery": self._recover_account_snapshot,
                "expected_effects": [
                    "account_snapshot.json age > 180s",
                    "Trader YELLOW and block entries",
                    "Resume → GREEN"
                ]
            },
            
            "health_file_blocked": {
                "name": "Health File Write Failure",
                "description": "헬스 파일 쓰기 실패 시뮬레이션",
                "injection": self._inject_health_file_blocked,
                "recovery": self._recover_health_file,
                "expected_effects": [
                    "Atomic helper retries",
                    "No crash",
                    "Single ERROR alert",
                    "System continues"
                ]
            },
            
            "order_failure_streak": {
                "name": "Order Failure Streak",
                "description": "연속 주문 실패",
                "injection": self._inject_order_failure_streak,
                "recovery": self._recover_order_failures,
                "expected_effects": [
                    "2-3 consecutive rejections on one symbol",
                    "Trader marks failsafe monitor-only",
                    "Alert emitted",
                    "Others unaffected"
                ]
            },
            
            "circuit_breaker_toggle": {
                "name": "Circuit Breaker Toggle",
                "description": "서킷 브레이커 ON/OFF",
                "injection": self._inject_circuit_breaker_on,
                "recovery": self._recover_circuit_breaker,
                "expected_effects": [
                    "Toggle ON → Trader blocks new entries",
                    "Toggle OFF → Resume trading"
                ]
            }
        }
    
    def validate_all_red_cascades(self) -> Tuple[bool, Dict[str, Any]]:
        """모든 RED Cascade 시나리오 검증"""
        print("🔴 RED Cascades 검증 시작")
        print("=" * 60)
        
        overall_success = True
        scenario_results = {}
        
        for scenario_id, scenario in self.fault_scenarios.items():
            print(f"\n🧪 시나리오: {scenario['name']}")
            print(f"   설명: {scenario['description']}")
            
            try:
                success, details = self._run_fault_scenario(scenario_id, scenario)
                scenario_results[scenario_id] = {
                    "success": success,
                    "details": details
                }
                
                if success:
                    print(f"   ✅ {scenario['name']} 검증 성공")
                else:
                    print(f"   ❌ {scenario['name']} 검증 실패")
                    overall_success = False
                
            except Exception as e:
                print(f"   ❌ {scenario['name']} 검증 중 오류: {e}")
                scenario_results[scenario_id] = {
                    "success": False,
                    "details": {"error": str(e)}
                }
                overall_success = False
            
            # 시나리오 간 대기
            print("   ⏳ 다음 시나리오까지 10초 대기...")
            time.sleep(10)
        
        # 전체 결과 요약
        print(f"\n📊 RED Cascades 검증 완료")
        print(f"전체 성공: {'✅' if overall_success else '❌'}")
        
        passed_count = sum(1 for result in scenario_results.values() if result["success"])
        total_count = len(scenario_results)
        print(f"시나리오 통과: {passed_count}/{total_count}")
        
        return overall_success, {
            "overall_success": overall_success,
            "scenario_results": scenario_results,
            "passed_count": passed_count,
            "total_count": total_count
        }
    
    def _run_fault_scenario(self, scenario_id: str, scenario: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """개별 결함 시나리오 실행"""
        results = {
            "injection_success": False,
            "effects_observed": [],
            "recovery_success": False,
            "expected_effects": scenario["expected_effects"],
            "errors": []
        }
        
        try:
            # 1. 초기 상태 확인 (GREEN)
            print("     1️⃣ 초기 상태 확인...")
            initial_wire_results = self.wire_checker.run_all_checks()
            initial_green = all(result.passed for result in initial_wire_results.values())
            
            if not initial_green:
                print("     ⚠️ 초기 상태가 GREEN이 아님 - 시나리오 건너뛰기")
                results["errors"].append("Initial state not GREEN")
                return False, results
            
            print("     ✅ 초기 상태 GREEN 확인")
            
            # 2. 결함 주입
            print("     2️⃣ 결함 주입...")
            injection_success = scenario["injection"]()
            results["injection_success"] = injection_success
            
            if not injection_success:
                results["errors"].append("Fault injection failed")
                return False, results
            
            print("     ✅ 결함 주입 성공")
            
            # 3. 효과 관찰 (30초 대기)
            print("     3️⃣ 효과 관찰 (30초)...")
            effects = self._observe_fault_effects(scenario_id, 30)
            results["effects_observed"] = effects
            
            # 4. 예상 효과와 비교
            expected_effects = scenario["expected_effects"]
            effects_match = self._validate_expected_effects(effects, expected_effects)
            
            if not effects_match:
                results["errors"].append("Expected effects not observed")
                print("     ❌ 예상 효과가 관찰되지 않음")
            else:
                print("     ✅ 예상 효과 관찰됨")
            
            # 5. 복구
            print("     4️⃣ 복구...")
            recovery_success = scenario["recovery"]()
            results["recovery_success"] = recovery_success
            
            if not recovery_success:
                results["errors"].append("Recovery failed")
                print("     ❌ 복구 실패")
            else:
                print("     ✅ 복구 성공")
            
            # 6. 최종 상태 확인 (복구 후 10초 대기)
            print("     5️⃣ 최종 상태 확인...")
            time.sleep(10)
            final_wire_results = self.wire_checker.run_all_checks()
            final_green = all(result.passed for result in final_wire_results.values())
            
            if not final_green:
                results["errors"].append("Final state not GREEN after recovery")
                print("     ❌ 복구 후 상태가 GREEN이 아님")
            else:
                print("     ✅ 복구 후 상태 GREEN 확인")
            
            # 전체 성공 판단
            overall_success = (injection_success and effects_match and recovery_success and final_green)
            
            return overall_success, results
            
        except Exception as e:
            results["errors"].append(f"Scenario execution error: {e}")
            return False, results
    
    def _observe_fault_effects(self, scenario_id: str, duration_seconds: int) -> List[str]:
        """결함 효과 관찰"""
        effects = []
        start_time = time.time()
        
        print(f"       관찰 중... ({duration_seconds}초)")
        
        while time.time() - start_time < duration_seconds:
            try:
                # Wire checks로 상태 확인
                wire_results = self.wire_checker.run_all_checks()
                
                # 실패한 체크들 수집
                failed_checks = []
                for check_name, result in wire_results.items():
                    if not result.passed:
                        failed_checks.append(f"{check_name}: {result.message}")
                
                # 헬스 상태 확인
                health_data = read_json_atomic(self.paths["shared_data"] / "health.json", {})
                red_components = []
                yellow_components = []
                
                for component, health in health_data.items():
                    if isinstance(health, dict):
                        state = health.get("state", "UNKNOWN")
                        if state == "RED":
                            red_components.append(component)
                        elif state == "YELLOW":
                            yellow_components.append(component)
                
                # 효과 기록
                if red_components:
                    effects.append(f"Components RED: {', '.join(red_components)}")
                if yellow_components:
                    effects.append(f"Components YELLOW: {', '.join(yellow_components)}")
                if failed_checks:
                    effects.append(f"Failed checks: {len(failed_checks)}")
                
                # 알림 확인
                alerts = read_ndjson_lines(self.paths["shared_data"] / "alerts.ndjson", max_lines=5)
                if alerts:
                    recent_alerts = [alert for alert in alerts if alert.get("timestamp", 0) > start_time]
                    if recent_alerts:
                        effects.append(f"New alerts: {len(recent_alerts)}")
                
                time.sleep(2)  # 2초마다 확인
                
            except Exception as e:
                effects.append(f"Observation error: {e}")
                time.sleep(5)
        
        return list(set(effects))  # 중복 제거
    
    def _validate_expected_effects(self, observed_effects: List[str], expected_effects: List[str]) -> bool:
        """예상 효과와 관찰된 효과 비교"""
        # 간단한 키워드 매칭
        observed_text = " ".join(observed_effects).lower()
        
        matches = 0
        for expected in expected_effects:
            expected_lower = expected.lower()
            # 키워드 추출
            keywords = []
            if "red" in expected_lower:
                keywords.append("red")
            if "yellow" in expected_lower:
                keywords.append("yellow")
            if "block" in expected_lower:
                keywords.append("block")
            if "alert" in expected_lower:
                keywords.append("alert")
            if "error" in expected_lower:
                keywords.append("error")
            
            # 키워드가 관찰된 효과에 있는지 확인
            if any(keyword in observed_text for keyword in keywords):
                matches += 1
        
        # 50% 이상 매칭되면 성공
        return matches >= len(expected_effects) * 0.5
    
    # 결함 주입 메서드들
    def _inject_feeder_crash(self) -> bool:
        """Feeder 크래시 주입"""
        try:
            is_running, pid = check_service_pid_lock("feeder")
            if not is_running:
                print("       Feeder가 실행되지 않음")
                return False
            
            # 프로세스 종료
            try:
                os.kill(pid, signal.SIGTERM)
                print(f"       Feeder 프로세스 종료 (PID: {pid})")
                time.sleep(2)
                return True
            except ProcessLookupError:
                print("       Feeder 프로세스가 이미 종료됨")
                return True
                
        except Exception as e:
            print(f"       Feeder 크래시 주입 실패: {e}")
            return False
    
    def _recover_feeder(self) -> bool:
        """Feeder 복구"""
        try:
            # PID 락 제거
            remove_service_pid_lock("feeder")
            
            # Auto-Heal이 자동으로 복구할 때까지 대기
            print("       Auto-Heal 복구 대기 중...")
            time.sleep(15)
            
            # Feeder가 다시 실행되는지 확인
            is_running, _ = check_service_pid_lock("feeder")
            return is_running
            
        except Exception as e:
            print(f"       Feeder 복구 실패: {e}")
            return False
    
    def _inject_uds_lapse(self) -> bool:
        """UDS heartbeat 중단"""
        try:
            # UDS 프로세스 찾기 및 종료
            is_running, pid = check_service_pid_lock("uds")
            if not is_running:
                print("       UDS가 실행되지 않음")
                return False
            
            os.kill(pid, signal.SIGTERM)
            print(f"       UDS 프로세스 종료 (PID: {pid})")
            return True
            
        except Exception as e:
            print(f"       UDS 중단 실패: {e}")
            return False
    
    def _recover_uds(self) -> bool:
        """UDS 복구"""
        try:
            remove_service_pid_lock("uds")
            time.sleep(10)
            is_running, _ = check_service_pid_lock("uds")
            return is_running
            
        except Exception as e:
            print(f"       UDS 복구 실패: {e}")
            return False
    
    def _inject_account_snapshot_stale(self) -> bool:
        """계좌 스냅샷 stale 상태 만들기"""
        try:
            # 계좌 스냅샷 파일을 과거 시간으로 설정
            account_file = self.paths["shared_data"] / "account_snapshot.json"
            if account_file.exists():
                # 파일 수정 시간을 5분 전으로 설정
                old_time = time.time() - 300
                os.utime(account_file, (old_time, old_time))
                print("       계좌 스냅샷을 stale 상태로 설정")
                return True
            else:
                print("       계좌 스냅샷 파일이 없음")
                return False
                
        except Exception as e:
            print(f"       계좌 스냅샷 stale 주입 실패: {e}")
            return False
    
    def _recover_account_snapshot(self) -> bool:
        """계좌 스냅샷 복구"""
        try:
            # 파일 시간을 현재로 복구
            account_file = self.paths["shared_data"] / "account_snapshot.json"
            if account_file.exists():
                current_time = time.time()
                os.utime(account_file, (current_time, current_time))
                print("       계좌 스냅샷 시간 복구")
                return True
            return False
            
        except Exception as e:
            print(f"       계좌 스냅샷 복구 실패: {e}")
            return False
    
    def _inject_health_file_blocked(self) -> bool:
        """헬스 파일 쓰기 차단"""
        try:
            health_file = self.paths["shared_data"] / "health.json"
            
            # 파일을 읽기 전용으로 설정
            if health_file.exists():
                health_file.chmod(0o444)  # 읽기 전용
                print("       헬스 파일을 읽기 전용으로 설정")
                return True
            else:
                print("       헬스 파일이 없음")
                return False
                
        except Exception as e:
            print(f"       헬스 파일 차단 실패: {e}")
            return False
    
    def _recover_health_file(self) -> bool:
        """헬스 파일 복구"""
        try:
            health_file = self.paths["shared_data"] / "health.json"
            
            # 파일 권한 복구
            health_file.chmod(0o644)  # 읽기/쓰기 권한
            print("       헬스 파일 권한 복구")
            return True
            
        except Exception as e:
            print(f"       헬스 파일 복구 실패: {e}")
            return False
    
    def _inject_order_failure_streak(self) -> bool:
        """주문 실패 연속 주입"""
        try:
            # 서킷 브레이커를 ON으로 설정하여 주문 차단
            circuit_data = {
                "active": True,
                "reason": "RED_CASCADE_TEST",
                "activated_at": time.time(),
                "timestamp": time.time()
            }
            
            circuit_file = self.paths["shared_data"] / "circuit_breaker.json"
            write_json_atomic(circuit_file, circuit_data)
            print("       서킷 브레이커 ON으로 설정")
            return True
            
        except Exception as e:
            print(f"       주문 실패 주입 실패: {e}")
            return False
    
    def _recover_order_failures(self) -> bool:
        """주문 실패 복구"""
        try:
            # 서킷 브레이커를 OFF로 설정
            circuit_data = {
                "active": False,
                "reason": "RED_CASCADE_TEST_RECOVERY",
                "deactivated_at": time.time(),
                "timestamp": time.time()
            }
            
            circuit_file = self.paths["shared_data"] / "circuit_breaker.json"
            write_json_atomic(circuit_file, circuit_data)
            print("       서킷 브레이커 OFF로 설정")
            return True
            
        except Exception as e:
            print(f"       주문 실패 복구 실패: {e}")
            return False
    
    def _inject_circuit_breaker_on(self) -> bool:
        """서킷 브레이커 ON"""
        return self._inject_order_failure_streak()  # 같은 로직
    
    def _recover_circuit_breaker(self) -> bool:
        """서킷 브레이커 복구"""
        return self._recover_order_failures()  # 같은 로직
    
    def generate_red_cascade_report(self, results: Dict[str, Any]) -> str:
        """RED Cascade 보고서 생성"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        status = "✅ SUCCESS" if results["overall_success"] else "❌ FAILED"
        
        report = f"""# RED Cascade Validation Report - {timestamp}

## 요약
- **전체 상태**: {status}
- **시나리오 통과**: {results['passed_count']}/{results['total_count']}

## 상세 결과

"""
        
        for scenario_id, result in results["scenario_results"].items():
            scenario = self.fault_scenarios[scenario_id]
            status_icon = "✅" if result["success"] else "❌"
            
            report += f"### {scenario['name']}: {status_icon}\n\n"
            report += f"**설명**: {scenario['description']}\n\n"
            
            if result["success"]:
                report += "**결과**: 검증 성공\n\n"
            else:
                report += "**결과**: 검증 실패\n\n"
                
                if "details" in result and "errors" in result["details"]:
                    report += "**오류**:\n"
                    for error in result["details"]["errors"]:
                        report += f"- {error}\n"
                    report += "\n"
            
            report += "**예상 효과**:\n"
            for effect in scenario["expected_effects"]:
                report += f"- {effect}\n"
            report += "\n"
        
        report += f"""
## 생성 시간
{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## 권장 조치
"""
        
        if results['overall_success']:
            report += "모든 RED Cascade 시나리오가 성공적으로 검증되었습니다. 시스템이 결함 상황에서도 안전하게 동작합니다.\n"
        else:
            report += "일부 RED Cascade 시나리오가 실패했습니다. 다음 사항을 확인하세요:\n"
            for scenario_id, result in results["scenario_results"].items():
                if not result["success"]:
                    scenario = self.fault_scenarios[scenario_id]
                    report += f"- {scenario['name']}: {result.get('details', {}).get('errors', ['Unknown error'])}\n"
        
        return report


# 전역 인스턴스
red_cascade_validator = RedCascadeValidator()


def validate_red_cascades() -> Tuple[bool, Dict[str, Any]]:
    """RED Cascade 검증 실행"""
    return red_cascade_validator.validate_all_red_cascades()


def generate_red_cascade_report(results: Dict[str, Any]) -> str:
    """RED Cascade 보고서 생성"""
    return red_cascade_validator.generate_red_cascade_report(results)


if __name__ == "__main__":
    # 직접 실행 시 RED Cascade 검증
    print("🔴 RED Cascade Validator - 독립 실행")
    print("⚠️ 경고: 이 테스트는 실제 시스템에 결함을 주입합니다!")
    print("계속하시겠습니까? (y/N): ", end="")
    
    response = input().strip().lower()
    if response != 'y':
        print("테스트가 취소되었습니다.")
        sys.exit(0)
    
    success, results = validate_red_cascades()
    
    # 보고서 생성 및 저장
    report = generate_red_cascade_report(results)
    reports_dir = get_repo_paths()["shared_data_reports"]
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = reports_dir / f"red_cascade_{timestamp}.md"
    
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"\n📄 보고서 저장: {report_file}")
    
    if success:
        print("\n🎉 RED Cascade 검증 완료!")
    else:
        print("\n❌ RED Cascade 검증 실패 - 시스템 강화 필요")
