#!/usr/bin/env python3
"""
Alert System - Normalized Alert Schema & Log Parsing
알림 정규화 및 로그 파싱 유틸리티
"""

import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional, Set, Tuple


@dataclass
class Alert:
    """정규화된 알림 스키마"""
    ts: float  # Unix timestamp
    level: str  # "error" | "warning" | "info" | "fill"
    source: str  # "feeder" | "trader" | "ares" | "ui" | "system"
    code: str  # 알림 코드 (예: "WS_STALL", "ORDER_FAIL")
    message: str
    symbol: Optional[str] = None
    meta: Optional[dict] = None
    read: bool = False
    critical: bool = False  # 중요 알림 여부 (토스트 표시용)
    ttl_sec: Optional[int] = None  # Auto-dismiss after N seconds (for trade fills)
    
    def to_dict(self):
        """딕셔너리 변환"""
        return asdict(self)
    
    @property
    def level_emoji(self) -> str:
        """레벨별 이모지"""
        return {
            "error": "🔴",
            "warning": "🟡",
            "info": "🔵",
            "fill": "💰"
        }.get(self.level, "⚪")
    
    @property
    def source_emoji(self) -> str:
        """소스별 이모지"""
        return {
            "feeder": "📡",
            "trader": "🤖",
            "ares": "🎯",
            "ui": "🖥️",
            "system": "⚙️"
        }.get(self.source, "📌")


class AlertParser:
    """로그 파일 파싱 및 알림 정규화"""

    # Allowed event types for single alert bar (filter all others)
    ALLOWED_TYPES = {"trade_fill", "error", "error_resolved"}

    # 중요 알림 코드 리스트 (토스트 표시용)
    CRITICAL_CODES = {
        "CIRCUIT_BREAKER_ACTIVE",
        "FEEDER_DOWN",
        "TRADER_DOWN",
        "EXCHANGE_ERROR",
        "ORDER_REJECTED",
        "POSITION_GUARD_ACTIVE"
    }
    
    def __init__(self, log_path: str = None):
        # 로그 파일 우선순위: trader_debug.log > trader.log > feeder.log
        if log_path is None:
            log_candidates = [
                "logs/trader_debug.log",
                "logs/trader.log",
                "logs/feeder.log",
                "logs/notifications.log"
            ]
            for candidate in log_candidates:
                if Path(candidate).exists():
                    log_path = candidate
                    break
            else:
                log_path = "logs/trader_debug.log"  # 기본값
        
        self.log_path = Path(log_path)
        self.last_position = 0
        self.last_mtime = 0
        self.parsed_alerts: List[Alert] = []
        
        # 인코딩 자동 감지
        self.encoding = self._detect_encoding()
    
    def _detect_encoding(self) -> str:
        """로그 파일 인코딩 감지"""
        if not self.log_path.exists():
            return 'utf-8'
        
        try:
            # 첫 바이트 확인
            with open(self.log_path, 'rb') as f:
                first_bytes = f.read(2)
                # UTF-16 LE BOM 체크
                if first_bytes == b'\xff\xfe':
                    return 'utf-16'
                # UTF-16 BE BOM 체크
                elif first_bytes == b'\xfe\xff':
                    return 'utf-16'
                # UTF-8 BOM 체크
                elif first_bytes[:3] == b'\xef\xbb\xbf':
                    return 'utf-8-sig'
        except:
            pass
        
        return 'utf-8'
    
    def parse_line(self, line: str) -> Optional[Alert]:
        """단일 로그 라인 파싱"""
        try:
            # 로그 포맷 예시:
            # 2025-09-30 14:10:28,843 - trader - INFO - 총 거래: 413회
            # 2025-09-30 14:10:28,843 - trader - WARNING - DataBus 스냅샷 없음

            # 정규식 파싱
            pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - (\w+) - (\w+) - (.+)'
            match = re.match(pattern, line)

            if not match:
                return None

            timestamp_str, source, level_str, message = match.groups()

            # 타임스탬프 변환
            ts = time.mktime(time.strptime(timestamp_str.split(',')[0], "%Y-%m-%d %H:%M:%S"))

            # 레벨 정규화
            level = level_str.lower()
            if level not in ["error", "warning", "info"]:
                level = "info"

            # 소스 정규화
            source = source.lower()
            if source not in ["feeder", "trader", "ares", "ui", "system"]:
                source = "system"

            # 코드 추출 (메시지 첫 단어 또는 패턴)
            code = self._extract_code(message)

            # 심볼 추출 (BTCUSDT, ETHUSDT 등)
            symbol = self._extract_symbol(message)

            # 중요 알림 여부
            critical = code in self.CRITICAL_CODES or level == "error"

            # TTL 설정 (trade fills only)
            ttl_sec = 10 if code == "TRADE_FILL" else None

            return Alert(
                ts=ts,
                level=level,
                source=source,
                code=code,
                message=message.strip(),
                symbol=symbol,
                critical=critical,
                ttl_sec=ttl_sec
            )

        except Exception as e:
            # 파싱 실패 시 None 반환
            return None
    
    def _extract_code(self, message: str) -> str:
        """메시지에서 코드 추출"""
        # 특정 패턴 우선 매칭
        patterns = {
            r'Circuit Breaker': 'CIRCUIT_BREAKER_ACTIVE',
            r'Feeder.*미실행': 'FEEDER_DOWN',
            r'Trader.*미실행': 'TRADER_DOWN',
            r'DataBus.*없음': 'DATABUS_MISSING',
            r'스냅샷.*없음': 'SNAPSHOT_MISSING',
            r'정규화 오류': 'NORMALIZATION_ERROR',
            r'체결': 'TRADE_FILL',
            r'주문.*실패': 'ORDER_FAIL',
        }
        
        for pattern, code in patterns.items():
            if re.search(pattern, message, re.IGNORECASE):
                return code
        
        # 기본: 첫 단어를 코드로 사용
        first_word = message.split()[0] if message.split() else "UNKNOWN"
        return first_word.upper().replace(":", "")
    
    def _extract_symbol(self, message: str) -> Optional[str]:
        """메시지에서 심볼 추출"""
        # USDT 페어 매칭
        symbol_pattern = r'\b([A-Z]{3,10}USDT)\b'
        match = re.search(symbol_pattern, message)
        return match.group(1) if match else None
    
    def read_new_alerts(self) -> List[Alert]:
        """새로운 알림 읽기 (tail 방식, 초기 로드는 최근 100줄)"""
        if not self.log_path.exists():
            return []
        
        try:
            # 파일 수정 시간 체크
            current_mtime = self.log_path.stat().st_mtime
            
            # 첫 실행 시 최근 100줄 로드
            if self.last_position == 0:
                new_alerts = []
                
                with open(self.log_path, 'r', encoding=self.encoding, errors='ignore') as f:
                    lines = f.readlines()
                    # 최근 100줄만 파싱
                    recent_lines = lines[-100:] if len(lines) > 100 else lines
                    
                    for line in recent_lines:
                        alert = self.parse_line(line.strip())
                        if alert:
                            new_alerts.append(alert)
                    
                    # 현재 위치 저장 (파일 끝)
                    self.last_position = f.tell()
                
                self.last_mtime = current_mtime
                self.parsed_alerts.extend(new_alerts)
                
                return new_alerts
            
            # 이후 실행은 변경된 부분만 읽기
            if current_mtime == self.last_mtime:
                # 파일 변경 없음
                return []
            
            new_alerts = []
            
            with open(self.log_path, 'r', encoding=self.encoding, errors='ignore') as f:
                # 이전 위치로 이동
                f.seek(self.last_position)
                
                # 새로운 라인 읽기
                for line in f:
                    alert = self.parse_line(line.strip())
                    if alert:
                        new_alerts.append(alert)
                
                # 현재 위치 저장
                self.last_position = f.tell()
            
            self.last_mtime = current_mtime
            self.parsed_alerts.extend(new_alerts)
            
            return new_alerts
            
        except Exception as e:
            print(f"[DEBUG] read_new_alerts 오류: {e}")
            return []
    
    def get_all_alerts(self) -> List[Alert]:
        """전체 알림 반환"""
        return self.parsed_alerts


class AlertDeduplicator:
    """알림 중복 제거"""
    
    def __init__(self, window_sec: int = 60):
        self.window_sec = window_sec
        self.seen: Set[Tuple[str, str, float]] = set()  # (code, message, ts)
    
    def deduplicate(self, alerts: List[Alert]) -> List[Alert]:
        """중복 제거"""
        unique_alerts = []
        current_time = time.time()
        
        # 오래된 항목 정리
        self.seen = {
            (code, msg, ts) 
            for code, msg, ts in self.seen 
            if current_time - ts < self.window_sec
        }
        
        for alert in alerts:
            key = (alert.code, alert.message, alert.ts)
            
            # 같은 code + message가 window 내에 있는지 확인
            is_duplicate = any(
                code == alert.code and 
                msg == alert.message and 
                abs(ts - alert.ts) < self.window_sec
                for code, msg, ts in self.seen
            )
            
            if not is_duplicate:
                unique_alerts.append(alert)
                self.seen.add(key)
        
        return unique_alerts


# 전역 파서 및 중복 제거기
_parser: Optional[AlertParser] = None
_deduplicator: Optional[AlertDeduplicator] = None


def get_alert_parser() -> AlertParser:
    """전역 알림 파서 반환"""
    global _parser
    if _parser is None:
        _parser = AlertParser()
    return _parser


def get_alert_deduplicator() -> AlertDeduplicator:
    """전역 중복 제거기 반환"""
    global _deduplicator
    if _deduplicator is None:
        _deduplicator = AlertDeduplicator()
    return _deduplicator


def load_alerts() -> List[Alert]:
    """새로운 알림 로드 (중복 제거 포함)"""
    parser = get_alert_parser()
    deduplicator = get_alert_deduplicator()
    
    new_alerts = parser.read_new_alerts()
    unique_alerts = deduplicator.deduplicate(new_alerts)
    
    return unique_alerts


if __name__ == "__main__":
    # 테스트
    parser = AlertParser()
    
    # 샘플 로그 라인 파싱
    sample_lines = [
        "2025-09-30 14:10:28,843 - trader - INFO - 총 거래: 413회",
        "2025-09-30 14:10:58,851 - trader - WARNING - DataBus 스냅샷 없음. Feeder 재시작 요청",
        "2025-09-30 14:11:28,889 - trader - ERROR - Circuit Breaker 활성화",
    ]
    
    for line in sample_lines:
        alert = parser.parse_line(line)
        if alert:
            print(f"{alert.level_emoji} [{alert.level.upper()}] {alert.source_emoji} {alert.source} - {alert.message}")
            print(f"  Code: {alert.code}, Critical: {alert.critical}")
