"""
PriceOracle - 통합 가격 데이터 소스
WebSocket 우선, REST 폴백, TTL 검증 포함
"""

import json
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal, Optional, Tuple

import requests


@dataclass
class PriceData:
    """가격 데이터 클래스"""
    price: Decimal
    timestamp: int  # epoch ms
    source: Literal['ws', 'rest', 'cache']
    symbol: str


class NoPriceData(Exception):
    """가격 데이터 없음 예외"""
    pass


class PriceOracle:
    """통합 가격 데이터 Oracle"""
    
    # TTL 상수 (초)
    WS_TTL = 5      # WebSocket 데이터 TTL
    REST_TTL = 30   # REST API 데이터 TTL
    CACHE_TTL = 60  # 캐시 데이터 TTL
    
    def __init__(self, testnet: bool = False):
        self.testnet = testnet
        self.base_url = "https://testnet.binance.vision" if testnet else "https://api.binance.com"
        
    def get_last_price(self, symbol: str) -> PriceData:
        """
        최신 가격 데이터 조회
        
        Returns:
            PriceData: (price, timestamp, source)
            
        Raises:
            NoPriceData: 가격 데이터를 사용할 수 없을 때
        """
        # 1. WebSocket 데이터 우선 (최신)
        try:
            ws_data = self._get_ws_price(symbol)
            if ws_data and self._is_fresh(ws_data.timestamp, self.WS_TTL):
                return ws_data
        except Exception:
            pass
            
        # 2. REST API 폴백
        try:
            rest_data = self._get_rest_price(symbol)
            if rest_data and self._is_fresh(rest_data.timestamp, self.REST_TTL):
                return rest_data
        except Exception:
            pass
            
        # 3. 캐시 데이터 (stale해도 사용)
        try:
            cache_data = self._get_cache_price(symbol)
            if cache_data:
                return cache_data
        except Exception:
            pass
            
        raise NoPriceData(f"No price data available for {symbol}")
    
    def get_1m_return(self, symbol: str) -> Tuple[Decimal, int]:
        """
        1분 수익률 계산 (UI와 동일한 바 데이터 사용)
        
        Returns:
            Tuple[Decimal, int]: (수익률 %, timestamp)
        """
        try:
            history_path = Path(f"shared_data/history/{symbol.lower()}_1m.jsonl")
            if not history_path.exists():
                return Decimal('0'), int(time.time() * 1000)
                
            # 최근 2개 캔들 읽기
            with open(history_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
            if len(lines) < 2:
                return Decimal('0'), int(time.time() * 1000)
                
            # 최근 2개 캔들 파싱
            current_candle = json.loads(lines[-1].strip())
            prev_candle = json.loads(lines[-2].strip())
            
            current_price = Decimal(str(current_candle.get('close', 0)))
            prev_price = Decimal(str(prev_candle.get('close', 0)))
            
            if prev_price == 0:
                return Decimal('0'), int(time.time() * 1000)
                
            # 수익률 계산
            return_pct = ((current_price - prev_price) / prev_price) * 100
            
            return return_pct, int(current_candle.get('timestamp', time.time() * 1000))
            
        except Exception as e:
            print(f"[PriceOracle] 1m return calculation failed for {symbol}: {e}")
            return Decimal('0'), int(time.time() * 1000)
    
    def _get_ws_price(self, symbol: str) -> Optional[PriceData]:
        """WebSocket 가격 데이터 조회"""
        try:
            # 심볼 정규화
            normalized_symbol = symbol.lower()
            
            # 스냅샷 파일 경로
            snapshot_path = Path(f"shared_data/snapshots/prices_{normalized_symbol}.json")
            if not snapshot_path.exists():
                return None
                
            with open(snapshot_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # 가격 추출 (다양한 필드명 지원)
            price_value = None
            if 'price' in data and data['price']:
                price_value = data['price']
            elif 'c' in data and data['c']:  # close price
                price_value = data['c']
            elif 'lastPrice' in data and data['lastPrice']:
                price_value = data['lastPrice']
                
            if not price_value:
                return None
                
            # Decimal 변환
            try:
                price = Decimal(str(price_value))
                if price <= 0:
                    return None
            except (InvalidOperation, ValueError):
                return None
                
            # 타임스탬프 추출
            timestamp = data.get('ts', data.get('timestamp', int(time.time() * 1000)))
            if isinstance(timestamp, float):
                timestamp = int(timestamp * 1000)
                
            return PriceData(
                price=price,
                timestamp=timestamp,
                source='ws',
                symbol=symbol
            )
            
        except Exception as e:
            print(f"[PriceOracle] WS price fetch failed for {symbol}: {e}")
            return None
    
    def _get_rest_price(self, symbol: str) -> Optional[PriceData]:
        """REST API 가격 데이터 조회"""
        try:
            url = f"{self.base_url}/api/v3/ticker/price"
            params = {'symbol': symbol.upper()}
            
            response = requests.get(url, params=params, timeout=5)
            response.raise_for_status()
            
            data = response.json()
            price_value = data.get('price')
            
            if not price_value:
                return None
                
            # Decimal 변환
            try:
                price = Decimal(str(price_value))
                if price <= 0:
                    return None
            except (InvalidOperation, ValueError):
                return None
                
            return PriceData(
                price=price,
                timestamp=int(time.time() * 1000),  # REST는 현재 시간
                source='rest',
                symbol=symbol
            )
            
        except Exception as e:
            print(f"[PriceOracle] REST price fetch failed for {symbol}: {e}")
            return None
    
    def _get_cache_price(self, symbol: str) -> Optional[PriceData]:
        """캐시 가격 데이터 조회 (stale 데이터도 허용)"""
        try:
            # 히스토리 파일에서 최신 캔들 사용
            history_path = Path(f"shared_data/history/{symbol.lower()}_1m.jsonl")
            if not history_path.exists():
                return None
                
            with open(history_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
            if not lines:
                return None
                
            # 최신 캔들 파싱
            latest_candle = json.loads(lines[-1].strip())
            price_value = latest_candle.get('close', 0)
            
            if not price_value:
                return None
                
            # Decimal 변환
            try:
                price = Decimal(str(price_value))
                if price <= 0:
                    return None
            except (InvalidOperation, ValueError):
                return None
                
            return PriceData(
                price=price,
                timestamp=int(latest_candle.get('timestamp', time.time() * 1000)),
                source='cache',
                symbol=symbol
            )
            
        except Exception as e:
            print(f"[PriceOracle] Cache price fetch failed for {symbol}: {e}")
            return None
    
    def _is_fresh(self, timestamp: int, ttl_seconds: int) -> bool:
        """데이터 신선도 검증"""
        current_time = int(time.time() * 1000)
        age_ms = current_time - timestamp
        age_seconds = age_ms / 1000
        
        return age_seconds <= ttl_seconds


# 전역 인스턴스
_price_oracle = None

def get_price_oracle(testnet: bool = False) -> PriceOracle:
    """PriceOracle 인스턴스 가져오기"""
    global _price_oracle
    if _price_oracle is None:
        _price_oracle = PriceOracle(testnet=testnet)
    return _price_oracle
