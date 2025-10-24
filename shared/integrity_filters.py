"""
무결성 필터 시스템
실시간으로 거래 무결성을 보장하는 7가지 필터
"""

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Set, Tuple

logger = logging.getLogger(__name__)


@dataclass
class FilterResult:
    """필터 결과"""

    passed: bool
    filter_name: str
    reason: str
    action: str  # "PASS", "BLOCK", "WARN", "MOCK_EXECUTE"
    mock_executable: bool = False  # 모의계좌에서 실행 가능한지 여부


class IntegrityFilters:
    """무결성 필터 시스템"""

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}

        # 중복 거래 추적
        self.duplicate_tracker: Set[str] = set()

        # 글로벌 쿨다운 추적
        self.cooldown_tracker: Dict[str, float] = {}

        # 전략 레지스트리
        self.strategy_registry = {
            "trend_multi_tf",
            "bb_mean_revert_v2",
            "volspike_scalper_v2",
            "carry_funding",
            "pairs_spread",
            "ensemble",
            "default",
            "ARES",
            "Manual",
        }

        # 설정값
        self.capital_limit_pct = self.config.get("capital_limit_pct", 30.0)  # 30%
        self.min_expected_return_pct = self.config.get(
            "min_expected_return_pct", 0.25
        )  # 0.25%
        self.global_cooldown_sec = self.config.get("global_cooldown_sec", 60)  # 60초
        self.duplicate_window_sec = self.config.get("duplicate_window_sec", 2)  # ±2초

        # 모의계좌 모드 설정
        self.mock_mode = self.config.get("mock_mode", True)  # 기본값: 모의계좌 모드
        self.fail_close_mode = self.config.get(
            "fail_close_mode", False
        )  # 기본값: FAIL-CLOSE 비활성화

    def filter_1_strategy_unidentified(
        self, trade_data: Dict[str, Any]
    ) -> FilterResult:
        """필터 1: 전략 미식별 차단"""
        try:
            strategy_id = trade_data.get("strategy_id", "")
            strategy_name = trade_data.get("strategy_name", "")

            # 전략 ID 빈값 체크
            if not strategy_id or strategy_id.strip() == "":
                logger.error(
                    f"filter_1_block | strategy_id_empty | trade_id={trade_data.get('trade_id', 'unknown')}"
                )
                if self.mock_mode and not self.fail_close_mode:
                    return FilterResult(
                        False,
                        "strategy_unidentified",
                        "strategy_id 빈값",
                        "MOCK_EXECUTE",
                        True,
                    )
                else:
                    return FilterResult(
                        False,
                        "strategy_unidentified",
                        "strategy_id 빈값",
                        "BLOCK",
                        False,
                    )

            # 전략명 레지스트리 체크
            if strategy_name not in self.strategy_registry:
                logger.error(
                    f"filter_1_block | strategy_name_unregistered | strategy_name={strategy_name} | trade_id={trade_data.get('trade_id', 'unknown')}"
                )
                if self.mock_mode and not self.fail_close_mode:
                    return FilterResult(
                        False,
                        "strategy_unidentified",
                        f"미등록 전략명: {strategy_name}",
                        "MOCK_EXECUTE",
                        True,
                    )
                else:
                    return FilterResult(
                        False,
                        "strategy_unidentified",
                        f"미등록 전략명: {strategy_name}",
                        "BLOCK",
                        False,
                    )

            # UNKNOWN 전략 차단
            if strategy_id == "UNKNOWN" or strategy_name == "UNKNOWN":
                logger.error(
                    f"filter_1_block | unknown_strategy | strategy_id={strategy_id} | trade_id={trade_data.get('trade_id', 'unknown')}"
                )
                if self.mock_mode and not self.fail_close_mode:
                    return FilterResult(
                        False,
                        "strategy_unidentified",
                        "UNKNOWN 전략",
                        "MOCK_EXECUTE",
                        True,
                    )
                else:
                    return FilterResult(
                        False, "strategy_unidentified", "UNKNOWN 전략", "BLOCK", False
                    )

            logger.info(
                f"filter_1_pass | strategy_identified | strategy_id={strategy_id} | strategy_name={strategy_name}"
            )
            return FilterResult(
                True, "strategy_unidentified", "전략 식별 성공", "PASS", True
            )

        except Exception as e:
            logger.error(
                f"filter_1_error | error={str(e)} | trade_id={trade_data.get('trade_id', 'unknown')}"
            )
            if self.mock_mode and not self.fail_close_mode:
                return FilterResult(
                    False,
                    "strategy_unidentified",
                    f"필터 오류: {str(e)}",
                    "MOCK_EXECUTE",
                    True,
                )
            else:
                return FilterResult(
                    False,
                    "strategy_unidentified",
                    f"필터 오류: {str(e)}",
                    "BLOCK",
                    False,
                )

    def filter_2_duplicate_prevention(self, trade_data: Dict[str, Any]) -> FilterResult:
        """필터 2: 중복 거래 방지"""
        try:
            # 중복키 생성: (exchange, orderId, tradeId, timestamp±2s)
            exchange = trade_data.get("exchange", "binance")
            order_id = trade_data.get("order_id", "")
            trade_id = trade_data.get("trade_id", "")
            ts_ns = trade_data.get("ts_ns", 0)

            # 타임스탬프를 2초 단위로 반올림
            ts_rounded = int(ts_ns / (2 * 1e9)) * (2 * 1e9)

            duplicate_key = f"{exchange}_{order_id}_{trade_id}_{ts_rounded}"

            if duplicate_key in self.duplicate_tracker:
                logger.warning(
                    f"filter_2_block | duplicate_detected | duplicate_key={duplicate_key}"
                )
                return FilterResult(
                    False, "duplicate_prevention", "중복 거래 감지", "BLOCK"
                )

            # 중복키 등록
            self.duplicate_tracker.add(duplicate_key)

            # 메모리 관리 (1000개 이상 시 오래된 것 제거)
            if len(self.duplicate_tracker) > 1000:
                # 단순히 절반 제거 (실제로는 시간 기반 제거가 더 좋음)
                old_keys = list(self.duplicate_tracker)[:500]
                for key in old_keys:
                    self.duplicate_tracker.discard(key)

            logger.info(f"filter_2_pass | no_duplicate | duplicate_key={duplicate_key}")
            return FilterResult(True, "duplicate_prevention", "중복 없음", "PASS")

        except Exception as e:
            logger.error(
                f"filter_2_error | error={str(e)} | trade_id={trade_data.get('trade_id', 'unknown')}"
            )
            return FilterResult(
                False, "duplicate_prevention", f"필터 오류: {str(e)}", "BLOCK"
            )

    def filter_3_capital_limit(self, trade_data: Dict[str, Any]) -> FilterResult:
        """필터 3: 자본 한도 초과 차단"""
        try:
            notional = trade_data.get("notional", 0)

            # 실제 계좌 잔고 조회
            try:
                from shared.balance_manager import get_total_balance
                total_capital = get_total_balance()
                if total_capital <= 0:
                    total_capital = 10000.0  # 기본값
            except Exception:
                total_capital = 10000.0  # 기본값

            capital_limit = total_capital * (self.capital_limit_pct / 100)

            if notional > capital_limit:
                # 테스트넷에서는 경고만
                is_testnet = trade_data.get(
                    "source", ""
                ) == "testnet" or trade_data.get("is_replay", False)

                if is_testnet:
                    logger.warning(
                        f"filter_3_warn | capital_limit_exceeded_testnet | notional={notional} | limit={capital_limit}"
                    )
                    return FilterResult(
                        False,
                        "capital_limit",
                        f"자본 한도 초과 (테스트넷 경고): {notional} > {capital_limit}",
                        "WARN",
                    )
                else:
                    logger.error(
                        f"filter_3_block | capital_limit_exceeded | notional={notional} | limit={capital_limit}"
                    )
                    return FilterResult(
                        False,
                        "capital_limit",
                        f"자본 한도 초과: {notional} > {capital_limit}",
                        "BLOCK",
                    )

            logger.info(
                f"filter_3_pass | capital_limit_ok | notional={notional} | limit={capital_limit}"
            )
            return FilterResult(True, "capital_limit", "자본 한도 내", "PASS")

        except Exception as e:
            logger.error(
                f"filter_3_error | error={str(e)} | trade_id={trade_data.get('trade_id', 'unknown')}"
            )
            return FilterResult(False, "capital_limit", f"필터 오류: {str(e)}", "BLOCK")

    def filter_4_replay_confusion(self, trade_data: Dict[str, Any]) -> FilterResult:
        """필터 4: 리플레이 혼선 차단"""
        try:
            is_replay = trade_data.get("is_replay", False)
            source = trade_data.get("source", "")

            # 리플레이 데이터는 실거래 합산에서 제외
            if is_replay:
                logger.warning(
                    f"filter_4_block | replay_data_excluded | source={source} | trade_id={trade_data.get('trade_id', 'unknown')}"
                )
                return FilterResult(
                    False,
                    "replay_confusion",
                    "리플레이 데이터는 실거래 합산 제외",
                    "BLOCK",
                )

            # USE_REPLAY 환경변수 체크 (실제로는 환경변수에서 가져와야 함)
            use_replay = False  # TODO: 환경변수에서 가져오기

            if use_replay and not is_replay:
                logger.warning(
                    f"filter_4_warn | live_data_in_replay_mode | source={source} | trade_id={trade_data.get('trade_id', 'unknown')}"
                )
                return FilterResult(
                    False, "replay_confusion", "리플레이 모드에서 실거래 데이터", "WARN"
                )

            logger.info(
                f"filter_4_pass | no_replay_confusion | is_replay={is_replay} | source={source}"
            )
            return FilterResult(True, "replay_confusion", "리플레이 혼선 없음", "PASS")

        except Exception as e:
            logger.error(
                f"filter_4_error | error={str(e)} | trade_id={trade_data.get('trade_id', 'unknown')}"
            )
            return FilterResult(
                False, "replay_confusion", f"필터 오류: {str(e)}", "BLOCK"
            )

    def filter_5_fee_unification(self, trade_data: Dict[str, Any]) -> FilterResult:
        """필터 5: 수수료/슬리피지 단일 적용 (SOT 검증)"""
        try:
            # SOT PnL 계산기로 검증
            from shared.pnl_calculator import verify_trade_pnl

            is_consistent, error_msg = verify_trade_pnl(trade_data)

            if not is_consistent:
                logger.error(f"filter_5_block | pnl_inconsistency | error={error_msg}")
                return FilterResult(
                    False, "fee_unification", f"PnL 불일치: {error_msg}", "BLOCK"
                )

            # 계산 소스 검증
            calculation_source = trade_data.get("calculation_source", "")
            if calculation_source != "SOT_PnLCalculator":
                logger.warning(
                    f"filter_5_warn | non_sot_calculation | source={calculation_source}"
                )
                return FilterResult(
                    False,
                    "fee_unification",
                    f"비SOT 계산 소스: {calculation_source}",
                    "WARN",
                )

            logger.info(
                f"filter_5_pass | sot_pnl_verified | source={calculation_source}"
            )
            return FilterResult(True, "fee_unification", "SOT PnL 검증 통과", "PASS")

        except Exception as e:
            logger.error(
                f"filter_5_error | error={str(e)} | trade_id={trade_data.get('trade_id', 'unknown')}"
            )
            return FilterResult(
                False, "fee_unification", f"필터 오류: {str(e)}", "BLOCK"
            )

    def filter_6_min_expected_return(self, trade_data: Dict[str, Any]) -> FilterResult:
        """필터 6: 최소 기대수익률 필터"""
        try:
            # 예상 수익률 또는 실현 수익률 확인
            expected_return_pct = trade_data.get("expected_return_pct", 0)
            realized_return_pct = trade_data.get("realized_return_pct", 0)
            net_pnl = trade_data.get("net_pnl", 0)
            notional = trade_data.get("notional", 0)

            # 실현 수익률 계산 (net_pnl 기준)
            if notional > 0:
                calculated_return_pct = (net_pnl / notional) * 100
            else:
                calculated_return_pct = 0

            # 최고 수익률 사용
            max_return_pct = max(
                expected_return_pct, realized_return_pct, calculated_return_pct
            )

            if max_return_pct < self.min_expected_return_pct:
                logger.warning(
                    f"filter_6_block | low_expected_return | return_pct={max_return_pct} | min_required={self.min_expected_return_pct}"
                )
                return FilterResult(
                    False,
                    "min_expected_return",
                    f"최소 기대수익률 미달: {max_return_pct}% < {self.min_expected_return_pct}%",
                    "BLOCK",
                )

            logger.info(
                f"filter_6_pass | expected_return_ok | return_pct={max_return_pct}"
            )
            return FilterResult(
                True,
                "min_expected_return",
                f"기대수익률 충족: {max_return_pct}%",
                "PASS",
            )

        except Exception as e:
            logger.error(
                f"filter_6_error | error={str(e)} | trade_id={trade_data.get('trade_id', 'unknown')}"
            )
            return FilterResult(
                False, "min_expected_return", f"필터 오류: {str(e)}", "BLOCK"
            )

    def filter_7_global_cooldown(self, trade_data: Dict[str, Any]) -> FilterResult:
        """필터 7: 글로벌 쿨다운"""
        try:
            strategy_name = trade_data.get("strategy_name", "")
            symbol = trade_data.get("symbol", "")
            current_time = time.time()

            # 쿨다운 키: 전략×심볼
            cooldown_key = f"{strategy_name}_{symbol}"

            # 마지막 거래 시간 확인
            last_trade_time = self.cooldown_tracker.get(cooldown_key, 0)

            if last_trade_time > 0:
                time_since_last = current_time - last_trade_time

                if time_since_last < self.global_cooldown_sec:
                    remaining_cooldown = self.global_cooldown_sec - time_since_last
                    logger.warning(
                        f"filter_7_block | global_cooldown_violation | strategy={strategy_name} | symbol={symbol} | remaining={remaining_cooldown:.1f}s"
                    )
                    return FilterResult(
                        False,
                        "global_cooldown",
                        f"글로벌 쿨다운 위반: {remaining_cooldown:.1f}초 남음",
                        "BLOCK",
                    )

            # 쿨다운 업데이트
            self.cooldown_tracker[cooldown_key] = current_time

            logger.info(
                f"filter_7_pass | global_cooldown_ok | strategy={strategy_name} | symbol={symbol}"
            )
            return FilterResult(True, "global_cooldown", "글로벌 쿨다운 통과", "PASS")

        except Exception as e:
            logger.error(
                f"filter_7_error | error={str(e)} | trade_id={trade_data.get('trade_id', 'unknown')}"
            )
            return FilterResult(
                False, "global_cooldown", f"필터 오류: {str(e)}", "BLOCK"
            )

    def apply_all_filters(self, trade_data: Dict[str, Any]) -> Tuple[bool, list]:
        """모든 무결성 필터 적용"""
        results = []

        # 7가지 필터 순차 적용
        filters = [
            self.filter_1_strategy_unidentified,
            self.filter_2_duplicate_prevention,
            self.filter_3_capital_limit,
            self.filter_4_replay_confusion,
            self.filter_5_fee_unification,
            self.filter_6_min_expected_return,
            self.filter_7_global_cooldown,
        ]

        overall_passed = True

        for filter_func in filters:
            result = filter_func(trade_data)
            results.append(result)

            # BLOCK 액션이면 전체 실패
            if result.action == "BLOCK":
                overall_passed = False
                logger.error(
                    f"integrity_filter_failed | filter={result.filter_name} | reason={result.reason}"
                )

                # 첫 번째 BLOCK에서 중단 (FAIL-CLOSE)
                break
            elif result.action == "WARN":
                logger.warning(
                    f"integrity_filter_warning | filter={result.filter_name} | reason={result.reason}"
                )

        if overall_passed:
            logger.info(
                f"integrity_filters_passed | all_filters_ok | trade_id={trade_data.get('trade_id', 'unknown')}"
            )
        else:
            logger.error(
                f"integrity_filters_failed | trade_blocked | trade_id={trade_data.get('trade_id', 'unknown')}"
            )

        return overall_passed, results


# 전역 인스턴스
_integrity_filters = None


def get_integrity_filters() -> IntegrityFilters:
    """무결성 필터 싱글톤 인스턴스 반환"""
    global _integrity_filters
    if _integrity_filters is None:
        _integrity_filters = IntegrityFilters()
    return _integrity_filters


def apply_integrity_filters(trade_data: Dict[str, Any]) -> Tuple[bool, list]:
    """무결성 필터 적용 (편의 함수)"""
    filters = get_integrity_filters()
    return filters.apply_all_filters(trade_data)
