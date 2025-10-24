#!/usr/bin/env python3
"""
Telemetry & Metrics Collection Module
텔레메트리 및 메트릭 수집 시스템
"""

import json
import logging
import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


@dataclass
class MetricData:
    """메트릭 데이터"""

    timestamp: float
    metric_type: str  # "execution", "file_io", "watchdog", "system"
    data: Dict[str, Any]


class TelemetryCollector:
    """텔레메트리 수집기"""

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {
            # Coin Quant v1.0 텔레메트리 설정
            "metrics_enabled": True,
            "metrics_interval_sec": 60,  # 메트릭 수집 간격 (60초)
            "metrics_retention_hours": 24,  # 메트릭 보존 기간 (24시간)
            "metrics_file": "logs/metrics.log",
            "summary_interval_min": 10,  # 요약 간격 (10분)
            "summary_file": "logs/metrics_summary.json",
        }

        self.name = "telemetry_collector"
        self.logger = logging.getLogger(f"{__name__}.{self.name}")

        # 메트릭 저장소
        self.metrics_buffer = deque(maxlen=10000)  # 최대 10000개 메트릭
        self.metrics_by_type = {
            "execution": deque(maxlen=1000),
            "file_io": deque(maxlen=1000),
            "watchdog": deque(maxlen=1000),
            "system": deque(maxlen=1000),
        }

        # 요약 통계
        self.summary_stats = {
            "execution": {
                "total_orders": 0,
                "successful_orders": 0,
                "avg_spread_bps": 0.0,
                "avg_slippage_bps": 0.0,
                "avg_fill_rate": 0.0,
                "avg_latency_ms": 0.0,
                "retry_count": 0,
                "consecutive_losses": 0,
                "rate_limit_hits": 0,
            },
            "file_io": {
                "total_operations": 0,
                "successful_operations": 0,
                "avg_file_size_bytes": 0.0,
                "avg_duration_ms": 0.0,
                "error_count": 0,
            },
            "watchdog": {
                "total_actions": 0,
                "successful_actions": 0,
                "restart_count": 0,
                "failure_count": 0,
                "recovery_count": 0,
            },
            "system": {
                "cpu_usage": 0.0,
                "memory_usage": 0.0,
                "disk_usage": 0.0,
                "network_latency_ms": 0.0,
            },
        }

        # 스레드 관리
        self.is_running = False
        self.collection_thread = None
        self.summary_thread = None

        # 상태 로드
        self._load_summary_stats()

    def _load_summary_stats(self):
        """요약 통계 로드"""
        try:
            if os.path.exists(self.config["summary_file"]):
                with open(self.config["summary_file"], "r", encoding="utf-8") as f:
                    data = json.load(f)

                self.summary_stats.update(data.get("summary_stats", {}))
                self.logger.info("요약 통계 로드 완료")

        except Exception as e:
            self.logger.error(f"요약 통계 로드 오류: {e}")

    def _save_summary_stats(self):
        """요약 통계 저장"""
        try:
            data = {
                "summary_stats": self.summary_stats,
                "last_update": time.time(),
                "timestamp": datetime.now().isoformat(),
            }

            os.makedirs(os.path.dirname(self.config["summary_file"]), exist_ok=True)
            with open(self.config["summary_file"], "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        except Exception as e:
            self.logger.error(f"요약 통계 저장 오류: {e}")

    def start(self):
        """텔레메트리 수집 시작"""
        try:
            self.is_running = True

            # 메트릭 수집 스레드 시작
            self.collection_thread = threading.Thread(
                target=self._collection_loop, daemon=True
            )
            self.collection_thread.start()

            # 요약 스레드 시작
            self.summary_thread = threading.Thread(
                target=self._summary_loop, daemon=True
            )
            self.summary_thread.start()

            self.logger.info("텔레메트리 수집 시작")

        except Exception as e:
            self.logger.error(f"텔레메트리 수집 시작 오류: {e}")

    def stop(self):
        """텔레메트리 수집 중지"""
        try:
            self.is_running = False

            if self.collection_thread and self.collection_thread.is_alive():
                self.collection_thread.join(timeout=5)

            if self.summary_thread and self.summary_thread.is_alive():
                self.summary_thread.join(timeout=5)

            # 최종 요약 저장
            self._save_summary_stats()

            self.logger.info("텔레메트리 수집 중지")

        except Exception as e:
            self.logger.error(f"텔레메트리 수집 중지 오류: {e}")

    def _collection_loop(self):
        """메트릭 수집 루프"""
        while self.is_running:
            try:
                # 시스템 메트릭 수집
                self._collect_system_metrics()

                # 메트릭 파일에 기록
                self._write_metrics_to_file()

                time.sleep(self.config["metrics_interval_sec"])

            except Exception as e:
                self.logger.error(f"메트릭 수집 루프 오류: {e}")
                time.sleep(self.config["metrics_interval_sec"])

    def _summary_loop(self):
        """요약 통계 루프"""
        while self.is_running:
            try:
                # 요약 통계 계산
                self._calculate_summary_stats()

                # 요약 통계 저장
                self._save_summary_stats()

                time.sleep(self.config["summary_interval_min"] * 60)

            except Exception as e:
                self.logger.error(f"요약 통계 루프 오류: {e}")
                time.sleep(self.config["summary_interval_min"] * 60)

    def _collect_system_metrics(self):
        """시스템 메트릭 수집"""
        try:
            import psutil

            # CPU 사용률
            cpu_percent = psutil.cpu_percent(interval=1)

            # 메모리 사용률
            memory = psutil.virtual_memory()
            memory_percent = memory.percent

            # 디스크 사용률
            disk = psutil.disk_usage("/")
            disk_percent = disk.percent

            # 네트워크 지연 (간단한 추정)
            network_latency = 0.0  # 실제로는 ping 등으로 측정

            # 시스템 메트릭 추가
            system_metric = MetricData(
                timestamp=time.time(),
                metric_type="system",
                data={
                    "cpu_usage": cpu_percent,
                    "memory_usage": memory_percent,
                    "disk_usage": disk_percent,
                    "network_latency_ms": network_latency,
                },
            )

            self.add_metric(system_metric)

        except Exception as e:
            self.logger.error(f"시스템 메트릭 수집 오류: {e}")

    def _write_metrics_to_file(self):
        """메트릭을 파일에 기록"""
        try:
            if not self.metrics_buffer:
                return

            # 최근 메트릭들을 파일에 기록
            recent_metrics = list(self.metrics_buffer)[-100:]  # 최근 100개

            with open(self.config["metrics_file"], "a", encoding="utf-8") as f:
                for metric in recent_metrics:
                    log_entry = {
                        "timestamp": metric.timestamp,
                        "metric_type": metric.metric_type,
                        "data": metric.data,
                    }
                    f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

            # 버퍼 정리 (파일에 기록된 메트릭 제거)
            for _ in range(len(recent_metrics)):
                if self.metrics_buffer:
                    self.metrics_buffer.popleft()

        except Exception as e:
            self.logger.error(f"메트릭 파일 기록 오류: {e}")

    def _calculate_summary_stats(self):
        """요약 통계 계산"""
        try:
            current_time = time.time()
            window_sec = self.config["summary_interval_min"] * 60

            # 각 메트릭 타입별로 요약 계산
            for metric_type, metrics in self.metrics_by_type.items():
                if not metrics:
                    continue

                # 시간 윈도우 내의 메트릭 필터링
                recent_metrics = [
                    m for m in metrics if current_time - m.timestamp <= window_sec
                ]

                if not recent_metrics:
                    continue

                # 메트릭 타입별 요약 계산
                if metric_type == "execution":
                    self._calculate_execution_summary(recent_metrics)
                elif metric_type == "file_io":
                    self._calculate_file_io_summary(recent_metrics)
                elif metric_type == "watchdog":
                    self._calculate_watchdog_summary(recent_metrics)
                elif metric_type == "system":
                    self._calculate_system_summary(recent_metrics)

        except Exception as e:
            self.logger.error(f"요약 통계 계산 오류: {e}")

    def _calculate_execution_summary(self, metrics: List[MetricData]):
        """실행 메트릭 요약 계산"""
        try:
            total_orders = len(metrics)
            successful_orders = sum(1 for m in metrics if m.data.get("success", False))

            spreads = [
                m.data.get("spread_bps", 0) for m in metrics if m.data.get("spread_bps")
            ]
            slippages = [
                m.data.get("slippage_bps", 0)
                for m in metrics
                if m.data.get("slippage_bps")
            ]
            fill_rates = [
                m.data.get("fill_rate", 0) for m in metrics if m.data.get("fill_rate")
            ]
            latencies = [
                m.data.get("latency_ms", 0) for m in metrics if m.data.get("latency_ms")
            ]

            retry_count = sum(m.data.get("retry_count", 0) for m in metrics)
            consecutive_losses = sum(1 for m in metrics if m.data.get("pnl", 0) < 0)
            rate_limit_hits = sum(
                1 for m in metrics if m.data.get("rate_limit_hit", False)
            )

            # 요약 통계 업데이트
            self.summary_stats["execution"].update(
                {
                    "total_orders": total_orders,
                    "successful_orders": successful_orders,
                    "avg_spread_bps": sum(spreads) / len(spreads) if spreads else 0.0,
                    "avg_slippage_bps": (
                        sum(slippages) / len(slippages) if slippages else 0.0
                    ),
                    "avg_fill_rate": (
                        sum(fill_rates) / len(fill_rates) if fill_rates else 0.0
                    ),
                    "avg_latency_ms": (
                        sum(latencies) / len(latencies) if latencies else 0.0
                    ),
                    "retry_count": retry_count,
                    "consecutive_losses": consecutive_losses,
                    "rate_limit_hits": rate_limit_hits,
                }
            )

        except Exception as e:
            self.logger.error(f"실행 메트릭 요약 계산 오류: {e}")

    def _calculate_file_io_summary(self, metrics: List[MetricData]):
        """파일 I/O 메트릭 요약 계산"""
        try:
            total_operations = len(metrics)
            successful_operations = sum(
                1 for m in metrics if m.data.get("success", False)
            )

            file_sizes = [
                m.data.get("file_size_bytes", 0)
                for m in metrics
                if m.data.get("file_size_bytes")
            ]
            durations = [
                m.data.get("duration_ms", 0)
                for m in metrics
                if m.data.get("duration_ms")
            ]
            error_count = sum(1 for m in metrics if not m.data.get("success", False))

            # 요약 통계 업데이트
            self.summary_stats["file_io"].update(
                {
                    "total_operations": total_operations,
                    "successful_operations": successful_operations,
                    "avg_file_size_bytes": (
                        sum(file_sizes) / len(file_sizes) if file_sizes else 0.0
                    ),
                    "avg_duration_ms": (
                        sum(durations) / len(durations) if durations else 0.0
                    ),
                    "error_count": error_count,
                }
            )

        except Exception as e:
            self.logger.error(f"파일 I/O 메트릭 요약 계산 오류: {e}")

    def _calculate_watchdog_summary(self, metrics: List[MetricData]):
        """Watchdog 메트릭 요약 계산"""
        try:
            total_actions = len(metrics)
            successful_actions = sum(1 for m in metrics if m.data.get("success", False))

            restart_count = sum(
                1 for m in metrics if m.data.get("action_type") == "restart"
            )
            failure_count = sum(1 for m in metrics if not m.data.get("success", False))
            recovery_count = sum(
                1 for m in metrics if m.data.get("action_type") == "recovery"
            )

            # 요약 통계 업데이트
            self.summary_stats["watchdog"].update(
                {
                    "total_actions": total_actions,
                    "successful_actions": successful_actions,
                    "restart_count": restart_count,
                    "failure_count": failure_count,
                    "recovery_count": recovery_count,
                }
            )

        except Exception as e:
            self.logger.error(f"Watchdog 메트릭 요약 계산 오류: {e}")

    def _calculate_system_summary(self, metrics: List[MetricData]):
        """시스템 메트릭 요약 계산"""
        try:
            cpu_usages = [
                m.data.get("cpu_usage", 0) for m in metrics if m.data.get("cpu_usage")
            ]
            memory_usages = [
                m.data.get("memory_usage", 0)
                for m in metrics
                if m.data.get("memory_usage")
            ]
            disk_usages = [
                m.data.get("disk_usage", 0) for m in metrics if m.data.get("disk_usage")
            ]
            network_latencies = [
                m.data.get("network_latency_ms", 0)
                for m in metrics
                if m.data.get("network_latency_ms")
            ]

            # 요약 통계 업데이트
            self.summary_stats["system"].update(
                {
                    "cpu_usage": (
                        sum(cpu_usages) / len(cpu_usages) if cpu_usages else 0.0
                    ),
                    "memory_usage": (
                        sum(memory_usages) / len(memory_usages)
                        if memory_usages
                        else 0.0
                    ),
                    "disk_usage": (
                        sum(disk_usages) / len(disk_usages) if disk_usages else 0.0
                    ),
                    "network_latency_ms": (
                        sum(network_latencies) / len(network_latencies)
                        if network_latencies
                        else 0.0
                    ),
                }
            )

        except Exception as e:
            self.logger.error(f"시스템 메트릭 요약 계산 오류: {e}")

    def add_metric(self, metric: MetricData):
        """메트릭 추가"""
        try:
            # 전체 버퍼에 추가
            self.metrics_buffer.append(metric)

            # 타입별 버퍼에 추가
            if metric.metric_type in self.metrics_by_type:
                self.metrics_by_type[metric.metric_type].append(metric)

            # 로그에 기록 (ERROR/CODE/SYMBOL/ACTION_RESULT 형식)
            if metric.metric_type == "execution":
                self._log_execution_metric(metric)
            elif metric.metric_type == "file_io":
                self._log_file_io_metric(metric)
            elif metric.metric_type == "watchdog":
                self._log_watchdog_metric(metric)

        except Exception as e:
            self.logger.error(f"메트릭 추가 오류: {e}")

    def _log_execution_metric(self, metric: MetricData):
        """실행 메트릭 로그 기록"""
        try:
            data = metric.data
            symbol = data.get("symbol", "UNKNOWN")
            action = data.get("action", "UNKNOWN")
            success = data.get("success", False)

            # ERROR/CODE/SYMBOL/ACTION_RESULT 형식
            result_code = "SUCCESS" if success else "FAILURE"
            log_message = f"EXECUTION/{result_code}/{symbol}/{action}"

            if success:
                self.logger.info(log_message)
            else:
                error_message = data.get("error_message", "Unknown error")
                self.logger.error(f"{log_message} - {error_message}")

        except Exception as e:
            self.logger.error(f"실행 메트릭 로그 기록 오류: {e}")

    def _log_file_io_metric(self, metric: MetricData):
        """파일 I/O 메트릭 로그 기록"""
        try:
            data = metric.data
            operation = data.get("operation", "UNKNOWN")
            symbol = data.get("symbol", "UNKNOWN")
            success = data.get("success", False)

            # ERROR/CODE/SYMBOL/ACTION_RESULT 형식
            result_code = "SUCCESS" if success else "FAILURE"
            log_message = f"FILE_IO/{result_code}/{symbol}/{operation}"

            if success:
                self.logger.info(log_message)
            else:
                error_message = data.get("error_message", "Unknown error")
                self.logger.error(f"{log_message} - {error_message}")

        except Exception as e:
            self.logger.error(f"파일 I/O 메트릭 로그 기록 오류: {e}")

    def _log_watchdog_metric(self, metric: MetricData):
        """Watchdog 메트릭 로그 기록"""
        try:
            data = metric.data
            action_type = data.get("action_type", "UNKNOWN")
            target = data.get("target", "UNKNOWN")
            success = data.get("success", False)

            # ERROR/CODE/SYMBOL/ACTION_RESULT 형식
            result_code = "SUCCESS" if success else "FAILURE"
            log_message = f"WATCHDOG/{result_code}/{target}/{action_type}"

            if success:
                self.logger.info(log_message)
            else:
                error_message = data.get("error_message", "Unknown error")
                self.logger.error(f"{log_message} - {error_message}")

        except Exception as e:
            self.logger.error(f"Watchdog 메트릭 로그 기록 오류: {e}")

    def get_summary_stats(self) -> Dict[str, Any]:
        """요약 통계 반환"""
        try:
            return {
                "summary_stats": self.summary_stats,
                "last_update": time.time(),
                "timestamp": datetime.now().isoformat(),
                "metrics_count": len(self.metrics_buffer),
                "metrics_by_type": {
                    metric_type: len(metrics)
                    for metric_type, metrics in self.metrics_by_type.items()
                },
            }

        except Exception as e:
            self.logger.error(f"요약 통계 반환 오류: {e}")
            return {"error": str(e)}

    def get_status(self) -> Dict[str, Any]:
        """텔레메트리 상태 반환"""
        try:
            return {
                "is_running": self.is_running,
                "metrics_enabled": self.config["metrics_enabled"],
                "metrics_interval_sec": self.config["metrics_interval_sec"],
                "summary_interval_min": self.config["summary_interval_min"],
                "metrics_count": len(self.metrics_buffer),
                "metrics_by_type": {
                    metric_type: len(metrics)
                    for metric_type, metrics in self.metrics_by_type.items()
                },
                "last_update": time.time(),
            }

        except Exception as e:
            self.logger.error(f"상태 반환 오류: {e}")
            return {"error": str(e)}


# 전역 텔레메트리 수집기 인스턴스
telemetry_collector = TelemetryCollector()


# 편의 함수들
def record_execution_metric(symbol: str, action: str, success: bool, **kwargs):
    """실행 메트릭 기록"""
    try:
        metric = MetricData(
            timestamp=time.time(),
            metric_type="execution",
            data={"symbol": symbol, "action": action, "success": success, **kwargs},
        )
        telemetry_collector.add_metric(metric)
    except Exception as e:
        logger.error(f"실행 메트릭 기록 오류: {e}")


def record_file_io_metric(operation: str, symbol: str, success: bool, **kwargs):
    """파일 I/O 메트릭 기록"""
    try:
        metric = MetricData(
            timestamp=time.time(),
            metric_type="file_io",
            data={
                "operation": operation,
                "symbol": symbol,
                "success": success,
                **kwargs,
            },
        )
        telemetry_collector.add_metric(metric)
    except Exception as e:
        logger.error(f"파일 I/O 메트릭 기록 오류: {e}")


def record_watchdog_metric(action_type: str, target: str, success: bool, **kwargs):
    """Watchdog 메트릭 기록"""
    try:
        metric = MetricData(
            timestamp=time.time(),
            metric_type="watchdog",
            data={
                "action_type": action_type,
                "target": target,
                "success": success,
                **kwargs,
            },
        )
        telemetry_collector.add_metric(metric)
    except Exception as e:
        logger.error(f"Watchdog 메트릭 기록 오류: {e}")


# 단위 테스트
if __name__ == "__main__":
    # 테스트 설정
    test_config = {
        "metrics_enabled": True,
        "metrics_interval_sec": 10,
        "metrics_retention_hours": 1,
        "metrics_file": "test_metrics.log",
        "summary_interval_min": 1,
        "summary_file": "test_metrics_summary.json",
    }

    # 텔레메트리 수집기 생성
    collector = TelemetryCollector(test_config)

    # 테스트: 메트릭 추가
    print("=== 메트릭 추가 테스트 ===")
    record_execution_metric("btcusdt", "buy", True, spread_bps=5.0, slippage_bps=2.0)
    record_file_io_metric("snapshot_write", "ethusdt", True, file_size_bytes=1024)
    record_watchdog_metric("restart", "feeder", True)

    # 테스트: 요약 통계
    print("\n=== 요약 통계 테스트 ===")
    summary = collector.get_summary_stats()
    print(f"실행 메트릭: {summary['summary_stats']['execution']}")
    print(f"파일 I/O 메트릭: {summary['summary_stats']['file_io']}")
    print(f"Watchdog 메트릭: {summary['summary_stats']['watchdog']}")

    # 정리
    if os.path.exists("test_metrics.log"):
        os.remove("test_metrics.log")
    if os.path.exists("test_metrics_summary.json"):
        os.remove("test_metrics_summary.json")
