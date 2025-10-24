#!/usr/bin/env python3
"""
사이드바 스타일링 컴포넌트
사이드바 컨트롤의 반응형 및 가시성 개선
"""

import streamlit as st


class SidebarStyles:
    """사이드바 스타일링"""

    def __init__(self):
        self.sidebar_css = """
        <style>
        /* 사이드바 스크롤 독립 */
        .css-1d391kg {
            overflow-y: auto !important;
            max-height: 100vh !important;
        }
        
        /* 사이드바 컨트롤 버튼 스타일링 */
        .stButton > button {
            width: 100% !important;
            margin-bottom: 0.5rem !important;
            font-weight: bold !important;
        }
        
        /* START 버튼 강조 */
        .stButton > button[data-testid="baseButton-secondary"] {
            background-color: #ff6b6b !important;
            color: white !important;
            border: 2px solid #ff5252 !important;
        }
        
        /* EMERGENCY 버튼 위험 색상 */
        .stButton > button[data-testid="baseButton-primary"] {
            background-color: #dc3545 !important;
            color: white !important;
            border: 2px solid #c82333 !important;
        }
        
        /* 쿨다운 상태 버튼 */
        .stButton > button:disabled {
            background-color: #6c757d !important;
            color: #adb5bd !important;
            cursor: not-allowed !important;
        }
        
        /* Pre-Flight Mini 스타일 */
        .preflight-mini {
            background-color: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 0.375rem;
            padding: 0.75rem;
            margin: 0.5rem 0;
        }
        
        /* Recent Actions 스타일 */
        .recent-actions {
            background-color: #fff3cd;
            border: 1px solid #ffeaa7;
            border-radius: 0.375rem;
            padding: 0.75rem;
            margin: 0.5rem 0;
            font-size: 0.875rem;
        }
        
        /* Session Info 스타일 */
        .session-info {
            background-color: #d1ecf1;
            border: 1px solid #bee5eb;
            border-radius: 0.375rem;
            padding: 0.75rem;
            margin: 0.5rem 0;
            font-size: 0.875rem;
        }
        
        /* 반응형 플로팅 EMERGENCY */
        @media (max-width: 1200px) {
            .floating-emergency {
                position: fixed !important;
                top: 20px !important;
                right: 20px !important;
                z-index: 9999 !important;
                background: #dc3545 !important;
                color: white !important;
                border: none !important;
                border-radius: 50px !important;
                padding: 15px 25px !important;
                font-size: 16px !important;
                font-weight: bold !important;
                cursor: pointer !important;
                box-shadow: 0 4px 8px rgba(0,0,0,0.3) !important;
                transition: all 0.3s ease !important;
            }
            
            .floating-emergency:hover {
                background: #c82333 !important;
                transform: scale(1.05) !important;
            }
            
            .floating-emergency:disabled {
                background: #6c757d !important;
                cursor: not-allowed !important;
                transform: none !important;
            }
        }
        
        @media (min-width: 1201px) {
            .floating-emergency {
                display: none !important;
            }
        }
        </style>
        """

    def apply_sidebar_styles(self):
        """사이드바 스타일 적용"""
        st.markdown(self.sidebar_css, unsafe_allow_html=True)

    def render_preflight_mini_styled(self, checks):
        """스타일이 적용된 Pre-Flight Mini 렌더링"""
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

        # Pre-Flight Mini 컨테이너
        with st.container():
            st.markdown('<div class="preflight-mini">', unsafe_allow_html=True)

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

            st.markdown("</div>", unsafe_allow_html=True)

    def render_recent_actions_styled(self, audit_logs):
        """스타일이 적용된 Recent Actions 렌더링"""
        st.markdown("#### 📋 Recent Actions")

        with st.container():
            st.markdown('<div class="recent-actions">', unsafe_allow_html=True)

            if audit_logs:
                for log in reversed(audit_logs[-3:]):  # 최근 3건
                    if isinstance(log, dict):
                        import time

                        timestamp = time.strftime(
                            "%H:%M:%S", time.localtime(log.get("ts", 0) / 1000)
                        )
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

            st.markdown("</div>", unsafe_allow_html=True)

    def render_session_info_styled(self):
        """스타일이 적용된 Session Info 렌더링"""
        st.markdown("#### 📊 Session Info")

        with st.container():
            st.markdown('<div class="session-info">', unsafe_allow_html=True)

            # 경과시간 (간단한 구현)
            st.markdown("**경과시간**: 00:00:00")

            # 일손절 잔여치 (간단한 구현)
            st.markdown("**일손절 잔여치**: -300 USDT")

            st.markdown("</div>", unsafe_allow_html=True)
