"""
차트 UI 모듈
"""

import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots


@st.cache_data(ttl=10)
def load_symbol_snapshot_cached(symbol):
    """심볼 스냅샷 데이터 로드 (캐시 적용)"""
    try:
        snapshot_file = Path(f"shared_data/snapshots/{symbol.lower()}_snapshot.json")
        if snapshot_file.exists():
            with open(snapshot_file, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"스냅샷 로드 실패 {symbol}: {e}")
    return None

@st.cache_data(ttl=5)
def load_kline_data_cached(symbol):
    """K라인 데이터 로드 (캐시 적용)"""
    try:
        kline_file = Path(f"shared_data/klines/{symbol.lower()}_1m.json")
        if kline_file.exists():
            with open(kline_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return pd.DataFrame(data)
    except Exception as e:
        print(f"K라인 데이터 로드 실패 {symbol}: {e}")
    return pd.DataFrame()

def render_detail_chart(symbol):
    """상세 차트 렌더링"""
    st.subheader(f"📈 {symbol.upper()} 상세 차트")
    
    # K라인 데이터 로드
    df = load_kline_data_cached(symbol)
    
    if df.empty:
        st.warning(f"{symbol} 차트 데이터를 불러올 수 없습니다.")
        return
    
    # 데이터 정리
    df["time"] = pd.to_datetime(df["t"], unit="ms")
    df["open"] = df["o"]
    df["high"] = df["h"]
    df["low"] = df["l"]
    df["close"] = df["c"]
    df["volume"] = df["v"]
    
    # 캔들스틱 차트 생성
    fig = make_subplots(
        rows=2, cols=1, 
        shared_xaxes=True, 
        vertical_spacing=0.1, 
        row_heights=[0.7, 0.3]
    )
    
    # 캔들스틱
    fig.add_trace(
        go.Candlestick(
            x=df["time"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="Price",
        ),
        row=1, col=1,
    )
    
    # 거래량
    fig.add_trace(
        go.Bar(
            x=df["time"],
            y=df["volume"],
            name="Volume",
            marker_color="rgba(158,202,225,0.8)",
        ),
        row=2, col=1,
    )
    
    # 레이아웃 설정
    fig.update_layout(
        title=f"{symbol.upper()} - 1m Chart",
        xaxis_rangeslider_visible=False,
        height=600,
        margin=dict(l=8, r=8, t=40, b=8),
        plot_bgcolor="#1e1e1e",
        paper_bgcolor="#0e1117",
        font_color="#fafafa",
    )
    
    # 차트 표시
    st.plotly_chart(fig, use_container_width=True)
    
    # 심볼 정보 표시
    render_symbol_info(symbol)

def render_symbol_info(symbol):
    """심볼 기본 정보 렌더링"""
    st.markdown("#### 📊 Symbol Info")
    
    snapshot = load_symbol_snapshot_cached(symbol)
    if snapshot:
        current_price = snapshot.get("c", 0)
        price_change = snapshot.get("P", 0)
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("현재가", f"${current_price:,.4f}")
        
        with col2:
            st.metric("변동률", f"{price_change:+.2f}%")
        
        with col3:
            st.metric("심볼", symbol.upper())
    else:
        st.warning("심볼 정보를 불러올 수 없습니다.")
