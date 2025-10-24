"""
심볼 선택기 UI 모듈
"""

import json
from pathlib import Path

import streamlit as st


@st.cache_data(ttl=30)
def load_available_symbols():
    """사용 가능한 심볼 목록 로드 (캐시 적용)"""
    try:
        # 관심종목 파일에서 로드
        watchlist_file = Path("shared_data/watchlist.json")
        if watchlist_file.exists():
            with open(watchlist_file, "r", encoding="utf-8") as f:
                watchlist = json.load(f)
                return watchlist.get("symbols", [])
        
        # 기본 심볼 목록
        default_symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT", "DOTUSDT", "LINKUSDT"]
        return default_symbols
        
    except Exception as e:
        print(f"심볼 목록 로드 실패: {e}")
        return ["BTCUSDT", "ETHUSDT"]

def render_symbol_selector():
    """심볼 선택기 렌더링"""
    st.subheader("🎯 심볼 선택")
    
    # 사용 가능한 심볼 목록 로드
    symbols = load_available_symbols()
    
    if not symbols:
        st.warning("사용 가능한 심볼이 없습니다.")
        return None
    
    # 심볼 선택
    selected_symbol = st.selectbox(
        "차트를 볼 심볼을 선택하세요:",
        options=symbols,
        index=0,
        key="symbol_selector"
    )
    
    return selected_symbol
