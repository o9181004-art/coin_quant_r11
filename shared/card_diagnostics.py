"""
Symbol Cards 진단 도구
데이터 불일치 문제 모니터링 및 디버깅
"""

import json
import time
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

from shared.candidate_oracle import get_candidate_oracle
from shared.position_oracle import get_position_oracle
from shared.price_oracle import NoPriceData, get_price_oracle


@dataclass
class CardDiagnostic:
    """심볼 카드 진단 결과"""
    symbol: str
    timestamp: int
    verdict: str  # OK, STALE_FEED, STALE_POS, STALE_ARES, NO_DATA, S_ERR
    
    # 가격 데이터
    price_value: Optional[Decimal]
    price_ts: Optional[int]
    price_source: Optional[str]
    price_age: float
    
    # 포지션 데이터
    position_side: str
    position_entry: Optional[Decimal]
    position_qty: Decimal
    position_ts: Optional[int]
    position_source: str
    position_age: float
    
    # 후보 데이터
    candidate_entry: Optional[Decimal]
    candidate_target: Optional[Decimal]
    candidate_stop: Optional[Decimal]
    candidate_ts: Optional[int]
    candidate_age: float
    candidate_valid: bool
    
    # 오류 정보
    errors: List[str]
    warnings: List[str]


class CardDiagnostics:
    """심볼 카드 진단 시스템"""
    
    def __init__(self, testnet: bool = False):
        self.testnet = testnet
        self.price_oracle = get_price_oracle(testnet=testnet)
        self.position_oracle = get_position_oracle(testnet=testnet)
        self.candidate_oracle = get_candidate_oracle(testnet=testnet)
        
        # 진단 결과 저장 디렉토리
        self.diag_dir = Path("shared_data/diag")
        self.diag_dir.mkdir(exist_ok=True)
        
    def diagnose_symbol(self, symbol: str) -> CardDiagnostic:
        """심볼 카드 진단 실행"""
        current_time = int(time.time() * 1000)
        errors = []
        warnings = []
        
        # 가격 데이터 진단
        try:
            price_data = self.price_oracle.get_last_price(symbol)
            price_value = price_data.price
            price_ts = price_data.timestamp
            price_source = price_data.source
            price_age = (current_time - price_ts) / 1000
        except NoPriceData:
            price_value = None
            price_ts = None
            price_source = None
            price_age = 999
            errors.append("NO_PRICE_DATA")
        except Exception as e:
            price_value = None
            price_ts = None
            price_source = None
            price_age = 999
            errors.append(f"PRICE_ERROR: {str(e)}")
            
        # 포지션 데이터 진단
        try:
            position_data = self.position_oracle.get_position(symbol)
            position_side = position_data.side
            position_entry = position_data.entry
            position_qty = position_data.qty
            position_ts = position_data.timestamp
            position_source = position_data.source
            position_age = (current_time - position_ts) / 1000
        except Exception as e:
            position_side = "FLAT"
            position_entry = None
            position_qty = Decimal('0')
            position_ts = None
            position_source = "error"
            position_age = 999
            errors.append(f"POSITION_ERROR: {str(e)}")
            
        # 후보 데이터 진단
        try:
            candidate = self.candidate_oracle.get_candidate(symbol)
            if candidate:
                candidate_entry = candidate.entry
                candidate_target = candidate.target
                candidate_stop = candidate.stop
                candidate_ts = candidate.snapshot_ts
                candidate_age = (current_time - candidate_ts) / 1000
                candidate_valid = candidate.is_valid
                
                # 후보 유효성 검증
                if not candidate_valid:
                    errors.extend(candidate.validation_errors)
                    
                # 가격 관계 검증
                if candidate_valid:
                    if candidate.side == 'BUY':
                        if not (candidate.stop < candidate.entry < candidate.target):
                            errors.append(f"BUY_PRICE_ORDER_INVALID: stop({candidate.stop}) < entry({candidate.entry}) < target({candidate.target})")
                    else:  # SELL
                        if not (candidate.target < candidate.entry < candidate.stop):
                            errors.append(f"SELL_PRICE_ORDER_INVALID: target({candidate.target}) < entry({candidate.entry}) < stop({candidate.stop})")
            else:
                candidate_entry = None
                candidate_target = None
                candidate_stop = None
                candidate_ts = None
                candidate_age = 999
                candidate_valid = False
                warnings.append("NO_CANDIDATE")
        except Exception as e:
            candidate_entry = None
            candidate_target = None
            candidate_stop = None
            candidate_ts = None
            candidate_age = 999
            candidate_valid = False
            errors.append(f"CANDIDATE_ERROR: {str(e)}")
            
        # 신선도 검증
        if price_age > 5:  # WS_TTL 초과
            warnings.append("STALE_FEED")
        if position_age > 15:  # POS_TTL 초과
            warnings.append("STALE_POS")
        if candidate_age > 20:  # ARES_TTL 초과
            warnings.append("STALE_ARES")
            
        # 진단 결과 결정
        if errors:
            if "NO_PRICE_DATA" in errors:
                verdict = "NO_DATA"
            elif any("STALE" in w for w in warnings):
                verdict = "STALE_FEED" if "STALE_FEED" in warnings else "STALE_POS" if "STALE_POS" in warnings else "STALE_ARES"
            else:
                verdict = "S_ERR"
        elif warnings:
            verdict = warnings[0]  # 첫 번째 경고를 verdict로 사용
        else:
            verdict = "OK"
            
        return CardDiagnostic(
            symbol=symbol,
            timestamp=current_time,
            verdict=verdict,
            price_value=price_value,
            price_ts=price_ts,
            price_source=price_source,
            price_age=price_age,
            position_side=position_side,
            position_entry=position_entry,
            position_qty=position_qty,
            position_ts=position_ts,
            position_source=position_source,
            position_age=position_age,
            candidate_entry=candidate_entry,
            candidate_target=candidate_target,
            candidate_stop=candidate_stop,
            candidate_ts=candidate_ts,
            candidate_age=candidate_age,
            candidate_valid=candidate_valid,
            errors=errors,
            warnings=warnings
        )
    
    def diagnose_watchlist(self, watchlist: List[str]) -> List[CardDiagnostic]:
        """워치리스트 전체 진단"""
        diagnostics = []
        for symbol in watchlist:
            try:
                diag = self.diagnose_symbol(symbol)
                diagnostics.append(diag)
            except Exception as e:
                print(f"[CardDiagnostics] 진단 실패 {symbol}: {e}")
                continue
        return diagnostics
    
    def save_diagnostics(self, diagnostics: List[CardDiagnostic], filename: str = "cards.ndjson"):
        """진단 결과 저장 (NDJSON 형식)"""
        try:
            diag_file = self.diag_dir / filename
            
            # 기존 파일이 있으면 최근 50개만 유지
            if diag_file.exists():
                with open(diag_file, 'r', encoding='utf-8') as f:
                    existing_lines = f.readlines()
                
                # 최근 50개만 유지
                if len(existing_lines) > 50:
                    existing_lines = existing_lines[-50:]
                    
                with open(diag_file, 'w', encoding='utf-8') as f:
                    f.writelines(existing_lines)
            
            # 새 진단 결과 추가
            with open(diag_file, 'a', encoding='utf-8') as f:
                for diag in diagnostics:
                    # Decimal을 문자열로 변환
                    diag_dict = asdict(diag)
                    for key, value in diag_dict.items():
                        if isinstance(value, Decimal):
                            diag_dict[key] = str(value)
                    
                    f.write(json.dumps(diag_dict, ensure_ascii=False) + '\n')
                    
        except Exception as e:
            print(f"[CardDiagnostics] 진단 결과 저장 실패: {e}")
    
    def generate_summary_report(self, diagnostics: List[CardDiagnostic]) -> str:
        """진단 결과 요약 보고서 생성"""
        total_symbols = len(diagnostics)
        verdict_counts = {}
        
        for diag in diagnostics:
            verdict = diag.verdict
            verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1
            
        report_lines = [
            f"=== Symbol Cards 진단 보고서 ===",
            f"진단 시간: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"총 심볼 수: {total_symbols}",
            f"",
            f"=== 진단 결과 ===",
        ]
        
        for verdict, count in sorted(verdict_counts.items()):
            percentage = (count / total_symbols) * 100
            report_lines.append(f"{verdict}: {count}개 ({percentage:.1f}%)")
            
        report_lines.extend([
            f"",
            f"=== 상세 진단 ===",
        ])
        
        for diag in diagnostics:
            if diag.verdict != "OK":
                report_lines.append(f"{diag.symbol}: {diag.verdict}")
                if diag.errors:
                    report_lines.append(f"  오류: {', '.join(diag.errors)}")
                if diag.warnings:
                    report_lines.append(f"  경고: {', '.join(diag.warnings)}")
                    
        return '\n'.join(report_lines)


# 전역 인스턴스
_diagnostics = None

def get_diagnostics(testnet: bool = False) -> CardDiagnostics:
    """CardDiagnostics 인스턴스 가져오기"""
    global _diagnostics
    if _diagnostics is None:
        _diagnostics = CardDiagnostics(testnet=testnet)
    return _diagnostics
