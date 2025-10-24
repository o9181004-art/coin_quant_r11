#!/usr/bin/env python3
"""
플로팅 EMERGENCY 버튼 컴포넌트
좁은 화면에서도 항상 접근 가능한 EMERGENCY 버튼
"""

import streamlit as st


class FloatingEmergency:
    """플로팅 EMERGENCY 버튼"""

    def __init__(self):
        self.button_style = """
        <style>
        .floating-emergency {
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 9999;
            background: #ff4444;
            color: white;
            border: none;
            border-radius: 50px;
            padding: 15px 25px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
            box-shadow: 0 4px 8px rgba(0,0,0,0.3);
            transition: all 0.3s ease;
        }
        
        .floating-emergency:hover {
            background: #cc0000;
            transform: scale(1.05);
        }
        
        .floating-emergency:disabled {
            background: #666;
            cursor: not-allowed;
            transform: none;
        }
        
        @media (max-width: 1200px) {
            .floating-emergency {
                display: block;
            }
        }
        
        @media (min-width: 1201px) {
            .floating-emergency {
                display: none;
            }
        }
        </style>
        """

    def render_floating_emergency(
        self, state: str, is_cooldown_active: bool, cooldown_remaining: float
    ):
        """플로팅 EMERGENCY 버튼 렌더링"""
        # CSS 스타일 적용
        st.markdown(self.button_style, unsafe_allow_html=True)

        # EMERGENCY 버튼 상태 확인
        can_emergency = state in ["LIVE", "PAUSED"] and not is_cooldown_active

        if can_emergency:
            button_html = """
            <button class="floating-emergency" onclick="confirmEmergency()">
                🚨 EMERGENCY
            </button>
            
            <script>
            function confirmEmergency() {
                if (confirm('🚨 EMERGENCY STOP을 실행하시겠습니까?\\n\\n이 작업은 즉시 모든 신규 주문을 차단하고 STOP.TXT를 생성합니다.')) {
                    // Streamlit 세션 상태 업데이트
                    parent.postMessage({
                        type: 'streamlit:setComponentValue',
                        key: 'emergency_triggered',
                        value: true
                    }, '*');
                }
            }
            </script>
            """

            st.markdown(button_html, unsafe_allow_html=True)

            # JavaScript 트리거 처리
            if st.session_state.get("emergency_triggered", False):
                st.session_state["emergency_triggered"] = False
                st.session_state["confirm_emergency"] = True
                st.error("🚨 EMERGENCY STOP - 사이드바에서 한 번 더 클릭하여 확인")
        else:
            disabled_reason = (
                "쿨다운 중" if is_cooldown_active else "LIVE/PAUSED 상태 필요"
            )
            button_html = f"""
            <button class="floating-emergency" disabled title="{disabled_reason}">
                🚨 EMERGENCY
            </button>
            """

            st.markdown(button_html, unsafe_allow_html=True)
