#!/usr/bin/env python3
"""
Health Thresholds - 완전무결 시스템 임계값 상수
모든 헬스체크의 임계값을 중앙집중식으로 관리
"""

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class HealthThresholds:
    """헬스체크 임계값 상수"""
    
    # Feeder 임계값
    FEEDER_DATABUS_SNAPSHOT_AGE_SEC = 90
    FEEDER_SNAPSHOT_COVERAGE_PCT = 80
    FEEDER_CANARY_FRESHNESS_SEC = 120  # BTC/ETH
    FEEDER_WRITER_STALL_DETECT_SEC = 90
    
    # ARES 임계값
    ARES_SIGNAL_AGE_SEC = 120
    ARES_TRACE_ID_REQUIRED = True
    
    # Trader 임계값
    TRADER_POSITION_SNAPSHOT_AGE_OK_SEC = 60
    TRADER_POSITION_SNAPSHOT_AGE_WARN_SEC = 180
    TRADER_POSITION_SNAPSHOT_AGE_FAIL_SEC = 300
    TRADER_EXPOSURE_DRIFT_PCT = 5.0
    
    # Auto-Heal 임계값
    AUTO_HEAL_CHECK_INTERVAL_SEC = 30
    AUTO_HEAL_CIRCUIT_BREAKER_SEC = 300
    AUTO_HEAL_CONSECUTIVE_FAILURES = 3
    
    # Pipeline Gates
    PIPELINE_FEEDER_TO_ARES_OK = True
    PIPELINE_ARES_TO_TRADER_OK = True
    PIPELINE_TRADER_TO_FILLS_OK = True
    PIPELINE_FILLS_TO_PNL_OK = True
    
    # Circuit Breaker
    CIRCUIT_BREAKER_ACTIVATION_FAILURES = 3
    CIRCUIT_BREAKER_DURATION_SEC = 300
    
    # Writer Resilience
    WRITER_MAX_QUEUE_SIZE = 1000
    WRITER_MAX_LOCK_RETRIES = 5
    WRITER_LOCK_RETRY_DELAY_MIN_SEC = 0.1
    WRITER_LOCK_RETRY_DELAY_MAX_SEC = 0.5
    
    # Backfill
    BACKFILL_MAX_WINDOW_HOURS = 24
    BACKFILL_BATCH_SIZE = 1000
    BACKFILL_TIMEOUT_SEC = 30
    
    # Path Security
    PATH_VIOLATION_RAISE = True
    SSOT_ROOT_REQUIRED = True
    
    # UI Refresh
    UI_REFRESH_INTERVAL_SEC = 5
    UI_ALERT_DRAWER_MAX_ITEMS = 20
    
    # Logging
    LOG_STRUCTURED_JSON = True
    LOG_INCLUDE_TRACE_ID = True
    LOG_INCLUDE_PATHS = True
    LOG_INCLUDE_BYTES = True
    LOG_INCLUDE_DURATIONS = True


# 전역 임계값 인스턴스
_thresholds = HealthThresholds()


def get_thresholds() -> HealthThresholds:
    """전역 임계값 인스턴스 반환"""
    return _thresholds


def get_feeder_thresholds() -> Dict[str, Any]:
    """Feeder 임계값 딕셔너리 반환"""
    return {
        "databus_snapshot_age_sec": _thresholds.FEEDER_DATABUS_SNAPSHOT_AGE_SEC,
        "snapshot_coverage_pct": _thresholds.FEEDER_SNAPSHOT_COVERAGE_PCT,
        "canary_freshness_sec": _thresholds.FEEDER_CANARY_FRESHNESS_SEC,
        "writer_stall_detect_sec": _thresholds.FEEDER_WRITER_STALL_DETECT_SEC
    }


def get_ares_thresholds() -> Dict[str, Any]:
    """ARES 임계값 딕셔너리 반환"""
    return {
        "signal_age_sec": _thresholds.ARES_SIGNAL_AGE_SEC,
        "trace_id_required": _thresholds.ARES_TRACE_ID_REQUIRED
    }


def get_trader_thresholds() -> Dict[str, Any]:
    """Trader 임계값 딕셔너리 반환"""
    return {
        "position_snapshot_age_ok_sec": _thresholds.TRADER_POSITION_SNAPSHOT_AGE_OK_SEC,
        "position_snapshot_age_warn_sec": _thresholds.TRADER_POSITION_SNAPSHOT_AGE_WARN_SEC,
        "position_snapshot_age_fail_sec": _thresholds.TRADER_POSITION_SNAPSHOT_AGE_FAIL_SEC,
        "exposure_drift_pct": _thresholds.TRADER_EXPOSURE_DRIFT_PCT
    }


def get_auto_heal_thresholds() -> Dict[str, Any]:
    """Auto-Heal 임계값 딕셔너리 반환"""
    return {
        "check_interval_sec": _thresholds.AUTO_HEAL_CHECK_INTERVAL_SEC,
        "circuit_breaker_sec": _thresholds.AUTO_HEAL_CIRCUIT_BREAKER_SEC,
        "consecutive_failures": _thresholds.AUTO_HEAL_CONSECUTIVE_FAILURES
    }


def get_pipeline_gates() -> Dict[str, bool]:
    """Pipeline Gates 딕셔너리 반환"""
    return {
        "feeder_to_ares_ok": _thresholds.PIPELINE_FEEDER_TO_ARES_OK,
        "ares_to_trader_ok": _thresholds.PIPELINE_ARES_TO_TRADER_OK,
        "trader_to_fills_ok": _thresholds.PIPELINE_TRADER_TO_FILLS_OK,
        "fills_to_pnl_ok": _thresholds.PIPELINE_FILLS_TO_PNL_OK
    }


def get_writer_thresholds() -> Dict[str, Any]:
    """Writer 임계값 딕셔너리 반환"""
    return {
        "max_queue_size": _thresholds.WRITER_MAX_QUEUE_SIZE,
        "max_lock_retries": _thresholds.WRITER_MAX_LOCK_RETRIES,
        "lock_retry_delay_min_sec": _thresholds.WRITER_LOCK_RETRY_DELAY_MIN_SEC,
        "lock_retry_delay_max_sec": _thresholds.WRITER_LOCK_RETRY_DELAY_MAX_SEC
    }


def get_backfill_thresholds() -> Dict[str, Any]:
    """Backfill 임계값 딕셔너리 반환"""
    return {
        "max_window_hours": _thresholds.BACKFILL_MAX_WINDOW_HOURS,
        "batch_size": _thresholds.BACKFILL_BATCH_SIZE,
        "timeout_sec": _thresholds.BACKFILL_TIMEOUT_SEC
    }


def get_circuit_breaker_thresholds() -> Dict[str, Any]:
    """Circuit Breaker 임계값 딕셔너리 반환"""
    return {
        "activation_failures": _thresholds.CIRCUIT_BREAKER_ACTIVATION_FAILURES,
        "duration_sec": _thresholds.CIRCUIT_BREAKER_DURATION_SEC
    }


def get_ui_thresholds() -> Dict[str, Any]:
    """UI 임계값 딕셔너리 반환"""
    return {
        "refresh_interval_sec": _thresholds.UI_REFRESH_INTERVAL_SEC,
        "alert_drawer_max_items": _thresholds.UI_ALERT_DRAWER_MAX_ITEMS
    }


def get_logging_thresholds() -> Dict[str, bool]:
    """로깅 임계값 딕셔너리 반환"""
    return {
        "structured_json": _thresholds.LOG_STRUCTURED_JSON,
        "include_trace_id": _thresholds.LOG_INCLUDE_TRACE_ID,
        "include_paths": _thresholds.LOG_INCLUDE_PATHS,
        "include_bytes": _thresholds.LOG_INCLUDE_BYTES,
        "include_durations": _thresholds.LOG_INCLUDE_DURATIONS
    }


if __name__ == "__main__":
    # 테스트
    thresholds = get_thresholds()
    
    print("=== Health Thresholds ===")
    print(f"Feeder databus snapshot age: {thresholds.FEEDER_DATABUS_SNAPSHOT_AGE_SEC}s")
    print(f"Feeder snapshot coverage: {thresholds.FEEDER_SNAPSHOT_COVERAGE_PCT}%")
    print(f"ARES signal age: {thresholds.ARES_SIGNAL_AGE_SEC}s")
    print(f"Trader position age (OK): {thresholds.TRADER_POSITION_SNAPSHOT_AGE_OK_SEC}s")
    print(f"Trader position age (WARN): {thresholds.TRADER_POSITION_SNAPSHOT_AGE_WARN_SEC}s")
    print(f"Trader position age (FAIL): {thresholds.TRADER_POSITION_SNAPSHOT_AGE_FAIL_SEC}s")
    print(f"Auto-Heal check interval: {thresholds.AUTO_HEAL_CHECK_INTERVAL_SEC}s")
    print(f"Circuit breaker duration: {thresholds.CIRCUIT_BREAKER_DURATION_SEC}s")
    print(f"Writer stall detect: {thresholds.FEEDER_WRITER_STALL_DETECT_SEC}s")
    print(f"Backfill max window: {thresholds.BACKFILL_MAX_WINDOW_HOURS}h")
    
    print("\n=== Feeder Thresholds ===")
    feeder_thresholds = get_feeder_thresholds()
    for key, value in feeder_thresholds.items():
        print(f"{key}: {value}")
    
    print("\n=== Trader Thresholds ===")
    trader_thresholds = get_trader_thresholds()
    for key, value in trader_thresholds.items():
        print(f"{key}: {value}")
    
    print("\n=== Pipeline Gates ===")
    pipeline_gates = get_pipeline_gates()
    for key, value in pipeline_gates.items():
        print(f"{key}: {value}")
