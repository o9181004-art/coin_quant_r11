"""
알림 설정 UI 모듈
"""

import streamlit as st


def render_notification_settings():
    """알림 설정 UI 렌더링"""
    st.subheader("🔔 알림 설정")
    
    # 알림 유형별 설정
    st.markdown("### 알림 유형")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.session_state.sound_notifications = st.checkbox(
            "🔊 사운드 알림",
            value=st.session_state.get("sound_notifications", True),
            key="sound_notifications"
        )
    
    with col2:
        st.session_state.desktop_notifications = st.checkbox(
            "🖥️ 데스크톱 알림",
            value=st.session_state.get("desktop_notifications", True),
            key="desktop_notifications"
        )
    
    with col3:
        st.session_state.browser_notifications = st.checkbox(
            "🌐 브라우저 알림",
            value=st.session_state.get("browser_notifications", True),
            key="browser_notifications"
        )
    
    st.markdown("---")
    
    # 알림 조건 설정
    st.markdown("### 알림 조건")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.session_state.min_confidence = st.slider(
            "최소 신뢰도 (%)",
            min_value=50,
            max_value=95,
            value=st.session_state.get("min_confidence", 75),
            step=5,
            key="min_confidence"
        )
    
    with col2:
        st.session_state.notification_interval = st.slider(
            "알림 간격 (초)",
            min_value=1,
            max_value=30,
            value=st.session_state.get("notification_interval", 5),
            step=1,
            key="notification_interval"
        )
    
    st.markdown("---")
    
    # 현재 설정 요약
    st.markdown("### 현재 설정")
    
    settings_summary = [
        f"- 🔊 사운드 알림: {'✅ 활성' if st.session_state.get('sound_notifications', True) else '❌ 비활성'}",
        f"- 🖥️ 데스크톱 알림: {'✅ 활성' if st.session_state.get('desktop_notifications', True) else '❌ 비활성'}",
        f"- 🌐 브라우저 알림: {'✅ 활성' if st.session_state.get('browser_notifications', True) else '❌ 비활성'}"
    ]
    
    for setting in settings_summary:
        st.write(setting)
    
    st.write(f"- 📊 최소 신뢰도: {st.session_state.get('min_confidence', 75)}%")
    st.write(f"- ⏰ 알림 간격: {st.session_state.get('notification_interval', 5)}초")
    
    # 테스트 알림 버튼
    st.markdown("---")
    st.markdown("### 알림 테스트")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🔊 사운드 테스트", use_container_width=True):
            from guard.ui.notifications import play_sound_alert
            play_sound_alert("alert")
            st.success("사운드 테스트 완료!")
    
    with col2:
        if st.button("🖥️ 데스크톱 테스트", use_container_width=True):
            from guard.ui.notifications import show_desktop_notification
            show_desktop_notification("테스트", "데스크톱 알림 테스트입니다.")
            st.success("데스크톱 알림 테스트 완료!")
    
    with col3:
        if st.button("📊 거래 알림 테스트", use_container_width=True):
            from guard.ui.notifications import show_trade_notification
            show_trade_notification("BTCUSDT", "buy", 0.001, 45000.0, 85)
            st.success("거래 알림 테스트 완료!")
