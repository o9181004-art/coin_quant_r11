#!/usr/bin/env python3
"""
One-Button Autotrade Control System
GO 토글 + EMERGENCY 버튼만으로 단순화된 자동매매 제어
"""

import json
import os
import time
import uuid
from typing import Dict, List, Optional, Tuple

import streamlit as st

# PreFlightChecker import (크래시 방지)
try:
    from guard.ui.components.preflight_checker import PreFlightChecker
    PREFlight_AVAILABLE = True
except ImportError as e:
    print(f"PreFlightChecker import 실패: {e}")
    PREFlight_AVAILABLE = False

class OneButtonControl:
    """One-Button 자동매매 컨트롤 시스템"""
    
    def __init__(self, file_reader):
        self.file_reader = file_reader
        self.cmd_queue_path = "control/trader_cmd_queue.jsonl"
        self.cmd_ack_path = "control/trader_cmd_ack.jsonl"
        self.audit_log_path = "logs/audit/control_actions.jsonl"
        
        # 디렉토리 생성
        os.makedirs("logs/audit", exist_ok=True)
        os.makedirs("logs/session", exist_ok=True)
        os.makedirs("logs/verification", exist_ok=True)
    
    def get_current_state(self) -> str:
        """현재 상태 확인: DISARMED | PAUSED | LIVE | STOPPED"""
        try:
            ack_logs = self.file_reader.read_jsonl_tail(self.cmd_ack_path, 10)
            
            if not ack_logs:
                return "DISARMED"
            
            # 최근 성공한 명령 확인
            for log in reversed(ack_logs):
                if isinstance(log, dict) and log.get('status') == 'success':
                    command = log.get('command', '')
                    if command == 'START':
                        return "LIVE"
                    elif command == 'PAUSE':
                        return "PAUSED"
                    elif command == 'STOP' or command == 'EMERGENCY':
                        return "STOPPED"
            
            return "DISARMED"
            
        except Exception:
            return "DISARMED"
    
    # check_preflight_5gates 메서드는 _check_preflight_from_checker로 대체됨
    
    # 개별 체크 메서드들은 PreFlightChecker로 대체됨
    
    def send_command(self, command: str, reason: str = "", payload: Dict = None) -> bool:
        """명령 전송"""
        try:
            nonce = str(uuid.uuid4())[:8]
            ts = int(time.time() * 1000)
            
            cmd = {
                "ts": ts,
                "actor": "one_button_ui",
                "env": "testnet",
                "command": command,
                "scope": "all",
                "payload": payload or {},
                "reason": reason,
                "nonce": nonce
            }
            
            # 큐에 추가
            with open(self.cmd_queue_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(cmd, ensure_ascii=False) + '\n')
            
            # 감사 로그 기록
            audit_entry = {
                "ts": ts,
                "command": command,
                "reason": reason,
                "nonce": nonce,
                "status": "sent"
            }
            
            os.makedirs(os.path.dirname(self.audit_log_path), exist_ok=True)
            with open(self.audit_log_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(audit_entry, ensure_ascii=False) + '\n')
            
            return True
            
        except Exception as e:
            st.error(f"명령 전송 실패: {e}")
            return False
    
    def wait_for_ack(self, command: str, timeout: int = 10) -> Tuple[bool, str]:
        """ACK 대기"""
        try:
            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    with open(self.cmd_ack_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                    
                    for line in lines:
                        try:
                            ack = json.loads(line.strip())
                            if ack.get('command') == command and ack.get('status') == 'success':
                                return True, ack.get('message', 'Success')
                            elif ack.get('command') == command and ack.get('status') == 'error':
                                return False, ack.get('message', 'Error')
                        except json.JSONDecodeError:
                            continue
                    
                    time.sleep(0.5)
                    
                except FileNotFoundError:
                    time.sleep(0.5)
                    continue
            
            return False, "Timeout"
            
        except Exception:
            return False, "Error"
    
    def _generate_preflight_snapshot(self, gates: List[Dict], passed_count: int):
        """Pre-Flight 스냅샷 생성"""
        try:
            snapshot = {
                "timestamp": int(time.time() * 1000),
                "feeder": gates[0]["status"],
                "uds": gates[1]["status"],
                "filters": gates[2]["status"],
                "loss_limits": gates[3]["status"],
                "queue_ack": gates[4]["status"],
                "passed": passed_count,
                "total": 5
            }
            
            with open("logs/verification/preflight_snapshot.json", 'w', encoding='utf-8') as f:
                json.dump(snapshot, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            print(f"Pre-flight snapshot 생성 실패: {e}")
    
    def _check_preflight_from_checker(self) -> Tuple[bool, List[str], List[Dict]]:
        """기존 PreFlightChecker와 통합된 체크"""
        if not PREFlight_AVAILABLE:
            return False, ["PreFlightChecker 사용 불가"], []
            
        try:
            
            checker = PreFlightChecker(self.file_reader)
            checks = checker.run_all_checks("testnet", "control")
            
            # 필수 5게이트만 확인
            required_checks = checks[:5]  # 처음 5개가 필수 게이트
            
            passed_count = len([c for c in required_checks if c.status == 'PASS'])
            all_passed = passed_count == 5
            
            failed_checks = []
            gates = []
            
            for check in required_checks:
                gates.append({
                    "name": check.name,
                    "status": "pass" if check.status == 'PASS' else "fail",
                    "reason": check.message
                })
                
                if check.status == 'FAIL':
                    failed_checks.append(f"{check.name}: {check.message}")
            
            return all_passed, failed_checks, gates
            
        except Exception as e:
            print(f"Pre-flight 체크 실패: {e}")
            return False, [f"체크 오류: {e}"], []
    
    def render_run_controls(self, mode: str):
        """Run Controls 섹션 렌더링"""
        try:
            st.markdown("### 🎮 Run Controls")
            
            # 현재 상태 가져오기
            current_state = self.get_current_state()
            
            # AUTO-PAUSE/STOP 트리거 검사
            auto_triggered = self._check_auto_triggers(current_state)
        
            # Pre-Flight 5게이트 검사 (기존 PreFlightChecker 사용)
            all_passed, failed_checks, gates = self._check_preflight_from_checker()
        
            # MODE 체크
            if mode == "read-only":
                st.info("📖 **READ-ONLY MODE** - 컨트롤 비활성화")
                return
        
            # AUTO 트리거 알림
            if auto_triggered:
                self._render_auto_trigger_alert(auto_triggered)
            
            # GO 토글 (Primary)
            col1, col2 = st.columns([2, 1])
        
            with col1:
                go_enabled = all_passed and current_state in ["DISARMED", "PAUSED"]
            
                if go_enabled:
                    go_state = st.toggle(
                        "🚀 GO",
                        value=(current_state == "LIVE"),
                        help="START/PAUSE 제어 - 필수 5게이트 통과 시 활성화"
                    )
                    
                    if go_state and current_state != "LIVE":
                        # GO ON - START 명령
                        if st.session_state.get('confirm_start', False):
                            if self.send_command("START", reason="GO ON - Start autotrade"):
                                with st.spinner("START 처리 중..."):
                                    success, message = self.wait_for_ack("START")
                                    if success:
                                        st.success("✅ LIVE 상태로 전환")
                                        st.rerun()
                                    else:
                                        st.error(f"START 실패: {message}")
                            else:
                                st.error("명령 전송 실패")
                        else:
                            st.session_state['confirm_start'] = True
                            st.warning("⚠️ START - 한 번 더 클릭하여 확인")
                    
                    elif not go_state and current_state == "LIVE":
                        # GO OFF - PAUSE 명령
                        if self.send_command("PAUSE", reason="GO OFF - Pause autotrade"):
                            with st.spinner("PAUSE 처리 중..."):
                                success, message = self.wait_for_ack("PAUSE")
                                if success:
                                    st.success("⏸️ PAUSE 상태로 전환")
                                    st.rerun()
                                else:
                                    st.error(f"PAUSE 실패: {message}")
                else:
                    # GO 비활성화
                    st.toggle("🚀 GO", disabled=True, help="필수 5게이트 미통과")
                    
                    if failed_checks:
                        st.caption(f"❌ {' | '.join(failed_checks[:2])}")
            
            with col2:
                # EMERGENCY 버튼 (Danger)
                if current_state in ["LIVE", "PAUSED"]:
                    if st.button("🚨 EMERGENCY", help="즉시 신규 차단 + STOP.TXT 생성", key="emergency_one_button"):
                        if st.session_state.get('confirm_emergency', False):
                            # STOP.TXT 생성
                            with open("STOP.TXT", 'w') as f:
                                f.write(f"EMERGENCY STOP - {int(time.time())}")
                            
                            if self.send_command("EMERGENCY", reason="Emergency stop"):
                                with st.spinner("EMERGENCY 처리 중..."):
                                    success, message = self.wait_for_ack("EMERGENCY")
                                    if success:
                                        st.error("🚨 EMERGENCY STOP 완료")
                                        st.rerun()
                                    else:
                                        st.error(f"EMERGENCY 실패: {message}")
                        else:
                            st.session_state['confirm_emergency'] = True
                            st.error("🚨 EMERGENCY STOP - 한 번 더 클릭하여 확인")
                else:
                    st.button("🚨 EMERGENCY", disabled=True, key="emergency_disabled")
            
            # Pre-Flight Mini
            st.markdown("#### 🔍 Pre-Flight (5게이트)")
            
            gate_cols = st.columns(5)
            for i, gate in enumerate(gates):
                with gate_cols[i]:
                    status_emoji = "✅" if gate["status"] == "pass" else "❌"
                    st.markdown(f"{status_emoji} **{gate['name']}**")
                    if gate["status"] == "fail":
                        st.caption(gate["reason"][:20])
            
            # 합격수 배지
            passed_emoji = "🟢" if all_passed else "🔴"
            st.markdown(f"{passed_emoji} **{len([g for g in gates if g['status'] == 'pass'])}/5 통과**")
            
            # Recent Actions (3개)
            st.markdown("#### 📋 Recent Actions")
            self._render_recent_actions()
            
            # Session Info
            st.markdown("#### ℹ️ Session Info")
            self._render_session_info()
            
        except Exception as e:
            st.error(f"Run Controls 렌더링 오류: {e}")
            st.caption("기본 컨트롤을 사용하세요.")
    
    def _render_recent_actions(self):
        """Recent Actions 렌더링"""
        try:
            if os.path.exists(self.audit_log_path):
                with open(self.audit_log_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                # 최근 3개 표시
                recent_lines = lines[-3:] if len(lines) >= 3 else lines
                
                for line in recent_lines:
                    try:
                        data = json.loads(line.strip())
                        command = data.get('command', '')
                        reason = data.get('reason', '')
                        timestamp = data.get('ts', 0)
                        
                        if timestamp:
                            time_str = time.strftime("%H:%M:%S", time.localtime(timestamp/1000))
                            st.caption(f"{time_str} - {command}: {reason}")
                    except json.JSONDecodeError:
                        continue
            else:
                st.caption("No recent actions")
                
        except Exception:
            st.caption("Error loading actions")
    
    def _render_session_info(self):
        """Session Info 렌더링"""
        try:
            # 경과시간 (세션 시작 시간 기준)
            current_state = self.get_current_state()
            
            if current_state == "LIVE":
                st.caption("⏱️ LIVE 상태")
            elif current_state == "PAUSED":
                st.caption("⏸️ PAUSED 상태")
            else:
                st.caption("🛑 STOPPED 상태")
            
            # 일손절 잔여치
            loss_path = "logs/hardening/daily_loss_cut.log"
            if os.path.exists(loss_path):
                with open(loss_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                if lines:
                    try:
                        data = json.loads(lines[-1].strip())
                        limit = data.get('limit', -300)
                        current = data.get('daily_pnl', 0)
                        remaining = limit - current
                        st.caption(f"💰 일손절 잔여: {remaining:.2f} USDT")
                    except json.JSONDecodeError:
                        pass
                        
        except Exception:
            pass
    
    def _check_auto_triggers(self, current_state: str) -> Optional[Dict]:
        """AUTO-PAUSE/STOP 트리거 검사"""
        try:
            triggers = []
            
            # 1. Feeder age_sec > 90s 2회 연속
            feeder_stale_count = self._check_feeder_stale_count()
            if feeder_stale_count >= 2:
                triggers.append({
                    "type": "AUTO-PAUSE",
                    "reason": f"Feeder stale {feeder_stale_count} times",
                    "action": "PAUSE"
                })
            
            # 2. ACK 지연 > 10s 3회/10분
            ack_delay_count = self._check_ack_delay_count()
            if ack_delay_count >= 3:
                triggers.append({
                    "type": "AUTO-PAUSE", 
                    "reason": f"ACK delays {ack_delay_count} times",
                    "action": "PAUSE"
                })
            
            # 3. 연속손실 3회
            consecutive_losses = self._check_consecutive_losses()
            if consecutive_losses >= 3:
                triggers.append({
                    "type": "AUTO-PAUSE",
                    "reason": f"Consecutive losses {consecutive_losses}",
                    "action": "PAUSE"
                })
            
            # 4. 운영 타이머 만료
            timer_expired = self._check_timer_expiry()
            if timer_expired:
                triggers.append({
                    "type": "AUTO-STOP",
                    "reason": "Session timer expired",
                    "action": "STOP"
                })
            
            # 5. 일손절/Fail-Safe 발동
            loss_limit_triggered = self._check_loss_limit_triggered()
            if loss_limit_triggered:
                triggers.append({
                    "type": "AUTO-STOP",
                    "reason": "Daily loss limit triggered",
                    "action": "STOP"
                })
            
            # 가장 높은 우선순위 트리거 반환
            if triggers:
                # AUTO-STOP이 AUTO-PAUSE보다 우선
                auto_stop = [t for t in triggers if t["type"] == "AUTO-STOP"]
                if auto_stop:
                    return auto_stop[0]
                else:
                    return triggers[0]
            
            return None
            
        except Exception as e:
            print(f"AUTO 트리거 검사 실패: {e}")
            return None
    
    def _check_feeder_stale_count(self) -> int:
        """Feeder stale 카운트 확인"""
        try:
            # 최근 10분간의 Feeder 상태 로그 확인
            stale_count = 0
            symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
            
            for symbol in symbols:
                snapshot_path = f"shared_data/snapshots/prices_{symbol}.json"
                if os.path.exists(snapshot_path):
                    with open(snapshot_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    last_event_ms = data.get('last_event_ms', 0)
                    if last_event_ms:
                        now_ms = int(time.time() * 1000)
                        age_sec = (now_ms - last_event_ms) / 1000
                        if age_sec > 90:
                            stale_count += 1
            
            return stale_count
            
        except Exception:
            return 0
    
    def _check_ack_delay_count(self) -> int:
        """ACK 지연 카운트 확인 (최근 10분)"""
        try:
            if not os.path.exists(self.audit_log_path):
                return 0
            
            with open(self.audit_log_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # 최근 10분간의 로그만 확인
            cutoff_time = int(time.time() * 1000) - (10 * 60 * 1000)
            delay_count = 0
            
            for line in lines:
                try:
                    data = json.loads(line.strip())
                    if data.get('ts', 0) > cutoff_time:
                        # ACK 지연 로직 (간단히 구현)
                        if 'delay' in data.get('reason', '').lower():
                            delay_count += 1
                except json.JSONDecodeError:
                    continue
            
            return delay_count
            
        except Exception:
            return 0
    
    def _check_consecutive_losses(self) -> int:
        """연속 손실 카운트 확인"""
        try:
            # 최근 거래 로그에서 손실 패턴 확인
            consecutive_losses = 0
            orders_path = "shared_data/orders"
            
            if os.path.exists(orders_path):
                # 모든 심볼의 주문 로그 확인
                for symbol_file in os.listdir(orders_path):
                    if symbol_file.endswith('.jsonl'):
                        symbol_path = os.path.join(orders_path, symbol_file)
                        with open(symbol_path, 'r', encoding='utf-8') as f:
                            lines = f.readlines()
                        
                        # 최근 거래들 확인
                        for line in reversed(lines[-10:]):
                            try:
                                data = json.loads(line.strip())
                                pnl = data.get('realized_pnl', 0)
                                if pnl < 0:
                                    consecutive_losses += 1
                                else:
                                    break  # 손실이 끊어지면 카운트 리셋
                            except json.JSONDecodeError:
                                continue
            
            return consecutive_losses
            
        except Exception:
            return 0
    
    def _check_timer_expiry(self) -> bool:
        """운영 타이머 만료 확인"""
        try:
            # 세션 시작 시간 확인 (간단히 구현)
            session_file = "logs/session/current_session.json"
            if os.path.exists(session_file):
                with open(session_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                start_time = data.get('started_at', 0)
                if start_time:
                    # 8시간 운영 제한
                    elapsed_hours = (int(time.time() * 1000) - start_time) / (1000 * 60 * 60)
                    return elapsed_hours >= 8
            
            return False
            
        except Exception:
            return False
    
    def _check_loss_limit_triggered(self) -> bool:
        """일손절/Fail-Safe 발동 확인"""
        try:
            # STOP.TXT 존재 확인
            if os.path.exists("STOP.TXT"):
                return True
            
            # 일손절 로그 확인
            loss_path = "logs/hardening/daily_loss_cut.log"
            if os.path.exists(loss_path):
                with open(loss_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                if lines:
                    data = json.loads(lines[-1].strip())
                    return data.get('triggered', False)
            
            return False
            
        except Exception:
            return False
    
    def _render_auto_trigger_alert(self, trigger: Dict):
        """AUTO 트리거 알림 렌더링"""
        trigger_type = trigger.get('type', '')
        reason = trigger.get('reason', '')
        action = trigger.get('action', '')
        
        if trigger_type == "AUTO-PAUSE":
            st.error(f"🚨 **AUTO-PAUSE** - {reason}")
            st.caption("GO가 자동으로 OFF로 전환됩니다.")
        elif trigger_type == "AUTO-STOP":
            st.error(f"🚨 **AUTO-STOP** - {reason}")
            st.caption("시스템이 자동으로 정지됩니다.")
        
        # 자동 실행
        if action == "PAUSE" and self.get_current_state() == "LIVE":
            self.send_command("PAUSE", reason=f"AUTO-PAUSE: {reason}")
            st.rerun()
        elif action == "STOP" and self.get_current_state() in ["LIVE", "PAUSED"]:
            self.send_command("STOP", reason=f"AUTO-STOP: {reason}")
            st.rerun()
