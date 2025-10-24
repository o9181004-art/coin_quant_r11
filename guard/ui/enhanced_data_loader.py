#!/usr/bin/env python3
"""
향상된 데이터 로더 - 첫 계산 시드, 무결성 검증, stale 로직 강화
"""

import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

import streamlit as st

from .file_watcher import get_global_watcher


@dataclass
class DataIntegrityResult:
    """데이터 무결성 검증 결과"""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    symbol_count: int
    timestamp: float
    age_sec: float


class EnhancedDataLoader:
    """향상된 데이터 로더"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.watcher = get_global_watcher()
        
        # Stale threshold 강화 (30초 → 15초)
        self.stale_threshold = 15.0
        self.heartbeat_threshold = 20.0
        
        # 첫 계산 시드를 위한 상태
        self.first_tick_seeded: Dict[str, bool] = {}
        self.last_snapshot_data: Optional[Dict] = None
    
    def validate_data_integrity(self, data: Dict, data_type: str = "snapshot") -> DataIntegrityResult:
        """데이터 무결성 검증"""
        errors = []
        warnings = []
        
        try:
            # JSON 파싱 확인
            if not isinstance(data, dict):
                errors.append("Data is not a dictionary")
                return DataIntegrityResult(False, errors, warnings, 0, 0, 0)
            
            # 필수 키 확인
            if data_type == "snapshot":
                required_keys = ['timestamp', 'meta', 'ohlcv_1m']
            elif data_type == "health":
                required_keys = ['heartbeat', 'symbols']
            else:
                required_keys = ['timestamp']
            
            for key in required_keys:
                if key not in data:
                    errors.append(f"Missing required key: {key}")
            
            # 타임스탬프 확인
            timestamp = data.get('timestamp', 0)
            if timestamp <= 0:
                errors.append("Invalid timestamp")
            
            current_time = time.time()
            age_sec = current_time - timestamp
            
            # Stale 데이터 경고
            if age_sec > self.stale_threshold:
                warnings.append(f"Stale data: {age_sec:.1f}s > {self.stale_threshold}s")
            
            # 심볼 수 확인
            symbol_count = 0
            if data_type == "snapshot":
                ohlcv_data = data.get('ohlcv_1m', {})
                symbol_count = len(ohlcv_data)
                
                if symbol_count < 5:
                    warnings.append(f"Low symbol count: {symbol_count}")
            
            # 타임스탬프 진행 확인
            if hasattr(self, '_last_timestamp'):
                if timestamp <= self._last_timestamp:
                    warnings.append(f"Timestamp not progressing: {timestamp} <= {self._last_timestamp}")
            
            self._last_timestamp = timestamp
            
            is_valid = len(errors) == 0
            
            return DataIntegrityResult(
                is_valid=is_valid,
                errors=errors,
                warnings=warnings,
                symbol_count=symbol_count,
                timestamp=timestamp,
                age_sec=age_sec
            )
            
        except Exception as e:
            errors.append(f"Validation error: {e}")
            return DataIntegrityResult(False, errors, warnings, 0, 0, 0)
    
    def seed_first_tick(self, symbol: str, data: Dict) -> bool:
        """첫 틱 시드 (2-tick 지연 방지)"""
        if symbol in self.first_tick_seeded:
            return False
        
        try:
            # 심볼 데이터 확인
            ohlcv_data = data.get('ohlcv_1m', {})
            if symbol not in ohlcv_data:
                return False
            
            # 타임스탬프 일관성 확인
            current_time = time.time()
            snapshot_ts = data.get('timestamp', 0)
            
            # 5분 이내 데이터만 사용
            if current_time - snapshot_ts > 300:
                return False
            
            # 시드 완료
            self.first_tick_seeded[symbol] = True
            self.logger.info(f"Seeded first tick for {symbol}")
            return True
            
        except Exception as e:
            self.logger.error(f"First tick seed error for {symbol}: {e}")
            return False
    
    def load_databus_snapshot(self) -> Tuple[Optional[Dict], DataIntegrityResult]:
        """databus_snapshot.json 로드 (무결성 검증 포함)"""
        try:
            snapshot_file = Path("shared_data/databus_snapshot.json")
            if not snapshot_file.exists():
                return None, DataIntegrityResult(False, ["File not found"], [], 0, 0, 0)
            
            with open(snapshot_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 무결성 검증
            integrity_result = self.validate_data_integrity(data, "snapshot")
            
            if integrity_result.is_valid:
                self.last_snapshot_data = data
                
                # 경고 로그 (에러가 아닌 경고만)
                for warning in integrity_result.warnings:
                    self.logger.warning(f"Data integrity warning: {warning}")
                
                return data, integrity_result
            else:
                # 에러 로그
                for error in integrity_result.errors:
                    self.logger.error(f"Data integrity error: {error}")
                
                return None, integrity_result
                
        except Exception as e:
            error_msg = f"Failed to load databus snapshot: {e}"
            self.logger.error(error_msg)
            return None, DataIntegrityResult(False, [error_msg], [], 0, 0, 0)
    
    def load_health_data(self) -> Tuple[Optional[Dict], DataIntegrityResult]:
        """health.json 로드 (무결성 검증 포함)"""
        try:
            health_file = Path("shared_data/health.json")
            if not health_file.exists():
                return None, DataIntegrityResult(False, ["File not found"], [], 0, 0, 0)
            
            with open(health_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 무결성 검증
            integrity_result = self.validate_data_integrity(data, "health")
            
            if integrity_result.is_valid:
                # Heartbeat 지연 확인
                heartbeat_ts = data.get('heartbeat', {}).get('ts', 0)
                current_time = time.time()
                lag_sec = current_time - heartbeat_ts
                
                if lag_sec > self.heartbeat_threshold:
                    integrity_result.warnings.append(f"Feeder lag: {lag_sec:.1f}s > {self.heartbeat_threshold}s")
                
                return data, integrity_result
            else:
                return None, integrity_result
                
        except Exception as e:
            error_msg = f"Failed to load health data: {e}"
            self.logger.error(error_msg)
            return None, DataIntegrityResult(False, [error_msg], [], 0, 0, 0)
    
    def load_ares_signals(self) -> Dict[str, Any]:
        """ARES 신호 로드 (첫 계산 시드 포함)"""
        signals = {}
        try:
            ares_dir = Path("shared_data/ares")
            if not ares_dir.exists():
                return signals
            
            for signal_file in ares_dir.glob("*.json"):
                try:
                    with open(signal_file, "r", encoding="utf-8") as f:
                        signal_data = json.load(f)
                        symbol = signal_file.stem.upper()
                        
                        # 첫 계산 시드 시도
                        if self.last_snapshot_data:
                            self.seed_first_tick(symbol, self.last_snapshot_data)
                        
                        # 새로운 ARES 데이터 구조 처리
                        if "signals" in signal_data and signal_data["signals"]:
                            # 가장 높은 신뢰도의 신호 선택
                            best_signal = max(
                                signal_data["signals"],
                                key=lambda x: x.get("confidence", 0)
                            )
                            
                            signals[symbol] = {
                                "action": best_signal.get("action", "HOLD"),
                                "confidence": best_signal.get("confidence", 0),
                                "timestamp": best_signal.get("timestamp", 0),
                                "price": best_signal.get("price", 0),
                                "reason": best_signal.get("reason", ""),
                            }
                        else:
                            # 기존 데이터 구조 처리
                            signals[symbol] = signal_data
                            
                except Exception as e:
                    self.logger.error(f"Failed to load signal file {signal_file}: {e}")
                    continue
                    
        except Exception as e:
            self.logger.error(f"Failed to load ARES signals: {e}")
        
        return signals
    
    def load_recent_executions(self) -> List[Dict]:
        """최근 체결 내역 로드"""
        executions = []
        try:
            orders_file = Path("data/orders_log.ndjson")
            if not orders_file.exists():
                return executions
            
            with open(orders_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
                # 최근 20개 로드
                recent_lines = lines[-20:] if len(lines) > 20 else lines
                
                for line in recent_lines:
                    try:
                        exec_data = json.loads(line.strip())
                        executions.append(exec_data)
                    except json.JSONDecodeError:
                        continue
                        
        except Exception as e:
            self.logger.error(f"Failed to load recent executions: {e}")
        
        return executions
    
    def get_stale_status(self, data_age_sec: float) -> Tuple[str, str]:
        """Stale 상태 반환"""
        if data_age_sec <= self.stale_threshold:
            return "🟢", "Fresh"
        elif data_age_sec <= self.stale_threshold * 2:
            return "🟡", "Stale"
        else:
            return "🔴", "Very Stale"
    
    def get_heartbeat_status(self, lag_sec: float) -> Tuple[str, str]:
        """Heartbeat 상태 반환"""
        if lag_sec <= self.heartbeat_threshold:
            return "🟢", "Connected"
        elif lag_sec <= self.heartbeat_threshold * 2:
            return "🟡", "Lagging"
        else:
            return "🔴", "Disconnected"


# 전역 인스턴스
_global_loader: Optional[EnhancedDataLoader] = None


def get_global_loader() -> EnhancedDataLoader:
    """전역 데이터 로더 반환"""
    global _global_loader
    if _global_loader is None:
        _global_loader = EnhancedDataLoader()
    return _global_loader


# Streamlit 캐시 데코레이터와 호환되는 래퍼 함수들
@st.cache_data(ttl=2)
def load_latest_signals_enhanced():
    """향상된 ARES 신호 로드"""
    loader = get_global_loader()
    return loader.load_ares_signals()


@st.cache_data(ttl=1)
def load_recent_executions_enhanced():
    """향상된 체결 내역 로드"""
    loader = get_global_loader()
    return loader.load_recent_executions()


@st.cache_data(ttl=1)
def load_databus_snapshot_enhanced():
    """향상된 databus 스냅샷 로드"""
    loader = get_global_loader()
    data, integrity = loader.load_databus_snapshot()
    return data, integrity


@st.cache_data(ttl=1)
def load_health_data_enhanced():
    """향상된 헬스 데이터 로드"""
    loader = get_global_loader()
    data, integrity = loader.load_health_data()
    return data, integrity
