#!/usr/bin/env python3
"""
Guardrails & Feature Flags - 중앙화된 설정 시스템
Single Source of Truth (SSOT) for all runtime configuration
"""

import json
import logging
import os
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Optional, Union
import yaml


@dataclass
class GuardrailConfig:
    """가드레일 설정 - 모든 모듈에서 사용하는 중앙화된 설정"""
    
    # === 핵심 안전장치 ===
    SIMULATION_MODE: bool = True  # 기본값: 시뮬레이션 모드
    BINANCE_USE_TESTNET: bool = True  # 기본값: 테스트넷 사용
    AUTO_HEAL_ENABLED: bool = True  # 기본값: 자가치유 활성화
    E_STOP: bool = False  # 글로벌 하드 스톱
    
    # === 거래 제한 ===
    MAX_DAILY_LOSS_USD: float = 100.0  # 일일 최대 손실
    MAX_OPEN_POSITIONS: int = 5  # 최대 오픈 포지션 수
    MAX_RETRY_PER_ORDER: int = 3  # 주문당 최대 재시도
    RETRY_BACKOFF_MS: int = 1000  # 재시도 백오프 (ms)
    ORDER_TIMEOUT_SEC: int = 30  # 주문 타임아웃 (초)
    
    # === 기능 플래그 ===
    EVENT_DRIVEN_REFRESH: bool = True  # 이벤트 기반 새로고침
    SEED_FIRST_TICK: bool = True  # 첫 틱 시드
    STRICT_SCHEMA_VALIDATE: bool = True  # 엄격한 스키마 검증
    TRADING_ENABLED: bool = False  # 기본값: 거래 비활성화
    
    # === 데이터 신선도 ===
    STALE_THRESHOLD_SEC: int = 15  # 스테일 임계값 (초)
    HEARTBEAT_THRESHOLD_SEC: int = 20  # 하트비트 임계값 (초)
    FEEDER_HEARTBEAT_INTERVAL_SEC: int = 2  # Feeder 하트비트 간격
    
    # === 리스크 관리 ===
    MAX_POSITION_SIZE_USD: float = 1000.0  # 최대 포지션 크기
    MIN_CONFIDENCE_THRESHOLD: float = 0.2  # 최소 신뢰도 임계값
    SLIPPAGE_LIMIT_BPS: int = 15  # 슬리피지 한도 (bps)
    
    # === 자가치유 ===
    AUTO_HEAL_COOLDOWN_SEC: int = 60  # 자가치유 쿨다운 (초)
    MAX_RESTART_ATTEMPTS: int = 3  # 최대 재시작 시도
    RESTART_BACKOFF_SEC: int = 30  # 재시작 백오프 (초)
    
    # === 로깅 ===
    LOG_LEVEL: str = "INFO"  # 로그 레벨
    ENABLE_FILE_WATCHER_LOGS: bool = True  # 파일 와처 로그 활성화
    
    # === 메타데이터 ===
    config_version: str = "1.0.0"  # 설정 버전
    last_updated: float = 0.0  # 마지막 업데이트 시간
    source: str = "default"  # 설정 소스


class GuardrailManager:
    """가드레일 관리자 - 중앙화된 설정 관리"""
    
    def __init__(self, config_file: str = "shared_data/guardrails.json"):
        self.config_file = Path(config_file)
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        
        self.logger = logging.getLogger(__name__)
        self._config: Optional[GuardrailConfig] = None
        self._last_load_time = 0.0
        
        # 설정 로드
        self.load_config()
    
    def load_config(self) -> GuardrailConfig:
        """설정 로드 (환경변수 → 파일 → 기본값 순서)"""
        try:
            # 1. 환경변수에서 로드
            env_config = self._load_from_env()
            
            # 2. 파일에서 로드 (있는 경우)
            file_config = self._load_from_file()
            
            # 3. 기본값으로 병합
            self._config = self._merge_configs(env_config, file_config)
            
            # 4. 파일에 저장 (환경변수 우선)
            self._save_to_file()
            
            self._last_load_time = time.time()
            self.logger.info(f"Guardrails loaded: SIMULATION_MODE={self._config.SIMULATION_MODE}, "
                           f"TRADING_ENABLED={self._config.TRADING_ENABLED}")
            
            return self._config
            
        except Exception as e:
            self.logger.error(f"Failed to load guardrails config: {e}")
            # 안전한 기본값 사용
            self._config = GuardrailConfig()
            return self._config
    
    def _load_from_env(self) -> Dict[str, Any]:
        """환경변수에서 설정 로드"""
        env_config = {}
        
        # 환경변수 매핑
        env_mapping = {
            'SIMULATION_MODE': ('SIMULATION_MODE', bool, True),
            'BINANCE_USE_TESTNET': ('BINANCE_USE_TESTNET', bool, True),
            'AUTO_HEAL_ENABLED': ('AUTO_HEAL_ENABLED', bool, True),
            'E_STOP': ('E_STOP', bool, False),
            'MAX_DAILY_LOSS_USD': ('MAX_DAILY_LOSS_USD', float, 100.0),
            'MAX_OPEN_POSITIONS': ('MAX_OPEN_POSITIONS', int, 5),
            'MAX_RETRY_PER_ORDER': ('MAX_RETRY_PER_ORDER', int, 3),
            'RETRY_BACKOFF_MS': ('RETRY_BACKOFF_MS', int, 1000),
            'ORDER_TIMEOUT_SEC': ('ORDER_TIMEOUT_SEC', int, 30),
            'EVENT_DRIVEN_REFRESH': ('EVENT_DRIVEN_REFRESH', bool, True),
            'SEED_FIRST_TICK': ('SEED_FIRST_TICK', bool, True),
            'STRICT_SCHEMA_VALIDATE': ('STRICT_SCHEMA_VALIDATE', bool, True),
            'TRADING_ENABLED': ('TRADING_ENABLED', bool, False),
            'STALE_THRESHOLD_SEC': ('STALE_THRESHOLD_SEC', int, 15),
            'HEARTBEAT_THRESHOLD_SEC': ('HEARTBEAT_THRESHOLD_SEC', int, 20),
            'FEEDER_HEARTBEAT_INTERVAL_SEC': ('FEEDER_HEARTBEAT_INTERVAL_SEC', int, 2),
            'MAX_POSITION_SIZE_USD': ('MAX_POSITION_SIZE_USD', float, 1000.0),
            'MIN_CONFIDENCE_THRESHOLD': ('MIN_CONFIDENCE_THRESHOLD', float, 0.2),
            'SLIPPAGE_LIMIT_BPS': ('SLIPPAGE_LIMIT_BPS', int, 15),
            'AUTO_HEAL_COOLDOWN_SEC': ('AUTO_HEAL_COOLDOWN_SEC', int, 60),
            'MAX_RESTART_ATTEMPTS': ('MAX_RESTART_ATTEMPTS', int, 3),
            'RESTART_BACKOFF_SEC': ('RESTART_BACKOFF_SEC', int, 30),
            'LOG_LEVEL': ('LOG_LEVEL', str, 'INFO'),
            'ENABLE_FILE_WATCHER_LOGS': ('ENABLE_FILE_WATCHER_LOGS', bool, True),
        }
        
        for key, (env_key, type_func, default) in env_mapping.items():
            env_value = os.getenv(env_key)
            if env_value is not None:
                try:
                    if type_func == bool:
                        env_config[key] = env_value.lower() in ('true', '1', 'yes', 'on')
                    else:
                        env_config[key] = type_func(env_value)
                except (ValueError, TypeError):
                    self.logger.warning(f"Invalid env value for {env_key}: {env_value}, using default: {default}")
                    env_config[key] = default
            else:
                env_config[key] = default
        
        return env_config
    
    def _load_from_file(self) -> Dict[str, Any]:
        """파일에서 설정 로드"""
        if not self.config_file.exists():
            return {}
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 메타데이터 제거하고 설정만 반환
            file_config = {k: v for k, v in data.items() 
                          if k not in ['config_version', 'last_updated', 'source']}
            
            return file_config
            
        except Exception as e:
            self.logger.warning(f"Failed to load config file {self.config_file}: {e}")
            return {}
    
    def _merge_configs(self, env_config: Dict[str, Any], file_config: Dict[str, Any]) -> GuardrailConfig:
        """설정 병합 (환경변수 우선)"""
        # 기본값으로 시작
        merged = asdict(GuardrailConfig())
        
        # 파일 설정 적용
        for key, value in file_config.items():
            if key in merged:
                merged[key] = value
        
        # 환경변수 설정 적용 (우선순위)
        for key, value in env_config.items():
            if key in merged:
                merged[key] = value
        
        # 메타데이터 설정
        merged['last_updated'] = time.time()
        merged['source'] = 'merged'
        
        return GuardrailConfig(**merged)
    
    def _save_to_file(self):
        """설정을 파일에 저장"""
        try:
            config_dict = asdict(self._config)
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config_dict, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            self.logger.error(f"Failed to save config to file {self.config_file}: {e}")
    
    def get_config(self) -> GuardrailConfig:
        """현재 설정 반환"""
        if self._config is None:
            self.load_config()
        return self._config
    
    def update_config(self, updates: Dict[str, Any]) -> bool:
        """설정 업데이트"""
        try:
            if self._config is None:
                self.load_config()
            
            # 업데이트 적용
            for key, value in updates.items():
                if hasattr(self._config, key):
                    setattr(self._config, key, value)
                else:
                    self.logger.warning(f"Unknown config key: {key}")
            
            # 메타데이터 업데이트
            self._config.last_updated = time.time()
            self._config.source = 'runtime_update'
            
            # 파일에 저장
            self._save_to_file()
            
            self.logger.info(f"Config updated: {updates}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to update config: {e}")
            return False
    
    def is_safe_to_trade(self) -> bool:
        """거래 안전성 확인"""
        if self._config is None:
            self.load_config()
        
        # E-STOP 확인
        if self._config.E_STOP:
            self.logger.warning("E-STOP is active - trading blocked")
            return False
        
        # 시뮬레이션 모드 확인
        if self._config.SIMULATION_MODE:
            self.logger.info("SIMULATION_MODE is active - no real trading")
            return False
        
        # 거래 활성화 확인
        if not self._config.TRADING_ENABLED:
            self.logger.warning("TRADING_ENABLED is false - trading blocked")
            return False
        
        return True
    
    def get_trading_mode(self) -> str:
        """거래 모드 반환"""
        if self._config is None:
            self.load_config()
        
        if self._config.SIMULATION_MODE:
            return "SIMULATION"
        elif self._config.BINANCE_USE_TESTNET:
            return "TESTNET"
        else:
            return "PRODUCTION"
    
    def get_risk_limits(self) -> Dict[str, float]:
        """리스크 한도 반환"""
        if self._config is None:
            self.load_config()
        
        return {
            'max_daily_loss_usd': self._config.MAX_DAILY_LOSS_USD,
            'max_position_size_usd': self._config.MAX_POSITION_SIZE_USD,
            'max_open_positions': self._config.MAX_OPEN_POSITIONS,
            'min_confidence_threshold': self._config.MIN_CONFIDENCE_THRESHOLD,
            'slippage_limit_bps': self._config.SLIPPAGE_LIMIT_BPS,
        }
    
    def get_retry_config(self) -> Dict[str, int]:
        """재시도 설정 반환"""
        if self._config is None:
            self.load_config()
        
        return {
            'max_retry_per_order': self._config.MAX_RETRY_PER_ORDER,
            'retry_backoff_ms': self._config.RETRY_BACKOFF_MS,
            'order_timeout_sec': self._config.ORDER_TIMEOUT_SEC,
        }
    
    def get_healing_config(self) -> Dict[str, Any]:
        """자가치유 설정 반환"""
        if self._config is None:
            self.load_config()
        
        return {
            'auto_heal_enabled': self._config.AUTO_HEAL_ENABLED,
            'cooldown_sec': self._config.AUTO_HEAL_COOLDOWN_SEC,
            'max_restart_attempts': self._config.MAX_RESTART_ATTEMPTS,
            'restart_backoff_sec': self._config.RESTART_BACKOFF_SEC,
        }
    
    def reload_config(self) -> GuardrailConfig:
        """설정 재로드"""
        self.logger.info("Reloading guardrails config...")
        return self.load_config()
    
    def validate_config(self) -> bool:
        """설정 유효성 검증"""
        if self._config is None:
            return False
        
        try:
            # 필수 값 확인
            assert self._config.MAX_DAILY_LOSS_USD > 0, "MAX_DAILY_LOSS_USD must be positive"
            assert self._config.MAX_OPEN_POSITIONS > 0, "MAX_OPEN_POSITIONS must be positive"
            assert self._config.MAX_RETRY_PER_ORDER > 0, "MAX_RETRY_PER_ORDER must be positive"
            assert self._config.RETRY_BACKOFF_MS > 0, "RETRY_BACKOFF_MS must be positive"
            assert self._config.ORDER_TIMEOUT_SEC > 0, "ORDER_TIMEOUT_SEC must be positive"
            assert self._config.STALE_THRESHOLD_SEC > 0, "STALE_THRESHOLD_SEC must be positive"
            assert self._config.HEARTBEAT_THRESHOLD_SEC > 0, "HEARTBEAT_THRESHOLD_SEC must be positive"
            assert 0 <= self._config.MIN_CONFIDENCE_THRESHOLD <= 1, "MIN_CONFIDENCE_THRESHOLD must be 0-1"
            assert 0 <= self._config.SLIPPAGE_LIMIT_BPS <= 1000, "SLIPPAGE_LIMIT_BPS must be 0-1000"
            
            return True
            
        except AssertionError as e:
            self.logger.error(f"Config validation failed: {e}")
            return False


# 전역 인스턴스
_global_guardrails: Optional[GuardrailManager] = None


def get_guardrails() -> GuardrailManager:
    """전역 가드레일 관리자 반환"""
    global _global_guardrails
    if _global_guardrails is None:
        _global_guardrails = GuardrailManager()
    return _global_guardrails


def get_config() -> GuardrailConfig:
    """현재 설정 반환"""
    return get_guardrails().get_config()


def is_safe_to_trade() -> bool:
    """거래 안전성 확인"""
    return get_guardrails().is_safe_to_trade()


def get_trading_mode() -> str:
    """거래 모드 반환"""
    return get_guardrails().get_trading_mode()


def update_config(updates: Dict[str, Any]) -> bool:
    """설정 업데이트"""
    return get_guardrails().update_config(updates)


def reload_config() -> GuardrailConfig:
    """설정 재로드"""
    return get_guardrails().reload_config()
