#!/usr/bin/env python3
"""
Health Metrics - Rolling window for uptime, restarts, last_ok_ts, failing_components
"""

import json
import logging
import time
from collections import deque
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Any, List, Optional, Deque


logger = logging.getLogger(__name__)


@dataclass
class ComponentMetrics:
    """Metrics for a single component"""
    name: str
    uptime_sec: float = 0.0
    restart_count: int = 0
    last_ok_ts: float = 0.0
    last_fail_ts: float = 0.0
    consecutive_failures: int = 0
    total_failures: int = 0
    availability_pct: float = 100.0


@dataclass
class SystemMetrics:
    """System-wide metrics"""
    timestamp: float
    uptime_sec: float
    total_restarts: int
    components: Dict[str, ComponentMetrics]
    failing_components: List[str]
    dor_history: List[bool]  # Last N DOR results
    last_dor_true_ts: float
    last_dor_false_ts: float


class HealthMetrics:
    """Health metrics collector with rolling window"""

    def __init__(self, window_size: int = 100):
        self.window_size = window_size
        self.project_root = Path(__file__).parent.parent.parent
        self.shared_data = self.project_root / "shared_data"
        self.metrics_file = self.shared_data / "health_metrics.json"

        # Rolling windows
        self.dor_history: Deque[bool] = deque(maxlen=window_size)
        self.component_metrics: Dict[str, ComponentMetrics] = {}

        # System start time
        self.system_start_ts = time.time()
        self.total_restarts = 0

        # Load existing metrics
        self._load_metrics()

    def _load_metrics(self):
        """Load metrics from disk"""
        try:
            if self.metrics_file.exists():
                with open(self.metrics_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Load component metrics
                for name, metrics_data in data.get("components", {}).items():
                    self.component_metrics[name] = ComponentMetrics(**metrics_data)

                # Load DOR history
                dor_history = data.get("dor_history", [])
                self.dor_history.extend(dor_history[-self.window_size:])

                # Load system metrics
                self.system_start_ts = data.get("system_start_ts", self.system_start_ts)
                self.total_restarts = data.get("total_restarts", 0)

                logger.info(f"Loaded metrics: {len(self.component_metrics)} components, {len(self.dor_history)} DOR history")

        except Exception as e:
            logger.error(f"Failed to load metrics: {e}")

    def _save_metrics(self):
        """Save metrics to disk"""
        try:
            # Prepare data
            data = {
                "timestamp": time.time(),
                "system_start_ts": self.system_start_ts,
                "total_restarts": self.total_restarts,
                "components": {
                    name: asdict(metrics) for name, metrics in self.component_metrics.items()
                },
                "dor_history": list(self.dor_history),
                "last_dor_true_ts": self._get_last_dor_true_ts(),
                "last_dor_false_ts": self._get_last_dor_false_ts()
            }

            # Atomic write
            # UTF-8, no BOM
            temp_file = self.metrics_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            temp_file.replace(self.metrics_file)

        except Exception as e:
            logger.error(f"Failed to save metrics: {e}")

    def update_from_health_check(self, health_result: Dict[str, Any]):
        """Update metrics from health check result"""
        try:
            # Update DOR history
            dor = health_result.get("dor", False)
            self.dor_history.append(dor)

            # Update component metrics
            failing_components = health_result.get("failing_components", [])
            probes = health_result.get("probes", {})

            # Map probes to components
            probe_to_component = {
                "ws_stream": "Feeder",
                "rest_latency": "REST_API",
                "databus_snapshot": "DataBus",
                "ares_signal_flow": "ARES",
                "trader_gateway": "Trader",
                "position_snapshot": "PositionTracker"
            }

            current_time = time.time()

            for probe_name, component_name in probe_to_component.items():
                probe_result = probes.get(probe_name, {})
                probe_ok = probe_result.get("ok", False)

                # Initialize component metrics if not exists
                if component_name not in self.component_metrics:
                    self.component_metrics[component_name] = ComponentMetrics(
                        name=component_name,
                        last_ok_ts=current_time if probe_ok else 0.0
                    )

                metrics = self.component_metrics[component_name]

                # Update metrics
                if probe_ok:
                    metrics.last_ok_ts = current_time
                    metrics.consecutive_failures = 0
                else:
                    metrics.last_fail_ts = current_time
                    metrics.consecutive_failures += 1
                    metrics.total_failures += 1

                # Calculate uptime (time since last failure)
                if metrics.last_fail_ts > 0:
                    metrics.uptime_sec = current_time - metrics.last_fail_ts
                else:
                    metrics.uptime_sec = current_time - self.system_start_ts

                # Calculate availability
                total_time = current_time - self.system_start_ts
                if total_time > 0:
                    # Simple heuristic: assume each failure = 60s downtime
                    downtime = metrics.total_failures * 60
                    metrics.availability_pct = max(0, (total_time - downtime) / total_time * 100)

            # Save metrics
            self._save_metrics()

        except Exception as e:
            logger.error(f"Failed to update metrics: {e}")

    def record_restart(self, component: str):
        """Record a component restart"""
        try:
            if component not in self.component_metrics:
                self.component_metrics[component] = ComponentMetrics(name=component)

            self.component_metrics[component].restart_count += 1
            self.total_restarts += 1

            self._save_metrics()

        except Exception as e:
            logger.error(f"Failed to record restart: {e}")

    def get_system_metrics(self) -> SystemMetrics:
        """Get current system metrics"""
        current_time = time.time()

        # Get failing components
        failing_components = [
            name for name, metrics in self.component_metrics.items()
            if metrics.consecutive_failures > 0
        ]

        return SystemMetrics(
            timestamp=current_time,
            uptime_sec=current_time - self.system_start_ts,
            total_restarts=self.total_restarts,
            components=self.component_metrics.copy(),
            failing_components=failing_components,
            dor_history=list(self.dor_history),
            last_dor_true_ts=self._get_last_dor_true_ts(),
            last_dor_false_ts=self._get_last_dor_false_ts()
        )

    def _get_last_dor_true_ts(self) -> float:
        """Get timestamp of last DOR=true"""
        try:
            if self.metrics_file.exists():
                with open(self.metrics_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return data.get("last_dor_true_ts", 0.0)
        except:
            pass
        return 0.0

    def _get_last_dor_false_ts(self) -> float:
        """Get timestamp of last DOR=false"""
        try:
            if self.metrics_file.exists():
                with open(self.metrics_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return data.get("last_dor_false_ts", 0.0)
        except:
            pass
        return 0.0

    def get_dor_success_rate(self) -> float:
        """Get DOR success rate from history"""
        if not self.dor_history:
            return 0.0

        success_count = sum(1 for dor in self.dor_history if dor)
        return (success_count / len(self.dor_history)) * 100

    def get_component_summary(self) -> Dict[str, Any]:
        """Get component summary"""
        summary = {}

        for name, metrics in self.component_metrics.items():
            summary[name] = {
                "uptime_sec": metrics.uptime_sec,
                "restart_count": metrics.restart_count,
                "last_ok_ts": metrics.last_ok_ts,
                "consecutive_failures": metrics.consecutive_failures,
                "total_failures": metrics.total_failures,
                "availability_pct": metrics.availability_pct,
                "status": "healthy" if metrics.consecutive_failures == 0 else "failing"
            }

        return summary

    def print_summary(self):
        """Print metrics summary"""
        metrics = self.get_system_metrics()

        print("\n" + "=" * 70)
        print("Health Metrics Summary")
        print("=" * 70)
        print(f"System Uptime: {metrics.uptime_sec / 3600:.2f} hours")
        print(f"Total Restarts: {metrics.total_restarts}")
        print(f"DOR Success Rate: {self.get_dor_success_rate():.1f}%")
        print(f"DOR History Size: {len(metrics.dor_history)}")

        if metrics.failing_components:
            print(f"\n⚠️  Failing Components: {', '.join(metrics.failing_components)}")
        else:
            print("\n✅ All components healthy")

        print("\nComponent Details:")
        print("-" * 70)

        for name, component in metrics.components.items():
            status_icon = "✅" if component.consecutive_failures == 0 else "❌"
            print(f"{status_icon} {name}:")
            print(f"   Uptime: {component.uptime_sec / 3600:.2f}h")
            print(f"   Restarts: {component.restart_count}")
            print(f"   Failures: {component.total_failures} (consecutive: {component.consecutive_failures})")
            print(f"   Availability: {component.availability_pct:.2f}%")

        print("=" * 70)


# Global instance
_global_metrics: Optional[HealthMetrics] = None


def get_metrics() -> HealthMetrics:
    """Get global metrics instance"""
    global _global_metrics
    if _global_metrics is None:
        _global_metrics = HealthMetrics()
    return _global_metrics


def update_from_health_check(health_result: Dict[str, Any]):
    """Update metrics from health check result"""
    get_metrics().update_from_health_check(health_result)


def record_restart(component: str):
    """Record a component restart"""
    get_metrics().record_restart(component)


def get_system_metrics() -> SystemMetrics:
    """Get current system metrics"""
    return get_metrics().get_system_metrics()


def print_summary():
    """Print metrics summary"""
    get_metrics().print_summary()


if __name__ == "__main__":
    # Test
    metrics = HealthMetrics()
    metrics.print_summary()
