#!/usr/bin/env python3
"""
상태 배지 렌더링 규칙
Read-only 배지, 색상 규칙, 상태 표시 담당
"""

import time
from typing import Optional

import streamlit as st


class StatusBadgeRenderer:
    """상태 배지 렌더러"""

    def __init__(self):
        self.color_map = {"green": "🟢", "yellow": "🟡", "red": "🔴", "gray": "⚪"}

    def render_env_chip(self, company: str = "COMPANY", mode: str = "READ-ONLY"):
        """환경 칩 렌더링 - 한 줄로 정리"""
        current_time = time.strftime("%H:%M:%S")
        env_text = f"ENV: {company} · {mode} · {current_time}"
        st.markdown(f"**{env_text}**", help="환경 정보")

    def render_watchlist_chip(
        self, symbol: str, age_sec: float, reconnect_count: int = 0
    ):
        """워치리스트 칩 렌더링 - age_sec 색상 규칙 적용"""
        age_color = self._get_age_color(age_sec)
        color_emoji = self.color_map.get(age_color, "⚪")

        reconnect_badge = f" 🔄{reconnect_count}" if reconnect_count > 0 else ""

        return f"{color_emoji} {symbol}{reconnect_badge}"

    def render_signal_execution_badge(
        self, signal: str, execution_status: str, blocked_reason: Optional[str] = None
    ):
        """신호 vs 실행 배지 렌더링"""
        signal_color = self._get_signal_color(signal)
        execution_color = self._get_execution_color(execution_status, blocked_reason)

        signal_emoji = self.color_map.get(signal_color, "⚪")
        execution_emoji = self.color_map.get(execution_color, "⚪")

        signal_text = f"{signal_emoji} Signal: {signal}"
        execution_text = f"{execution_emoji} Execution: {execution_status}"

        if execution_status == "Blocked" and blocked_reason:
            execution_text += f" ({blocked_reason})"

        return signal_text, execution_text

    def render_regime_badge(self, regime: str, confidence: float):
        """레짐 배지 렌더링"""
        regime_colors = {"trend": "green", "range": "yellow", "vol": "red"}

        regime_color = regime_colors.get(regime, "gray")
        color_emoji = self.color_map.get(regime_color, "⚪")

        return f"{color_emoji} {regime.title()} ({confidence:.0%})"

    def render_health_badge(
        self, is_connected: bool, age_sec: float, update_count: int, error_count: int
    ):
        """헬스 배지 렌더링 - 연결 상태와 age_sec 분리"""
        connection_status = "🟢 Connected" if is_connected else "🔴 Disconnected"
        age_color = self._get_age_color(age_sec)
        age_emoji = self.color_map.get(age_color, "⚪")

        health_text = f"{connection_status} | {age_emoji} {age_sec:.1f}s | 📊 {update_count} | ❌ {error_count}"

        return health_text

    def render_age_badge(self, age_sec: float):
        """age_sec 전용 배지 렌더링"""
        age_color = self._get_age_color(age_sec)
        age_emoji = self.color_map.get(age_color, "⚪")

        return f"{age_emoji} {age_sec:.1f}s"

    def render_filter_badge(
        self, min_notional: float, step_size: float, tick_size: float, normalized: bool
    ):
        """필터 배지 렌더링"""
        norm_status = "✅ Normalized" if normalized else "⚠️ Raw"

        filter_text = f"Min: {min_notional:.6f} | Step: {step_size:.6f} | Tick: {tick_size:.6f} | {norm_status}"

        return filter_text

    def render_quality_badge(
        self, avg_offset_ms: float, max_offset_ms: float, violations: int
    ):
        """품질 배지 렌더링"""
        if violations == 0 and abs(avg_offset_ms) <= 500:
            quality_color = "green"
        elif violations <= 5 and abs(max_offset_ms) <= 1000:
            quality_color = "yellow"
        else:
            quality_color = "red"

        color_emoji = self.color_map.get(quality_color, "⚪")

        quality_text = f"{color_emoji} Avg: {avg_offset_ms:.1f}ms | Max: {max_offset_ms:.1f}ms | Violations: {violations}"

        return quality_text

    def render_alert_badge(self, alert_type: str, count: int):
        """알림 배지 렌더링"""
        alert_colors = {
            "Fail-Safe": "red",
            "Daily-Stop": "red",
            "Reconnect": "yellow",
            "Reconciliation": "yellow",
        }

        alert_color = alert_colors.get(alert_type, "gray")
        color_emoji = self.color_map.get(alert_color, "⚪")

        return f"{color_emoji} {alert_type}: {count}"

    def _get_age_color(self, age_sec: float) -> str:
        """age_sec에 따른 색상 반환"""
        if age_sec <= 30:
            return "green"
        elif age_sec <= 90:
            return "yellow"
        else:
            return "red"

    def _get_signal_color(self, signal: str) -> str:
        """신호에 따른 색상 반환"""
        signal_colors = {"BUY": "green", "SELL": "red", "HOLD": "gray"}
        return signal_colors.get(signal, "gray")

    def _get_execution_color(
        self, execution_status: str, blocked_reason: Optional[str] = None
    ) -> str:
        """실행 상태에 따른 색상 반환"""
        if execution_status == "Executed":
            return "green"
        elif execution_status == "Blocked":
            return "red"
        else:
            return "gray"

    def render_status_summary(self, status: str, details: str = ""):
        """상태 요약 렌더링"""
        status_colors = {
            "PASS": "green",
            "PARTIAL": "yellow",
            "FAIL": "red",
            "N/A": "gray",
        }

        status_color = status_colors.get(status, "gray")
        color_emoji = self.color_map.get(status_color, "⚪")

        return f"{color_emoji} {status}" + (f" - {details}" if details else "")


# 전역 인스턴스
badge_renderer = StatusBadgeRenderer()
