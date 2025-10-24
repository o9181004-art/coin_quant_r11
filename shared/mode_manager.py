#!/usr/bin/env python3
"""
운영 모드 관리
SIMULATION / PAPER(TESTNET) / LIVE 3단계 모드 관리
"""

import logging
import os
from enum import Enum
from typing import Any, Dict


class TradingMode(Enum):
    """거래 모드"""

    SIMULATION = "simulation"
    PAPER = "paper"  # TESTNET
    LIVE = "live"


class ModeManager:
    """운영 모드 관리자"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._current_mode = self._load_mode()

    def _load_mode(self) -> TradingMode:
        """환경변수에서 모드 로드"""
        mode_str = os.getenv("TRADING_MODE", "paper").lower()

        try:
            mode = TradingMode(mode_str)
            self.logger.info(f"거래 모드 로드: {mode.value}")
            return mode
        except ValueError:
            self.logger.warning(f"잘못된 거래 모드: {mode_str}, PAPER 모드로 설정")
            return TradingMode.PAPER

    def get_current_mode(self) -> TradingMode:
        """현재 모드 반환"""
        return self._current_mode

    def set_mode(self, mode: TradingMode) -> bool:
        """모드 설정"""
        try:
            self._current_mode = mode
            os.environ["TRADING_MODE"] = mode.value
            self.logger.info(f"거래 모드 변경: {mode.value}")
            return True
        except Exception as e:
            self.logger.error(f"모드 설정 실패: {e}")
            return False

    def is_simulation(self) -> bool:
        """시뮬레이션 모드 확인"""
        return self._current_mode == TradingMode.SIMULATION

    def is_paper(self) -> bool:
        """페이퍼(테스트넷) 모드 확인"""
        return self._current_mode == TradingMode.PAPER

    def is_live(self) -> bool:
        """실거래 모드 확인"""
        return self._current_mode == TradingMode.LIVE

    def get_mode_config(self) -> Dict[str, Any]:
        """모드별 설정 반환"""
        configs = {
            TradingMode.SIMULATION: {
                "use_testnet": False,
                "dry_run": True,
                "order_source": "simulation",
                "slippage_bps": 5,
                "fee_bps": 10,
                "min_order_usdt": 1.0,
                "max_order_usdt": 10000.0,
            },
            TradingMode.PAPER: {
                "use_testnet": True,
                "dry_run": False,
                "order_source": "testnet",
                "slippage_bps": 10,
                "fee_bps": 10,
                "min_order_usdt": 0.1,  # 5.0에서 0.1로 감소
                "max_order_usdt": 1000.0,
            },
            TradingMode.LIVE: {
                "use_testnet": False,
                "dry_run": False,
                "order_source": "mainnet",
                "slippage_bps": 20,
                "fee_bps": 10,
                "min_order_usdt": 10.0,
                "max_order_usdt": 50000.0,
            },
        }

        return configs.get(self._current_mode, configs[TradingMode.PAPER])

    def get_mode_display_name(self) -> str:
        """모드 표시명 반환"""
        display_names = {
            TradingMode.SIMULATION: "시뮬레이션",
            TradingMode.PAPER: "테스트넷",
            TradingMode.LIVE: "실거래",
        }
        return display_names.get(self._current_mode, "알 수 없음")

    def get_mode_color(self) -> str:
        """모드별 색상 반환"""
        colors = {
            TradingMode.SIMULATION: "blue",
            TradingMode.PAPER: "orange",
            TradingMode.LIVE: "red",
        }
        return colors.get(self._current_mode, "gray")

    def can_trade(self) -> bool:
        """거래 가능 여부 확인"""
        # LIVE 모드는 추가 확인 필요
        if self.is_live():
            # 실제 구현에서는 추가 안전장치 확인
            return os.getenv("LIVE_TRADING_ENABLED", "false").lower() == "true"

        return True

    def get_risk_limits(self) -> Dict[str, float]:
        """모드별 리스크 한도 반환"""
        limits = {
            TradingMode.SIMULATION: {
                "max_position_usdt": 10000.0,
                "max_daily_loss_usdt": 1000.0,
                "max_daily_loss_pct": 10.0,
                "max_total_exposure_usdt": 50000.0,
                "max_symbols": 40,
            },
            TradingMode.PAPER: {
                "max_position_usdt": 20000.0,  # 1000.0에서 20000.0으로 증가
                "max_daily_loss_usdt": 100.0,
                "max_daily_loss_pct": 10.0,
                "max_total_exposure_usdt": 5000.0,
                "max_symbols": 40,
            },
            TradingMode.LIVE: {
                "max_position_usdt": 5000.0,
                "max_daily_loss_usdt": 500.0,
                "max_daily_loss_pct": 5.0,
                "max_total_exposure_usdt": 25000.0,
                "max_symbols": 40,
            },
        }

        return limits.get(self._current_mode, limits[TradingMode.PAPER])


# 전역 인스턴스
mode_manager = ModeManager()

if __name__ == "__main__":
    # 테스트
    logging.basicConfig(level=logging.INFO)

    print("=== 모드 관리자 테스트 ===")
    print(f"현재 모드: {mode_manager.get_current_mode().value}")
    print(f"표시명: {mode_manager.get_mode_display_name()}")
    print(f"색상: {mode_manager.get_mode_color()}")
    print(f"거래 가능: {mode_manager.can_trade()}")
    print(f"설정: {mode_manager.get_mode_config()}")
    print(f"리스크 한도: {mode_manager.get_risk_limits()}")
