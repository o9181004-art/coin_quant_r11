"""
Shared utilities and modules for coin_quant trading system
"""

# 주요 모듈들을 import하여 쉽게 접근할 수 있도록 함
try:
    from .metrics_collector import (get_metrics_stats, get_recent_metrics,
                                    metrics_collector, record_execution_metric,
                                    record_file_io_metric,
                                    record_watchdog_metric,
                                    start_metrics_collection,
                                    stop_metrics_collection)
except ImportError:
    # metrics_collector 모듈이 없는 경우 더미 함수들 제공
    def start_metrics_collection():
        pass

    def stop_metrics_collection():
        pass

    def record_execution_metric(*args, **kwargs):
        pass

    def record_file_io_metric(*args, **kwargs):
        pass

    def record_watchdog_metric(*args, **kwargs):
        pass

    def get_metrics_stats():
        return {}

    def get_recent_metrics(*args, **kwargs):
        return []


try:
    from .symbol_utils import normalize_symbol
except ImportError:

    def normalize_symbol(symbol):
        return symbol.lower()


try:
    from .telemetry import TelemetryCollector
except ImportError:

    class TelemetryCollector:
        def __init__(self):
            pass

        def start(self):
            pass

        def stop(self):
            pass


__all__ = [
    "metrics_collector",
    "start_metrics_collection",
    "stop_metrics_collection",
    "record_execution_metric",
    "record_file_io_metric",
    "record_watchdog_metric",
    "get_metrics_stats",
    "get_recent_metrics",
    "normalize_symbol",
    "TelemetryCollector",
]
