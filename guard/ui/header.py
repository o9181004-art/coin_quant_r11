"""
헤더 UI 모듈 - 상단 헤더와 제어 버튼
"""

import json
import time
from pathlib import Path

import streamlit as st

from guard.ui.health_dashboard import render_health_badges


@st.cache_data(ttl=5, max_entries=10)
def load_watchlist_cached():
    """관심종목 목록 로드 (캐시 적용)"""
    try:
        watchlist_file = Path("shared_data/watchlist.json")
        if watchlist_file.exists():
            with open(watchlist_file, "r", encoding="utf-8") as f:
                watchlist = json.load(f)
                return watchlist.get("symbols", [])
        
        # 기본 심볼 목록
        default_symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT", "DOTUSDT", "LINKUSDT"]
        return default_symbols
        
    except Exception as e:
        print(f"관심종목 로드 실패: {e}")
        return ["BTCUSDT", "ETHUSDT"]

def get_freshness_badge(age_sec):
    """데이터 신선도 배지"""
    if age_sec < 60:
        return '<span style="color: #00ff88; font-size: 0.7rem; background: #0d2818; padding: 0.2rem 0.4rem; border-radius: 0.3rem;">FRESH</span>'
    elif age_sec < 300:
        return '<span style="color: #ffaa00; font-size: 0.7rem; background: #2d1f1f; padding: 0.2rem 0.4rem; border-radius: 0.3rem;">WARM</span>'
    else:
        return '<span style="color: #ff4444; font-size: 0.7rem; background: #2d1f1f; padding: 0.2rem 0.4rem; border-radius: 0.3rem;">STALE</span>'

def get_event_timestamps():
    """이벤트 소스의 타임스탬프 수집"""
    current_time = time.time()
    
    # Price age: state_bus.json 또는 feeder quotes 파일 mtime
    price_last_ts = current_time
    try:
        state_bus_file = Path("shared_data/state_bus.json")
        if state_bus_file.exists():
            with open(state_bus_file, "r", encoding="utf-8") as f:
                state_data = json.load(f)
                price_last_ts = state_data.get("price_last_ts", current_time)
        else:
            # fallback: databus_snapshot.json mtime
            databus_file = Path("shared_data/databus_snapshot.json")
            if databus_file.exists():
                price_last_ts = databus_file.stat().st_mtime
    except Exception:
        pass
    
    # ARES age: 최신 candidate snapshot_ts 또는 candidates.ndjson mtime
    ares_last_ts = current_time
    try:
        candidates_file = Path("shared_data/candidates.ndjson")
        if candidates_file.exists():
            ares_last_ts = candidates_file.stat().st_mtime
    except Exception:
        pass
    
    return {
        "current_time": current_time,
        "price_last_ts": price_last_ts,
        "ares_last_ts": ares_last_ts
    }

def detect_app_mode():
    """앱 모드 감지 - state_bus.json 우선, .env fallback"""
    try:
        # state_bus.json에서 app_mode 확인
        state_bus_file = Path("shared_data/state_bus.json")
        if state_bus_file.exists():
            with open(state_bus_file, "r", encoding="utf-8") as f:
                state_data = json.load(f)
                app_mode = state_data.get("app_mode")
                if app_mode in ["SIM", "TESTNET", "LIVE"]:
                    return app_mode
    except Exception:
        pass
    
    # .env fallback
    import os
    app_mode = os.getenv("APP_MODE", "TESTNET")
    return app_mode if app_mode in ["SIM", "TESTNET", "LIVE"] else "TESTNET"

def create_header_view_model():
    """헤더용 ViewModel 생성 - 원본과 동일한 로직"""
    timestamps = get_event_timestamps()
    
    # 환경 및 모드 배지 - 동적 감지
    app_mode = detect_app_mode()
    
    # 자동 유니버스 상태 확인
    import os
    auto_universe_enabled = os.getenv("FEEDER_MODE", "MANUAL").upper() == "ALL"
    
    # 워치리스트 로드
    watchlist = load_watchlist_cached()
    
    # 활성 심볼 수 계산 - 워치리스트 전체 개수 표시
    active_symbols = len(watchlist)
    
    # 이벤트 기반 ages 계산
    price_age = timestamps["current_time"] - timestamps["price_last_ts"]
    ares_age = timestamps["current_time"] - timestamps["ares_last_ts"]
    
    # 모드별 색상 결정
    mode_colors = {
        "SIM": "#888888",      # 회색
        "TESTNET": "#2196F3",  # 파란색
        "LIVE": "#4CAF50"      # 녹색
    }
    mode_color = mode_colors.get(app_mode, "#888888")
    
    # 자동매매 상태
    auto_trading_active = st.session_state.get("auto_trading_active", False)
    
    # 서비스 상태
    feeder_running = st.session_state.get("feeder_running", False)
    trader_running = st.session_state.get("trader_running", False)
    auto_healing_active = st.session_state.get("auto_healing_active", False)
    
    return {
        'mode_badge': app_mode,
        'mode_color': mode_color,
        'current_time': time.strftime("%Y-%m-%d %H:%M:%S"),
        'active_symbols': active_symbols,
        'auto_universe_enabled': auto_universe_enabled,
        'price_age': price_age,
        'price_age_display': f"{price_age:.0f}s",
        'ares_age': ares_age,
        'ares_age_display': f"{ares_age:.0f}s",
        'feeder_running': feeder_running,
        'trader_running': trader_running,
        'auto_healing_active': auto_healing_active,
        'auto_trading_active': auto_trading_active
    }

def render_header():
    """헤더 렌더링 - 이벤트 기반 실시간 업데이트"""
    vm = create_header_view_model()

    st.markdown(
        f"""
    <div style="background-color: #1e1e1e; padding: 1rem; border-radius: 0.5rem; margin-bottom: 1rem; border: 1px solid #333;">
        <div style="display: grid; grid-template-columns: 1fr 2fr 1fr; gap: 1rem; align-items: center;">
            <div style="display: flex; align-items: center; gap: 0.5rem;">
                <span style="background-color: {vm['mode_color']}; color: white; padding: 0.3rem 0.6rem; border-radius: 0.3rem; font-size: 0.8rem; font-weight: 600;">{vm['mode_badge']}</span>
                <span style="font-size: 14px; color: #888;">
                    {vm['current_time']}
                </span>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 16px; font-weight: 600; margin-bottom: 4px;">
                    Active Symbols: {vm['active_symbols']}
                    {'<span style="color: #00ff88; font-size: 0.7rem; background: #0d2818; padding: 0.2rem 0.4rem; border-radius: 0.3rem;">AUTO</span>' if vm['auto_universe_enabled'] else '<span style="color: #ffaa00; font-size: 0.7rem; background: #2d1f1f; padding: 0.2rem 0.4rem; border-radius: 0.3rem;">MANUAL</span>'}
                </div>
                <div style="font-size: 12px; color: #aaa;">
                    {get_freshness_badge(vm['price_age'])} Price age {vm['price_age_display']}
                    {get_freshness_badge(vm['ares_age'])} ARES age {vm['ares_age_display']}
                </div>
                <div style="font-size: 11px; color: #888; margin-top: 2px;">
                    Feeder: {'🟢' if vm['feeder_running'] else '🔴'} | 
                    Trader: {'🟢' if vm['trader_running'] else '🔴'} |
                    Auto-Heal: {'🟢' if vm['auto_healing_active'] else '🔴'}
                </div>
                <div style="font-size: 10px; color: #666; margin-top: 4px;">
                    <!-- 헬스 배지가 여기에 표시됩니다 -->
                </div>
            </div>
            <div style="text-align: right;">
                <div style="display: inline-block; padding: 0.5rem 1rem; border-radius: 0.3rem; background-color: {'#2d1f1f' if not vm['auto_trading_active'] else '#1f2d24'}; border: 1px solid {'#ff4444' if not vm['auto_trading_active'] else '#00ff88'};">
                    <div style="color: {'#ff4444' if not vm['auto_trading_active'] else '#00ff88'}; font-weight: 600; font-size: 0.9rem;">
                        {'자동매매 멈춤' if not vm['auto_trading_active'] else '자동매매 활성'}
                    </div>
                </div>
            </div>
        </div>
    </div>
    """,
        unsafe_allow_html=True,
    )

    # 헤더와 버튼 사이 간격 최소화
    st.markdown('<div style="margin-top: -10px;"></div>', unsafe_allow_html=True)

    # 실제 작동하는 버튼들 추가
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button(
            "🚀 Start Feeder", key="start_feeder_btn", use_container_width=True
        ):
            try:
                st.session_state.feeder_running = True
                st.success("Feeder 시작됨!")
                # st.rerun() 제거 - 상태 변경만으로 UI 업데이트
            except Exception as e:
                st.error(f"Feeder 시작 오류: {str(e)}")

    with col2:
        if st.button(
            "📈 Start Trader", key="start_trader_btn", use_container_width=True
        ):
            try:
                st.session_state.trader_running = True
                st.success("Trader 시작됨!")
                # st.rerun() 제거 - 상태 변경만으로 UI 업데이트
            except Exception as e:
                st.error(f"Trader 시작 오류: {str(e)}")

    with col3:
        if st.button(
            "📄 Open Logs", key="open_logs_btn", use_container_width=True
        ):
            st.info("로그 파일을 여는 기능은 추후 구현 예정입니다.")

    with col4:
        if st.button(
            "🛑 비상정지", key="emergency_stop_btn", use_container_width=True
        ):
            try:
                st.session_state.auto_trading_active = False
                st.session_state.feeder_running = False
                st.session_state.trader_running = False
                st.warning("비상정지 실행됨!")
                # st.rerun() 제거 - 상태 변경만으로 UI 업데이트
            except Exception as e:
                st.error(f"비상정지 오류: {str(e)}")
    
    # 헬스 배지 표시
    st.markdown("---")
    render_health_badges()
    st.markdown("---")
