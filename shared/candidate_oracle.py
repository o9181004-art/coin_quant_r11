"""
TradeCandidateV1 - 표준화된 거래 후보 데이터 구조
ARES 엔진과 UI 간의 계약 정의
"""

import json
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Literal, Optional


@dataclass
class TradeCandidateV1:
    """표준화된 거래 후보 데이터 클래스"""
    
    # 기본 정보
    symbol: str
    side: Literal['BUY', 'SELL']
    
    # 가격 정보 (Decimal 사용)
    entry: Decimal
    target: Decimal
    stop: Decimal
    
    # 신뢰도
    raw_confidence: float  # 0.0 ~ 1.0
    net_confidence: float  # 비용 차감 후 신뢰도
    
    # 메타데이터
    snapshot_ts: int  # epoch ms
    trace_id: str    # 추적 ID
    regime: str      # 시장 레짐
    
    # 추가 정보
    size_quote: Decimal  # USDT 기준 포지션 크기
    reason: str         # 신호 발생 사유
    strategy_id: str    # 전략 ID
    
    # 유효성 검증 결과
    is_valid: bool = True
    validation_errors: list = None
    
    def __post_init__(self):
        """초기화 후 유효성 검증"""
        if self.validation_errors is None:
            self.validation_errors = []
            
        self._validate_candidate()
    
    def _validate_candidate(self):
        """후보 유효성 검증"""
        errors = []
        
        # 기본 검증
        if not self.symbol:
            errors.append("Symbol is required")
            
        if self.side not in ['BUY', 'SELL']:
            errors.append(f"Invalid side: {self.side}")
            
        # 가격 검증
        if self.entry <= 0:
            errors.append(f"Invalid entry price: {self.entry}")
            
        if self.target <= 0:
            errors.append(f"Invalid target price: {self.target}")
            
        if self.stop <= 0:
            errors.append(f"Invalid stop price: {self.stop}")
            
        # 가격 관계 검증
        if self.side == 'BUY':
            # BUY: stop < entry < target
            if not (self.stop < self.entry < self.target):
                errors.append(f"BUY price order invalid: stop({self.stop}) < entry({self.entry}) < target({self.target})")
        else:  # SELL
            # SELL: target < entry < stop
            if not (self.target < self.entry < self.stop):
                errors.append(f"SELL price order invalid: target({self.target}) < entry({self.entry}) < stop({self.stop})")
                
        # 신뢰도 검증 (0~100 범위로 수정)
        if not (0.0 <= self.raw_confidence <= 100.0):
            errors.append(f"Raw confidence out of range: {self.raw_confidence}")
            
        if not (0.0 <= self.net_confidence <= 100.0):
            errors.append(f"Net confidence out of range: {self.net_confidence}")
            
        # 타임스탬프 검증
        current_time = int(time.time() * 1000)
        if self.snapshot_ts > current_time:
            errors.append(f"Future timestamp: {self.snapshot_ts}")
            
        # 수량 검증
        if self.size_quote <= 0:
            errors.append(f"Invalid size quote: {self.size_quote}")
            
        self.validation_errors = errors
        self.is_valid = len(errors) == 0
        
        if not self.is_valid:
            print(f"[TradeCandidateV1] Validation failed for {self.symbol}: {errors}")
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            'symbol': self.symbol,
            'side': self.side,
            'entry': str(self.entry),
            'target': str(self.target),
            'stop': str(self.stop),
            'raw_confidence': self.raw_confidence,
            'net_confidence': self.net_confidence,
            'snapshot_ts': self.snapshot_ts,
            'trace_id': self.trace_id,
            'regime': self.regime,
            'size_quote': str(self.size_quote),
            'reason': self.reason,
            'strategy_id': self.strategy_id,
            'is_valid': self.is_valid,
            'validation_errors': self.validation_errors
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TradeCandidateV1':
        """딕셔너리에서 생성"""
        try:
            return cls(
                symbol=data['symbol'],
                side=data['side'],
                entry=Decimal(str(data['entry'])),
                target=Decimal(str(data['target'])),
                stop=Decimal(str(data['stop'])),
                raw_confidence=float(data['raw_confidence']),
                net_confidence=float(data['net_confidence']),
                snapshot_ts=int(data['snapshot_ts']),
                trace_id=data['trace_id'],
                regime=data['regime'],
                size_quote=Decimal(str(data['size_quote'])),
                reason=data['reason'],
                strategy_id=data['strategy_id']
            )
        except (KeyError, InvalidOperation, ValueError) as e:
            raise ValueError(f"Invalid TradeCandidateV1 data: {e}")
    
    def is_fresh(self, ttl_seconds: int = 20) -> bool:
        """후보 신선도 검증"""
        current_time = int(time.time() * 1000)
        age_ms = current_time - self.snapshot_ts
        age_seconds = age_ms / 1000
        
        return age_seconds <= ttl_seconds


class CandidateOracle:
    """거래 후보 데이터 Oracle"""
    
    # TTL 상수 (초)
    ARES_TTL = 20  # ARES 후보 TTL
    
    def __init__(self, testnet: bool = False):
        self.testnet = testnet
        
    def get_candidate(self, symbol: str) -> Optional[TradeCandidateV1]:
        """
        거래 후보 조회
        
        Returns:
            Optional[TradeCandidateV1]: 유효한 후보 또는 None
        """
        try:
            # ARES 데이터 파일 조회
            ares_path = Path(f"shared_data/ares/{symbol.lower()}.json")
            if not ares_path.exists():
                return None
                
            with open(ares_path, 'r', encoding='utf-8') as f:
                ares_data = json.load(f)
                
            # 신호 데이터 추출
            signals = ares_data.get('signals', [])
            if not signals:
                return None
                
            # 최신 신호 사용
            signal = signals[0]
            
            # TradeCandidateV1 변환
            candidate = self._convert_to_candidate(symbol, signal, ares_data)
            
            # 유효성 검증
            if not candidate.is_valid:
                return None
                
            # 신선도 검증
            if not candidate.is_fresh(self.ARES_TTL):
                return None
                
            return candidate
            
        except Exception as e:
            print(f"[CandidateOracle] Candidate fetch failed for {symbol}: {e}")
            return None
    
    def _convert_to_candidate(self, symbol: str, signal: Dict[str, Any], ares_data: Dict[str, Any]) -> TradeCandidateV1:
        """ARES 신호를 TradeCandidateV1으로 변환"""
        
        # 기본 정보
        action = signal.get('action', 'flat').upper()
        if action not in ['BUY', 'SELL']:
            action = 'BUY'  # 기본값
            
        # 가격 정보 (Decimal 변환)
        try:
            entry_price = Decimal(str(signal.get('entry_price', signal.get('price', 0))))
            target_price = Decimal(str(signal.get('tp', signal.get('price', 0))))
            stop_price = Decimal(str(signal.get('sl', signal.get('price', 0))))
            
            # 가격이 0이면 기본값 설정
            if entry_price <= 0:
                entry_price = Decimal('100')  # 기본값
            if target_price <= 0:
                target_price = entry_price * Decimal('1.02') if action == 'BUY' else entry_price * Decimal('0.98')
            if stop_price <= 0:
                stop_price = entry_price * Decimal('0.98') if action == 'BUY' else entry_price * Decimal('1.02')
                
        except (InvalidOperation, ValueError):
            # 변환 실패 시 기본값
            entry_price = Decimal('100')
            target_price = Decimal('102') if action == 'BUY' else Decimal('98')
            stop_price = Decimal('98') if action == 'BUY' else Decimal('102')
            
        # 신뢰도
        raw_confidence = float(signal.get('confidence', 0.5))
        net_confidence = raw_confidence  # 비용 차감은 향후 구현
        
        # 메타데이터
        snapshot_ts = int(signal.get('timestamp', time.time() * 1000))
        trace_id = f"{symbol}_{snapshot_ts}"
        regime = ares_data.get('meta', {}).get('regime', 'unknown')
        
        # 수량
        size_quote = Decimal(str(signal.get('size', 10)))  # 기본 10 USDT
        
        # 기타 정보
        reason = signal.get('reason', 'ARES signal')
        strategy_id = signal.get('strategy_id', 'ARES')
        
        return TradeCandidateV1(
            symbol=symbol,
            side=action,
            entry=entry_price,
            target=target_price,
            stop=stop_price,
            raw_confidence=raw_confidence,
            net_confidence=net_confidence,
            snapshot_ts=snapshot_ts,
            trace_id=trace_id,
            regime=regime,
            size_quote=size_quote,
            reason=reason,
            strategy_id=strategy_id
        )


# 전역 인스턴스
_candidate_oracle = None

def get_candidate_oracle(testnet: bool = False) -> CandidateOracle:
    """CandidateOracle 인스턴스 가져오기"""
    global _candidate_oracle
    if _candidate_oracle is None:
        _candidate_oracle = CandidateOracle(testnet=testnet)
    return _candidate_oracle
