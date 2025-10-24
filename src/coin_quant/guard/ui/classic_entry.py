#!/usr/bin/env python3
"""
Classic UI Entry Point for Coin Quant R11 Dashboard

Restores the original dashboard content/flow exactly as before,
while using the new robust pathing and DAL under the hood.
"""

import logging
import os
import time
from typing import Dict, Any, List, Optional

import streamlit as st

from coin_quant.shared.data_compat import (
    get_price, get_signal, get_position, get_ages,
    get_health, get_exposure, get_account_info, get_trading_state,
    get_symbols, format_age, format_price, format_percentage
)


def setup_logging():
    """Setup logging for Streamlit"""
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )


def render_environment_guardrails():
    """Render environment guardrails section"""
    st.markdown("""
    ### 🔒 Environment Guardrails - 검증 시작
    ============================================================
    """)
    
    # Python interpreter validation
    import sys
    current_python = sys.executable
    expected_python = os.path.join(os.getcwd(), "venv", "Scripts", "python.exe")
    
    st.markdown("🐍 Python 인터프리터 검증:")
    st.markdown(f"   현재: {current_python}")
    st.markdown(f"   기대: {expected_python}")
    
    if current_python != expected_python:
        st.error("""
        ❌ 잘못된 Python 인터프리터!
        해결방법: 프로젝트 venv를 활성화하세요
        Windows: venv\\Scripts\\activate.bat
        """)
    else:
        st.success("✅ Python 인터프리터 검증 통과")


def render_profit_status():
    """Render profit status section"""
    account_info = get_account_info()
    
    today_profit = account_info.get("today_profit", 0.0)
    total_profit = account_info.get("total_profit", 0.0)
    today_return = account_info.get("today_return", 0.0)
    total_return = account_info.get("total_return", 0.0)
    current_capital = account_info.get("current_capital", 100000.0)
    initial_capital = account_info.get("initial_capital", 100000.0)
    
    st.markdown("### 📊 수익률 현황")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("오늘 수익", f"{today_profit:.2f} USDT")
        st.metric("누적 수익", f"{total_profit:.2f} USDT")
    
    with col2:
        st.metric("오늘 수익률", f"{today_return:.2f}%")
        st.metric("누적 수익률", f"{total_return:.2f}%")
    
    with col3:
        st.metric("현재 자본", f"{current_capital:.2f} USDT")
        st.metric("초기 자본", f"{initial_capital:.2f} USDT")


def render_symbol_card(symbol: str):
    """Render a single symbol card"""
    st.markdown(f"### {symbol}")
    
    # Get data
    price_data = get_price(symbol)
    signal_data = get_signal(symbol)
    position_data = get_position(symbol)
    ages = get_ages(symbol)
    
    # Display price information
    if price_data:
        last_price = price_data.get("last", price_data.get("price"))
        price_change = price_data.get("change", 0.0)
        price_change_pct = price_data.get("change_percent", 0.0)
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("현재가", format_price(last_price))
            st.metric("변동률", f"{price_change_pct:.2f}%")
        
        with col2:
            if signal_data:
                entry_price = signal_data.get("entry", signal_data.get("target_price"))
                target_price = signal_data.get("target", signal_data.get("take_profit"))
                st.metric("진입가", format_price(entry_price))
                st.metric("목표가", format_price(target_price))
            else:
                st.metric("진입가", "N/A")
                st.metric("목표가", "N/A")
        
        with col3:
            if position_data:
                unrealized_pnl = position_data.get("unrealized_pnl", 0.0)
                unrealized_pnl_pct = position_data.get("unrealized_pnl_percent", 0.0)
                st.metric("미실현 손익", f"{unrealized_pnl:.2f} USDT")
                st.metric("미실현 수익률", f"{unrealized_pnl_pct:.2f}%")
            else:
                st.metric("미실현 손익", "N/A")
                st.metric("미실현 수익률", "N/A")
    else:
        st.warning(f"⚠️ {symbol} 가격 데이터를 찾을 수 없습니다")
    
    # Display age information
    col1, col2 = st.columns(2)
    
    with col1:
        price_age = ages.get("price_age")
        st.metric("가격 데이터 나이", format_age(price_age))
    
    with col2:
        signal_age = ages.get("ares_age")
        st.metric("ARES 신호 나이", format_age(signal_age))
    
    # Display status
    if signal_data:
        status = signal_data.get("status", "UNKNOWN")
        if status == "ACTIVE":
            st.success(f"✅ 상태: {status}")
        elif status == "ERROR":
            st.error(f"❌ 상태: {status}")
        else:
            st.info(f"ℹ️ 상태: {status}")
    else:
        st.warning("⚠️ 신호 데이터 없음")


def render_health_status():
    """Render health status section"""
    st.markdown("### 🏥 시스템 상태")
    
    health_data = get_health()
    
    if not health_data:
        st.warning("⚠️ 시스템 상태 데이터를 찾을 수 없습니다")
        return
    
    col1, col2, col3, col4 = st.columns(4)
    
    components = [
        ("feeder", "Feeder", col1),
        ("ares", "ARES", col2),
        ("trader", "Trader", col3),
        ("memory", "Memory", col4)
    ]
    
    for component_key, component_name, col in components:
        with col:
            if component_key in health_data:
                status = health_data[component_key].get("status", "UNKNOWN")
                last_update = health_data[component_key].get("last_update")
                
                if status == "HEALTHY":
                    st.success(f"✅ {component_name}")
                elif status == "ERROR":
                    st.error(f"❌ {component_name}")
                else:
                    st.warning(f"⚠️ {component_name}")
                
                if last_update:
                    st.caption(f"마지막 업데이트: {last_update}")
            else:
                st.warning(f"⚠️ {component_name} (데이터 없음)")


def render_gates_status():
    """Render gates status section"""
    st.markdown("### 🚪 게이트 상태")
    
    trading_state = get_trading_state()
    
    if trading_state:
        pre_trade_gate = trading_state.get("pre_trade_gate", False)
        exposure_gate = trading_state.get("exposure_gate", False)
        
        col1, col2 = st.columns(2)
        
        with col1:
            if pre_trade_gate:
                st.success("✅ Pre-trade Gate: 활성화")
            else:
                st.error("❌ Pre-trade Gate: 비활성화")
        
        with col2:
            if exposure_gate:
                st.success("✅ Exposure Gate: 활성화")
            else:
                st.error("❌ Exposure Gate: 비활성화")
    else:
        st.warning("⚠️ 게이트 상태 데이터를 찾을 수 없습니다")


def render_exposure_status():
    """Render exposure status section"""
    st.markdown("### 📊 노출 현황")
    
    exposure_data = get_exposure()
    
    if exposure_data:
        total_exposure = exposure_data.get("total_exposure", 0.0)
        max_exposure = exposure_data.get("max_exposure", 0.0)
        exposure_ratio = exposure_data.get("exposure_ratio", 0.0)
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("총 노출", f"{total_exposure:.2f} USDT")
        
        with col2:
            st.metric("최대 노출", f"{max_exposure:.2f} USDT")
        
        with col3:
            st.metric("노출 비율", f"{exposure_ratio:.2f}%")
    else:
        st.warning("⚠️ 노출 현황 데이터를 찾을 수 없습니다")


def render_main_layout():
    """Render the main layout of the classic dashboard"""
    # Page configuration
    st.set_page_config(
        page_title="Coin Quant R11 - Classic Dashboard",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Header
    st.title("📊 Coin Quant R11 - Classic Dashboard")
    
    # Auto-refresh logic
    auto_refresh_enabled = os.getenv("AUTO_REFRESH_ENABLED", "true").lower() == "true"
    auto_refresh_seconds = int(os.getenv("AUTO_REFRESH_SEC", "5"))
    
    if auto_refresh_enabled:
        st.markdown(f"⏱️ 자동 새로고침 활성화됨: {auto_refresh_seconds}초")
    
    # Environment guardrails
    render_environment_guardrails()
    
    st.markdown("---")
    
    # Profit status
    render_profit_status()
    
    st.markdown("---")
    
    # Symbol cards
    st.markdown("### 💰 심볼 현황")
    
    symbols = get_symbols()
    
    for symbol in symbols:
        render_symbol_card(symbol)
        st.markdown("---")
    
    # System status
    render_health_status()
    
    st.markdown("---")
    
    # Gates status
    render_gates_status()
    
    st.markdown("---")
    
    # Exposure status
    render_exposure_status()
    
    # Auto-refresh implementation
    if auto_refresh_enabled:
        time.sleep(auto_refresh_seconds)
        st.rerun()


def main():
    """Main entry point for classic UI"""
    setup_logging()
    render_main_layout()


if __name__ == "__main__":
    main()
