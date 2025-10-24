#!/usr/bin/env python3
"""
Order Latency Monitor
Tracks signal-to-order latency with stage-by-stage budget tracking
"""

import json
import logging
import time
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from .path_registry import get_absolute_path


class LatencyStage(Enum):
    """Latency tracking stages"""
    PARSE_VALIDATE = "parse_validate"
    GATE_CHECKS = "gate_checks"
    SUBMIT_EMIT = "submit_emit"


@dataclass
class LatencyBudget:
    """Latency budget per stage (milliseconds)"""
    parse_validate_ms: float = 300.0
    gate_checks_ms: float = 300.0
    submit_emit_ms: float = 2000.0
    
    @property
    def total_ms(self) -> float:
        return self.parse_validate_ms + self.gate_checks_ms + self.submit_emit_ms


@dataclass
class LatencyMeasurement:
    """Single latency measurement"""
    signal_ref: str
    symbol: str
    stage: str
    latency_ms: float
    budget_ms: float
    exceeded: bool
    ts: float


@dataclass
class OrderLatencyEvent:
    """Event when latency budget is exceeded"""
    event: str = "order_degraded"
    signal_ref: str = ""
    symbol: str = ""
    stage: str = ""
    latency_ms: float = 0.0
    budget_ms: float = 0.0
    exceeded_by_ms: float = 0.0
    ts: float = 0.0


class OrderLatencyMonitor:
    """
    Monitors signal-to-order latency
    Emits warnings when budget is exceeded
    """
    
    def __init__(self):
        self.logger = logging.getLogger('OrderLatency')
        self.events_path = get_absolute_path('shared_data') / 'order_latency_events.jsonl'
        self.summary_path = get_absolute_path('shared_data') / 'order_latency_summary.json'
        
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        self.summary_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.budget = LatencyBudget()
        self.measurements = []
    
    def start_timer(self) -> float:
        """Start a timer and return start timestamp"""
        return time.time()
    
    def measure_stage(
        self, 
        start_time: float, 
        stage: LatencyStage, 
        signal_ref: str = "",
        symbol: str = ""
    ) -> LatencyMeasurement:
        """
        Measure latency for a stage
        
        Args:
            start_time: Start timestamp from start_timer()
            stage: Latency stage
            signal_ref: Signal reference ID
            symbol: Trading symbol
        
        Returns:
            LatencyMeasurement with exceeded flag
        """
        latency_ms = (time.time() - start_time) * 1000
        
        # Get budget for this stage
        if stage == LatencyStage.PARSE_VALIDATE:
            budget_ms = self.budget.parse_validate_ms
        elif stage == LatencyStage.GATE_CHECKS:
            budget_ms = self.budget.gate_checks_ms
        elif stage == LatencyStage.SUBMIT_EMIT:
            budget_ms = self.budget.submit_emit_ms
        else:
            budget_ms = 0.0
        
        exceeded = latency_ms > budget_ms
        
        measurement = LatencyMeasurement(
            signal_ref=signal_ref,
            symbol=symbol,
            stage=stage.value,
            latency_ms=latency_ms,
            budget_ms=budget_ms,
            exceeded=exceeded,
            ts=time.time()
        )
        
        self.measurements.append(measurement)
        
        # Log if exceeded
        if exceeded:
            self._log_exceeded(measurement)
        
        return measurement
    
    def _log_exceeded(self, measurement: LatencyMeasurement):
        """Log when budget is exceeded"""
        exceeded_by = measurement.latency_ms - measurement.budget_ms
        
        event = OrderLatencyEvent(
            event="order_degraded",
            signal_ref=measurement.signal_ref,
            symbol=measurement.symbol,
            stage=measurement.stage,
            latency_ms=measurement.latency_ms,
            budget_ms=measurement.budget_ms,
            exceeded_by_ms=exceeded_by,
            ts=measurement.ts
        )
        
        # Log to file
        try:
            with open(self.events_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(asdict(event), ensure_ascii=False) + '\n')
        except Exception as e:
            self.logger.error(f"Failed to log latency event: {e}")
        
        # Log warning
        self.logger.warning(
            f"⚠️ Latency EXCEEDED: {measurement.symbol} {measurement.stage} "
            f"{measurement.latency_ms:.1f}ms (budget: {measurement.budget_ms:.1f}ms, "
            f"exceeded by: {exceeded_by:.1f}ms)"
        )
    
    def get_summary(self, last_n: int = 100) -> dict:
        """Get latency summary for last N measurements"""
        if not self.measurements:
            return {
                "total_measurements": 0,
                "exceeded_count": 0,
                "stages": {}
            }
        
        # Get last N measurements
        recent = self.measurements[-last_n:] if len(self.measurements) > last_n else self.measurements
        
        exceeded_count = sum(1 for m in recent if m.exceeded)
        
        # Group by stage
        stages = {}
        for m in recent:
            if m.stage not in stages:
                stages[m.stage] = {
                    "count": 0,
                    "total_latency_ms": 0.0,
                    "max_latency_ms": 0.0,
                    "exceeded_count": 0
                }
            
            stages[m.stage]["count"] += 1
            stages[m.stage]["total_latency_ms"] += m.latency_ms
            stages[m.stage]["max_latency_ms"] = max(
                stages[m.stage]["max_latency_ms"], m.latency_ms
            )
            if m.exceeded:
                stages[m.stage]["exceeded_count"] += 1
        
        # Calculate averages
        for stage_data in stages.values():
            if stage_data["count"] > 0:
                stage_data["avg_latency_ms"] = stage_data["total_latency_ms"] / stage_data["count"]
        
        return {
            "total_measurements": len(recent),
            "exceeded_count": exceeded_count,
            "exceeded_rate": exceeded_count / len(recent) if recent else 0.0,
            "stages": stages,
            "budget": asdict(self.budget)
        }
    
    def save_summary(self):
        """Save summary to file"""
        try:
            from shared.io.jsonio import write_json_atomic_nobom
            summary = self.get_summary()
            write_json_atomic_nobom(self.summary_path, summary)
        except Exception as e:
            self.logger.error(f"Failed to save summary: {e}")


# Global instance
_latency_monitor = OrderLatencyMonitor()


def start_timer() -> float:
    """Start a latency timer"""
    return _latency_monitor.start_timer()


def measure_stage(
    start_time: float, 
    stage: LatencyStage, 
    signal_ref: str = "",
    symbol: str = ""
) -> LatencyMeasurement:
    """Measure a latency stage"""
    return _latency_monitor.measure_stage(start_time, stage, signal_ref, symbol)


def get_latency_summary(last_n: int = 100) -> dict:
    """Get latency summary"""
    return _latency_monitor.get_summary(last_n)


def save_latency_summary():
    """Save latency summary"""
    _latency_monitor.save_summary()

