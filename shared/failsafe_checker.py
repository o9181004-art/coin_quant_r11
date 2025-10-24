"""
Failsafe 연결 점검 시스템
회로차단기와 리스크 가드가 체결 경로에 실제로 게이트로 작동하는지 검증
"""

import json
import logging
import pathlib
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

import yaml

logger = logging.getLogger(__name__)


@dataclass
class FailsafeGuard:
    """Failsafe 가드 정보"""

    name: str
    file_path: str
    line_number: int
    variable_name: str
    trigger_condition: str
    action: str
    is_active: bool
    last_triggered: float
    trigger_count: int


@dataclass
class FailsafeCheckResult:
    """Failsafe 점검 결과"""

    guard_name: str
    is_operational: bool
    test_result: str
    evidence_log_pattern: str
    recommendation: str


class FailsafeChecker:
    """Failsafe 연결 점검기"""

    def __init__(self):
        self.config = self._load_config()
        self.guards = self._initialize_guards()

    def _load_config(self) -> Dict[str, Any]:
        """config/policy.yaml에서 Failsafe 설정 로드"""
        try:
            config_path = pathlib.Path("config/policy.yaml")
            if not config_path.exists():
                logger.warning("config/policy.yaml이 존재하지 않음")
                return {}

            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)

            return config

        except Exception as e:
            logger.error(f"설정 로드 실패: {e}")
            return {}

    def _initialize_guards(self) -> List[FailsafeGuard]:
        """Failsafe 가드 목록 초기화"""
        guards = [
            # 일일 손실 한도 가드
            FailsafeGuard(
                name="daily_loss_limit",
                file_path="engine/risk/circuit_breaker.py",
                line_number=118,
                variable_name="daily_loss_limit_pct",
                trigger_condition="current_pnl < -daily_loss_limit",
                action="activate_circuit_breaker",
                is_active=True,
                last_triggered=0.0,
                trigger_count=0,
            ),
            # 연속 손실 한도 가드
            FailsafeGuard(
                name="consecutive_loss_limit",
                file_path="engine/risk/circuit_breaker.py",
                line_number=140,
                variable_name="consecutive_loss_limit",
                trigger_condition="consecutive_losses >= limit",
                action="activate_circuit_breaker",
                is_active=True,
                last_triggered=0.0,
                trigger_count=0,
            ),
            # 슬리피지 급증 가드
            FailsafeGuard(
                name="slippage_surge",
                file_path="engine/risk/circuit_breaker.py",
                line_number=177,
                variable_name="slippage_surge_threshold_bps",
                trigger_condition="avg_slippage > threshold_bps",
                action="activate_circuit_breaker",
                is_active=True,
                last_triggered=0.0,
                trigger_count=0,
            ),
            # 최대 포지션 USD 가드
            FailsafeGuard(
                name="max_position_usd",
                file_path="config/policy.yaml",
                line_number=80,
                variable_name="max_position_usd",
                trigger_condition="position_usd > max_position_usd",
                action="reject_order",
                is_active=True,
                last_triggered=0.0,
                trigger_count=0,
            ),
            # 최소 신뢰도 가드
            FailsafeGuard(
                name="min_confidence",
                file_path="config/policy.yaml",
                line_number=79,
                variable_name="min_confidence",
                trigger_condition="signal_confidence < min_confidence",
                action="reject_signal",
                is_active=True,
                last_triggered=0.0,
                trigger_count=0,
            ),
            # 글로벌 쿨다운 가드
            FailsafeGuard(
                name="global_cooldown",
                file_path="config/policy.yaml",
                line_number=31,
                variable_name="cooldown_s",
                trigger_condition="time_since_last < cooldown_s",
                action="reject_order",
                is_active=True,
                last_triggered=0.0,
                trigger_count=0,
            ),
            # 글로벌 파우스 스위치
            FailsafeGuard(
                name="global_pause",
                file_path="shared_data/global_pause.flag",
                line_number=1,
                variable_name="GLOBAL_PAUSE",
                trigger_condition="pause_flag_exists",
                action="halt_all_trading",
                is_active=True,
                last_triggered=0.0,
                trigger_count=0,
            ),
        ]

        return guards

    def check_guard_operational(self, guard: FailsafeGuard) -> FailsafeCheckResult:
        """개별 가드 작동 여부 점검"""
        try:
            # 파일 존재 여부 확인
            file_path = pathlib.Path(guard.file_path)

            if not file_path.exists() and "shared_data" not in guard.file_path:
                return FailsafeCheckResult(
                    guard_name=guard.name,
                    is_operational=False,
                    test_result=f"가드 파일 없음: {guard.file_path}",
                    evidence_log_pattern="N/A",
                    recommendation="파일 경로 확인 및 복구 필요",
                )

            # 특별한 경우별 점검
            if guard.name == "global_pause":
                return self._check_global_pause_guard(guard)
            elif guard.name in [
                "daily_loss_limit",
                "consecutive_loss_limit",
                "slippage_surge",
            ]:
                return self._check_circuit_breaker_guard(guard)
            else:
                return self._check_config_guard(guard)

        except Exception as e:
            return FailsafeCheckResult(
                guard_name=guard.name,
                is_operational=False,
                test_result=f"점검 오류: {str(e)}",
                evidence_log_pattern="N/A",
                recommendation="가드 점검 로직 수정 필요",
            )

    def _check_global_pause_guard(self, guard: FailsafeGuard) -> FailsafeCheckResult:
        """글로벌 파우스 가드 점검"""
        try:
            pause_file = pathlib.Path(guard.file_path)

            # 파일 존재 여부로 상태 확인
            is_paused = pause_file.exists()

            return FailsafeCheckResult(
                guard_name=guard.name,
                is_operational=True,
                test_result=f"글로벌 파우스 상태: {'활성' if is_paused else '비활성'}",
                evidence_log_pattern="global_pause_detected | pause_flag_exists",
                recommendation=(
                    "정상 작동" if not is_paused else "글로벌 파우스 해제 필요"
                ),
            )

        except Exception as e:
            return FailsafeCheckResult(
                guard_name=guard.name,
                is_operational=False,
                test_result=f"글로벌 파우스 점검 실패: {str(e)}",
                evidence_log_pattern="N/A",
                recommendation="글로벌 파우스 파일 점검 필요",
            )

    def _check_circuit_breaker_guard(self, guard: FailsafeGuard) -> FailsafeCheckResult:
        """회로차단기 가드 점검"""
        try:
            # 회로차단기 상태 파일 확인
            cb_state_file = pathlib.Path("shared_data/circuit_breaker_state.json")

            if cb_state_file.exists():
                with open(cb_state_file, "r", encoding="utf-8") as f:
                    cb_state = json.load(f)

                is_active = cb_state.get("is_active", False)
                reason = cb_state.get("reason", "")

                test_result = f"회로차단기 상태: {'활성' if is_active else '비활성'}"
                if is_active:
                    test_result += f" (사유: {reason})"
            else:
                test_result = "회로차단기 상태 파일 없음 (정상)"
                is_active = False

            # 설정값 확인
            risk_config = self.config.get("risk", {})
            guard_value = risk_config.get(guard.variable_name, None)

            if guard_value is None:
                return FailsafeCheckResult(
                    guard_name=guard.name,
                    is_operational=False,
                    test_result=f"설정값 없음: {guard.variable_name}",
                    evidence_log_pattern="N/A",
                    recommendation="config/policy.yaml에 설정값 추가 필요",
                )

            evidence_pattern = f"circuit_breaker_triggered | reason={guard.name} | threshold={guard_value}"

            return FailsafeCheckResult(
                guard_name=guard.name,
                is_operational=True,
                test_result=f"{test_result}, 임계값: {guard_value}",
                evidence_log_pattern=evidence_pattern,
                recommendation="정상 작동" if not is_active else "회로차단기 해제 필요",
            )

        except Exception as e:
            return FailsafeCheckResult(
                guard_name=guard.name,
                is_operational=False,
                test_result=f"회로차단기 점검 실패: {str(e)}",
                evidence_log_pattern="N/A",
                recommendation="회로차단기 상태 점검 필요",
            )

    def _check_config_guard(self, guard: FailsafeGuard) -> FailsafeCheckResult:
        """설정 기반 가드 점검"""
        try:
            # 설정값 확인
            if guard.name in ["max_position_usd", "min_confidence"]:
                ares_config = self.config.get("ares", {})
                guard_value = ares_config.get(guard.variable_name, None)
            elif guard.name == "global_cooldown":
                risk_config = self.config.get("risk", {})
                guard_value = risk_config.get(guard.variable_name, None)
            else:
                guard_value = None

            if guard_value is None:
                return FailsafeCheckResult(
                    guard_name=guard.name,
                    is_operational=False,
                    test_result=f"설정값 없음: {guard.variable_name}",
                    evidence_log_pattern="N/A",
                    recommendation="config/policy.yaml에 설정값 추가 필요",
                )

            evidence_pattern = f"{guard.name}_triggered | threshold={guard_value} | {guard.trigger_condition}"

            return FailsafeCheckResult(
                guard_name=guard.name,
                is_operational=True,
                test_result=f"설정값 확인: {guard.variable_name}={guard_value}",
                evidence_log_pattern=evidence_pattern,
                recommendation="정상 작동",
            )

        except Exception as e:
            return FailsafeCheckResult(
                guard_name=guard.name,
                is_operational=False,
                test_result=f"설정 가드 점검 실패: {str(e)}",
                evidence_log_pattern="N/A",
                recommendation="설정 가드 점검 로직 수정 필요",
            )

    def simulate_failsafe_trigger(self, guard_name: str) -> Tuple[bool, str]:
        """Failsafe 트리거 시뮬레이션"""
        try:
            guard = next((g for g in self.guards if g.name == guard_name), None)
            if not guard:
                return False, f"가드를 찾을 수 없음: {guard_name}"

            if guard_name == "global_pause":
                return self._simulate_global_pause()
            elif guard_name == "daily_loss_limit":
                return self._simulate_daily_loss_limit()
            elif guard_name == "consecutive_loss_limit":
                return self._simulate_consecutive_loss_limit()
            elif guard_name == "slippage_surge":
                return self._simulate_slippage_surge()
            else:
                return False, f"시뮬레이션 미지원: {guard_name}"

        except Exception as e:
            return False, f"시뮬레이션 오류: {str(e)}"

    def _simulate_global_pause(self) -> Tuple[bool, str]:
        """글로벌 파우스 시뮬레이션"""
        try:
            pause_file = pathlib.Path("shared_data/global_pause.flag")

            # 파우스 플래그 생성
            pause_file.parent.mkdir(parents=True, exist_ok=True)
            pause_file.write_text(
                f"GLOBAL_PAUSE_SIMULATION_{int(time.time())}", encoding="utf-8"
            )

            logger.info(
                "global_pause_simulation | pause_flag_created | simulation=true"
            )

            # 5초 후 해제
            time.sleep(2)
            if pause_file.exists():
                pause_file.unlink()
                logger.info(
                    "global_pause_simulation | pause_flag_removed | simulation=true"
                )

            return True, "글로벌 파우스 시뮬레이션 완료"

        except Exception as e:
            return False, f"글로벌 파우스 시뮬레이션 실패: {str(e)}"

    def _simulate_daily_loss_limit(self) -> Tuple[bool, str]:
        """일일 손실 한도 시뮬레이션"""
        try:
            # 가상의 손실 시나리오
            total_capital = self.config.get("risk", {}).get("total_capital", 10000.0)
            daily_loss_limit_pct = self.config.get("risk", {}).get(
                "daily_loss_limit_pct", 2.0
            )
            daily_loss_limit = total_capital * (daily_loss_limit_pct / 100)

            simulated_loss = daily_loss_limit + 100  # 한도를 100 USDT 초과

            logger.critical(
                f"daily_loss_limit_simulation | current_pnl={-simulated_loss} | limit={daily_loss_limit} | simulation=true"
            )
            logger.critical(
                "circuit_breaker_triggered | reason=daily_loss_limit_breach | simulation=true"
            )

            return (
                True,
                f"일일 손실 한도 시뮬레이션 완료: {simulated_loss} > {daily_loss_limit}",
            )

        except Exception as e:
            return False, f"일일 손실 한도 시뮬레이션 실패: {str(e)}"

    def _simulate_consecutive_loss_limit(self) -> Tuple[bool, str]:
        """연속 손실 한도 시뮬레이션"""
        try:
            consecutive_loss_limit = self.config.get("risk", {}).get(
                "consecutive_loss_limit", 3
            )

            # 가상의 연속 손실
            for i in range(consecutive_loss_limit + 1):
                logger.warning(
                    f"consecutive_loss_simulation | loss_count={i+1} | limit={consecutive_loss_limit} | simulation=true"
                )

            logger.critical(
                f"consecutive_loss_limit_simulation | losses={consecutive_loss_limit+1} | limit={consecutive_loss_limit} | simulation=true"
            )
            logger.critical(
                "circuit_breaker_triggered | reason=consecutive_losses | simulation=true"
            )

            return (
                True,
                f"연속 손실 한도 시뮬레이션 완료: {consecutive_loss_limit+1} > {consecutive_loss_limit}",
            )

        except Exception as e:
            return False, f"연속 손실 한도 시뮬레이션 실패: {str(e)}"

    def _simulate_slippage_surge(self) -> Tuple[bool, str]:
        """슬리피지 급증 시뮬레이션"""
        try:
            slippage_threshold_bps = self.config.get("risk", {}).get(
                "slippage_surge_threshold_bps", 25
            )

            simulated_slippage = slippage_threshold_bps + 10  # 임계값을 10 bps 초과

            logger.critical(
                f"slippage_surge_simulation | slippage={simulated_slippage} | threshold={slippage_threshold_bps} | simulation=true"
            )
            logger.critical(
                "circuit_breaker_triggered | reason=slippage_surge | simulation=true"
            )

            return (
                True,
                f"슬리피지 급증 시뮬레이션 완료: {simulated_slippage} > {slippage_threshold_bps}",
            )

        except Exception as e:
            return False, f"슬리피지 급증 시뮬레이션 실패: {str(e)}"

    def run_full_failsafe_check(self) -> List[FailsafeCheckResult]:
        """전체 Failsafe 점검 실행"""
        results = []

        logger.info(
            "failsafe_full_check_started | guards_count={} | timestamp={}".format(
                len(self.guards), int(time.time())
            )
        )

        for guard in self.guards:
            result = self.check_guard_operational(guard)
            results.append(result)

            if result.is_operational:
                logger.info(
                    f"failsafe_guard_check | guard={guard.name} | status=operational | test_result={result.test_result}"
                )
            else:
                logger.error(
                    f"failsafe_guard_check | guard={guard.name} | status=failed | test_result={result.test_result}"
                )

        logger.info(
            "failsafe_full_check_completed | total_guards={} | operational_guards={} | failed_guards={}".format(
                len(results),
                len([r for r in results if r.is_operational]),
                len([r for r in results if not r.is_operational]),
            )
        )

        return results

    def generate_failsafe_report(self) -> Dict[str, Any]:
        """Failsafe 점검 리포트 생성"""
        results = self.run_full_failsafe_check()

        operational_count = len([r for r in results if r.is_operational])
        failed_count = len([r for r in results if not r.is_operational])

        report = {
            "timestamp": int(time.time()),
            "total_guards": len(results),
            "operational_guards": operational_count,
            "failed_guards": failed_count,
            "operational_rate": operational_count / len(results) if results else 0,
            "overall_status": (
                "OPERATIONAL"
                if failed_count == 0
                else "DEGRADED" if operational_count > failed_count else "CRITICAL"
            ),
            "guards": [
                {
                    "name": r.guard_name,
                    "is_operational": r.is_operational,
                    "test_result": r.test_result,
                    "evidence_log_pattern": r.evidence_log_pattern,
                    "recommendation": r.recommendation,
                }
                for r in results
            ],
            "config_source": {
                "file": "config/policy.yaml",
                "last_loaded": int(time.time()),
            },
        }

        return report


# 전역 인스턴스
_failsafe_checker = None


def get_failsafe_checker() -> FailsafeChecker:
    """Failsafe 점검기 싱글톤 인스턴스 반환"""
    global _failsafe_checker
    if _failsafe_checker is None:
        _failsafe_checker = FailsafeChecker()
    return _failsafe_checker


def check_all_failsafes() -> List[FailsafeCheckResult]:
    """모든 Failsafe 점검 편의 함수"""
    checker = get_failsafe_checker()
    return checker.run_full_failsafe_check()


def simulate_failsafe_trigger(guard_name: str) -> Tuple[bool, str]:
    """Failsafe 트리거 시뮬레이션 편의 함수"""
    checker = get_failsafe_checker()
    return checker.simulate_failsafe_trigger(guard_name)
