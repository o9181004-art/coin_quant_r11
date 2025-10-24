#!/usr/bin/env python3
"""
Pre-Flight 체크 시스템
START 버튼 활성화를 위한 7개 체크 항목
"""

import json
import os
import time
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class CheckResult:
    """체크 결과"""

    name: str
    status: str  # PASS, FAIL, WARN
    message: str
    details: Optional[Dict] = None


class PreFlightChecker:
    """Pre-Flight 체크 시스템"""

    def __init__(self, file_reader):
        self.file_reader = file_reader

    def run_all_checks(self, env: str, mode: str) -> List[CheckResult]:
        """필수 5개 게이트 체크 실행"""
        # 필수 5개 게이트 (통과 시에만 START 활성)
        required_checks = [
            self.check_feeder_health(),
            self.check_uds_heartbeat(),
            self.check_filters(),
            self.check_loss_limits(),
            self.check_queue_ack_wiring(),
        ]

        # 경고 체크 (TimeSync, RestartRecovery)
        warning_checks = [self.check_time_sync(), self.check_restart_recovery()]

        return required_checks + warning_checks

    def check_time_sync(self) -> CheckResult:
        """TimeSync 체크: 경고로만 표기"""
        try:
            time_logs = self.file_reader.read_hardening_logs("time_guard", 10)

            if not time_logs or len(time_logs) == 0:
                return CheckResult("TimeSync", "WARN", "N/A (로그 없음)")

            offsets = []
            violations = 0

            for log in time_logs:
                if isinstance(log, dict):
                    offset = abs(log.get("offset_ms", 0))
                    if offset > 0:
                        offsets.append(offset)
                    violations += log.get("boundary_violations", 0)

            if not offsets:
                return CheckResult("TimeSync", "WARN", "N/A (데이터 없음)")

            avg_offset = sum(offsets) / len(offsets)
            max_offset = max(offsets)

            # 숫자 나오면 초록, 없으면 노랑
            return CheckResult(
                "TimeSync",
                "PASS",
                f"avg: {avg_offset:.1f}ms, max: {max_offset:.1f}ms, violations: {violations}",
                {"avg_ms": avg_offset, "max_ms": max_offset, "violations": violations},
            )

        except Exception:
            return CheckResult("TimeSync", "WARN", "N/A (오류)")

    def check_uds_heartbeat(self) -> CheckResult:
        """UDS 하트비트 체크: 최근 60s 이내 이벤트 수신"""
        try:
            # UserStream 로그 확인
            current_time = int(time.time() * 1000)
            sixty_seconds_ago = current_time - (60 * 1000)

            # userstream_heartbeat.log 확인
            heartbeat_logs = self.file_reader.read_hardening_logs(
                "userstream_heartbeat", 10
            )

            if not heartbeat_logs:
                return CheckResult("UDS Heartbeat", "FAIL", "하트비트 로그 없음")

            # 최근 60초 이내 이벤트 확인
            recent_events = []
            for log in heartbeat_logs:
                if isinstance(log, dict):
                    # ts 또는 ts_ms 필드 지원
                    event_ts = log.get("ts", log.get("ts_ms", 0))
                    if event_ts >= sixty_seconds_ago:
                        recent_events.append(log)

            if recent_events:
                return CheckResult(
                    "UDS Heartbeat",
                    "PASS",
                    f"최근 60초 이내 이벤트 {len(recent_events)}건 수신",
                )
            else:
                return CheckResult(
                    "UDS Heartbeat", "FAIL", "최근 60초 이내 이벤트 없음"
                )

        except Exception as e:
            return CheckResult("UDS Heartbeat", "FAIL", f"체크 오류: {str(e)}")

    def check_feeder_health(self) -> CheckResult:
        """Feeder Health 체크: 모든 활성 심볼 is_connected=true & age_sec ≤ 90s"""
        try:
            symbols = self.file_reader.read_watchlist()
            failed_symbols = []

            for symbol in symbols:
                snapshot = self.file_reader.read_symbol_snapshot(symbol)
                if not snapshot:
                    failed_symbols.append(f"{symbol}: 스냅샷 없음")
                    continue

                # is_connected 필드 확인
                if not snapshot.get("is_connected", False):
                    failed_symbols.append(f"{symbol}: 연결 끊김")
                    continue

                # last_event_ms 필드 확인 및 표준화
                last_event_ms = snapshot.get("last_event_ms", 0)
                if not last_event_ms:
                    # fallback: last_update 사용
                    last_event_ms = snapshot.get("last_update", 0)

                # 10자리(초)면 1000 곱해 ms로 변환
                if last_event_ms < 1e12:
                    last_event_ms *= 1000

                age_sec = self.file_reader.get_age_sec(last_event_ms)

                if age_sec > 90:
                    failed_symbols.append(f"{symbol}: {age_sec:.1f}s")

            if not failed_symbols:
                return CheckResult(
                    "Feeder Health", "PASS", f"{len(symbols)}심볼 모두 연결 및 신선"
                )
            else:
                return CheckResult(
                    "Feeder Health", "FAIL", f"실패: {', '.join(failed_symbols)}"
                )

        except Exception as e:
            return CheckResult("Feeder Health", "FAIL", f"체크 오류: {str(e)}")

    def check_filters(self) -> CheckResult:
        """Filters 체크: rejected=0, 정규화 OK"""
        try:
            filter_logs = self.file_reader.read_hardening_logs(
                "filter_normalization", 10
            )

            if not filter_logs:
                return CheckResult("Filters", "WARN", "필터 로그 없음")

            rejected_count = 0
            normalized_count = 0

            for log in filter_logs:
                if isinstance(log, dict):
                    if log.get("normalized", False):
                        normalized_count += 1
                    else:
                        rejected_count += 1

            if rejected_count == 0:
                return CheckResult(
                    "Filters",
                    "PASS",
                    f"정규화: {normalized_count}, 반려: {rejected_count}",
                )
            else:
                return CheckResult("Filters", "FAIL", f"반려 발생: {rejected_count}건")

        except Exception as e:
            return CheckResult("Filters", "FAIL", f"체크 오류: {str(e)}")

    def check_restart_recovery(self) -> CheckResult:
        """재시작 복원 체크: 경고로만 표기"""
        try:
            # 상태 대사 로그 확인 (간단한 구현)
            return CheckResult("Restart Recovery", "WARN", "N/A (구현 필요)")

        except Exception:
            return CheckResult("Restart Recovery", "WARN", "N/A (오류)")

    def check_loss_limits(self) -> CheckResult:
        """일손절/Fail-Safe 체크: 미발동"""
        try:
            # STOP.TXT 파일 확인
            stop_file = "STOP.TXT"
            if os.path.exists(stop_file):
                return CheckResult(
                    "Loss Limits", "FAIL", "STOP.TXT 존재 - 일손절/Fail-Safe 발동"
                )

            # daily_loss_cut.log 확인
            loss_logs = self.file_reader.read_hardening_logs("daily_loss_cut", 5)

            if loss_logs:
                for log in loss_logs:
                    if isinstance(log, dict) and log.get("triggered", False):
                        return CheckResult(
                            "Loss Limits", "FAIL", "일손절/Fail-Safe 발동 중"
                        )

            return CheckResult("Loss Limits", "PASS", "일손절/Fail-Safe 미발동")

        except Exception as e:
            return CheckResult("Loss Limits", "FAIL", f"체크 오류: {str(e)}")

    def check_queue_ack_wiring(self) -> CheckResult:
        """큐/ACK 배선 체크: 큐 쓰기 가능, ACK 갱신 확인"""
        try:
            # 큐 파일 쓰기 가능 여부 확인
            queue_path = "control/trader_cmd_queue.jsonl"
            ack_path = "control/trader_cmd_ack.jsonl"

            # 큐 파일 쓰기 테스트
            test_cmd = {
                "ts": int(time.time() * 1000),
                "actor": "test",
                "env": "testnet",
                "command": "TEST",
                "scope": "all",
                "payload": {},
                "reason": "Queue wiring test",
                "nonce": "test",
            }

            with open(queue_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(test_cmd, ensure_ascii=False) + "\n")

            # ACK 파일 존재 확인
            if os.path.exists(ack_path):
                return CheckResult(
                    "Queue/ACK Wiring", "PASS", "큐 쓰기 가능, ACK 파일 존재"
                )
            else:
                return CheckResult("Queue/ACK Wiring", "FAIL", "ACK 파일 없음")

        except Exception as e:
            return CheckResult("Queue/ACK Wiring", "FAIL", f"체크 오류: {str(e)}")

    def can_start(self, checks: List[CheckResult]) -> bool:
        """START 가능 여부 - 필수 5개 게이트만 확인"""
        # 필수 5개 게이트만 확인 (첫 5개)
        required_checks = checks[:5]
        return all(check.status == "PASS" for check in required_checks)

    def get_failed_required_checks(
        self, checks: List[CheckResult]
    ) -> List[CheckResult]:
        """실패한 필수 체크 목록"""
        required_checks = checks[:5]
        return [check for check in required_checks if check.status == "FAIL"]
