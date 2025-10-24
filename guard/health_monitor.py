#!/usr/bin/env python3
"""
시스템 헬스 모니터링 및 자가치유 관리자
- 오류 패턴 감지
- 자동 복구 트리거
- 서비스 상태 모니터링
- 알림 시스템
"""

import json
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class HealthStatus:
    """헬스 상태 정보"""

    service_name: str
    status: str  # "healthy", "warning", "critical", "down"
    last_check: float
    error_count: int = 0
    last_error: Optional[str] = None
    auto_healing_attempts: int = 0
    last_healing: Optional[float] = None


class HealthMonitor:
    """시스템 헬스 모니터링 및 자가치유 관리자"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.running = False
        self.monitoring_thread = None

        # 헬스 상태 저장소
        self.health_status: Dict[str, HealthStatus] = {}

        # 오류 패턴 저장소
        self.error_patterns: Dict[str, List[float]] = {}

        # 자가치유 설정
        self.auto_healing_enabled = True
        self.healing_cooldown = 300  # 5분 쿨다운
        self.max_healing_attempts = 3

        # 파일 경로
        self.health_file = Path("shared_data/health_status.json")
        self.health_file.parent.mkdir(exist_ok=True)

        # 모니터링할 서비스들
        self.monitored_services = [
            "feeder",
            "trader",
            "ares",
            "databus",
            "websocket_connections",
        ]

    def start(self):
        """헬스 모니터링 시작"""
        if self.running:
            self.logger.warning("헬스 모니터가 이미 실행 중")
            return

        self.running = True
        self.logger.info("헬스 모니터 시작")

        # 초기 헬스 상태 로드
        self._load_health_status()

        # 모니터링 스레드 시작
        self.monitoring_thread = threading.Thread(
            target=self._monitoring_loop, daemon=True
        )
        self.monitoring_thread.start()

    def stop(self):
        """헬스 모니터링 중지"""
        self.running = False
        self.logger.info("헬스 모니터 중지")

        # 헬스 상태 저장
        self._save_health_status()

    def _monitoring_loop(self):
        """메인 모니터링 루프"""
        while self.running:
            try:
                current_time = time.time()

                # 1. 각 서비스 헬스 체크
                for service_name in self.monitored_services:
                    self._check_service_health(service_name)

                # 2. 오류 패턴 분석
                self._analyze_error_patterns()

                # 3. 자가치유 트리거
                if self.auto_healing_enabled:
                    self._trigger_auto_healing()

                # 4. 헬스 상태 저장 (5분마다)
                if current_time % 300 < 5:
                    self._save_health_status()

                time.sleep(10)  # 10초마다 체크

            except Exception as e:
                self.logger.error(f"모니터링 루프 오류: {e}")
                time.sleep(30)  # 오류 시 30초 대기

    def _check_service_health(self, service_name: str):
        """개별 서비스 헬스 체크"""
        try:
            current_time = time.time()

            if service_name == "feeder":
                health_status = self._check_feeder_health()
            elif service_name == "trader":
                health_status = self._check_trader_health()
            elif service_name == "ares":
                health_status = self._check_ares_health()
            elif service_name == "databus":
                health_status = self._check_databus_health()
            elif service_name == "websocket_connections":
                health_status = self._check_websocket_health()
            else:
                health_status = "unknown"

            # 헬스 상태 업데이트
            if service_name not in self.health_status:
                self.health_status[service_name] = HealthStatus(
                    service_name=service_name, status="unknown", last_check=current_time
                )

            status_obj = self.health_status[service_name]
            status_obj.last_check = current_time

            # 상태 변화 감지
            if status_obj.status != health_status:
                old_status = status_obj.status
                status_obj.status = health_status

                if health_status in ["warning", "critical", "down"]:
                    status_obj.error_count += 1
                    self._record_error_pattern(
                        service_name, f"Status change: {old_status} -> {health_status}"
                    )
                else:
                    status_obj.error_count = 0  # 성공 시 에러 카운트 리셋

                self.logger.info(
                    f"서비스 상태 변화: {service_name} {old_status} -> {health_status}"
                )

        except Exception as e:
            self.logger.error(f"{service_name} 헬스 체크 오류: {e}")

    def _check_feeder_health(self) -> str:
        """Feeder 서비스 헬스 체크"""
        try:
            # PID 파일 체크
            feeder_pid_file = Path("shared_data/feeder.pid")
            if not feeder_pid_file.exists():
                return "down"

            # 로그 파일 체크 (최근 5분 이내 활동)
            log_file = Path("logs/feeder.log")
            if log_file.exists():
                stat = log_file.stat()
                if time.time() - stat.st_mtime > 300:  # 5분 이상 오래됨
                    return "warning"

            # DataBus 업데이트 체크
            databus_file = Path("shared_data/databus_snapshot.json")
            if databus_file.exists():
                stat = databus_file.stat()
                if time.time() - stat.st_mtime > 120:  # 2분 이상 오래됨
                    return "warning"

            return "healthy"

        except Exception:
            return "critical"

    def _check_trader_health(self) -> str:
        """Trader 서비스 헬스 체크"""
        try:
            # PID 파일 체크
            trader_pid_file = Path("shared_data/trader.pid")
            if not trader_pid_file.exists():
                return "down"

            # 로그 파일 체크 (최근 5분 이내 활동)
            log_file = Path("logs/trader.log")
            if log_file.exists():
                stat = log_file.stat()
                if time.time() - stat.st_mtime > 300:  # 5분 이상 오래됨
                    return "warning"

            return "healthy"

        except Exception:
            return "critical"

    def _check_ares_health(self) -> str:
        """ARES 분석 엔진 헬스 체크"""
        try:
            # ARES 출력 파일 체크
            ares_files = list(Path("shared_data/ares").glob("*.json"))
            if not ares_files:
                return "warning"

            # 최근 파일이 10분 이내인지 체크
            latest_file = max(ares_files, key=lambda f: f.stat().st_mtime)
            if time.time() - latest_file.stat().st_mtime > 600:  # 10분 이상 오래됨
                return "warning"

            return "healthy"

        except Exception:
            return "critical"

    def _check_databus_health(self) -> str:
        """DataBus 헬스 체크"""
        try:
            databus_file = Path("shared_data/databus_snapshot.json")
            if not databus_file.exists():
                return "down"

            # 파일 내용 체크
            with open(databus_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 필수 필드 체크
            required_fields = ["timestamp", "meta", "ohlcv_1m"]
            for field in required_fields:
                if field not in data:
                    return "warning"

            # 타임스탬프 체크 (5분 이내)
            file_time = data.get("timestamp", 0)
            if time.time() - file_time > 300:
                return "warning"

            return "healthy"

        except Exception:
            return "critical"

    def _check_websocket_health(self) -> str:
        """WebSocket 연결 헬스 체크"""
        try:
            # 시스템 상태 파일 체크
            system_state_file = Path("shared_data/system_state.json")
            if not system_state_file.exists():
                return "down"

            with open(system_state_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 데이터 나이 체크
            age_sec = data.get("age_sec", 999)
            if age_sec > 120:  # 2분 이상 오래됨
                return "warning"
            elif age_sec > 300:  # 5분 이상 오래됨
                return "critical"

            return "healthy"

        except Exception:
            return "critical"

    def _analyze_error_patterns(self):
        """오류 패턴 분석"""
        try:
            current_time = time.time()

            for service_name, errors in self.error_patterns.items():
                # 최근 1시간 이내 오류만 유지
                recent_errors = [t for t in errors if current_time - t < 3600]
                self.error_patterns[service_name] = recent_errors

                # 오류 빈도 분석
                if len(recent_errors) > 10:  # 1시간에 10회 이상 오류
                    self.logger.warning(
                        f"서비스 {service_name} 오류 빈도 높음: {len(recent_errors)}회/시간"
                    )

                    # 해당 서비스 상태를 warning으로 변경
                    if service_name in self.health_status:
                        self.health_status[service_name].status = "warning"

        except Exception as e:
            self.logger.error(f"오류 패턴 분석 오류: {e}")

    def _trigger_auto_healing(self):
        """자가치유 트리거"""
        try:
            current_time = time.time()

            for service_name, status_obj in self.health_status.items():
                # 쿨다운 체크
                if (
                    status_obj.last_healing
                    and current_time - status_obj.last_healing < self.healing_cooldown
                ):
                    continue

                # 최대 시도 횟수 체크
                if status_obj.auto_healing_attempts >= self.max_healing_attempts:
                    continue

                # 치유가 필요한 상태인지 체크
                if status_obj.status in ["warning", "critical", "down"]:
                    self.logger.info(
                        f"자가치유 트리거: {service_name} ({status_obj.status})"
                    )
                    self._execute_auto_healing(service_name, status_obj)

        except Exception as e:
            self.logger.error(f"자가치유 트리거 오류: {e}")

    def _execute_auto_healing(self, service_name: str, status_obj: HealthStatus):
        """자가치유 실행"""
        try:
            current_time = time.time()
            status_obj.auto_healing_attempts += 1
            status_obj.last_healing = current_time

            self.logger.info(
                f"자가치유 실행: {service_name} (시도 {status_obj.auto_healing_attempts}/{self.max_healing_attempts})"
            )

            if service_name == "feeder":
                self._heal_feeder_service()
            elif service_name == "trader":
                self._heal_trader_service()
            elif service_name == "ares":
                self._heal_ares_service()
            elif service_name == "databus":
                self._heal_databus_service()
            elif service_name == "websocket_connections":
                self._heal_websocket_connections()

        except Exception as e:
            self.logger.error(f"{service_name} 자가치유 실행 오류: {e}")

    def _heal_feeder_service(self):
        """Feeder 서비스 자가치유"""
        try:
            # Feeder 서비스 재시작 명령 (PID 파일 삭제)
            feeder_pid_file = Path("shared_data/feeder.pid")
            if feeder_pid_file.exists():
                feeder_pid_file.unlink()
                self.logger.info("자가치유: Feeder 서비스 재시작 트리거")

        except Exception as e:
            self.logger.error(f"Feeder 자가치유 실패: {e}")

    def _heal_trader_service(self):
        """Trader 서비스 자가치유"""
        try:
            # Trader 서비스 재시작 명령 (PID 파일 삭제)
            trader_pid_file = Path("shared_data/trader.pid")
            if trader_pid_file.exists():
                trader_pid_file.unlink()
                self.logger.info("자가치유: Trader 서비스 재시작 트리거")

        except Exception as e:
            self.logger.error(f"Trader 자가치유 실패: {e}")

    def _heal_ares_service(self):
        """ARES 서비스 자가치유"""
        try:
            # ARES 캐시 정리
            ares_dir = Path("shared_data/ares")
            if ares_dir.exists():
                for file in ares_dir.glob("*.json"):
                    file.unlink()
                self.logger.info("자가치유: ARES 캐시 정리")

        except Exception as e:
            self.logger.error(f"ARES 자가치유 실패: {e}")

    def _heal_databus_service(self):
        """DataBus 자가치유"""
        try:
            # DataBus 파일 재생성
            databus_file = Path("shared_data/databus_snapshot.json")
            if databus_file.exists():
                # 백업 생성
                backup_file = databus_file.with_suffix(".json.backup")
                databus_file.rename(backup_file)

                # 새 파일 생성
                empty_databus = {
                    "timestamp": time.time(),
                    "meta": {"age_sec": 999, "update_count": 0},
                    "ohlcv_1m": {},
                    "account": {"equity": 10000.0},
                    "risk_budget": {"daily_loss_cap": 1000.0},
                }

                with open(databus_file, "w", encoding="utf-8") as f:
                    json.dump(empty_databus, f, indent=2, ensure_ascii=False)

                self.logger.info("자가치유: DataBus 파일 재생성")

        except Exception as e:
            self.logger.error(f"DataBus 자가치유 실패: {e}")

    def _heal_websocket_connections(self):
        """WebSocket 연결 자가치유"""
        try:
            # 시스템 상태 파일 재생성
            system_state_file = Path("shared_data/system_state.json")
            if system_state_file.exists():
                # 백업 생성
                backup_file = system_state_file.with_suffix(".json.backup")
                system_state_file.rename(backup_file)

                # 새 파일 생성
                empty_system_state = {
                    "timestamp": time.time(),
                    "age_sec": 0,
                    "symbol": "btcusdt",
                    "interval": "1m",
                    "kline_status": "unknown",
                }

                with open(system_state_file, "w", encoding="utf-8") as f:
                    json.dump(empty_system_state, f, indent=2, ensure_ascii=False)

                self.logger.info("자가치유: 시스템 상태 파일 재생성")

        except Exception as e:
            self.logger.error(f"WebSocket 자가치유 실패: {e}")

    def _record_error_pattern(self, service_name: str, error_msg: str):
        """오류 패턴 기록"""
        try:
            if service_name not in self.error_patterns:
                self.error_patterns[service_name] = []

            self.error_patterns[service_name].append(time.time())

            # 최근 100개 오류만 유지
            if len(self.error_patterns[service_name]) > 100:
                self.error_patterns[service_name] = self.error_patterns[service_name][
                    -100:
                ]

        except Exception as e:
            self.logger.error(f"오류 패턴 기록 실패: {e}")

    def _save_health_status(self):
        """헬스 상태 저장"""
        try:
            data = {}
            for service_name, status_obj in self.health_status.items():
                data[service_name] = {
                    "status": status_obj.status,
                    "last_check": status_obj.last_check,
                    "error_count": status_obj.error_count,
                    "last_error": status_obj.last_error,
                    "auto_healing_attempts": status_obj.auto_healing_attempts,
                    "last_healing": status_obj.last_healing,
                }

            with open(self.health_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        except Exception as e:
            self.logger.error(f"헬스 상태 저장 실패: {e}")

    def _load_health_status(self):
        """헬스 상태 로드"""
        try:
            if not self.health_file.exists():
                return

            with open(self.health_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            for service_name, status_data in data.items():
                self.health_status[service_name] = HealthStatus(
                    service_name=service_name,
                    status=status_data.get("status", "unknown"),
                    last_check=status_data.get("last_check", 0),
                    error_count=status_data.get("error_count", 0),
                    last_error=status_data.get("last_error"),
                    auto_healing_attempts=status_data.get("auto_healing_attempts", 0),
                    last_healing=status_data.get("last_healing"),
                )

        except Exception as e:
            self.logger.error(f"헬스 상태 로드 실패: {e}")

    def get_health_summary(self) -> Dict[str, Any]:
        """헬스 요약 정보 반환"""
        try:
            summary = {
                "timestamp": time.time(),
                "auto_healing_enabled": self.auto_healing_enabled,
                "services": {},
            }

            for service_name, status_obj in self.health_status.items():
                summary["services"][service_name] = {
                    "status": status_obj.status,
                    "last_check": status_obj.last_check,
                    "error_count": status_obj.error_count,
                    "auto_healing_attempts": status_obj.auto_healing_attempts,
                }

            return summary

        except Exception as e:
            self.logger.error(f"헬스 요약 생성 실패: {e}")
            return {"timestamp": time.time(), "error": str(e)}


# 전역 헬스 모니터 인스턴스
health_monitor = HealthMonitor()

if __name__ == "__main__":
    # 테스트
    logging.basicConfig(level=logging.INFO)

    monitor = HealthMonitor()
    monitor.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        monitor.stop()
        print("헬스 모니터 중지됨")
