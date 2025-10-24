#!/usr/bin/env python3
"""
헬스 대시보드 UI 모듈
컴포넌트별 헬스 상태를 실시간으로 표시
"""

import json
import time
from pathlib import Path

import streamlit as st


def load_health_data():
    """헬스 데이터 로드"""
    try:
        health_file = Path("shared_data/health.json")
        if health_file.exists():
            with open(health_file, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        st.error(f"헬스 데이터 로드 실패: {e}")
    
    return {"timestamp": 0, "components": {}}

def get_status_color(state):
    """상태별 색상 반환"""
    colors = {
        "GREEN": "#4CAF50",   # 녹색
        "YELLOW": "#FF9800",  # 주황색
        "RED": "#F44336"      # 빨간색
    }
    return colors.get(state, "#9E9E9E")  # 기본 회색

def get_status_icon(state):
    """상태별 아이콘 반환"""
    icons = {
        "GREEN": "🟢",
        "YELLOW": "🟡", 
        "RED": "🔴"
    }
    return icons.get(state, "⚪")

def format_age(age_seconds):
    """나이를 읽기 쉬운 형태로 포맷"""
    if age_seconds == float('inf'):
        return "∞"
    elif age_seconds < 60:
        return f"{age_seconds:.1f}s"
    elif age_seconds < 3600:
        return f"{age_seconds/60:.1f}m"
    else:
        return f"{age_seconds/3600:.1f}h"

def render_health_dashboard():
    """헬스 대시보드 렌더링"""
    st.markdown("### 🏥 시스템 헬스 상태")
    
    # 헬스 데이터 로드
    health_data = load_health_data()
    components = health_data.get("components", {})
    
    # 전체 상태 요약
    total_components = len(components)
    green_count = sum(1 for comp in components.values() if comp.get("state") == "GREEN")
    yellow_count = sum(1 for comp in components.values() if comp.get("state") == "YELLOW")
    red_count = sum(1 for comp in components.values() if comp.get("state") == "RED")
    
    # 전체 상태 결정
    if red_count > 0:
        overall_state = "RED"
        overall_color = "#F44336"
    elif yellow_count > 0:
        overall_state = "YELLOW"
        overall_color = "#FF9800"
    else:
        overall_state = "GREEN"
        overall_color = "#4CAF50"
    
    # 전체 상태 표시
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "전체 상태",
            f"{get_status_icon(overall_state)} {overall_state}",
            delta=None
        )
    
    with col2:
        st.metric("정상", f"{green_count}/{total_components}", delta=None)
    
    with col3:
        st.metric("경고", f"{yellow_count}/{total_components}", delta=None)
    
    with col4:
        st.metric("오류", f"{red_count}/{total_components}", delta=None)
    
    st.markdown("---")
    
    # 컴포넌트별 상세 상태
    if not components:
        st.info("헬스 데이터가 없습니다. 서비스가 시작되지 않았거나 아직 상태를 보고하지 않았습니다.")
        return
    
    # 컴포넌트 순서 정의
    component_order = ["feeder", "uds", "trader", "autoheal"]
    
    for comp_name in component_order:
        if comp_name not in components:
            continue
            
        comp_data = components[comp_name]
        state = comp_data.get("state", "UNKNOWN")
        metrics = comp_data.get("metrics", {})
        last_updated = comp_data.get("last_updated", 0)
        
        # 컴포넌트별 상세 정보
        with st.expander(f"{get_status_icon(state)} {comp_name.upper()} - {state}", expanded=False):
            
            # 기본 정보
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown(f"**상태:** <span style='color: {get_status_color(state)}'>{state}</span>", unsafe_allow_html=True)
                st.markdown(f"**마지막 업데이트:** {format_age(time.time() - last_updated)} 전")
            
            with col2:
                st.markdown(f"**상태 텍스트:** {comp_data.get('status_text', 'N/A')}")
            
            # 컴포넌트별 메트릭 표시
            if comp_name == "feeder":
                col1, col2, col3 = st.columns(3)
                with col1:
                    ws_age = metrics.get("ws_age", 0)
                    st.metric("WebSocket 나이", format_age(ws_age))
                with col2:
                    symbols_count = metrics.get("symbols_count", 0)
                    st.metric("모니터링 심볼", f"{symbols_count}개")
                with col3:
                    rest_state = metrics.get("rest_state", "UNKNOWN")
                    st.metric("REST 상태", rest_state)
            
            elif comp_name == "uds":
                col1, col2, col3 = st.columns(3)
                with col1:
                    heartbeat_age = metrics.get("heartbeat_age", 0)
                    st.metric("하트비트 나이", format_age(heartbeat_age))
                with col2:
                    listenkey_age = metrics.get("listenKey_age", 0)
                    st.metric("ListenKey 나이", format_age(listenkey_age))
                with col3:
                    uds_state = metrics.get("state", "UNKNOWN")
                    st.metric("연결 상태", uds_state)
            
            elif comp_name == "trader":
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    trader_state = metrics.get("state", "UNKNOWN")
                    st.metric("Trader 상태", trader_state)
                with col2:
                    filters_state = metrics.get("filters_state", "UNKNOWN")
                    st.metric("필터 상태", filters_state)
                with col3:
                    uds_age = metrics.get("uds_age", 0)
                    st.metric("UDS 나이", format_age(uds_age))
                with col4:
                    account_age = metrics.get("account_snapshot_age", 0)
                    st.metric("계좌 나이", format_age(account_age))
                
                # 주문 통계
                col1, col2 = st.columns(2)
                with col1:
                    orders_count = metrics.get("orders_count", 0)
                    st.metric("주문 시도", f"{orders_count}회")
                with col2:
                    fills_count = metrics.get("fills_count", 0)
                    st.metric("체결 횟수", f"{fills_count}회")
            
            elif comp_name == "autoheal":
                col1, col2, col3 = st.columns(3)
                with col1:
                    last_action = metrics.get("last_action", 0)
                    st.metric("마지막 액션", format_age(time.time() - last_action))
                with col2:
                    restart_count = metrics.get("restart_count", 0)
                    st.metric("재시작 횟수", f"{restart_count}회")
                with col3:
                    watchdog_active = metrics.get("watchdog_active", False)
                    st.metric("워치독 활성", "✅" if watchdog_active else "❌")
    
    # 새로고침 버튼 제거됨 (중복 제거)
    
    # 마지막 업데이트 시간
    last_update = health_data.get("timestamp", 0)
    if last_update > 0:
        st.caption(f"마지막 업데이트: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(last_update))}")

def render_health_badges():
    """컴팩트한 헬스 배지 렌더링 (헤더용)"""
    health_data = load_health_data()
    components = health_data.get("components", {})
    
    # 컴포넌트 순서
    component_order = ["feeder", "uds", "trader", "autoheal"]
    component_names = {
        "feeder": "Feeder",
        "uds": "UDS", 
        "trader": "Trader",
        "autoheal": "AutoHeal"
    }
    
    badges = []
    for comp_name in component_order:
        if comp_name in components:
            comp_data = components[comp_name]
            state = comp_data.get("state", "UNKNOWN")
            metrics = comp_data.get("metrics", {})
            
            # 컴포넌트별 요약 정보
            if comp_name == "feeder":
                ws_age = metrics.get("ws_age", 0)
                summary = f"{format_age(ws_age)}"
            elif comp_name == "uds":
                heartbeat_age = metrics.get("heartbeat_age", 0)
                summary = f"{format_age(heartbeat_age)}"
            elif comp_name == "trader":
                trader_state = metrics.get("state", "UNKNOWN")
                summary = trader_state
            elif comp_name == "autoheal":
                last_action = metrics.get("last_action", 0)
                summary = f"{format_age(time.time() - last_action)}"
            else:
                summary = ""
            
            # 배지 생성
            color = get_status_color(state)
            icon = get_status_icon(state)
            badge = f'<span style="color: {color}; font-weight: bold;">{icon} {component_names[comp_name]}: {summary}</span>'
            badges.append(badge)
    
    if badges:
        st.markdown(" | ".join(badges), unsafe_allow_html=True)
    else:
        st.markdown('<span style="color: #9E9E9E;">헬스 데이터 없음</span>', unsafe_allow_html=True)
