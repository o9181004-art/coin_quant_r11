#!/usr/bin/env python3
"""
사이드바 컨트롤 컴포넌트
ARM/START/PAUSE/STOP/EMERGENCY 버튼을 사이드바에 고정 배치
"""

import json
import time
import uuid
from typing import Dict, List, Tuple

import streamlit as st

from .sidebar_styles import SidebarStyles


class SidebarControls:
    """사이드바 컨트롤 시스템"""

    def __init__(self, file_reader):
        self.file_reader = file_reader
        self.cmd_queue_path = "control/trader_cmd_queue.jsonl"
        self.cmd_ack_path = "control/trader_cmd_ack.jsonl"
        self.audit_log_path = "logs/audit/control_actions.jsonl"

        # 쿨다운 관리
        self.cooldowns = {}
        self.cooldown_duration = 30  # 30초

        # 스타일링
        self.styles = SidebarStyles()

    def get_current_state(self) -> str:
        """현재 상태 확인"""
        try:
            ack_logs = self.file_reader.read_jsonl_tail(self.cmd_ack_path, 10)

            if not ack_logs:
                return "DISARMED"

            # 최근 성공한 명령 확인
            for log in reversed(ack_logs):
                if isinstance(log, dict) and log.get("status") == "success":
                    command = log.get("command", "")
                    if command == "START":
                        return "LIVE"
                    elif command == "PAUSE":
                        return "PAUSED"
                    elif command == "STOP":
                        return "STOPPED"
                    elif command == "ARM":
                        return "ARMED"

            return "DISARMED"

        except Exception:
            return "DISARMED"

    def send_command(
        self, command: str, scope: str = "all", reason: str = "", payload: Dict = None
    ) -> bool:
        """명령 전송"""
        try:
            # 쿨다운 체크
            if self._is_cooldown_active(command):
                remaining = self._get_cooldown_remaining(command)
                st.error(f"{command} 쿨다운 중... {remaining:.1f}초 남음")
                return False

            # 명령 큐에 추가
            cmd_data = {
                "ts": int(time.time() * 1000),
                "actor": "dashboard",
                "env": "testnet",
                "command": command,
                "scope": scope,
                "payload": payload or {},
                "reason": reason,
                "nonce": str(uuid.uuid4())[:8],
            }

            # 큐 파일에 추가
            with open(self.cmd_queue_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(cmd_data, ensure_ascii=False) + "\n")

            # 감사 로그에 기록
            audit_data = {
                **cmd_data,
                "status": "pending",
                "ip": "127.0.0.1",
                "user_agent": "streamlit",
            }

            with open(self.audit_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(audit_data, ensure_ascii=False) + "\n")

            # 쿨다운 시작
            self._start_cooldown(command)

            return True

        except Exception as e:
            st.error(f"명령 전송 실패: {e}")
            return False

    def wait_for_ack(self, command: str, timeout_seconds: int = 10) -> Tuple[bool, str]:
        """ACK 대기"""
        start_time = time.time()

        while time.time() - start_time < timeout_seconds:
            try:
                ack_logs = self.file_reader.read_jsonl_tail(self.cmd_ack_path, 5)

                for log in reversed(ack_logs):
                    if isinstance(log, dict) and log.get("command") == command:
                        if log.get("status") == "success":
                            return True, log.get("message", "Success")
                        elif log.get("status") == "fail":
                            return False, log.get("message", "Failed")

                time.sleep(0.5)  # 0.5초 대기

            except Exception as e:
                return False, f"ACK 확인 오류: {e}"

        return False, "타임아웃 (10초)"

    def _is_cooldown_active(self, command: str) -> bool:
        """쿨다운 활성 여부"""
        if command not in self.cooldowns:
            return False

        elapsed = time.time() - self.cooldowns[command]
        return elapsed < self.cooldown_duration

    def _get_cooldown_remaining(self, command: str) -> float:
        """쿨다운 남은 시간"""
        if command not in self.cooldowns:
            return 0.0

        elapsed = time.time() - self.cooldowns[command]
        remaining = self.cooldown_duration - elapsed
        return max(0.0, remaining)

    def _start_cooldown(self, command: str):
        """쿨다운 시작"""
        self.cooldowns[command] = time.time()

    def render_env_mode_state_chips(self, env: str, mode: str, state: str):
        """ENV · MODE · STATE 칩 렌더링"""
        st.markdown("#### 🎛️ Run Controls")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown("**ENV**")
            st.markdown(f"`{env}`")

        with col2:
            st.markdown("**MODE**")
            st.markdown(f"`{mode}`")

        with col3:
            st.markdown("**STATE**")
            state_colors = {
                "DISARMED": "gray",
                "ARMED": "yellow",
                "LIVE": "green",
                "PAUSED": "yellow",
                "STOPPED": "red",
            }
            color = state_colors.get(state, "gray")
            st.markdown(f"`{state}`")

    def render_control_buttons(
        self, state: str, can_start: bool, failed_checks: List, env: str, mode: str
    ):
        """컨트롤 버튼 렌더링"""
        st.markdown("#### 🎮 Control Buttons")

        # 스코프 선택 드롭다운
        scope_options = ["all", "BTCUSDT", "ETHUSDT", "SOLUSDT"]
        selected_scope = st.selectbox(
            "Scope", options=scope_options, index=0, help="제어할 심볼 범위 선택"
        )

        # ARM 버튼
        if state == "DISARMED":
            arm_disabled = self._is_cooldown_active("ARM")
            arm_tooltip = (
                f"쿨다운: {self._get_cooldown_remaining('ARM'):.1f}s"
                if arm_disabled
                else "시스템 무장"
            )

            if st.button("🔓 ARM", disabled=arm_disabled, help=arm_tooltip):
                if self.send_command("ARM", scope=selected_scope, reason="System arm"):
                    with st.spinner("ARM 처리 중..."):
                        success, message = self.wait_for_ack("ARM")
                        if success:
                            st.success("ARM 완료")
                            st.rerun()
                        else:
                            st.error(f"ARM 실패: {message}")
        else:
            st.button("🔓 ARM", disabled=True, help="이미 무장됨")

        # START 버튼
        if state == "ARMED" and can_start:
            start_disabled = self._is_cooldown_active("START")
            start_tooltip = (
                f"쿨다운: {self._get_cooldown_remaining('START'):.1f}s"
                if start_disabled
                else "필수 5개 게이트 통과 시 활성화"
            )

            if st.button(
                "🚀 START", disabled=start_disabled, help=start_tooltip, type="primary"
            ):
                # 더블 컨펌
                if st.session_state.get("confirm_start", False):
                    if self.send_command(
                        "START", scope=selected_scope, reason="Start autotrade"
                    ):
                        with st.spinner("START 처리 중..."):
                            success, message = self.wait_for_ack("START")
                            if success:
                                st.success("Autotrade started")
                                st.rerun()
                            else:
                                st.error(f"START 실패: {message}")
                else:
                    st.session_state["confirm_start"] = True
                    st.warning("한 번 더 클릭하여 확인")
        else:
            disabled_reason = "5게이트 미통과" if not can_start else "ARMED 상태 필요"
            if not can_start and failed_checks:
                failed_names = [check.name for check in failed_checks]
                disabled_reason = f"실패: {', '.join(failed_names)}"

            st.button("🚀 START", disabled=True, help=disabled_reason)

        # PAUSE 버튼
        if state == "LIVE":
            pause_disabled = self._is_cooldown_active("PAUSE")
            pause_tooltip = (
                f"쿨다운: {self._get_cooldown_remaining('PAUSE'):.1f}s"
                if pause_disabled
                else "신규 주문만 차단, 보유 관리 유지"
            )

            if st.button("⏸️ PAUSE", disabled=pause_disabled, help=pause_tooltip):
                if self.send_command("PAUSE", reason="Pause new orders"):
                    with st.spinner("PAUSE 처리 중..."):
                        success, message = self.wait_for_ack("PAUSE")
                        if success:
                            st.success("PAUSE 완료")
                            st.rerun()
                        else:
                            st.error(f"PAUSE 실패: {message}")
        else:
            st.button("⏸️ PAUSE", disabled=True, help="LIVE 상태 필요")

        # STOP 버튼
        if state in ["LIVE", "PAUSED"]:
            stop_disabled = self._is_cooldown_active("STOP")
            stop_tooltip = (
                f"쿨다운: {self._get_cooldown_remaining('STOP'):.1f}s"
                if stop_disabled
                else "규정 청산 후 완전 정지"
            )

            if st.button("⏹️ STOP", disabled=stop_disabled, help=stop_tooltip):
                # 더블 컨펌
                if st.session_state.get("confirm_stop", False):
                    if self.send_command("STOP", reason="Stop autotrade"):
                        with st.spinner("STOP 처리 중..."):
                            success, message = self.wait_for_ack("STOP")
                            if success:
                                st.success("STOP 완료")
                                st.rerun()
                            else:
                                st.error(f"STOP 실패: {message}")
                else:
                    st.session_state["confirm_stop"] = True
                    st.warning("한 번 더 클릭하여 확인")
        else:
            st.button("⏹️ STOP", disabled=True, help="LIVE/PAUSED 상태 필요")

        # EMERGENCY 버튼 (Danger Zone)
        st.markdown("#### 🚨 Danger Zone")
        if state in ["LIVE", "PAUSED"]:
            emergency_disabled = self._is_cooldown_active("EMERGENCY")
            emergency_tooltip = (
                f"쿨다운: {self._get_cooldown_remaining('EMERGENCY'):.1f}s"
                if emergency_disabled
                else "즉시 신규 차단 + STOP.TXT 생성"
            )

            if st.button(
                "🚨 EMERGENCY",
                disabled=emergency_disabled,
                help=emergency_tooltip,
                type="secondary",
            ):
                # 더블 컨펌
                if st.session_state.get("confirm_emergency", False):
                    if self.send_command("EMERGENCY", reason="Emergency stop"):
                        with st.spinner("EMERGENCY 처리 중..."):
                            success, message = self.wait_for_ack("EMERGENCY")
                            if success:
                                st.error("🚨 EMERGENCY STOP 활성화")
                                st.rerun()
                            else:
                                st.error(f"EMERGENCY 실패: {message}")
                else:
                    st.session_state["confirm_emergency"] = True
                    st.error("🚨 EMERGENCY STOP - 한 번 더 클릭하여 확인")
        else:
            st.button("🚨 EMERGENCY", disabled=True, help="LIVE/PAUSED 상태 필요")

    def render_preflight_mini(self, checks: List):
        """Pre-Flight Mini (5게이트 요약)"""
        st.markdown("#### 🔍 Pre-Flight Mini")

        # 필수 5개 게이트만 확인
        required_checks = checks[:5]
        passed_count = sum(1 for check in required_checks if check.status == "PASS")

        # 게이트별 아이콘
        gate_icons = {
            "Feeder Health": "📡",
            "UDS Heartbeat": "💓",
            "Filters": "🔍",
            "Loss Limits": "🛡️",
            "Queue/ACK Wiring": "🔗",
        }

        for check in required_checks:
            icon = gate_icons.get(check.name, "⚪")
            if check.status == "PASS":
                st.markdown(f"✅ {icon} {check.name}")
            else:
                st.markdown(f"❌ {icon} {check.name}")

        # 통과 개수 표시
        if passed_count == 5:
            st.success(f"🎯 {passed_count}/5 통과")
        else:
            st.error(f"⚠️ {passed_count}/5 통과")

    def render_recent_actions(self):
        """최근 액션 3건 축약 타임라인"""
        st.markdown("#### 📋 Recent Actions")

        try:
            audit_logs = self.file_reader.read_jsonl_tail(self.audit_log_path, 3)

            if audit_logs:
                for log in reversed(audit_logs[-3:]):  # 최근 3건
                    if isinstance(log, dict):
                        timestamp = time.strftime(
                            "%H:%M:%S", time.localtime(log.get("ts", 0) / 1000)
                        )
                        actor = log.get("actor", "unknown")
                        command = log.get("command", "unknown")
                        status = log.get("status", "pending")

                        status_emoji = (
                            "✅"
                            if status == "success"
                            else "❌" if status == "fail" else "⏳"
                        )

                        st.markdown(f"{status_emoji} **{timestamp}** {command}")
            else:
                st.markdown("액션 기록이 없습니다.")

        except Exception as e:
            st.error(f"액션 로드 실패: {e}")

    def render_session_info(self):
        """세션 정보"""
        st.markdown("#### 📊 Session Info")

        # 경과시간 (간단한 구현)
        st.markdown("**경과시간**: 00:00:00")

        # 일손절 잔여치 (간단한 구현)
        st.markdown("**일손절 잔여치**: -300 USDT")

    def render_sidebar_controls(self, env: str, mode: str, checks: List):
        """전체 사이드바 컨트롤 렌더링"""
        # 스타일 적용
        self.styles.apply_sidebar_styles()

        if mode != "control":
            st.markdown("#### 🔒 Read-Only Mode")
            st.info("컨트롤 버튼은 MODE=control일 때만 활성화됩니다.")
            return

        current_state = self.get_current_state()
        can_start = all(check.status == "PASS" for check in checks[:5])
        failed_checks = [check for check in checks[:5] if check.status != "PASS"]

        # ENV · MODE · STATE 칩
        self.render_env_mode_state_chips(env, mode, current_state)

        # 컨트롤 버튼
        self.render_control_buttons(current_state, can_start, failed_checks, env, mode)

        # Pre-Flight Mini (스타일 적용)
        self.styles.render_preflight_mini_styled(checks)

        # Recent Actions (스타일 적용)
        try:
            audit_logs = self.file_reader.read_jsonl_tail(self.audit_log_path, 3)
            self.styles.render_recent_actions_styled(audit_logs)
        except Exception:
            self.styles.render_recent_actions_styled([])

        # Session Info (스타일 적용)
        self.styles.render_session_info_styled()
