"""
거래 신호 UI 모듈
"""

import json
import time
from pathlib import Path

import streamlit as st


@st.cache_data(ttl=5, max_entries=10)
def load_latest_signals():
    """최신 거래 신호 로드 (캐시 적용)"""
    try:
        signals = []
        signals_dir = Path("shared_data/signals")
        
        if signals_dir.exists():
            for signal_file in signals_dir.glob("*.json"):
                try:
                    with open(signal_file, "r", encoding="utf-8") as f:
                        signal_data = json.load(f)
                        signals.append(signal_data)
                except Exception as e:
                    print(f"신호 파일 로드 실패 {signal_file}: {e}")
        
        # 시간순 정렬 (최신순)
        signals.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        return signals[:10]  # 최신 10개만 반환
        
    except Exception as e:
        print(f"신호 로드 실패: {e}")
        return []

def render_trading_signals():
    """거래 신호 렌더링"""
    st.subheader("📊 실시간 거래 신호")
    
    signals = load_latest_signals()
    
    if not signals:
        st.info("현재 신호 데이터가 없습니다.")
        return
    
    # 신호 카드 표시
    for signal in signals:
        with st.container():
            col1, col2, col3 = st.columns([2, 1, 1])
            
            with col1:
                st.markdown("**🔔 최근 신호:**")
                symbol = signal.get("symbol", "N/A")
                side = signal.get("side", "N/A")
                confidence = signal.get("confidence", 0)
                
                st.write(
                    f"**{symbol}** {side} 신호 (신뢰도: {confidence}%)"
                )
            
            with col2:
                price = signal.get("price", 0)
                st.metric("가격", f"${price:,.4f}")
            
            with col3:
                timestamp = signal.get("timestamp", 0)
                if timestamp:
                    time_str = time.strftime("%H:%M:%S", time.localtime(timestamp))
                    st.write(f"시간: {time_str}")
            
            st.markdown("---")
