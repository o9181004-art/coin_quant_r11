#!/usr/bin/env python3
"""
Execution Gating - Single source of truth for trading mode and live trading permissions
"""

import os
import logging
from typing import Dict, Any, Optional
from enum import Enum

from shared.guardrails import get_guardrails


class TradingMode(Enum):
    """거래 모드"""
    PAPER = "paper"
    SIM = "sim"
    LIVE = "live"


class ExecutionGating:
    """실행 게이팅"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.guardrails = get_guardrails()
        self.config = self.guardrails.get_config()
        
        # 통계
        self._stats = {
            "simulation_forced": 0,
            "live_blocked": 0,
            "testnet_enforced": 0,
            "api_key_checks": 0,
        }
    
    def is_simulation(self) -> bool:
        """시뮬레이션 모드 확인"""
        try:
            trading_mode = os.getenv("TRADING_MODE", "paper").lower()
            return trading_mode in {'paper', 'sim'}
            
        except Exception as e:
            self.logger.error(f"Simulation mode check failed: {e}")
            return True  # 안전하게 시뮬레이션 모드로 기본값
    
    def is_live(self) -> bool:
        """라이브 모드 확인"""
        try:
            trading_mode = os.getenv("TRADING_MODE", "paper").lower()
            return trading_mode == 'live'
            
        except Exception as e:
            self.logger.error(f"Live mode check failed: {e}")
            return False  # 안전하게 라이브 모드 비활성화
    
    def has_valid_api_keys(self) -> bool:
        """유효한 API 키 확인"""
        try:
            self._stats["api_key_checks"] += 1
            
            api_key = os.getenv("BINANCE_API_KEY")
            api_secret = os.getenv("BINANCE_API_SECRET")
            
            # API 키 존재 및 길이 확인
            if not api_key or not api_secret:
                return False
            
            if len(api_key) < 20 or len(api_secret) < 20:
                return False
            
            # API 키 형식 확인 (기본적인 형식 검증)
            if not api_key.isalnum() or not api_secret.isalnum():
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"API key validation failed: {e}")
            return False
    
    def allow_live_trading(self) -> bool:
        """라이브 거래 허용 확인"""
        try:
            # 라이브 모드가 아니면 거부
            if not self.is_live():
                return False
            
            # 라이브 거래 활성화 플래그 확인
            live_trading_enabled = os.getenv("LIVE_TRADING_ENABLED", "false").lower() == "true"
            if not live_trading_enabled:
                self.logger.warning("Live trading disabled by LIVE_TRADING_ENABLED flag")
                self._stats["live_blocked"] += 1
                return False
            
            # 유효한 API 키 확인
            if not self.has_valid_api_keys():
                self.logger.warning("Live trading blocked: invalid or missing API keys")
                self._stats["live_blocked"] += 1
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Live trading permission check failed: {e}")
            return False
    
    def force_simulation_path(self, reason: str = "Live trading not allowed"):
        """시뮬레이션 경로 강제"""
        try:
            self.logger.warning(f"Forcing simulation path: {reason}")
            self._stats["simulation_forced"] += 1
            return True
            
        except Exception as e:
            self.logger.error(f"Simulation path forcing failed: {e}")
            return False
    
    def require_testnet(self) -> bool:
        """테스트넷 요구사항 확인"""
        try:
            # 라이브 모드가 아닌 경우 테스트넷 요구
            if not self.is_live():
                use_testnet = os.getenv("BINANCE_USE_TESTNET", "true").lower() == "true"
                if not use_testnet:
                    self.logger.warning("Non-live mode requires BINANCE_USE_TESTNET=true")
                    self._stats["testnet_enforced"] += 1
                    return False
                return True
            
            # 라이브 모드에서는 테스트넷 비활성화 요구
            use_testnet = os.getenv("BINANCE_USE_TESTNET", "true").lower() == "true"
            if use_testnet:
                self.logger.warning("Live mode requires BINANCE_USE_TESTNET=false")
                self._stats["testnet_enforced"] += 1
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Testnet requirement check failed: {e}")
            return False
    
    def get_trading_mode(self) -> TradingMode:
        """거래 모드 반환"""
        try:
            trading_mode = os.getenv("TRADING_MODE", "paper").lower()
            
            if trading_mode == "live":
                return TradingMode.LIVE
            elif trading_mode == "sim":
                return TradingMode.SIM
            else:
                return TradingMode.PAPER
                
        except Exception as e:
            self.logger.error(f"Trading mode retrieval failed: {e}")
            return TradingMode.PAPER
    
    def get_mode_display_name(self) -> str:
        """모드 표시명 반환"""
        try:
            mode = self.get_trading_mode()
            
            if mode == TradingMode.LIVE:
                return "LIVE"
            elif mode == TradingMode.SIM:
                return "SIMULATION"
            else:
                return "PAPER"
                
        except Exception as e:
            self.logger.error(f"Mode display name retrieval failed: {e}")
            return "PAPER"
    
    def validate_environment(self) -> Dict[str, Any]:
        """환경 검증"""
        try:
            validation_result = {
                "is_simulation": self.is_simulation(),
                "is_live": self.is_live(),
                "allow_live_trading": self.allow_live_trading(),
                "has_valid_api_keys": self.has_valid_api_keys(),
                "require_testnet": self.require_testnet(),
                "trading_mode": self.get_trading_mode().value,
                "mode_display_name": self.get_mode_display_name(),
                "issues": []
            }
            
            # 문제점 수집
            if self.is_live() and not self.allow_live_trading():
                validation_result["issues"].append("Live mode enabled but live trading blocked")
            
            if not self.is_live() and not self.require_testnet():
                validation_result["issues"].append("Non-live mode but testnet not required")
            
            if self.is_live() and self.require_testnet():
                validation_result["issues"].append("Live mode but testnet enabled")
            
            return validation_result
            
        except Exception as e:
            self.logger.error(f"Environment validation failed: {e}")
            return {
                "is_simulation": True,
                "is_live": False,
                "allow_live_trading": False,
                "has_valid_api_keys": False,
                "require_testnet": True,
                "trading_mode": "paper",
                "mode_display_name": "PAPER",
                "issues": [f"Validation error: {e}"]
            }
    
    def get_stats(self) -> Dict[str, Any]:
        """통계 반환"""
        return self._stats.copy()


# 전역 인스턴스
_global_execution_gating: Optional[ExecutionGating] = None


def get_execution_gating() -> ExecutionGating:
    """전역 실행 게이팅 반환"""
    global _global_execution_gating
    if _global_execution_gating is None:
        _global_execution_gating = ExecutionGating()
    return _global_execution_gating


def is_simulation() -> bool:
    """시뮬레이션 모드 확인"""
    return get_execution_gating().is_simulation()


def is_live() -> bool:
    """라이브 모드 확인"""
    return get_execution_gating().is_live()


def allow_live_trading() -> bool:
    """라이브 거래 허용 확인"""
    return get_execution_gating().allow_live_trading()


def force_simulation_path(reason: str = "Live trading not allowed") -> bool:
    """시뮬레이션 경로 강제"""
    return get_execution_gating().force_simulation_path(reason)


def require_testnet() -> bool:
    """테스트넷 요구사항 확인"""
    return get_execution_gating().require_testnet()


def get_trading_mode() -> TradingMode:
    """거래 모드 반환"""
    return get_execution_gating().get_trading_mode()


def get_mode_display_name() -> str:
    """모드 표시명 반환"""
    return get_execution_gating().get_mode_display_name()


def validate_environment() -> Dict[str, Any]:
    """환경 검증"""
    return get_execution_gating().validate_environment()
