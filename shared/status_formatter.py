#!/usr/bin/env python3
"""
SSOT Status Formatter
Health.json 기반 상세 상태 문구 생성
"""
import json
import time
from pathlib import Path
from typing import Optional


def format_trader_status() -> str:
    """
    Trader 상태 문구 생성 (원인 표기)
    
    Returns:
        상태 문구 (예: "IDLE — Filters STALE (refreshing...)")
    """
    try:
        health_file = Path("shared_data/health.json")
        if not health_file.exists():
            return "STOPPED"
        
        with open(health_file, 'r', encoding='utf-8') as f:
            health_data = json.load(f)
        
        trader_health = health_data.get("trader", {})
        state = trader_health.get("state", "UNKNOWN")
        filters = trader_health.get("filters", "UNKNOWN")
        error_msg = trader_health.get("error_message", "")
        
        # UDS heartbeat 확인
        uds_health = health_data.get("uds", {})
        uds_age = uds_health.get("heartbeat_age_sec", 999)
        
        # 상태 문구 생성
        if state == "RUNNING":
            return f"RUNNING — Filters {filters}"
        elif state == "IDLE":
            # IDLE 원인 판단
            if "UDS" in error_msg or uds_age >= 60:
                return f"IDLE — UDS heartbeat {uds_age:.0f}s (≥60s)"
            elif "Filters" in error_msg or filters == "STALE":
                return f"IDLE — Filters STALE (refreshing...)"
            elif error_msg:
                # 에러 메시지가 너무 길면 잘라서
                short_msg = error_msg[:40] + "..." if len(error_msg) > 40 else error_msg
                return f"IDLE — {short_msg}"
            else:
                return "IDLE"
        elif state == "DEGRADE":
            return f"DEGRADE — {error_msg[:40] if error_msg else 'REST API unavailable'}"
        else:
            return state
    
    except Exception:
        return "UNKNOWN"


def format_feeder_status() -> str:
    """
    Feeder 상태 문구 생성
    
    Returns:
        상태 문구
    """
    try:
        health_file = Path("shared_data/health.json")
        if not health_file.exists():
            return "STOPPED"
        
        with open(health_file, 'r', encoding='utf-8') as f:
            health_data = json.load(f)
        
        # Feeder 상태 (새 형식)
        feeder_health = health_data.get("feeder", {})
        if feeder_health:
            state = feeder_health.get("state", "UNKNOWN")
            ws_age = health_data.get("health_stats", {}).get("age_sec", 999)
            
            if state == "RUNNING":
                return f"RUNNING — WS age {ws_age:.1f}s"
            elif state == "DEGRADE":
                error = feeder_health.get("last_rest_error", "")
                short_error = error[:30] + "..." if len(error) > 30 else error
                return f"DEGRADE — {short_error or 'REST unavailable'}"
            else:
                return state
        
        # Feeder 상태 (기존 형식)
        feeder_ok = health_data.get("feeder_ok", False)
        health_stats = health_data.get("health_stats", {})
        ws_age = health_stats.get("age_sec", 999)
        
        if feeder_ok:
            return f"RUNNING — WS age {ws_age:.1f}s"
        else:
            return "STOPPED"
    
    except Exception:
        return "UNKNOWN"


def get_service_status_detail() -> dict:
    """
    전체 서비스 상태 상세 정보
    
    Returns:
        dict: {
            "feeder": {"status": str, "pid": int, "age": float},
            "trader": {...},
            "uds": {...},
            "autoheal": {...}
        }
    """
    status = {}
    
    # PID 파일들
    pid_files = {
        "feeder": Path("shared_data/feeder.pid"),
        "trader": Path("shared_data/trader.pid"),
        "uds": Path("shared_data/uds.pid"),
        "autoheal": Path("shared_data/autoheal.pid")
    }
    
    for service, pid_file in pid_files.items():
        if pid_file.exists():
            try:
                content = pid_file.read_text().strip()
                try:
                    pid_data = json.loads(content)
                    pid = pid_data.get('pid') if isinstance(pid_data, dict) else int(content)
                    started_at = pid_data.get('started_at', 0) if isinstance(pid_data, dict) else 0
                except json.JSONDecodeError:
                    pid = int(content)
                    started_at = 0
                
                age = time.time() - started_at if started_at > 0 else 0
                
                # PID 생존 확인
                try:
                    import psutil
                    is_alive = psutil.pid_exists(pid) and psutil.Process(pid).is_running()
                except:
                    is_alive = False
                
                status[service] = {
                    "status": "RUNNING" if is_alive else "STOPPED",
                    "pid": pid if is_alive else None,
                    "age": age if is_alive else 0
                }
            except:
                status[service] = {"status": "STOPPED", "pid": None, "age": 0}
        else:
            status[service] = {"status": "STOPPED", "pid": None, "age": 0}
    
    return status


def format_service_info_line(service: str) -> str:
    """
    서비스 정보 한 줄 포맷
    
    Returns:
        "Feeder: PID 1234, age 00:12:34"
    """
    status = get_service_status_detail()
    service_status = status.get(service, {})
    
    if service_status.get('status') == "RUNNING":
        pid = service_status.get('pid', 0)
        age = service_status.get('age', 0)
        
        # age를 HH:MM:SS 포맷으로
        hours = int(age // 3600)
        minutes = int((age % 3600) // 60)
        seconds = int(age % 60)
        age_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        
        # 상세 상태
        if service == "trader":
            detail = format_trader_status()
            return f"{service.capitalize()}: PID {pid}, {detail}, age {age_str}"
        elif service == "feeder":
            detail = format_feeder_status()
            return f"{service.capitalize()}: PID {pid}, {detail}, age {age_str}"
        else:
            return f"{service.capitalize()}: PID {pid}, age {age_str}"
    else:
        return f"{service.capitalize()}: STOPPED"


if __name__ == "__main__":
    # 테스트
    print("=" * 70)
    print("Status Formatter Test")
    print("=" * 70)
    
    print(f"\nTrader: {format_trader_status()}")
    print(f"Feeder: {format_feeder_status()}")
    
    print(f"\n상세 정보:")
    print(format_service_info_line("feeder"))
    print(format_service_info_line("trader"))
    print(format_service_info_line("uds"))
    print(format_service_info_line("autoheal"))

