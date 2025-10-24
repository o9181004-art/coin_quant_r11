"""
알림 시스템 UI 모듈
"""

import time

import streamlit as st

# 알림 시스템을 위한 import
try:
    import winsound
    WINSOUND_AVAILABLE = True
except ImportError:
    WINSOUND_AVAILABLE = False

try:
    from plyer import notification
    PLYER_AVAILABLE = True
except ImportError:
    PLYER_AVAILABLE = False

def play_sound_alert(sound_type="buy"):
    """사운드 알림 재생"""
    if not WINSOUND_AVAILABLE:
        return
    
    try:
        if sound_type == "buy":
            winsound.Beep(800, 200)  # 매수 사운드
        elif sound_type == "sell":
            winsound.Beep(600, 200)  # 매도 사운드
        elif sound_type == "alert":
            winsound.Beep(1000, 300)  # 경고 사운드
    except Exception as e:
        print(f"사운드 재생 실패: {e}")

def show_desktop_notification(title, message, sound_type="info"):
    """데스크톱 알림 표시"""
    if not PLYER_AVAILABLE:
        return
    
    try:
        notification.notify(
            title=title,
            message=message,
            timeout=5
        )
        
        # 사운드 재생
        if sound_type != "info":
            play_sound_alert(sound_type)
            
    except Exception as e:
        print(f"데스크톱 알림 실패: {e}")

def show_trade_notification(symbol, side, amount, price, confidence=None):
    """거래 알림 표시"""
    side_emoji = "🟢" if side == "buy" else "🔴"
    side_text = "매수" if side == "buy" else "매도"
    
    title = f"{side_emoji} {side_text} 신호"
    message = f"{symbol} {side_text}\n수량: {amount:.6f}\n가격: ${price:,.4f}"
    
    if confidence:
        message += f"\n신뢰도: {confidence}%"
    
    show_desktop_notification(title, message, side)

def add_notification(message, notification_type="info"):
    """알림 메시지 추가"""
    if "notifications" not in st.session_state:
        st.session_state.notifications = []
    
    notification_data = {
        "message": message,
        "type": notification_type,
        "timestamp": time.time()
    }
    
    st.session_state.notifications.append(notification_data)
    
    # 최대 10개까지만 유지
    if len(st.session_state.notifications) > 10:
        st.session_state.notifications = st.session_state.notifications[-10:]

def setup_notifications():
    """알림 시스템 초기 설정"""
    # 기본 알림 설정값 초기화
    if "sound_notifications" not in st.session_state:
        st.session_state.sound_notifications = True
    
    if "desktop_notifications" not in st.session_state:
        st.session_state.desktop_notifications = True
    
    if "browser_notifications" not in st.session_state:
        st.session_state.browser_notifications = True
    
    if "min_confidence" not in st.session_state:
        st.session_state.min_confidence = 75
    
    if "notification_interval" not in st.session_state:
        st.session_state.notification_interval = 5
