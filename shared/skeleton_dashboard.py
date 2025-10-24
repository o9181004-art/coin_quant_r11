#!/usr/bin/env python3
"""
Skeleton Dashboard - Minimal UI when services are not GREEN
========================================
Renders lightweight dashboard with:
- App header
- Environment status badges
- Last heartbeat age
- Account summary (static)

No tables, charts, or symbol cards until GREEN.
Keeps initial render time under 500ms.
"""

import json
import time
from pathlib import Path
from typing import Any, Dict

import streamlit as st

from shared.green_gate import format_service_status, get_service_status_summary
from shared.ssot_paths import print_ssot_banner, get_account_snapshot_path


def render_skeleton_dashboard():
    """Render skeleton dashboard when services are not GREEN"""
    
    # Header
    st.title("📊 자동매매 대시보드 (대기 중)")
    
    # SSOT Path Banner
    with st.expander("🔍 SSOT Paths", expanded=False):
        try:
            account_snapshot_path = get_account_snapshot_path()
            st.code(f"account_snapshot_path: {account_snapshot_path}")
            
            # Show UDS/ARES paths (matching Trader logs)
            from shared.ssot_paths import get_ssot_path
            from shared.watchlist_loader import WatchlistLoader
            from shared.symbol_normalizer import normalize_symbol
            
            shared_data = get_ssot_path("shared_data")
            uds_dir = Path(shared_data) / "snapshots"
            ares_dir = Path(shared_data) / "signals"
            
            st.code(f"UDS_DIR: {uds_dir.absolute()}")
            st.code(f"ARES_DIR: {ares_dir.absolute()}")
            
            # Show example paths for first symbol
            try:
                watchlist = WatchlistLoader().load_watchlist()
                if watchlist:
                    symbol = normalize_symbol(watchlist[0])
                    uds_path = uds_dir / f"prices_{symbol}.json"
                    ares_path = ares_dir / f"{symbol}_signals.json"
                    st.code(f"SYMBOL: {symbol}")
                    st.code(f"UDS_PATH: {uds_path.absolute()}")
                    st.code(f"ARES_PATH: {ares_path.absolute()}")
            except Exception:
                st.code("SYMBOL: [watchlist loading failed]")
            
            # Show other key paths
            paths = {
                "repo_root": get_ssot_path("repo_root"),
                "shared_data": get_ssot_path("shared_data"),
                "health": get_ssot_path("health"),
                "logs": get_ssot_path("logs"),
                "ares_candidates": get_ssot_path("ares_candidates")
            }
            
            for key, path in paths.items():
                st.code(f"{key}: {path}")
                
        except Exception as e:
            st.error(f"SSOT Path 로드 실패: {e}")
    
    # Get service status
    status = get_service_status_summary()
    
    # Status badges
    col1, col2, col3 = st.columns(3)
    
    with col1:
        feeder_emoji = {
            'GREEN': '🟢',
            'YELLOW': '🟡',
            'RED': '🔴',
            'UNKNOWN': '⚪'
        }.get(status['feeder_state'], '⚪')
        
        st.metric(
            label="Feeder 상태",
            value=f"{feeder_emoji} {status['feeder_state']}",
            delta=f"{status['feeder_age']:.1f}s ago" if status['feeder_age'] < float('inf') else "N/A"
        )
    
    with col2:
        trader_emoji = {
            'GREEN': '🟢',
            'YELLOW': '🟡',
            'RED': '🔴',
            'UNKNOWN': '⚪'
        }.get(status['trader_state'], '⚪')
        
        st.metric(
            label="Trader 상태",
            value=f"{trader_emoji} {status['trader_state']}",
            delta=f"{status['trader_age']:.1f}s ago" if status['trader_age'] < float('inf') else "N/A"
        )
    
    with col3:
        health_color = '🟢' if status['health_age'] < 10.0 else '🟡' if status['health_age'] < 60.0 else '🔴'
        st.metric(
            label="Health 데이터",
            value=f"{health_color} {status['health_age']:.1f}s",
            delta="Fresh" if status['health_age'] < 10.0 else "Stale"
        )
    
    # Divider
    st.divider()
    
    # Info message
    if not status['both_green']:
        st.info(
            "⏳ **서비스 시작 대기 중**\n\n"
            "Feeder와 Trader가 모두 GREEN 상태가 되면 전체 대시보드를 표시합니다.\n\n"
            f"현재 상태: {format_service_status(status)}"
        )
    
    # Account summary (static, lightweight)
    st.subheader("💰 계좌 요약 (정적)")
    
    try:
        # Use SSOT path for account snapshot
        account_file = get_account_snapshot_path()
        if account_file.exists():
            # Use BOM-tolerant reader
            from shared.bom_tolerant_reader import read_json_bom_tolerant
            account_data = read_json_bom_tolerant(str(account_file), {})
            
            account_age = time.time() - account_data.get('timestamp', 0)
            
            col1, col2 = st.columns(2)
            
            with col1:
                total_equity = account_data.get('total_equity_usdt', 0.0)
                st.metric(label="총 자산 (USDT)", value=f"${total_equity:,.2f}")
            
            with col2:
                st.metric(label="계좌 데이터 나이", value=f"{account_age:.1f}s")
        else:
            st.warning("계좌 데이터 파일이 없습니다.")
    
    except Exception as e:
        st.error(f"계좌 데이터 로드 실패: {e}")
    
    # Environment info
    st.divider()
    st.subheader("🔧 환경 정보")
    
    import os
    env_info = {
        "TESTNET 모드": os.getenv("TESTNET", "unknown"),
        "IS_MOCK": os.getenv("IS_MOCK", "unknown"),
        "AUTO_REFRESH_DEFER_SEC": os.getenv("UI_AUTO_REFRESH_DEFER_SEC", "N/A")
    }
    
    for key, value in env_info.items():
        st.text(f"{key}: {value}")
    
    # Tooltip
    st.caption(
        "💡 **팁**: 전체 대시보드를 표시하려면 Feeder와 Trader 서비스가 모두 정상 실행 중이어야 합니다. "
        "서비스 시작 후 수 초 이내에 자동으로 전체 대시보드가 로드됩니다."
    )


if __name__ == "__main__":
    # Test skeleton dashboard
    render_skeleton_dashboard()

