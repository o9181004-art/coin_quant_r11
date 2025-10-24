"""
거래 내역 UI 모듈
"""

import json
from pathlib import Path

import streamlit as st


@st.cache_data(ttl=5, max_entries=10)
def load_recent_trades():
    """최근 거래 내역 로드 (캐시 적용)"""
    try:
        trades = []
        trades_file = Path("shared_data/trades_log.jsonl")
        
        if trades_file.exists():
            with open(trades_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        trade_data = json.loads(line.strip())
                        trades.append(trade_data)
                    except json.JSONDecodeError:
                        continue
        
        # 시간순 정렬 (최신순)
        trades.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        return trades[:20]  # 최신 20개만 반환
        
    except Exception as e:
        print(f"거래 내역 로드 실패: {e}")
        return []

def render_trades_clean():
    """거래 내역 렌더링 (깔끔한 버전)"""
    st.subheader("📋 거래 내역")
    
    trades = load_recent_trades()
    
    if not trades:
        st.info("체결 내역이 없습니다")
        return
    
    # 매수/매도 분리
    buy_trades = [t for t in trades if t.get("side") == "buy"]
    sell_trades = [t for t in trades if t.get("side") == "sell"]
    
    st.markdown(
        f"**총 거래:** {len(trades)}건 | "
        f"**매수:** {len(buy_trades)}건 | "
        f"**매도:** {len(sell_trades)}건"
    )
    st.markdown("---")
    
    # 매수/매도 내역을 나란히 표시
    col_buy, col_sell = st.columns([1, 1.5])
    
    with col_buy:
        st.markdown("### 🟢 매수")
        if not buy_trades:
            st.info("매수 내역 없음")
        else:
            for trade in buy_trades[:5]:  # 최신 5개만
                symbol = trade.get("symbol", "N/A")
                amount = trade.get("amount", 0)
                price = trade.get("price", 0)
                
                st.markdown(
                    f"**{symbol}**\n"
                    f"수량: {amount:.6f}\n"
                    f"가격: ${price:,.4f}"
                )
                st.markdown("---")
    
    with col_sell:
        st.markdown("### 🔴 매도")
        if not sell_trades:
            st.info("매도 내역 없음")
        else:
            for trade in sell_trades[:5]:  # 최신 5개만
                symbol = trade.get("symbol", "N/A")
                amount = trade.get("amount", 0)
                price = trade.get("price", 0)
                profit = trade.get("profit", 0)
                
                profit_color = "🟢" if profit > 0 else "🔴" if profit < 0 else "⚪"
                
                st.markdown(
                    f"**{symbol}** {profit_color}\n"
                    f"수량: {amount:.6f}\n"
                    f"가격: ${price:,.4f}\n"
                    f"수익: ${profit:,.2f}"
                )
                st.markdown("---")
