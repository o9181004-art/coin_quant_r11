"""
PositionOracle - 통합 포지션 데이터 소스
실제 거래소 포지션과 로컬 포지션 통합 관리
"""

import json
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, Literal, Optional, Tuple


@dataclass
class PositionData:
    """포지션 데이터 클래스"""
    side: Literal['LONG', 'SHORT', 'FLAT']
    entry: Optional[Decimal]  # None if FLAT
    qty: Decimal
    timestamp: int  # epoch ms
    source: Literal['exchange', 'local']
    symbol: str


class PositionOracle:
    """통합 포지션 데이터 Oracle"""
    
    # TTL 상수 (초)
    POS_TTL = 15  # 포지션 데이터 TTL
    
    def __init__(self, testnet: bool = False):
        self.testnet = testnet
        
    def get_position(self, symbol: str) -> PositionData:
        """
        포지션 데이터 조회
        
        Returns:
            PositionData: 포지션 정보
        """
        # 1. 로컬 포지션 파일 우선 조회
        try:
            local_pos = self._get_local_position(symbol)
            if local_pos and self._is_fresh(local_pos.timestamp, self.POS_TTL):
                return local_pos
        except Exception:
            pass
            
        # 2. 거래소 API 조회 (향후 구현)
        try:
            exchange_pos = self._get_exchange_position(symbol)
            if exchange_pos:
                return exchange_pos
        except Exception:
            pass
            
        # 3. 기본 FLAT 포지션 반환
        return PositionData(
            side='FLAT',
            entry=None,
            qty=Decimal('0'),
            timestamp=int(time.time() * 1000),
            source='local',
            symbol=symbol
        )
    
    def get_last_fill_price(self, symbol: str) -> Optional[Decimal]:
        """
        최근 체결가 조회 (UI 히스토리용)
        
        Returns:
            Optional[Decimal]: 최근 체결가 또는 None
        """
        try:
            trades_path = Path(f"shared_data/trades/{symbol.lower()}_trades.jsonl")
            if not trades_path.exists():
                return None
                
            with open(trades_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
            if not lines:
                return None
                
            # 최근 거래 파싱
            latest_trade = json.loads(lines[-1].strip())
            price_value = latest_trade.get('price', 0)
            
            if not price_value:
                return None
                
            # Decimal 변환
            try:
                return Decimal(str(price_value))
            except (InvalidOperation, ValueError):
                return None
                
        except Exception as e:
            print(f"[PositionOracle] Last fill price fetch failed for {symbol}: {e}")
            return None
    
    def _get_local_position(self, symbol: str) -> Optional[PositionData]:
        """로컬 포지션 파일 조회"""
        try:
            # 심볼 정규화
            normalized_symbol = symbol.lower()
            
            # 포지션 파일 경로들 시도
            position_paths = [
                Path(f"shared_data/positions/{normalized_symbol}_position.json"),
                Path(f"shared_data/positions/{symbol.upper()}_position.json"),
                Path(f"shared_data/{normalized_symbol}_position.json"),
            ]
            
            position_data = None
            for path in position_paths:
                if path.exists():
                    with open(path, 'r', encoding='utf-8') as f:
                        position_data = json.load(f)
                    break
                    
            if not position_data:
                return None
                
            # 포지션 데이터 파싱
            qty_value = position_data.get('qty', 0)
            avg_price_value = position_data.get('avg_price', 0)
            
            # Decimal 변환
            try:
                qty = Decimal(str(qty_value))
                avg_price = Decimal(str(avg_price_value)) if avg_price_value else None
            except (InvalidOperation, ValueError):
                return None
                
            # 포지션 사이드 결정
            if qty > 0:
                side = 'LONG'
                entry = avg_price
            elif qty < 0:
                side = 'SHORT'
                entry = avg_price
            else:
                side = 'FLAT'
                entry = None
                
            # 타임스탬프 추출
            timestamp = position_data.get('timestamp', position_data.get('last_update', int(time.time() * 1000)))
            if isinstance(timestamp, float):
                timestamp = int(timestamp * 1000)
                
            return PositionData(
                side=side,
                entry=entry,
                qty=qty,
                timestamp=timestamp,
                source='local',
                symbol=symbol
            )
            
        except Exception as e:
            print(f"[PositionOracle] Local position fetch failed for {symbol}: {e}")
            return None
    
    def _get_exchange_position(self, symbol: str) -> Optional[PositionData]:
        """거래소 API 포지션 조회 (향후 구현)"""
        # TODO: Binance API 연동
        # 현재는 로컬 포지션만 사용
        return None
    
    def _is_fresh(self, timestamp: int, ttl_seconds: int) -> bool:
        """데이터 신선도 검증"""
        current_time = int(time.time() * 1000)
        age_ms = current_time - timestamp
        age_seconds = age_ms / 1000
        
        return age_seconds <= ttl_seconds


# 전역 인스턴스
_position_oracle = None

def get_position_oracle(testnet: bool = False) -> PositionOracle:
    """PositionOracle 인스턴스 가져오기"""
    global _position_oracle
    if _position_oracle is None:
        _position_oracle = PositionOracle(testnet=testnet)
    return _position_oracle
