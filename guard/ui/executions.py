"""
실시간 체결 내역 UI 모듈
"""

import json
import time
from pathlib import Path

import streamlit as st


@st.cache_data(ttl=3, max_entries=5)
def load_recent_executions():
    """최근 체결 내역 로드 (캐시 적용)"""
    try:
        executions = []
        exec_file = Path("shared_data/executions_log.jsonl")
        
        if exec_file.exists():
            with open(exec_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        exec_data = json.loads(line.strip())
                        executions.append(exec_data)
                    except json.JSONDecodeError:
                        continue
        
        # 시간순 정렬 (최신순)
        executions.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        return executions[:15]  # 최신 15개만 반환
        
    except Exception as e:
        print(f"체결 내역 로드 실패: {e}")
        return []

def render_live_executions():
    """실시간 체결 내역 렌더링"""
    st.subheader("⚡ 최근 체결 내역")
    
    executions = load_recent_executions()
    
    if not executions:
        st.info("체결 내역이 없습니다.")
        return
    
    # 체결 내역 표시
    for execution in executions:
        with st.container():
            col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
            
            with col1:
                symbol = execution.get("symbol", "N/A")
                side = execution.get("side", "N/A")
                side_emoji = "🟢" if side == "buy" else "🔴"
                
                st.write(f"**{symbol}** {side_emoji} {side.upper()}")
            
            with col2:
                amount = execution.get("amount", 0)
                st.metric("수량", f"{amount:.6f}")
            
            with col3:
                price = execution.get("price", 0)
                st.metric("가격", f"${price:,.4f}")
            
            with col4:
                timestamp = execution.get("timestamp", 0)
                if timestamp:
                    time_str = time.strftime("%H:%M:%S", time.localtime(timestamp))
                    st.write(f"시간: {time_str}")
            
            st.markdown("---")
