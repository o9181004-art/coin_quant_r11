"""
잔고 표시 UI 모듈
"""

import json
import time
from pathlib import Path

import streamlit as st


def get_real_balance():
    """실제 잔고 조회 함수 (5xx Resilience)"""
    try:
        def fetch_balances():
            try:
                # shared_data 디렉토리에서 잔고 데이터 로드
                balance_file = Path("shared_data/balance_snapshot.json")
                if balance_file.exists():
                    with open(balance_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        return data.get("balances", {})
            except Exception as e:
                print(f"잔고 파일 로드 실패: {e}")
            
            # 기본값 반환
            default_balances = {"USDT": 0.0, "BTC": 0.0, "ETH": 0.0}
            return default_balances

        return fetch_balances()
    except Exception as e:
        print(f"잔고 조회 실패: {e}")
        return {"USDT": 0.0, "BTC": 0.0, "ETH": 0.0}

def update_balance_display():
    """잔고 표시 업데이트"""
    balance_data = get_real_balance()
    
    if balance_data:
        st.subheader("💰 계좌 잔고")
        
        # USDT 잔고 강조 표시
        usdt_balance = balance_data.get("USDT", 0.0)
        st.metric(
            label="USDT 잔고",
            value=f"${usdt_balance:,.2f}",
            delta=None
        )
        
        # 기타 코인 잔고
        other_coins = {k: v for k, v in balance_data.items() if k != "USDT" and v > 0}
        if other_coins:
            st.markdown("**기타 보유 코인:**")
            for coin, balance in other_coins.items():
                st.write(f"• {coin}: {balance:.6f}")
    else:
        st.warning("잔고 정보를 불러올 수 없습니다.")

def render_balance_section():
    """잔고 섹션 렌더링"""
    update_balance_display()
