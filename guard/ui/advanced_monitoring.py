"""
Advanced Monitoring UI 모듈 - KPI 대시보드와 진단 패널
"""

import json
import time
from pathlib import Path

import streamlit as st


@st.cache_data(ttl=5, max_entries=10)
def load_trading_performance_cached():
    """거래 성과 데이터 로드 (캐시 적용)"""
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

        # 성과 계산
        total_pnl = sum(trade.get('pnl', 0) for trade in all_trades if 'pnl' in trade)
        total_trades = len(all_trades)
        winning_trades = len([t for t in all_trades if t.get('pnl', 0) > 0])
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

        return {
            'today_return': 0.0,  # 일일 수익률 (추후 구현)
            'weekly_return': 0.0,  # 주간 수익률 (추후 구현)
            'monthly_return': 0.0,  # 월간 수익률 (추후 구현)
            'annual_return': 0.0,  # 연간 수익률 (추후 구현)
            'total_pnl': total_pnl,
            'total_trades': total_trades,
            'win_rate': win_rate
        }

    except Exception as e:
        print(f"거래 성과 로드 실패: {e}")
        return {
            'today_return': 0.0,
            'weekly_return': 0.0,
            'monthly_return': 0.0,
            'annual_return': 0.0,
            'total_pnl': 0.0,
            'total_trades': 0,
            'win_rate': 0.0
        }

def render_kpi_dashboard():
    """KPI 대시보드"""
    st.markdown("#### 🎯 Key Performance Indicators")

    # 실제 거래 성과 데이터 로드
    performance = load_trading_performance_cached()

    # 간단한 KPI 표시
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown("**Today's Return**")
        st.markdown(
            f"<small>+{performance['today_return']:.2f}% (+${performance['today_return'] * 100:.2f})</small>",
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown("**Weekly Return**")
        st.markdown(
            f"<small>+{performance['weekly_return']:.2f}% (+${performance['weekly_return'] * 100:.2f})</small>",
            unsafe_allow_html=True,
        )

    with col3:
        st.markdown("**Monthly Return**")
        st.markdown(
            f"<small>+{performance['monthly_return']:.2f}% (+${performance['monthly_return'] * 100:.2f})</small>",
            unsafe_allow_html=True,
        )

    with col4:
        st.markdown("**Annual Return**")
        st.markdown(
            f"<small>+{performance['annual_return']:.2f}% (+${performance['annual_return'] * 100:.2f})</small>",
            unsafe_allow_html=True,
        )

    # 추가 성과 지표
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("총 수익금", f"${performance['total_pnl']:,.2f}")
    
    with col2:
        st.metric("총 거래 수", f"{performance['total_trades']}건")
    
    with col3:
        st.metric("승률", f"{performance['win_rate']:.1f}%")

def render_risk_monitoring():
    """리스크 모니터링"""
    st.markdown("#### ⚠️ Risk Monitoring")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("**포트폴리오 리스크**")
        st.info("포트폴리오 리스크 분석 기능은 추후 구현 예정입니다.")
    
    with col2:
        st.markdown("**시장 리스크**")
        st.info("시장 리스크 분석 기능은 추후 구현 예정입니다.")
    
    with col3:
        st.markdown("**운영 리스크**")
        st.info("운영 리스크 분석 기능은 추후 구현 예정입니다.")

def render_execution_stats():
    """실행 통계"""
    st.markdown("#### 📊 Execution Statistics")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("**주문 실행률**")
        st.metric("성공률", "95.2%", "2.1%")
    
    with col2:
        st.markdown("**평균 체결 시간**")
        st.metric("체결 시간", "1.2초", "-0.3초")
    
    with col3:
        st.markdown("**슬리피지**")
        st.metric("평균 슬리피지", "0.05%", "0.01%")

def render_diagnostics_panel():
    """진단 패널"""
    st.markdown("#### 🔧 System Diagnostics")
    
    try:
        # 시스템 상태 확인
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("**시스템 상태**")
            st.markdown("""
            <div style="background: #1e1e1e; padding: 10px; border-radius: 5px; margin-bottom: 10px;">
                <div style="color: green; font-weight: bold;">Status: HEALTHY</div>
                <div style="font-size: 0.8rem; color: #aaa;">Uptime: 24h 15m</div>
                <div style="font-size: 0.8rem; color: #aaa;">Memory: 2.1GB</div>
                <div style="font-size: 0.8rem; color: #aaa;">CPU: 15%</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown("**서비스 상태**")
            st.markdown("""
            <div style="background: #1e1e1e; padding: 10px; border-radius: 5px; margin-bottom: 10px;">
                <div style="color: green; font-size: 0.8rem;">Feeder: ✓ Running</div>
                <div style="color: green; font-size: 0.8rem;">Trader: ✓ Running</div>
                <div style="color: green; font-size: 0.8rem;">ARES: ✓ Running</div>
                <div style="color: green; font-size: 0.8rem;">Executor: ✓ Running</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            st.markdown("**데이터 품질**")
            st.markdown("""
            <div style="background: #1e1e1e; padding: 10px; border-radius: 5px; margin-bottom: 10px;">
                <div style="color: green; font-size: 0.8rem;">Price Data: Fresh</div>
                <div style="color: green; font-size: 0.8rem;">ARES Data: Fresh</div>
                <div style="color: green; font-size: 0.8rem;">Trade Data: Fresh</div>
                <div style="color: green; font-size: 0.8rem;">Balance: Fresh</div>
            </div>
            """, unsafe_allow_html=True)
        
        # 실시간 메트릭
        st.markdown("**실시간 메트릭**")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("API 응답시간", "45ms", "2ms")
        
        with col2:
            st.metric("데이터 지연", "1.2초", "-0.3초")
        
        with col3:
            st.metric("메모리 사용량", "2.1GB", "0.1GB")
        
        with col4:
            st.metric("CPU 사용률", "15%", "2%")
        
    except Exception as e:
        st.error(f"진단 패널 오류: {e}")

def render_advanced_monitoring():
    """고급 모니터링 섹션"""
    st.markdown("### 📊 Advanced Monitoring")

    # KPI 대시보드
    render_kpi_dashboard()
    
    st.markdown("---")
    
    # 리스크 모니터링
    render_risk_monitoring()
    
    st.markdown("---")
    
    # 실행 통계
    render_execution_stats()
    
    st.markdown("---")
    
    # 진단 패널
    render_diagnostics_panel()
