"""
PnL 계산 단일 소스 (SOT)
수수료/슬리피지 중복 차감 방지를 위한 통합 계산 모듈
"""

import logging
import pathlib
from dataclasses import dataclass
from typing import Any, Dict, Tuple

import yaml

logger = logging.getLogger(__name__)


@dataclass
class PnLComponents:
    """PnL 구성 요소"""

    gross_pnl: float  # 총손익
    fee: float  # 수수료 (USDT)
    slippage_cost: float  # 슬리피지 비용 (USDT)
    net_pnl: float  # 순손익 (USDT)
    fee_rate_bps: int  # 적용된 수수료율 (bps)
    slippage_bps: int  # 적용된 슬리피지 (bps)
    maker_taker: str  # "MAKER" or "TAKER"
    calculation_source: str  # 계산 소스 (SOT 추적용)


class PnLCalculator:
    """PnL 계산 단일 소스"""

    def __init__(self):
        self.config = self._load_config()
        self.calculation_count = 0  # 중복 계산 추적

    def _load_config(self) -> Dict[str, Any]:
        """config/policy.yaml에서 수수료/슬리피지 설정 로드"""
        try:
            config_path = pathlib.Path("config/policy.yaml")
            if not config_path.exists():
                logger.warning("config/policy.yaml이 존재하지 않음, 기본값 사용")
                return self._get_default_config()

            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)

            return config

        except Exception as e:
            logger.error(f"설정 로드 실패: {e}, 기본값 사용")
            return self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """기본 설정값"""
        return {
            "execution": {
                "maker_fee_bps": 2,  # 2 bps
                "taker_fee_bps": 4,  # 4 bps
                "slippage_limit_bps": 20,  # 20 bps
                "spread_filter_bps": 8,  # 8 bps
            }
        }

    def calculate_pnl(
        self,
        gross_pnl: float,
        notional: float,
        maker_taker: str = "TAKER",
        custom_slippage_bps: int = None,
    ) -> PnLComponents:
        """
        NetPnL 계산 (단일 소스, 중복 차감 방지)

        Args:
            gross_pnl: 총손익 (USDT)
            notional: 거래 금액 (USDT)
            maker_taker: "MAKER" or "TAKER"
            custom_slippage_bps: 커스텀 슬리피지 (없으면 기본값 사용)

        Returns:
            PnLComponents: PnL 구성 요소
        """
        try:
            self.calculation_count += 1

            # 설정값 가져오기
            execution_config = self.config.get("execution", {})

            # 수수료율 결정
            if maker_taker.upper() == "MAKER":
                fee_rate_bps = execution_config.get("maker_fee_bps", 2)
            else:  # TAKER
                fee_rate_bps = execution_config.get("taker_fee_bps", 4)

            # 슬리피지 결정
            if custom_slippage_bps is not None:
                slippage_bps = custom_slippage_bps
            else:
                slippage_bps = execution_config.get("slippage_limit_bps", 20)

            # 수수료 계산
            fee = notional * (fee_rate_bps / 10000)

            # 슬리피지 비용 계산
            slippage_cost = notional * (slippage_bps / 10000)

            # Net PnL = Gross PnL - Fee - Slippage (단일 계산)
            net_pnl = gross_pnl - fee - slippage_cost

            # 계산 로그
            logger.info(
                f"pnl_calculated | gross={gross_pnl:.4f} | fee={fee:.4f} | slippage={slippage_cost:.4f} | net={net_pnl:.4f} | count={self.calculation_count}"
            )

            return PnLComponents(
                gross_pnl=gross_pnl,
                fee=fee,
                slippage_cost=slippage_cost,
                net_pnl=net_pnl,
                fee_rate_bps=fee_rate_bps,
                slippage_bps=slippage_bps,
                maker_taker=maker_taker.upper(),
                calculation_source="SOT_PnLCalculator",
            )

        except Exception as e:
            logger.error(f"PnL 계산 오류: {e}")
            # 오류 시 안전한 기본값 반환
            return PnLComponents(
                gross_pnl=gross_pnl,
                fee=0.0,
                slippage_cost=0.0,
                net_pnl=gross_pnl,
                fee_rate_bps=0,
                slippage_bps=0,
                maker_taker=maker_taker.upper(),
                calculation_source="SOT_PnLCalculator_ERROR",
            )

    def verify_pnl_consistency(self, trade_data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        PnL 일관성 검증 (중복 차감 검출)

        Args:
            trade_data: 거래 데이터

        Returns:
            Tuple[bool, str]: (일관성 여부, 오류 메시지)
        """
        try:
            # 기존 NetPnL과 재계산된 NetPnL 비교
            existing_net_pnl = trade_data.get("net_pnl", 0)
            gross_pnl = trade_data.get("gross_pnl", 0)
            notional = trade_data.get("notional", 0)
            maker_taker = trade_data.get("maker_taker", "TAKER")

            # 재계산
            calculated = self.calculate_pnl(gross_pnl, notional, maker_taker)

            # 허용 오차 (0.01 USDT)
            tolerance = 0.01

            if abs(existing_net_pnl - calculated.net_pnl) > tolerance:
                error_msg = f"PnL 불일치: 기존={existing_net_pnl:.4f}, 계산={calculated.net_pnl:.4f}, 차이={abs(existing_net_pnl - calculated.net_pnl):.4f}"
                logger.warning(f"pnl_inconsistency | {error_msg}")
                return False, error_msg

            logger.info(
                f"pnl_consistency_ok | existing={existing_net_pnl:.4f} | calculated={calculated.net_pnl:.4f}"
            )
            return True, "PnL 일관성 확인"

        except Exception as e:
            error_msg = f"PnL 검증 오류: {str(e)}"
            logger.error(f"pnl_verification_error | {error_msg}")
            return False, error_msg

    def get_config_source(self) -> Dict[str, Any]:
        """현재 사용 중인 설정값과 소스 반환"""
        execution_config = self.config.get("execution", {})

        return {
            "source_file": "config/policy.yaml",
            "maker_fee_bps": execution_config.get("maker_fee_bps", 2),
            "taker_fee_bps": execution_config.get("taker_fee_bps", 4),
            "slippage_limit_bps": execution_config.get("slippage_limit_bps", 20),
            "spread_filter_bps": execution_config.get("spread_filter_bps", 8),
            "calculation_count": self.calculation_count,
            "last_updated": "2025-09-24",
        }


# 전역 싱글톤 인스턴스
_pnl_calculator = None


def get_pnl_calculator() -> PnLCalculator:
    """PnL 계산기 싱글톤 인스턴스 반환"""
    global _pnl_calculator
    if _pnl_calculator is None:
        _pnl_calculator = PnLCalculator()
    return _pnl_calculator


def calculate_net_pnl(
    gross_pnl: float, notional: float, maker_taker: str = "TAKER"
) -> PnLComponents:
    """NetPnL 계산 편의 함수 (SOT)"""
    calculator = get_pnl_calculator()
    return calculator.calculate_pnl(gross_pnl, notional, maker_taker)


def verify_trade_pnl(trade_data: Dict[str, Any]) -> Tuple[bool, str]:
    """거래 PnL 검증 편의 함수"""
    calculator = get_pnl_calculator()
    return calculator.verify_pnl_consistency(trade_data)


def get_pnl_config() -> Dict[str, Any]:
    """PnL 설정 정보 반환 편의 함수"""
    calculator = get_pnl_calculator()
    return calculator.get_config_source()
