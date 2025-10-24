#!/usr/bin/env python3
"""
UI Signal→Order Panel
Streamlit component for displaying signal processing and order statistics
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

from .centralized_path_registry import get_path_registry
from .signal_order_admission import DropCode, get_signal_order_admission


def render_signal_order_panel(path_registry) -> None:
    """Signal→Order 패널 렌더링"""
    st.markdown("---")
    st.subheader("📊 Signal → Order Processing")
    
    # 실시간 카운터
    render_live_counters()
    
    # 드롭 코드 히스토그램
    render_drop_code_histogram()
    
    # 최근 AdmissionResult
    render_recent_admission_results()
    
    # 제어 버튼들
    render_control_buttons()


def render_live_counters() -> None:
    """실시간 카운터 표시"""
    st.markdown("#### 📈 Live Counters")
    
    try:
        # SignalOrderAdmission 인스턴스에서 통계 조회
        repo_root = Path(__file__).parent.parent
        admission = get_signal_order_admission(repo_root)
        counters = admission.get_live_counters()
        
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric("Signals In", counters["signals_in"])
        
        with col2:
            st.metric("Orders Sent", counters["orders_sent"])
        
        with col3:
            st.metric("Orders Filled", counters["orders_filled"])
        
        with col4:
            st.metric("Drops", counters["drops"])
        
        with col5:
            st.metric("Uptime", f"{counters['uptime_seconds']}s")
        
        # 성공률 계산
        if counters["signals_in"] > 0:
            success_rate = (counters["orders_sent"] / counters["signals_in"]) * 100
            st.metric("Success Rate", f"{success_rate:.1f}%")
        
    except Exception as e:
        st.error(f"Failed to load live counters: {e}")


def render_drop_code_histogram() -> None:
    """드롭 코드 히스토그램 표시"""
    st.markdown("#### 🚫 Drop Code Histogram")
    
    try:
        repo_root = Path(__file__).parent.parent
        admission = get_signal_order_admission(repo_root)
        histogram = admission.get_drop_code_histogram()
        
        if not histogram:
            st.info("No drops recorded yet")
            return
        
        # 히스토그램을 차트로 표시
        import pandas as pd
        
        df = pd.DataFrame(list(histogram.items()), columns=['Drop Code', 'Count'])
        df = df.sort_values('Count', ascending=False)
        
        st.bar_chart(df.set_index('Drop Code'))
        
        # 상세 테이블
        with st.expander("Drop Code Details"):
            st.dataframe(df, use_container_width=True)
        
    except Exception as e:
        st.error(f"Failed to load drop code histogram: {e}")


def render_recent_admission_results() -> None:
    """최근 AdmissionResult 표시"""
    st.markdown("#### 📋 Recent Signal Processing")
    
    try:
        # order_evidence.jsonl에서 최근 결과 읽기
        repo_root = Path(__file__).parent.parent
        evidence_file = repo_root / "logs" / "orders" / "order_evidence.jsonl"
        
        if not evidence_file.exists():
            st.info("No order evidence found")
            return
        
        # 최근 20개 결과 읽기
        recent_results = []
        with open(evidence_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            for line in lines[-20:]:  # 최근 20개
                try:
                    data = json.loads(line.strip())
                    recent_results.append(data)
                except json.JSONDecodeError:
                    continue
        
        if not recent_results:
            st.info("No valid order evidence found")
            return
        
        # 테이블로 표시
        display_data = []
        for result in recent_results:
            admission = result.get("admission_result", {})
            display_data.append({
                "Timestamp": time.strftime("%H:%M:%S", time.localtime(result.get("timestamp", 0))),
                "Symbol": result.get("symbol", "N/A"),
                "Side": result.get("side", "N/A"),
                "Qty": result.get("qty", 0),
                "Price": result.get("price", 0),
                "Status": "✅ Accepted" if admission.get("accepted") else "❌ Dropped",
                "Drop Code": admission.get("drop_code", "N/A") if not admission.get("accepted") else "N/A",
                "Trace ID": result.get("trace_id", "N/A")[:8] + "..."
            })
        
        if display_data:
            import pandas as pd
            df = pd.DataFrame(display_data)
            st.dataframe(df, use_container_width=True)
        
    except Exception as e:
        st.error(f"Failed to load recent admission results: {e}")


def render_control_buttons() -> None:
    """제어 버튼들 표시"""
    st.markdown("#### 🎛️ Controls")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🔄 Refresh Stats", key="refresh_signal_stats"):
            st.rerun()
    
    with col2:
        # Dry-Run / Live 토글
        dry_run = st.checkbox("Dry Run Mode", value=False, key="dry_run_toggle")
        if dry_run:
            st.info("🔍 Dry Run Mode: Orders will be computed but not sent")
        else:
            st.info("🚀 Live Mode: Orders will be sent to exchange")
    
    with col3:
        if st.button("🛑 Emergency STOP", key="emergency_stop"):
            # Emergency stop 로직
            st.error("🚨 Emergency STOP activated!")
            st.warning("All new orders will be blocked until manually reset")
            
            # STOP.TXT 파일 생성
            try:
                repo_root = Path(__file__).parent.parent
                stop_file = repo_root / "STOP.TXT"
                with open(stop_file, 'w') as f:
                    f.write(f"Emergency stop activated at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write("All new orders are blocked\n")
                    f.write("Manual intervention required\n")
                
                st.success("Emergency stop file created")
                
            except Exception as e:
                st.error(f"Failed to create emergency stop file: {e}")


def render_why_not_traded_table() -> None:
    """Why Not Traded 테이블 표시"""
    st.markdown("#### ❓ Why Not Traded")
    
    try:
        # order_evidence.jsonl에서 드롭된 주문들만 필터링
        repo_root = Path(__file__).parent.parent
        evidence_file = repo_root / "logs" / "orders" / "order_evidence.jsonl"
        
        if not evidence_file.exists():
            st.info("No order evidence found")
            return
        
        dropped_orders = []
        with open(evidence_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    admission = data.get("admission_result", {})
                    if not admission.get("accepted", False):
                        dropped_orders.append(data)
                except json.JSONDecodeError:
                    continue
        
        if not dropped_orders:
            st.info("No dropped orders found")
            return
        
        # 최근 10개 드롭된 주문만 표시
        recent_drops = dropped_orders[-10:]
        
        display_data = []
        for order in recent_drops:
            admission = order.get("admission_result", {})
            display_data.append({
                "Time": time.strftime("%H:%M:%S", time.localtime(order.get("timestamp", 0))),
                "Symbol": order.get("symbol", "N/A"),
                "Side": order.get("side", "N/A"),
                "Drop Code": admission.get("drop_code", "N/A"),
                "Reason": admission.get("drop_details", "N/A")[:50] + "..." if len(admission.get("drop_details", "")) > 50 else admission.get("drop_details", "N/A"),
                "Trace ID": order.get("trace_id", "N/A")[:8] + "..."
            })
        
        if display_data:
            import pandas as pd
            df = pd.DataFrame(display_data)
            st.dataframe(df, use_container_width=True)
        
    except Exception as e:
        st.error(f"Failed to load why not traded table: {e}")


def render_order_router_stats() -> None:
    """Order Router 통계 표시"""
    st.markdown("#### 🔄 Order Router Statistics")
    
    try:
        # OrderRouterResilience 통계 조회
        from .order_router_resilience import get_order_router_resilience
        
        repo_root = Path(__file__).parent.parent
        router = get_order_router_resilience()
        stats = router.get_stats()
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Orders Sent", stats["orders_sent"])
        
        with col2:
            st.metric("Success Rate", f"{stats['success_rate']:.1f}%")
        
        with col3:
            st.metric("Retry Rate", f"{stats['retry_rate']:.1f}%")
        
        with col4:
            st.metric("Total Retries", stats["total_retries"])
        
        # 최근 재시도 시도
        recent_retries = router.get_recent_retry_attempts(5)
        if recent_retries:
            with st.expander("Recent Retry Attempts"):
                retry_data = []
                for retry in recent_retries:
                    retry_data.append({
                        "Attempt": retry.attempt,
                        "Delay": f"{retry.delay:.1f}s",
                        "Error": retry.error[:50] + "..." if len(retry.error) > 50 else retry.error,
                        "Time": time.strftime("%H:%M:%S", time.localtime(retry.timestamp))
                    })
                
                if retry_data:
                    import pandas as pd
                    df = pd.DataFrame(retry_data)
                    st.dataframe(df, use_container_width=True)
        
    except Exception as e:
        st.error(f"Failed to load order router stats: {e}")


def render_comprehensive_signal_order_panel(path_registry) -> None:
    """포괄적인 Signal→Order 패널 렌더링"""
    st.markdown("---")
    st.subheader("📊 Signal → Order Processing (Comprehensive)")
    
    # 탭으로 구분
    tab1, tab2, tab3, tab4 = st.tabs(["📈 Live Stats", "🚫 Drop Analysis", "❓ Why Not Traded", "🔄 Router Stats"])
    
    with tab1:
        render_live_counters()
        render_control_buttons()
    
    with tab2:
        render_drop_code_histogram()
    
    with tab3:
        render_why_not_traded_table()
    
    with tab4:
        render_order_router_stats()
