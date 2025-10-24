"""
Multi Board UI 모듈 - 수익률 현황과 Symbol Cards
"""

import json
import time
from pathlib import Path

import streamlit as st


@st.cache_data(ttl=5, max_entries=10)
def load_watchlist_cached():
    """관심종목 목록 로드 (캐시 적용)"""
    try:
        watchlist_file = Path("shared_data/watchlist.json")
        if watchlist_file.exists():
            with open(watchlist_file, "r", encoding="utf-8") as f:
                watchlist = json.load(f)
                return watchlist.get("symbols", [])
        
        # 기본 심볼 목록
        default_symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT", "DOTUSDT", "LINKUSDT"]
        return default_symbols
        
    except Exception as e:
        print(f"관심종목 로드 실패: {e}")
        return ["BTCUSDT", "ETHUSDT"]

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
def load_ares_data_cached(symbol):
    """ARES 데이터 로드 (캐시 적용)"""
    try:
        ares_file = Path(f"shared_data/ares/{symbol.lower()}_ares.json")
        if ares_file.exists():
            with open(ares_file, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"ARES 데이터 로드 실패 {symbol}: {e}")
    return None

@st.cache_data(ttl=5)
def load_symbol_history_cached(symbol, limit=50):
    """심볼 히스토리 로드 (캐시 적용)"""
    try:
        history_file = Path(f"shared_data/history/{symbol.lower()}_history.json")
        if history_file.exists():
            with open(history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data[-limit:] if len(data) > limit else data
                return data
    except Exception as e:
        print(f"히스토리 로드 실패 {symbol}: {e}")
    return []

def create_profit_metrics_view_model():
    """수익률 현황 ViewModel 생성"""
    try:
        # 거래 기록 파일들 찾기
        trade_files = []
        possible_paths = [
            "trades/trades.jsonl",
            "logs/trader_fills.ndjson",
            "shared_data/trades/*.json",
            "logs/trades/*.json",
            "executor/trades/*.json",
            "shared_data/logs/*.json",
        ]

        for pattern in possible_paths:
            if "*" in pattern:
                import glob
                trade_files.extend(glob.glob(pattern))
            else:
                if Path(pattern).exists():
                    trade_files.append(pattern)

        # 거래 기록 로드
        all_trades = []
        for file_path in trade_files:
            try:
                if file_path.endswith(".jsonl"):
                    with open(file_path, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                try:
                                    trade_data = json.loads(line)
                                    all_trades.append(trade_data)
                                except json.JSONDecodeError:
                                    continue
                elif file_path.endswith(".json"):
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            all_trades.extend(data)
                        else:
                            all_trades.append(data)
            except Exception as e:
                print(f"거래 파일 로드 실패 {file_path}: {e}")
                continue

        # 수익률 계산 (간단한 버전)
        if not all_trades:
            return {
                'daily_return_pct': 0.0,
                'daily_pnl': 0.0,
                'cumulative_return_pct': 0.0,
                'cumulative_pnl': 0.0,
                'sharpe_ratio': 0.0
            }

        # 기본 수익률 계산
        total_pnl = sum(trade.get('pnl', 0) for trade in all_trades if 'pnl' in trade)
        initial_balance = 10000.0  # 기본값
        cumulative_return_pct = (total_pnl / initial_balance) * 100 if initial_balance > 0 else 0.0

        return {
            'daily_return_pct': 0.0,  # 일일 수익률 (추후 구현)
            'daily_pnl': 0.0,  # 일일 수익금 (추후 구현)
            'cumulative_return_pct': cumulative_return_pct,
            'cumulative_pnl': total_pnl,
            'sharpe_ratio': 0.0  # 샤프 비율 (추후 구현)
        }

    except Exception as e:
        print(f"수익률 계산 실패: {e}")
        return {
            'daily_return_pct': 0.0,
            'daily_pnl': 0.0,
            'cumulative_return_pct': 0.0,
            'cumulative_pnl': 0.0,
            'sharpe_ratio': 0.0
        }

def create_symbol_view_model(symbol):
    """심볼 카드용 ViewModel 생성"""
    snapshot = load_symbol_snapshot_cached(symbol)
    ares_data = load_ares_data_cached(symbol)
    history = load_symbol_history_cached(symbol, 50)
    
    current_time = time.strftime("%H:%M:%S")
    
    # 기본값 설정
    vm = {
        'symbol': symbol,
        'current_time': current_time,
        'price_age': 0,
        'current_price': None,
        'price_change': None,
        'unrealized_pnl': None,
        'entry_price': None,
        'signal_side': "HOLD",
        'confidence': None,
        'signal_price': None,
        'is_stale_price': False,
        'is_stale_ares': False
    }
    
    # 스냅샷 데이터 처리
    if snapshot:
        vm['current_price'] = snapshot.get('c', 0)
        vm['price_change'] = snapshot.get('P', 0)
        vm['price_age'] = time.time() - (snapshot.get('last_event_ms', 0) / 1000)
        vm['is_stale_price'] = vm['price_age'] > 300  # 5분 이상이면 stale
    
    # ARES 데이터 처리
    if ares_data:
        vm['signal_side'] = ares_data.get('signal', 'HOLD')
        vm['confidence'] = ares_data.get('confidence', 0)
        vm['signal_price'] = ares_data.get('target_price', 0)
        vm['is_stale_ares'] = time.time() - ares_data.get('timestamp', 0) > 300
    
    return vm

def render_symbol_card(symbol):
    """심볼 카드 렌더링"""
    vm = create_symbol_view_model(symbol)
    
    # 전처리된 문자열 생성
    def format_price_safe(price):
        if price is None or price == 0:
            return "—"
        return f"{price:,.4f}"
    
    def format_percentage_safe(percent):
        if percent is None:
            return "—"
        return f"{percent:+.2f}%"
    
    # Entry 가격 표시
    entry_display = "—" if vm["entry_price"] is None else format_price_safe(vm["entry_price"])
    
    # Target/Confidence
    target_display = "—" if vm["signal_price"] is None else format_price_safe(vm["signal_price"])
    confidence_display = "—" if vm["confidence"] is None else f"{vm['confidence']:.1f}%"
    
    # 1m Return
    return_display = format_percentage_safe(vm["price_change"])
    
    # 신호 상태에 따른 스타일 결정
    signal_color = "#666666"
    signal_icon = "⚪"
    
    if vm["signal_side"] == "BUY" and vm["confidence"] and vm["confidence"] >= 75:
        signal_color = "#00ff00"
        signal_icon = "🟢"
    elif vm["signal_side"] == "SELL" and vm["confidence"] and vm["confidence"] >= 75:
        signal_color = "#ff4444"
        signal_icon = "🔴"
    elif vm["signal_side"] == "BUY" or vm["signal_side"] == "SELL":
        signal_color = "#ffaa00"
        signal_icon = "🟡"
    
    # ARES 배지
    ares_badge = ""
    if vm["is_stale_ares"]:
        ares_badge = '<span style="color: #ffaa00; font-size: 0.7rem; background: #2d1f1f; padding: 0.2rem 0.4rem; border-radius: 0.3rem;">STALE_ARES</span>'
    else:
        ares_badge = '<span style="color: #00ff88; font-size: 0.7rem; background: #0d2818; padding: 0.2rem 0.4rem; border-radius: 0.3rem;">WARMING</span>'
    
    # 상태 요약
    status_parts = []
    if vm["is_stale_price"]:
        status_parts.append("STALE_PRICE")
    if vm["is_stale_ares"]:
        status_parts.append("STALE_ARES")
    
    if not status_parts:
        status_summary = "OK"
    elif len(status_parts) == 1:
        status_summary = status_parts[0]
    else:
        status_summary = f"{len(status_parts)} STALE"

    st.markdown(
        f"""
    <div style="background-color: #1e1e1e; border: 1px solid #333; border-radius: 0.5rem; padding: 1rem; margin-bottom: 1rem;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
            <strong style="color: #ffffff; font-size: 1.1rem;">{vm['symbol'].upper()}</strong>
            <div style="font-size: 0.8rem; color: #888;">
                {vm['current_time']} KST age {vm['price_age']:.0f}s
            </div>
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
            <div>
                <div style="color: #ffffff; margin-bottom: 0.3rem;">Last: ${format_price_safe(vm['current_price'])}</div>
                <div style="color: #ffffff; margin-bottom: 0.3rem;">1m Return: {return_display}</div>
                <div style="color: #ffffff; margin-bottom: 0.3rem;">Unrealized: ${format_price_safe(vm['unrealized_pnl'])}</div>
            </div>
            <div>
                <div style="color: {signal_color}; font-weight: bold; margin-bottom: 0.3rem;">
                    {signal_icon} {vm['signal_side']} | {confidence_display}
                </div>
                <div style="color: #ffffff; margin-bottom: 0.3rem;">Entry: ${entry_display}</div>
                <div style="color: #ffffff; margin-bottom: 0.3rem;">Target: ${target_display}</div>
                <div style="margin-bottom: 0.3rem;">{ares_badge}</div>
            </div>
        </div>
        <div style="font-size: 0.6rem; color: #888; margin-top: 0.5rem; text-align: center;">
            Status: {status_summary}
        </div>
    </div>
    """,
        unsafe_allow_html=True,
    )

def render_multi_board():
    """Multi Board 렌더링 - 종합 대시보드"""
    st.markdown("### 📊 Multi Board - 종합 대시보드")

    # 핵심 수익률 KPI (4개 타일)
    st.markdown("#### 💰 수익률 현황")
    col1, col2, col3, col4 = st.columns(4)

    # 수익률 현황 ViewModel 생성
    pnl_vm = create_profit_metrics_view_model()
    
    # ViewModel에서 변수 추출
    daily_return_pct = pnl_vm['daily_return_pct']
    daily_pnl = pnl_vm['daily_pnl']
    cumulative_return_pct = pnl_vm['cumulative_return_pct']
    cumulative_pnl = pnl_vm['cumulative_pnl']
    sharpe_ratio = pnl_vm['sharpe_ratio']

    with col1:
        st.markdown(
            f"""
        <div style="text-align: center; padding: 1rem; background-color: #1e1e1e; border-radius: 0.5rem; border: 1px solid #333;">
            <div style="font-size: 0.8rem; color: #ffffff; margin-bottom: 0.5rem;">오늘 수익률</div>
            <div style="font-size: 1.07rem; font-weight: bold; color: #ffffff; margin-bottom: 0.5rem;">{daily_return_pct:+.2f}%</div>
            <div style="font-size: 0.6rem; color: #00ff88; background-color: #0d2818; padding: 0.2rem 0.5rem; border-radius: 0.3rem; display: inline-block;">↗ {daily_pnl:+.2f}</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            f"""
        <div style="text-align: center; padding: 1rem; background-color: #1e1e1e; border-radius: 0.5rem; border: 1px solid #333;">
            <div style="font-size: 0.8rem; color: #ffffff; margin-bottom: 0.5rem;">누적 수익률</div>
            <div style="font-size: 1.07rem; font-weight: bold; color: #ffffff; margin-bottom: 0.5rem;">{cumulative_return_pct:+.2f}%</div>
            <div style="font-size: 0.6rem; color: #00ff88; background-color: #0d2818; padding: 0.2rem 0.5rem; border-radius: 0.3rem; display: inline-block;">↗ {cumulative_pnl:+.2f}</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with col3:
        st.markdown(
            f"""
        <div style="text-align: center; padding: 1rem; background-color: #1e1e1e; border-radius: 0.5rem; border: 1px solid #333;">
            <div style="font-size: 0.8rem; color: #ffffff; margin-bottom: 0.5rem;">누적 수익금</div>
            <div style="font-size: 1.07rem; font-weight: bold; color: #ffffff; margin-bottom: 0.5rem;">{cumulative_pnl:+,.2f} USDT</div>
            <div style="font-size: 0.6rem; color: #00ff88; background-color: #0d2818; padding: 0.2rem 0.5rem; border-radius: 0.3rem; display: inline-block;">총 수익</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with col4:
        st.markdown(
            f"""
        <div style="text-align: center; padding: 1rem; background-color: #1e1e1e; border-radius: 0.5rem; border: 1px solid #333;">
            <div style="font-size: 0.8rem; color: #ffffff; margin-bottom: 0.5rem;">샤프 비율</div>
            <div style="font-size: 1.07rem; font-weight: bold; color: #ffffff; margin-bottom: 0.5rem;">{sharpe_ratio:.2f}</div>
            <div style="font-size: 0.6rem; color: #00ff88; background-color: #0d2818; padding: 0.2rem 0.5rem; border-radius: 0.3rem; display: inline-block;">{"우수" if sharpe_ratio > 2 else "보통"}</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    # 심볼 카드들 (3-4개 per row, max 12개)
    st.markdown("#### Symbol Cards")

    # 그리드로 카드 표시 - 모든 심볼 표시
    watchlist = load_watchlist_cached()
    symbols_to_show = watchlist  # 모든 심볼 표시

    # 데이터가 있는 심볼만 필터링
    valid_symbols = []
    for symbol in symbols_to_show:
        try:
            snapshot = load_symbol_snapshot_cached(symbol)
            ares_data = load_ares_data_cached(symbol)
            history = load_symbol_history_cached(symbol, 50)
            
            # 데이터가 하나라도 있으면 유효한 심볼로 간주
            if snapshot or ares_data or history:
                valid_symbols.append(symbol)
        except Exception:
            continue
    
    # 유효한 심볼들을 3열 그리드로 배치
    for i in range(0, len(valid_symbols), 3):
        cols = st.columns(3)
        for j, col in enumerate(cols):
            if i + j < len(valid_symbols):
                symbol = valid_symbols[i + j]
                with col:
                    render_symbol_card(symbol)
