#!/usr/bin/env python3
"""
모의 데이터 생성 스크립트
WebSocket 연결이 실패할 때 대시보드가 정상적으로 작동하도록 모의 데이터를 생성합니다.
"""

import json
import time
import os
from pathlib import Path

def create_mock_data():
    """모의 데이터 생성"""
    
    # 기본 디렉토리 생성
    shared_data = Path("shared_data")
    shared_data.mkdir(exist_ok=True)
    
    snapshots_dir = shared_data / "snapshots"
    snapshots_dir.mkdir(exist_ok=True)
    
    signals_dir = shared_data / "signals"
    signals_dir.mkdir(exist_ok=True)
    
    health_dir = shared_data / "health"
    health_dir.mkdir(exist_ok=True)
    
    # 모의 가격 데이터 생성
    symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "EURUSDT", "DEGOUSDT", "TAOUSDT", "KDAUSDT", "FDUSDUSDT"]
    
    base_prices = {
        "BTCUSDT": 65000.0,
        "ETHUSDT": 3200.0,
        "ADAUSDT": 0.45,
        "SOLUSDT": 180.0,
        "XRPUSDT": 0.52,
        "DOGEUSDT": 0.08,
        "EURUSDT": 1.0,
        "DEGOUSDT": 0.00012,
        "TAOUSDT": 1.0,
        "KDAUSDT": 0.85,
        "FDUSDUSDT": 1.0
    }
    
    current_time = time.time()
    
    # 각 심볼에 대한 모의 가격 데이터 생성
    for symbol in symbols:
        base_price = base_prices.get(symbol, 1.0)
        
        # 약간의 변동성을 추가
        import random
        variation = random.uniform(0.95, 1.05)
        current_price = base_price * variation
        
        price_data = {
            "symbol": symbol,
            "price": round(current_price, 4),
            "change": round((variation - 1) * 100, 2),
            "volume": random.randint(1000000, 10000000),
            "timestamp": current_time,
            "source": "mock_data"
        }
        
        # 가격 스냅샷 파일 생성
        price_file = snapshots_dir / f"prices_{symbol.lower()}.json"
        with open(price_file, 'w', encoding='utf-8') as f:
            json.dump(price_data, f, indent=2, ensure_ascii=False)
        
        # ARES 신호 생성
        signal_data = {
            "symbol": symbol,
            "side": "BUY" if variation > 1.02 else "SELL" if variation < 0.98 else "HOLD",
            "confidence": round(random.uniform(0.6, 0.9), 2),
            "price": round(current_price, 4),
            "timestamp": current_time,
            "strategy": "mock_signal"
        }
        
        signal_file = signals_dir / f"ares_{symbol.lower()}.json"
        with open(signal_file, 'w', encoding='utf-8') as f:
            json.dump(signal_data, f, indent=2, ensure_ascii=False)
    
    # Feeder 헬스 데이터 생성
    feeder_health = {
        "status": "GREEN",
        "last_update_ts": current_time,
        "updated_within_sec": 0,
        "ws_connected": True,
        "symbol_count": len(symbols),
        "source": "mock_data"
    }
    
    feeder_health_file = health_dir / "feeder.json"
    with open(feeder_health_file, 'w', encoding='utf-8') as f:
        json.dump(feeder_health, f, indent=2, ensure_ascii=False)
    
    # ARES 헬스 데이터 생성
    ares_health = {
        "status": "GREEN",
        "last_update_ts": current_time,
        "updated_within_sec": 0,
        "signal_count": len(symbols),
        "feeder_health_ok": True,
        "source": "mock_data"
    }
    
    ares_health_file = health_dir / "ares.json"
    with open(ares_health_file, 'w', encoding='utf-8') as f:
        json.dump(ares_health, f, indent=2, ensure_ascii=False)
    
    # Trader 헬스 데이터 생성
    trader_health = {
        "status": "GREEN",
        "last_update_ts": current_time,
        "updated_within_sec": 0,
        "ares_health_ok": True,
        "source": "mock_data"
    }
    
    trader_health_file = health_dir / "trader.json"
    with open(trader_health_file, 'w', encoding='utf-8') as f:
        json.dump(trader_health, f, indent=2, ensure_ascii=False)
    
    # 포지션 데이터 생성
    positions_data = {
        "positions": [],
        "total_value": 100000.0,
        "available_balance": 50000.0,
        "timestamp": current_time,
        "source": "mock_data"
    }
    
    positions_file = shared_data / "positions_snapshot.json"
    with open(positions_file, 'w', encoding='utf-8') as f:
        json.dump(positions_data, f, indent=2, ensure_ascii=False)
    
    # 계좌 정보 생성
    account_data = {
        "balance": 100000.0,
        "available_balance": 50000.0,
        "currency": "USDT",
        "timestamp": current_time,
        "source": "mock_data"
    }
    
    account_file = shared_data / "account_snapshot.json"
    with open(account_file, 'w', encoding='utf-8') as f:
        json.dump(account_data, f, indent=2, ensure_ascii=False)
    
    print("✅ 모의 데이터 생성 완료!")
    print(f"📁 생성된 파일들:")
    print(f"   - 가격 데이터: {len(symbols)}개 심볼")
    print(f"   - 신호 데이터: {len(symbols)}개 심볼")
    print(f"   - 헬스 데이터: Feeder, ARES, Trader")
    print(f"   - 포지션 데이터: positions_snapshot.json")
    print(f"   - 계좌 데이터: account_snapshot.json")

if __name__ == "__main__":
    create_mock_data()
