#!/usr/bin/env python3
"""
Audit - 감사 로그 시스템
모드 변경 및 중요 이벤트 로깅
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class AuditLogger:
    """감사 로그 클래스"""
    
    def __init__(self, repo_root: Optional[Path] = None):
        if repo_root is None:
            repo_root = Path(__file__).parent.parent.absolute()
        
        self.repo_root = repo_root
        self.audit_dir = repo_root / "logs" / "audit"
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        
        # 오늘 날짜의 로그 파일
        today = datetime.now().strftime("%Y%m%d")
        self.audit_file = self.audit_dir / f"audit_{today}.jsonl"
    
    def log_event(self, event_type: str, details: Dict[str, Any], user: str = "system") -> bool:
        """이벤트 로깅"""
        try:
            audit_entry = {
                "timestamp": int(time.time()),
                "datetime": datetime.now(timezone.utc).isoformat(),
                "event_type": event_type,
                "user": user,
                "details": details
            }
            
            # JSONL 형식으로 추가
            with open(self.audit_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(audit_entry, ensure_ascii=False) + '\n')
            
            return True
            
        except Exception as e:
            print(f"Audit log error: {e}")
            return False
    
    def log_mode_change(self, old_mode: str, new_mode: str, user: str = "user") -> bool:
        """모드 변경 로깅"""
        details = {
            "old_mode": old_mode,
            "new_mode": new_mode,
            "change_type": "manual"
        }
        
        return self.log_event("mode_change", details, user)
    
    def log_auto_downgrade(self, old_mode: str, new_mode: str, reason: str = "risk_limit_exceeded") -> bool:
        """자동 다운그레이드 로깅"""
        details = {
            "old_mode": old_mode,
            "new_mode": new_mode,
            "change_type": "auto",
            "reason": reason
        }
        
        return self.log_event("auto_downgrade", details, "system")
    
    def log_risk_limit_breach(self, limit_type: str, current_value: float, limit_value: float) -> bool:
        """리스크 한도 위반 로깅"""
        details = {
            "limit_type": limit_type,
            "current_value": current_value,
            "limit_value": limit_value,
            "breach_pct": (current_value / limit_value - 1) * 100 if limit_value > 0 else 0
        }
        
        return self.log_event("risk_limit_breach", details, "system")
    
    def log_trade_execution(self, symbol: str, side: str, qty: float, price: float, mode: str) -> bool:
        """거래 실행 로깅"""
        details = {
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "price": price,
            "mode": mode,
            "total_value": qty * price
        }
        
        return self.log_event("trade_execution", details, "system")
    
    def get_recent_events(self, event_type: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """최근 이벤트 조회"""
        try:
            if not self.audit_file.exists():
                return []
            
            events = []
            with open(self.audit_file, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        event = json.loads(line.strip())
                        if event_type is None or event.get("event_type") == event_type:
                            events.append(event)
                    except json.JSONDecodeError:
                        continue
            
            # 최신순으로 정렬
            events.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
            
            return events[:limit]
            
        except Exception as e:
            print(f"Audit read error: {e}")
            return []
    
    def get_mode_change_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """모드 변경 이력 조회"""
        return self.get_recent_events("mode_change", limit)
    
    def get_auto_downgrade_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """자동 다운그레이드 이력 조회"""
        return self.get_recent_events("auto_downgrade", limit)


# 전역 인스턴스
_audit_logger = None

def get_audit_logger(repo_root: Optional[Path] = None) -> AuditLogger:
    """AuditLogger 인스턴스 획득"""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger(repo_root)
    return _audit_logger


# 편의 함수들
def log_mode_change(old_mode: str, new_mode: str, user: str = "user") -> bool:
    """모드 변경 로깅 (편의 함수)"""
    return get_audit_logger().log_mode_change(old_mode, new_mode, user)


def log_auto_downgrade(old_mode: str, new_mode: str, reason: str = "risk_limit_exceeded") -> bool:
    """자동 다운그레이드 로깅 (편의 함수)"""
    return get_audit_logger().log_auto_downgrade(old_mode, new_mode, reason)


def log_risk_limit_breach(limit_type: str, current_value: float, limit_value: float) -> bool:
    """리스크 한도 위반 로깅 (편의 함수)"""
    return get_audit_logger().log_risk_limit_breach(limit_type, current_value, limit_value)


def log_trade_execution(symbol: str, side: str, qty: float, price: float, mode: str) -> bool:
    """거래 실행 로깅 (편의 함수)"""
    return get_audit_logger().log_trade_execution(symbol, side, qty, price, mode)


def get_recent_events(event_type: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    """최근 이벤트 조회 (편의 함수)"""
    return get_audit_logger().get_recent_events(event_type, limit)


def get_mode_change_history(limit: int = 50) -> List[Dict[str, Any]]:
    """모드 변경 이력 조회 (편의 함수)"""
    return get_audit_logger().get_mode_change_history(limit)
