#!/usr/bin/env python3
"""
중앙화된 파일 읽기 모듈
Read-only 파일 접근, 캐싱, 파싱 담당
"""

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional


class FileSourceReader:
    """파일 소스 리더 - Read-only 파일 접근"""

    def __init__(self, cache_ttl: float = 5.0):
        self.cache_ttl = cache_ttl
        self.cache = {}
        self.logger = logging.getLogger(__name__)

        # Read-only 검증
        self.write_attempts = 0
        self.read_only_mode = True

    def _validate_read_only(self):
        """Read-only 모드 검증"""
        if self.write_attempts > 0:
            self.logger.warning(f"Write attempt detected: {self.write_attempts}")
        return self.read_only_mode

    def _get_cached_or_read(self, file_path: str, parser_func) -> Any:
        """캐시된 데이터 반환 또는 파일 읽기"""
        try:
            current_time = time.time()

            # 캐시 확인
            if file_path in self.cache:
                cached_data, cache_time = self.cache[file_path]
                if current_time - cache_time < self.cache_ttl:
                    return cached_data

            # 파일 읽기
            if not os.path.exists(file_path):
                return None

            data = parser_func(file_path)

            # 캐시 저장
            self.cache[file_path] = (data, current_time)

            return data

        except Exception as e:
            self.logger.error(f"파일 읽기 실패 {file_path}: {e}")
            return None

    def read_json(self, file_path: str) -> Optional[Dict]:
        """JSON 파일 읽기"""

        def _parse_json(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)

        return self._get_cached_or_read(file_path, _parse_json)

    def read_jsonl_tail(self, file_path: str, lines: int = 500) -> List[Dict]:
        """JSONL 파일 마지막 N줄 읽기"""

        def _parse_jsonl_tail(path):
            result = []
            try:
                with open(path, "r", encoding="utf-8") as f:
                    # 파일 크기가 작으면 전체 읽기
                    file_size = os.path.getsize(path)
                    if file_size < 1024 * 1024:  # 1MB 미만
                        for line in f:
                            line = line.strip()
                            if line:
                                try:
                                    result.append(json.loads(line))
                                except json.JSONDecodeError:
                                    continue
                        return result[-lines:] if len(result) > lines else result

                    # 큰 파일의 경우 역순으로 읽기
                    f.seek(0, 2)  # 파일 끝으로
                    file_size = f.tell()
                    f.seek(max(0, file_size - 1024 * 1024))  # 마지막 1MB

                    buffer = f.read()
                    lines_list = buffer.split("\n")[-lines - 1 : -1]  # 마지막 N줄

                    for line in lines_list:
                        line = line.strip()
                        if line:
                            try:
                                result.append(json.loads(line))
                            except json.JSONDecodeError:
                                continue

                    return result

            except Exception as e:
                self.logger.error(f"JSONL 읽기 실패 {path}: {e}")
                return []

        return self._get_cached_or_read(file_path, _parse_jsonl_tail)

    def read_watchlist(self) -> List[str]:
        """워치리스트 읽기"""
        watchlist_data = self.read_json("shared_data/coin_watchlist.json")
        if watchlist_data and isinstance(watchlist_data, list):
            return [symbol.upper() for symbol in watchlist_data]
        return ["BTCUSDT", "ETHUSDT", "SOLUSDT"]  # 기본값

    def read_symbol_snapshot(self, symbol: str) -> Optional[Dict]:
        """심볼별 스냅샷 읽기"""
        file_path = f"shared_data/snapshots/prices_{symbol}.json"
        return self.read_json(file_path)

    def read_symbol_signal(self, symbol: str) -> Optional[Dict]:
        """심볼별 신호 읽기"""
        file_path = f"shared_data/signals/{symbol}.json"
        return self.read_json(file_path)

    def read_symbol_history_tail(self, symbol: str, lines: int = 100) -> List[Dict]:
        """심볼별 히스토리 마지막 N줄 읽기"""
        file_path = f"shared_data/history/{symbol}_1m.jsonl"
        return self.read_jsonl_tail(file_path, lines)

    def read_execution_logs(self, lines: int = 100) -> List[Dict]:
        """실행 로그 읽기"""
        return self.read_jsonl_tail("logs/execution_filter.log", lines)

    def read_failsafe_logs(self, lines: int = 100) -> List[Dict]:
        """Fail-Safe 로그 읽기"""
        return self.read_jsonl_tail("logs/failsafe_trading.log", lines)

    def read_hardening_logs(self, log_name: str, lines: int = 50) -> List[Dict]:
        """하드닝 로그 읽기"""
        file_path = f"logs/hardening/{log_name}.log"
        return self.read_jsonl_tail(file_path, lines)

    def read_notifications(self, lines: int = 50) -> List[Dict]:
        """알림 로그 읽기"""
        return self.read_jsonl_tail("logs/notifications.log", lines)

    def read_system_state(self) -> Optional[Dict]:
        """시스템 상태 읽기"""
        return self.read_json("shared_data/system_state.json")

    def read_positions_snapshot(self) -> Optional[Dict]:
        """포지션 스냅샷 읽기"""
        return self.read_json("shared_data/positions_snapshot.json")

    def get_age_sec(self, timestamp_ms: int) -> float:
        """타임스탬프로부터 경과 시간 계산 - 표준화된 epoch_ms 기반"""
        if not timestamp_ms or timestamp_ms <= 0:
            return 999.0

        # 현재 시간을 epoch_ms로 통일
        now_ms = int(time.time() * 1000)

        # age_sec = max(0, (now_ms - last_event_ms) / 1000.0)
        age_sec = max(0.0, (now_ms - timestamp_ms) / 1000.0)

        # 소수 1자리로 반올림
        return round(age_sec, 1)

    def get_age_color(self, age_sec: float) -> str:
        """age_sec에 따른 색상 반환"""
        if age_sec <= 30:
            return "green"
        elif age_sec <= 90:
            return "yellow"
        else:
            return "red"

    def get_status_color(self, status: str) -> str:
        """상태에 따른 색상 반환"""
        status_colors = {
            "PASS": "green",
            "PARTIAL": "yellow",
            "FAIL": "red",
            "N/A": "gray",
            "Executed": "green",
            "Blocked": "red",
            "HOLD": "gray",
        }
        return status_colors.get(status, "gray")

    def validate_read_only_mode(self) -> Dict[str, Any]:
        """Read-only 모드 검증 결과 반환"""
        return {
            "mode": "read-only",
            "writes_detected": self.write_attempts,
            "read_only_enforced": self.read_only_mode,
            "timestamp": int(time.time() * 1000),
        }


# 전역 인스턴스
file_reader = FileSourceReader(cache_ttl=5.0)
