#!/usr/bin/env python3
"""
Trades Ledger Dashboard - Fast, read-only, event-driven
"""
import json
import os
import threading
import time
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

try:
    from guard.ui.utils.trades_reader import (TradeRecord, TradesReader,
                                              TradesSummary, get_trades_reader)
    from shared.environment_manager import EnvironmentManager
    from shared.path_registry import PathRegistry
except ImportError as e:
    st.error(f"Import error: {e}")
    st.stop()

# Page config
st.set_page_config(
    page_title="거래 내역장",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Environment variables
LEDGER_DEBUG = os.getenv("LEDGER_DEBUG", "false").lower() == "true"
UI_AUTO_REFRESH_MS = int(os.getenv("UI_AUTO_REFRESH_MS", "5000"))
UI_EVENT_POLL_MS = int(os.getenv("UI_EVENT_POLL_MS", "600"))
UI_RERUN_DEBOUNCE_MS = int(os.getenv("UI_RERUN_DEBOUNCE_MS", "1200"))


class TradesLedgerWatcher:
    """Event-driven file watcher for trades ledger"""
    
    def __init__(self):
        self._running = False
        self._thread = None
        self._last_signatures = {}
        self._last_rerun = 0
        
    def start(self):
        """Start the watcher thread"""
        if self._running:
            return
            
        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()
        
    def stop(self):
        """Stop the watcher thread"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)
            
    def _watch_loop(self):
        """Main watching loop"""
        reader = get_trades_reader()
        
        while self._running:
            try:
                # Check for file changes
                current_time = time.time()
                file_path = reader.get_trading_log_path()
                
                if file_path.exists():
                    signature = reader.get_file_signature(file_path)
                    signature_key = f"{signature[0]}:{signature[1]}:{signature[2]}"
                    
                    if signature_key != self._last_signatures.get("trading_log"):
                        # File changed, check debounce
                        if current_time - self._last_rerun >= UI_RERUN_DEBOUNCE_MS / 1000:
                            self._last_signatures["trading_log"] = signature_key
                            self._last_rerun = current_time
                            
                            # Trigger rerun
                            try:
                                st.rerun()
                            except Exception as e:
                                if LEDGER_DEBUG:
                                    print(f"Rerun error: {e}")
                
                # time.sleep(UI_EVENT_POLL_MS / 1000)  # UI 블로킹 방지
                
            except Exception as e:
                if LEDGER_DEBUG:
                    print(f"Watcher error: {e}")
                # time.sleep(1)  # UI 블로킹 방지


# Session state will be initialized in main()


def get_filtered_trades(trades: List[TradeRecord], filters: Dict[str, Any]) -> List[TradeRecord]:
    """Apply filters to trades list"""
    filtered = trades.copy()
    
    # Date filter
    if filters.get("date_range") == "today":
        today = datetime.now().date()
        filtered = [t for t in filtered if datetime.fromtimestamp(t.ts).date() == today]
    elif filters.get("date_range") == "yesterday":
        yesterday = (datetime.now() - timedelta(days=1)).date()
        filtered = [t for t in filtered if datetime.fromtimestamp(t.ts).date() == yesterday]
    elif filters.get("date_range") == "7days":
        week_ago = datetime.now() - timedelta(days=7)
        filtered = [t for t in filtered if datetime.fromtimestamp(t.ts) >= week_ago]
    
    # Symbol filter
    if filters.get("symbols"):
        filtered = [t for t in filtered if t.symbol in filters["symbols"]]
    
    # Side filter
    if filters.get("side"):
        filtered = [t for t in filtered if t.side == filters["side"]]
    
    # Strategy filter
    if filters.get("strategy"):
        filtered = [t for t in filtered if t.strategy == filters["strategy"]]
    
    # Min notional filter
    min_notional = filters.get("min_notional", 0)
    if min_notional > 0:
        filtered = [t for t in filtered if t.notional >= min_notional]
    
    return filtered


def render_summary_bar(summary: TradesSummary):
    """Render top summary bar"""
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        pnl_color = "red" if summary.realized_pnl > 0 else "blue" if summary.realized_pnl < 0 else "gray"
        st.metric(
            "실현손익", 
            f"{summary.realized_pnl:,.2f} USDT",
            delta=None,
            help="수수료 차감 후 순손익"
        )
    
    with col2:
        st.metric(
            "총 체결수",
            f"{summary.total_trades:,}건",
            help="필터 적용된 거래 건수"
        )
    
    with col3:
        st.metric(
            "평균체결가",
            f"{summary.avg_price:,.2f} USDT",
            help="거래량 가중 평균가"
        )
    
    with col4:
        st.metric(
            "총수수료",
            f"{summary.total_fees:,.4f} USDT",
            help="누적 수수료"
        )
    
    with col5:
        buy_sell_ratio = summary.buy_count / summary.sell_count if summary.sell_count > 0 else 0
        st.metric(
            "매수/매도",
            f"{summary.buy_count}/{summary.sell_count}",
            help=f"비율: {buy_sell_ratio:.2f}"
        )


def render_filters_sidebar() -> Dict[str, Any]:
    """Render filters in sidebar"""
    st.sidebar.header("🔍 필터")
    
    filters = {}
    
    # Date range filter
    filters["date_range"] = st.sidebar.selectbox(
        "기간",
        ["all", "today", "yesterday", "7days"],
        format_func=lambda x: {
            "all": "전체",
            "today": "오늘",
            "yesterday": "어제", 
            "7days": "최근 7일"
        }[x]
    )
    
    # Get available symbols from trades
    reader = get_trades_reader()
    file_path = reader.get_trading_log_path()
    trades, _ = reader.read_trades(file_path)
    
    if trades:
        symbols = sorted(list(set(trade.symbol for trade in trades)))
        filters["symbols"] = st.sidebar.multiselect(
            "종목",
            symbols,
            default=symbols,
            help="선택된 종목만 표시"
        )
        
        # Side filter
        sides = ["BUY", "SELL"]
        selected_side = st.sidebar.selectbox(
            "방향",
            ["all"] + sides,
            format_func=lambda x: {
                "all": "전체",
                "BUY": "매수",
                "SELL": "매도"
            }[x]
        )
        if selected_side != "all":
            filters["side"] = selected_side
        
        # Strategy filter
        strategies = sorted(list(set(trade.strategy for trade in trades if trade.strategy)))
        if strategies:
            selected_strategy = st.sidebar.selectbox(
                "전략",
                ["all"] + strategies,
                format_func=lambda x: x if x != "all" else "전체"
            )
            if selected_strategy != "all":
                filters["strategy"] = selected_strategy
    
    # Min notional filter
    filters["min_notional"] = st.sidebar.number_input(
        "최소 체결금액 (USDT)",
        min_value=0.0,
        value=0.0,
        step=10.0,
        help="이 금액 이상의 거래만 표시"
    )
    
    return filters


def render_trades_table(trades: List[TradeRecord]):
    """Render trades table with virtualized scrolling"""
    if not trades:
        st.info("표시할 거래 내역이 없습니다.")
        return
    
    # Convert to DataFrame for display
    df_data = []
    for trade in trades:
        df_data.append({
            "시간": trade.time,
            "종목": trade.symbol,
            "방향": trade.side,
            "수량": f"{trade.qty:,.6f}",
            "체결가": f"{trade.price:,.2f}",
            "수수료": f"{trade.fee:.4f}",
            "실현손익": f"{trade.realized_pnl:,.2f}",
            "전략": trade.strategy,
            "주문ID": trade.order_id[:12] + "..." if len(trade.order_id) > 12 else trade.order_id
        })
    
    df = pd.DataFrame(df_data)
    
    # Color coding for PnL
    def color_pnl(val):
        try:
            pnl = float(val.replace(',', ''))
            if pnl > 0:
                return 'color: red; font-weight: bold'
            elif pnl < 0:
                return 'color: blue; font-weight: bold'
            else:
                return 'color: gray'
        except:
            return ''
    
    # Apply styling
    styled_df = df.style.applymap(color_pnl, subset=['실현손익'])
    
    # Display table with fixed height
    st.dataframe(
        styled_df,
        height=600,
        use_container_width=True,
        hide_index=True
    )


def render_actions_bar(trades: List[TradeRecord]):
    """Render action buttons"""
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if st.button("📊 CSV 내보내기", help="현재 필터된 데이터를 CSV로 다운로드"):
            if trades:
                # Convert to CSV
                df_data = []
                for trade in trades:
                    df_data.append(asdict(trade))
                
                df = pd.DataFrame(df_data)
                csv = df.to_csv(index=False)
                
                st.download_button(
                    label="CSV 다운로드",
                    data=csv,
                    file_name=f"trades_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
            else:
                st.warning("내보낼 데이터가 없습니다.")
    
    with col2:
        if st.button("📋 클립보드 복사", help="선택된 거래 정보를 클립보드에 복사"):
            if trades:
                # Create summary text
                summary_text = f"총 {len(trades)}건의 거래\n"
                summary_text += f"실현손익: {sum(t.realized_pnl for t in trades):,.2f} USDT\n"
                summary_text += f"총 수수료: {sum(t.fee for t in trades):,.4f} USDT\n"
                
                st.text_area("복사할 내용", summary_text, height=100)
                st.info("위 내용을 복사하여 사용하세요.")
            else:
                st.warning("복사할 데이터가 없습니다.")
    
    with col3:
        if st.button("📁 로그 열기", help="거래 로그 파일 위치 열기"):
            reader = get_trades_reader()
            file_path = reader.get_trading_log_path()
            st.code(f"로그 파일: {file_path}")
            st.info("파일 탐색기에서 해당 경로를 열어보세요.")
    
    with col4:
        # Live update toggle
        live_enabled = st.checkbox("🔄 실시간 업데이트", value=True, help="파일 변경 시 자동 새로고침")
        if live_enabled:
            st.session_state.watcher.start()
        else:
            st.session_state.watcher.stop()


def render_diagnostics(diagnostics: Dict[str, Any]):
    """Render debug diagnostics"""
    if not LEDGER_DEBUG:
        return
    
    with st.expander("🔧 진단 정보", expanded=False):
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**파일 정보**")
            st.write(f"경로: `{diagnostics.get('file_path', 'N/A')}`")
            st.write(f"존재: {diagnostics.get('file_exists', False)}")
            st.write(f"크기: {diagnostics.get('file_size', 0):,} bytes")
            st.write(f"나이: {diagnostics.get('age_seconds', 0):.1f}초")
        
        with col2:
            st.write("**파싱 정보**")
            st.write(f"총 라인: {diagnostics.get('total_lines', 0):,}")
            st.write(f"유효 거래: {diagnostics.get('valid_trades', 0):,}")
            st.write(f"파싱 오류: {diagnostics.get('parse_errors', 0):,}")
            st.write(f"삭제된 라인: {diagnostics.get('dropped_lines', 0):,}")


def render_empty_state(diagnostics: Dict[str, Any]):
    """Render empty state with reason badges"""
    if diagnostics.get("file_exists", False):
        return False
    
    st.warning("📁 거래 로그 파일을 찾을 수 없습니다")
    
    # Show reason badges
    reasons = []
    if not diagnostics.get("file_exists", False):
        reasons.append("파일 없음")
    
    if diagnostics.get("file_size", 0) == 0:
        reasons.append("크기 0")
    
    if diagnostics.get("age_seconds", 0) > 300:
        reasons.append("5분 이상 오래됨")
    
    if reasons:
        st.error("원인: " + " | ".join(reasons))
    
    # Show available fallback files
    reader = get_trades_reader()
    fallbacks = reader.get_fallback_paths()
    
    if fallbacks:
        st.info("사용 가능한 대체 파일:")
        for fallback in fallbacks:
            st.write(f"• {fallback}")
    
    return True


def main():
    """Main trades ledger dashboard"""
    # Initialize session state
    if "ledger_initialized" not in st.session_state:
        st.session_state.ledger_initialized = True
        st.session_state.watcher = TradesLedgerWatcher()
        st.session_state.last_update = 0
        st.session_state.trades_cache = {}
        st.session_state.summary_cache = {}
    
    # Header
    st.title("📊 거래 내역장")
    st.caption("실시간 거래 내역 조회 및 분석")
    
    # Read-only mode indicator
    st.info("🔒 읽기 전용 모드 - 서비스 변경 불가")
    
    # Get trades reader
    reader = get_trades_reader()
    
    # Render filters
    filters = render_filters_sidebar()
    
    # Get trades data
    file_path = reader.get_trading_log_path()
    trades, diagnostics = reader.read_trades(file_path)
    
    # Check for empty state
    if render_empty_state(diagnostics):
        render_diagnostics(diagnostics)
        return
    
    # Apply filters
    filtered_trades = get_filtered_trades(trades, filters)
    
    # Calculate summary
    summary = reader.get_trades_summary(filtered_trades)
    
    # Render summary bar
    render_summary_bar(summary)
    
    # Render actions
    render_actions_bar(filtered_trades)
    
    # Render trades table
    st.subheader(f"거래 내역 ({len(filtered_trades):,}건)")
    render_trades_table(filtered_trades)
    
    # Render diagnostics
    render_diagnostics(diagnostics)
    
    # Auto-refresh info
    if st.session_state.watcher._running:
        st.caption("🔄 실시간 모드 - 파일 변경 감지 중")


if __name__ == "__main__":
    main()
