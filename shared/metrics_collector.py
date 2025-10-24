#!/usr/bin/env python3
"""
로그/계측 시스템
체결, 파일 I/O, Watchdog 메트릭 수집 및 분석
"""

import json
import logging
import sys
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@dataclass
class ExecutionMetrics:
    """체결 메트릭"""

    timestamp: float
    symbol: str
    action: str
    size_usdt: float
    effective_spread_bps: float
    slippage_bps: float
    fill_ratio: float
    latency_ms: float
    strategy: str
    success: bool


@dataclass
class FileIOMetrics:
    """파일 I/O 메트릭"""

    timestamp: float
    operation: str  # "history_write", "snapshot_write", "tmp_replace"
    symbol: str
    success: bool
    file_size_bytes: int
    duration_ms: float
    error_message: str = ""


@dataclass
class WatchdogMetrics:
    """Watchdog 메트릭"""

    timestamp: float
    action: str  # "restart", "restart_all", "stop"
    module: str
    attempt: int
    cause: str
    success: bool
    duration_ms: float


class MetricsCollector:
    """메트릭 수집기"""

    def __init__(self):
        self.logger = self._setup_logging()

        # 메트릭 저장소
        self.execution_metrics: deque = deque(maxlen=1000)
        self.file_io_metrics: deque = deque(maxlen=1000)
        self.watchdog_metrics: deque = deque(maxlen=1000)

        # 실시간 통계
        self.stats = {
            "execution": {
                "total_trades": 0,
                "successful_trades": 0,
                "avg_slippage_bps": 0.0,
                "avg_latency_ms": 0.0,
                "avg_fill_ratio": 0.0,
            },
            "file_io": {
                "total_operations": 0,
                "successful_operations": 0,
                "avg_duration_ms": 0.0,
                "error_rate": 0.0,
            },
            "watchdog": {
                "total_actions": 0,
                "restart_count": 0,
                "avg_restart_duration_ms": 0.0,
            },
        }

        # 메트릭 파일 경로
        self.metrics_dir = Path("logs/metrics")
        self.metrics_dir.mkdir(exist_ok=True)

        # 백그라운드 스레드
        self.running = False
        self.flush_thread = None

    def _setup_logging(self) -> logging.Logger:
        """로깅 설정"""
        logger = logging.getLogger("metrics")
        logger.setLevel(logging.INFO)

        # 파일 핸들러
        file_handler = logging.FileHandler("logs/metrics.log", encoding="utf-8")
        file_handler.setLevel(logging.INFO)

        # 포맷터
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(formatter)

        # 핸들러 추가
        logger.addHandler(file_handler)

        return logger

    def start(self):
        """메트릭 수집기 시작"""
        if self.running:
            return

        self.running = True
        self.flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self.flush_thread.start()

        self.logger.info("메트릭 수집기 시작")

    def stop(self):
        """메트릭 수집기 중지"""
        self.running = False
        if self.flush_thread:
            self.flush_thread.join(timeout=5)

        # 최종 메트릭 저장
        self._flush_metrics()
        self.logger.info("메트릭 수집기 중지")

    def record_execution(
        self,
        symbol: str,
        action: str,
        size_usdt: float,
        effective_spread_bps: float,
        slippage_bps: float,
        fill_ratio: float,
        latency_ms: float,
        strategy: str,
        success: bool,
    ):
        """체결 메트릭 기록"""
        try:
            metric = ExecutionMetrics(
                timestamp=time.time(),
                symbol=symbol,
                action=action,
                size_usdt=size_usdt,
                effective_spread_bps=effective_spread_bps,
                slippage_bps=slippage_bps,
                fill_ratio=fill_ratio,
                latency_ms=latency_ms,
                strategy=strategy,
                success=success,
            )

            self.execution_metrics.append(metric)
            self._update_execution_stats()

        except Exception as e:
            self.logger.error(f"체결 메트릭 기록 오류: {e}")

    def record_file_io(
        self,
        operation: str,
        symbol: str,
        success: bool,
        file_size_bytes: int,
        duration_ms: float,
        error_message: str = "",
    ):
        """파일 I/O 메트릭 기록"""
        try:
            metric = FileIOMetrics(
                timestamp=time.time(),
                operation=operation,
                symbol=symbol,
                success=success,
                file_size_bytes=file_size_bytes,
                duration_ms=duration_ms,
                error_message=error_message,
            )

            self.file_io_metrics.append(metric)
            self._update_file_io_stats()

        except Exception as e:
            self.logger.error(f"파일 I/O 메트릭 기록 오류: {e}")

    def record_watchdog_action(
        self,
        action: str,
        module: str,
        attempt: int,
        cause: str,
        success: bool,
        duration_ms: float,
    ):
        """Watchdog 메트릭 기록"""
        try:
            metric = WatchdogMetrics(
                timestamp=time.time(),
                action=action,
                module=module,
                attempt=attempt,
                cause=cause,
                success=success,
                duration_ms=duration_ms,
            )

            self.watchdog_metrics.append(metric)
            self._update_watchdog_stats()

        except Exception as e:
            self.logger.error(f"Watchdog 메트릭 기록 오류: {e}")

    def _update_execution_stats(self):
        """체결 통계 업데이트"""
        try:
            if not self.execution_metrics:
                return

            total_trades = len(self.execution_metrics)
            successful_trades = sum(1 for m in self.execution_metrics if m.success)

            if total_trades > 0:
                avg_slippage = (
                    sum(m.slippage_bps for m in self.execution_metrics) / total_trades
                )
                avg_latency = (
                    sum(m.latency_ms for m in self.execution_metrics) / total_trades
                )
                avg_fill_ratio = (
                    sum(m.fill_ratio for m in self.execution_metrics) / total_trades
                )

                self.stats["execution"].update(
                    {
                        "total_trades": total_trades,
                        "successful_trades": successful_trades,
                        "avg_slippage_bps": avg_slippage,
                        "avg_latency_ms": avg_latency,
                        "avg_fill_ratio": avg_fill_ratio,
                    }
                )

        except Exception as e:
            self.logger.error(f"체결 통계 업데이트 오류: {e}")

    def _update_file_io_stats(self):
        """파일 I/O 통계 업데이트"""
        try:
            if not self.file_io_metrics:
                return

            total_ops = len(self.file_io_metrics)
            successful_ops = sum(1 for m in self.file_io_metrics if m.success)

            if total_ops > 0:
                avg_duration = (
                    sum(m.duration_ms for m in self.file_io_metrics) / total_ops
                )
                error_rate = (total_ops - successful_ops) / total_ops

                self.stats["file_io"].update(
                    {
                        "total_operations": total_ops,
                        "successful_operations": successful_ops,
                        "avg_duration_ms": avg_duration,
                        "error_rate": error_rate,
                    }
                )

        except Exception as e:
            self.logger.error(f"파일 I/O 통계 업데이트 오류: {e}")

    def _update_watchdog_stats(self):
        """Watchdog 통계 업데이트"""
        try:
            if not self.watchdog_metrics:
                return

            total_actions = len(self.watchdog_metrics)
            restart_count = sum(
                1 for m in self.watchdog_metrics if m.action == "restart"
            )

            if total_actions > 0:
                avg_duration = (
                    sum(m.duration_ms for m in self.watchdog_metrics) / total_actions
                )

                self.stats["watchdog"].update(
                    {
                        "total_actions": total_actions,
                        "restart_count": restart_count,
                        "avg_restart_duration_ms": avg_duration,
                    }
                )

        except Exception as e:
            self.logger.error(f"Watchdog 통계 업데이트 오류: {e}")

    def _flush_loop(self):
        """메트릭 플러시 루프 (백그라운드 스레드)"""
        while self.running:
            try:
                time.sleep(60)  # 1분마다 플러시
                self._flush_metrics()
            except Exception as e:
                self.logger.error(f"메트릭 플러시 루프 오류: {e}")

    def _flush_metrics(self):
        """메트릭을 파일에 저장"""
        try:
            current_time = datetime.now()

            # 체결 메트릭 저장
            if self.execution_metrics:
                execution_file = (
                    self.metrics_dir
                    / f"execution_{current_time.strftime('%Y%m%d_%H%M')}.json"
                )
                with open(execution_file, "w", encoding="utf-8") as f:
                    json.dump(
                        [asdict(m) for m in self.execution_metrics],
                        f,
                        ensure_ascii=False,
                        indent=2,
                    )

            # 파일 I/O 메트릭 저장
            if self.file_io_metrics:
                file_io_file = (
                    self.metrics_dir
                    / f"file_io_{current_time.strftime('%Y%m%d_%H%M')}.json"
                )
                with open(file_io_file, "w", encoding="utf-8") as f:
                    json.dump(
                        [asdict(m) for m in self.file_io_metrics],
                        f,
                        ensure_ascii=False,
                        indent=2,
                    )

            # Watchdog 메트릭 저장
            if self.watchdog_metrics:
                watchdog_file = (
                    self.metrics_dir
                    / f"watchdog_{current_time.strftime('%Y%m%d_%H%M')}.json"
                )
                with open(watchdog_file, "w", encoding="utf-8") as f:
                    json.dump(
                        [asdict(m) for m in self.watchdog_metrics],
                        f,
                        ensure_ascii=False,
                        indent=2,
                    )

            # 통계 저장
            stats_file = (
                self.metrics_dir / f"stats_{current_time.strftime('%Y%m%d_%H%M')}.json"
            )
            with open(stats_file, "w", encoding="utf-8") as f:
                json.dump(self.stats, f, ensure_ascii=False, indent=2)

            self.logger.info(
                f"메트릭 플러시 완료: {len(self.execution_metrics)} 체결, {len(self.file_io_metrics)} 파일I/O, {len(self.watchdog_metrics)} Watchdog"
            )

        except Exception as e:
            self.logger.error(f"메트릭 플러시 오류: {e}")

    def get_current_stats(self) -> Dict[str, Any]:
        """현재 통계 반환"""
        return self.stats.copy()

    def get_recent_metrics(self, metric_type: str, limit: int = 100) -> List[Dict]:
        """최근 메트릭 반환"""
        try:
            if metric_type == "execution":
                return [asdict(m) for m in list(self.execution_metrics)[-limit:]]
            elif metric_type == "file_io":
                return [asdict(m) for m in list(self.file_io_metrics)[-limit:]]
            elif metric_type == "watchdog":
                return [asdict(m) for m in list(self.watchdog_metrics)[-limit:]]
            else:
                return []
        except Exception as e:
            self.logger.error(f"최근 메트릭 조회 오류: {e}")
            return []


# 전역 메트릭 수집기 인스턴스
metrics_collector = MetricsCollector()


def start_metrics_collection():
    """메트릭 수집 시작"""
    metrics_collector.start()


def stop_metrics_collection():
    """메트릭 수집 중지"""
    metrics_collector.stop()


def record_execution_metric(
    symbol: str,
    action: str,
    size_usdt: float,
    effective_spread_bps: float,
    slippage_bps: float,
    fill_ratio: float,
    latency_ms: float,
    strategy: str,
    success: bool,
):
    """체결 메트릭 기록 (편의 함수)"""
    metrics_collector.record_execution(
        symbol,
        action,
        size_usdt,
        effective_spread_bps,
        slippage_bps,
        fill_ratio,
        latency_ms,
        strategy,
        success,
    )


def record_file_io_metric(
    operation: str,
    symbol: str,
    success: bool,
    file_size_bytes: int,
    duration_ms: float,
    error_message: str = "",
):
    """파일 I/O 메트릭 기록 (편의 함수)"""
    metrics_collector.record_file_io(
        operation, symbol, success, file_size_bytes, duration_ms, error_message
    )


def record_watchdog_metric(
    action: str,
    module: str,
    attempt: int,
    cause: str,
    success: bool,
    duration_ms: float,
):
    """Watchdog 메트릭 기록 (편의 함수)"""
    metrics_collector.record_watchdog_action(
        action, module, attempt, cause, success, duration_ms
    )


def get_metrics_stats() -> Dict[str, Any]:
    """메트릭 통계 반환 (편의 함수)"""
    return metrics_collector.get_current_stats()


def get_recent_metrics(metric_type: str, limit: int = 100) -> List[Dict]:
    """최근 메트릭 반환 (편의 함수)"""
    return metrics_collector.get_recent_metrics(metric_type, limit)


if __name__ == "__main__":
    # 테스트 실행
    metrics_collector.start()

    try:
        # 테스트 메트릭 기록
        record_execution_metric(
            "btcusdt", "buy", 1000, 2.5, 1.2, 0.95, 150, "trend_multi_tf", True
        )
        record_file_io_metric("history_write", "btcusdt", True, 1024, 25)
        record_watchdog_metric("restart", "feeder", 1, "process_down", True, 2000)

        # 통계 출력
        stats = get_metrics_stats()
        print("현재 통계:")
        print(json.dumps(stats, ensure_ascii=False, indent=2))

        time.sleep(2)

    finally:
        metrics_collector.stop()
