#!/usr/bin/env python3
"""
UI Implementation Module - Extracted from app.py
Contains the actual UI logic without entry point code
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
from plotly.subplots import make_subplots

# Import CSS loader
from guard.ui.assets.css_loader import get_style_tag

# Load environment variables
load_dotenv()

# Event-driven configuration
UI_LIVE_SIGNALS = os.getenv("UI_LIVE_SIGNALS", "true").lower() in ("true", "1", "yes")
UI_EVENT_POLL_MS = int(os.getenv("UI_EVENT_POLL_MS", "600"))  # Default 600ms
UI_RERUN_DEBOUNCE_MS = int(os.getenv("UI_RERUN_DEBOUNCE_MS", "1200"))  # Default 1.2s
UI_MAX_RERUNS_PER_MIN = int(os.getenv("UI_MAX_RERUNS_PER_MIN", "10"))  # Default 10
UI_DEBUG = os.getenv("UI_DEBUG", "false").lower() in ("true", "1", "yes")

# Import read-only UI components
try:
    from guard.ui.readonly_ui import get_readonly_ui, show_readonly_banner
    READONLY_UI_AVAILABLE = True
except ImportError:
    READONLY_UI_AVAILABLE = False
    print("Read-only UI components not available")


def inject_css():
    """Inject CSS from external file"""
    try:
        css_content = get_style_tag()
        st.markdown(css_content, unsafe_allow_html=True)
    except Exception as e:
        # Fallback to minimal CSS if loading fails
        st.markdown("""
        <style>
        /* Minimal fallback CSS */
        body { background-color: #0e1117; color: #ffffff; }
        </style>
        """, unsafe_allow_html=True)


def show_fixed_notification_area():
    """고정된 알림 영역 표시 (대시보드 밀림 방지)"""
    # 알림이 있으면 표시, 없으면 빈 영역 유지
    if "notifications" not in st.session_state or not st.session_state.notifications:
        # 알림이 없을 때는 빈 영역만 표시 (고정된 공간 유지)
        st.markdown(
            """
        <div id="fixed-notification-area" class="spacing-medium"></div>
        """,
            unsafe_allow_html=True,
        )
        return

    # 가장 최근 알림 표시
    latest_notification = st.session_state.notifications[-1]
    message = latest_notification["message"]
    notification_type = latest_notification["type"]

    # 알림 타입별 색상 설정 (매우 부드러운 투명도 적용)
    if notification_type == "success":
        bg_color = "rgba(40, 167, 69, 0.4)"  # 녹색 + 매우 부드러운 투명도
        text_color = "white"
        border_color = "rgba(30, 126, 52, 0.3)"
    elif notification_type == "error":
        bg_color = "rgba(220, 53, 69, 0.4)"  # 빨간색 + 매우 부드러운 투명도
        text_color = "white"
        border_color = "rgba(189, 33, 48, 0.3)"
    elif notification_type == "warning":
        bg_color = "rgba(220, 53, 69, 0.35)"  # 빨간색 계열 + 매우 부드러운 투명도
        text_color = "white"
        border_color = "rgba(189, 33, 48, 0.25)"
    else:
        bg_color = "rgba(23, 162, 184, 0.4)"  # 청록색 + 매우 부드러운 투명도
        text_color = "white"
        border_color = "rgba(19, 132, 150, 0.3)"

    # 고정된 알림 영역에 알림 표시
    st.markdown(
        f"""
    <div id="fixed-notification-area" style="
        min-height: 50px;
        margin-bottom: 10px;
        background-color: {bg_color};
        color: {text_color};
        padding: 12px 15px;
        border-radius: 5px;
        border: 1px solid {border_color};
        box-shadow: 0 1px 4px rgba(0,0,0,0.05);
        font-size: 14px;
        font-weight: 500;
        display: flex;
        align-items: center;
        animation: slideIn 0.3s ease-out;
        backdrop-filter: blur(12px);
    ">
        <span style="margin-right: 8px;">🔔</span>
        <span>{message}</span>
    </div>
    """,
        unsafe_allow_html=True,
    )


def add_notification(message: str, notification_type: str = "info"):
    """알림 추가"""
    if "notifications" not in st.session_state:
        st.session_state.notifications = []

    # 알림 추가
    st.session_state.notifications.append({
        "message": message,
        "type": notification_type,
        "timestamp": time.time()
    })

    # 최대 5개까지만 유지
    if len(st.session_state.notifications) > 5:
        st.session_state.notifications = st.session_state.notifications[-5:]

    # 데스크톱 알림 (설정된 경우)
    if st.session_state.get("desktop_notifications", True):
        show_desktop_notification("코인퀀트 알림", message, notification_type)


def show_desktop_notification(title: str, message: str, notification_type: str = "info"):
    """데스크톱 알림 표시"""
    # JavaScript로 데스크톱 알림 표시
    if notification_type == "success":
        icon = "✅"
    elif notification_type == "error":
        icon = "❌"
    elif notification_type == "warning":
        icon = "⚠️"
    else:
        icon = "ℹ️"

    # 브라우저 알림 API 사용
    components.html(
        f"""
        <script>
        if (Notification.permission === 'granted') {{
            new Notification('{title}', {{
                body: '{icon} {message}',
                icon: 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text y=".9em" font-size="90">📈</text></svg>'
            }});
        }} else if (Notification.permission !== 'denied') {{
            Notification.requestPermission().then(function(permission) {{
                if (permission === 'granted') {{
                    new Notification('{title}', {{
                        body: '{icon} {message}',
                        icon: 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text y=".9em" font-size="90">📈</text></svg>'
                    }});
                }}
            }});
        }}
        </script>
        """,
        height=0,
    )


def render_live_signal_diagnostics():
    """실시간 시그널 진단 렌더링"""
    try:
        from shared.event_watcher import EventWatcher
        watcher = EventWatcher()
        
        # 안전한 상태 확인
        try:
            status = watcher.get_status()
            if status is None:
                st.markdown("**Event watcher:** status is None")
            elif not isinstance(status, dict):
                st.markdown(f"**Event watcher:** unexpected status type: {type(status)}")
            else:
                # 안전한 딕셔너리 접근
                running = status.get('running', 'Unknown')
                combined_hash = status.get('combined_hash', 'Unknown')
                watched_files = status.get('watched_files', 0)
                rerun_count = status.get('rerun_count', 0)
                poll_interval = status.get('poll_interval', 0)
                
                st.markdown(f"**Running:** {running}")
                if combined_hash != 'Unknown':
                    st.markdown(f"**Combined Hash:** {combined_hash[:8]}...")
                st.markdown(f"**Watched Files:** {watched_files}")
                st.markdown(f"**Rerun Count:** {rerun_count}")
                st.markdown(f"**Poll Interval:** {poll_interval}s")
        except Exception as e:
            st.markdown(f"**Event watcher error:** {e}")
            
    except Exception as e:
        st.markdown(f"**Event watcher initialization error:** {e}")


def render_header_badges():
    """헤더 배지 렌더링"""
    try:
        # Trading mode badge using SSOT
        from shared.state_bus import get_trading_mode
        
        current_mode = get_trading_mode()
        
        # Mode badge mapping
        mode_badges = {
            "DRYRUN": ("🔒 Read-only Mode", "gray"),
            "TESTNET": ("🟡 Testnet Mode", "orange"), 
            "LIVE": ("🔴 Live Trading", "red")
        }
        
        badge_text, badge_color = mode_badges.get(current_mode, ("❓ Unknown Mode", "gray"))
        st.markdown(f"### {badge_text}")
        
        # LIVE 배지 (rerun_count 사용)
        try:
            from shared.event_watcher import EventWatcher
            watcher = EventWatcher()
            status = watcher.get_status()
            if status and isinstance(status, dict):
                rerun_count = status.get('rerun_count', 0)
                st.markdown(f"**LIVE:** {rerun_count} reruns")
        except Exception:
            st.markdown("**LIVE:** Status unavailable")
            
    except Exception as e:
        st.error(f"헤더 배지 오류: {e}")


def main_ui():
    """메인 UI 렌더링"""
    # CSS 주입
    inject_css()
    
    # 헤더 배지
    render_header_badges()
    
    # 고정된 알림 영역
    show_fixed_notification_area()
    
    # 메인 컨텐츠
    st.markdown("## 📊 실시간 자동매매 대시보드")
    
    # 라이브 시그널 진단
    with st.expander("🔍 Live Signal Diagnostics"):
        render_live_signal_diagnostics()
    
    # 기본 정보 표시
    st.markdown("### 시스템 상태")
    st.markdown("- 자동매매 시스템이 정상 작동 중입니다")
    st.markdown("- 실시간 데이터 수신 중")
    st.markdown("- 거래 엔진 활성화됨")


# Export main functions for use by app_entry.py
__all__ = [
    'inject_css',
    'show_fixed_notification_area', 
    'add_notification',
    'show_desktop_notification',
    'render_live_signal_diagnostics',
    'render_header_badges',
    'main_ui'
]
