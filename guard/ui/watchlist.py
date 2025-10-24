"""
관심종목 관리 UI 모듈
"""

import json
from pathlib import Path

import streamlit as st


def load_watchlist():
    """관심종목 목록 로드"""
    try:
        watchlist_file = Path("shared_data/watchlist.json")
        if watchlist_file.exists():
            with open(watchlist_file, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"관심종목 로드 실패: {e}")
    
    return {"symbols": ["BTCUSDT", "ETHUSDT"]}

def save_watchlist(watchlist):
    """관심종목 목록 저장"""
    try:
        watchlist_file = Path("shared_data/watchlist.json")
        watchlist_file.parent.mkdir(exist_ok=True)
        
        with open(watchlist_file, "w", encoding="utf-8") as f:
            json.dump(watchlist, f, ensure_ascii=False, indent=2)
            
    except Exception as e:
        print(f"관심종목 저장 실패: {e}")

def render_watchlist_controls():
    """관심종목 관리 UI 렌더링"""
    st.markdown("### ⭐ 관심종목")
    
    # 현재 관심종목 로드
    watchlist = load_watchlist()
    current_symbols = watchlist.get("symbols", [])
    
    # 관심종목 표시
    if current_symbols:
        st.markdown("**현재 관심종목:**")
        for symbol in current_symbols[:5]:  # 최대 5개만 표시
            st.markdown(f"• {symbol}")
        
        if len(current_symbols) > 5:
            st.markdown(f"... 외 {len(current_symbols) - 5}개")
    else:
        st.info("관심종목이 없습니다.")
    
    # 심볼 추가/제거
    st.markdown("**관심종목 관리:**")
    
    col1, col2 = st.columns(2)
    
    with col1:
        new_symbol = st.text_input(
            "심볼 추가 (예: BTCUSDT)",
            key="new_symbol_input",
            placeholder="BTCUSDT"
        )
        
        if st.button("➕ 추가", use_container_width=True) and new_symbol:
            if new_symbol.upper() not in current_symbols:
                current_symbols.append(new_symbol.upper())
                watchlist["symbols"] = current_symbols
                save_watchlist(watchlist)
                st.success(f"{new_symbol.upper()}이(가) 추가되었습니다!")
                st.rerun()
            else:
                st.warning("이미 관심종목에 있습니다.")
    
    with col2:
        if current_symbols:
            symbol_to_remove = st.selectbox(
                "제거할 심볼",
                options=current_symbols,
                key="remove_symbol_select"
            )
            
            if st.button("➖ 제거", use_container_width=True):
                current_symbols.remove(symbol_to_remove)
                watchlist["symbols"] = current_symbols
                save_watchlist(watchlist)
                st.success(f"{symbol_to_remove}이(가) 제거되었습니다!")
                st.rerun()
    
    # 관심종목 초기화
    if st.button("🔄 초기화", use_container_width=True):
        watchlist["symbols"] = ["BTCUSDT", "ETHUSDT"]
        save_watchlist(watchlist)
        st.info("관심종목이 초기화되었습니다!")
        st.rerun()
