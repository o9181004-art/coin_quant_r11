#!/usr/bin/env python3
"""
자동매매 컨트롤 패널 컴포넌트
ARM → START → PAUSE/STOP/EMERGENCY 버튼 및 상태 관리
"""

import json
import time
import uuid
from typing import Dict, List, Tuple

import streamlit as st


class AutotradeControl:
    """자동매매 컨트롤 시스템"""

    def __init__(self, file_reader):
        self.file_reader = file_reader
        self.cmd_queue_path = "control/trader_cmd_queue.jsonl"
        self.cmd_ack_path = "control/trader_cmd_ack.jsonl"
        self.audit_log_path = "logs/audit/control_actions.jsonl"

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
            # 명령 큐에 추가
            cmd_data = {
                "ts": int(time.time() * 1000),
                "actor": "dashboard",
                "env": "testnet",  # 환경에 따라 동적 설정
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

    def render_state_chip(self, state: str):
        """상태 칩 렌더링"""
        state_colors = {
            "DISARMED": "gray",
            "ARMED": "yellow",
            "LIVE": "green",
            "PAUSED": "yellow",
            "STOPPED": "red",
        }

        color = state_colors.get(state, "gray")
        emoji_map = {
            "DISARMED": "⚪",
            "ARMED": "🟡",
            "LIVE": "🟢",
            "PAUSED": "🟡",
            "STOPPED": "🔴",
        }

        emoji = emoji_map.get(state, "⚪")
        st.markdown(f"**{emoji} State: {state}**")

    def render_control_buttons(
        self, state: str, can_start: bool, env: str, mode: str, failed_checks: List
    ):
        """컨트롤 버튼 렌더링 - ENV/MODE 기반"""
        col1, col2, col3, col4, col5 = st.columns(5)

        with col1:
            if state == "DISARMED":
                if st.button("ARM", help="시스템 무장", key="arm_main"):
                    if self.send_command("ARM", reason="System arm"):
                        with st.spinner("ARM 처리 중..."):
                            success, message = self.wait_for_ack("ARM")
                            if success:
                                st.success("ARM 완료")
                                st.rerun()
                            else:
                                st.error(f"ARM 실패: {message}")
            else:
                st.button("ARM", disabled=True, key="arm_disabled")

        with col2:
            if state == "ARMED" and can_start:
                if st.button(
                    "START", help="필수 5개 게이트 통과 시 활성화", key="start_main"
                ):
                    # 더블 컨펌 모달 - START (ENV와 무관)
                    if st.session_state.get("confirm_start", False):
                        if self.send_command("START", reason="Start autotrade"):
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
                st.button("START", disabled=True, key="start_disabled")
                # 실패 사유 표시
                if not can_start and failed_checks:
                    failed_names = [check.name for check in failed_checks]
                    st.caption(f"❌ {', '.join(failed_names)}")

        with col3:
            if state == "LIVE":
                if st.button(
                    "PAUSE", help="신규 주문만 차단, 보유 관리 유지", key="pause_main"
                ):
                    if self.send_command("PAUSE", reason="Pause new orders"):
                        with st.spinner("PAUSE 처리 중..."):
                            success, message = self.wait_for_ack("PAUSE")
                            if success:
                                st.success("PAUSE 완료")
                                st.rerun()
                            else:
                                st.error(f"PAUSE 실패: {message}")
            else:
                st.button("PAUSE", disabled=True, key="pause_disabled")

        with col4:
            if state in ["LIVE", "PAUSED"]:
                if st.button("STOP", help="규정 청산 후 완전 정지", key="stop_main"):
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
                st.button("STOP", disabled=True, key="stop_disabled")

        with col5:
            if state in ["LIVE", "PAUSED"]:
                if st.button(
                    "🚨 EMERGENCY",
                    help="즉시 신규 차단 + STOP.TXT 생성",
                    key="emergency_main",
                ):
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
                st.button("🚨 EMERGENCY", disabled=True, key="emergency_disabled")

    def render_preflight_checks(self, checks: List):
        """Pre-Flight 체크 표시 - 필수 5개 + 경고 2개"""
        st.markdown("#### 🔍 Pre-Flight Checks")

        # 필수 5개 게이트
        st.markdown("**필수 5개 게이트 (통과 시에만 START 활성):**")
        required_checks = checks[:5]

        for check in required_checks:
            if check.status == "PASS":
                st.markdown(f"✅ **{check.name}**: {check.message}")
            elif check.status == "FAIL":
                st.markdown(f"❌ **{check.name}**: {check.message}")
            else:  # WARN
                st.markdown(f"⚠️ **{check.name}**: {check.message}")

        # 경고 체크
        if len(checks) > 5:
            st.markdown("**경고 체크 (N/A 가능):**")
            warning_checks = checks[5:]

            for check in warning_checks:
                if check.status == "PASS":
                    st.markdown(f"✅ **{check.name}**: {check.message}")
                elif check.status == "FAIL":
                    st.markdown(f"❌ **{check.name}**: {check.message}")
                else:  # WARN
                    st.markdown(f"⚠️ **{check.name}**: {check.message}")

    def render_control_actions_timeline(self):
        """최근 컨트롤 액션 타임라인"""
        st.markdown("#### 📋 Recent Control Actions")

        try:
            audit_logs = self.file_reader.read_jsonl_tail(self.audit_log_path, 10)

            if audit_logs:
                for log in reversed(audit_logs[-10:]):  # 최근 10건
                    if isinstance(log, dict):
                        timestamp = time.strftime(
                            "%H:%M:%S", time.localtime(log.get("ts", 0) / 1000)
                        )
                        actor = log.get("actor", "unknown")
                        command = log.get("command", "unknown")
                        status = log.get("status", "pending")
                        reason = log.get("reason", "")

                        status_emoji = (
                            "✅"
                            if status == "success"
                            else "❌" if status == "fail" else "⏳"
                        )

                        st.markdown(
                            f"{status_emoji} **{timestamp}** {actor} → {command} ({status})"
                        )
                        if reason:
                            st.markdown(f"   💭 {reason}")
            else:
                st.markdown("컨트롤 액션 기록이 없습니다.")

        except Exception as e:
            st.error(f"액션 타임라인 로드 실패: {e}")

    def render_control_panel(self, env: str, mode: str, checks: List):
        """컨트롤 패널 렌더링 - 상태 표시 전용 (버튼은 사이드바로 이관)"""
        st.markdown("#### 📊 Autotrade Status")

        # 현재 상태
        current_state = self.get_current_state()
        self.render_state_chip(current_state)

        # Pre-Flight 체크 상세
        self.render_preflight_checks(checks)

        # 안내 문구
        st.info("🎮 **컨트롤 버튼은 좌측 사이드바의 'Run Controls'에서 조작하세요**")

        # 최근 액션 타임라인 (상세)
        self.render_control_actions_timeline()
