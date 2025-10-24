"""
심볼 케이스 표준화 유틸리티
대문자/소문자 혼용 문제 해결을 위한 일관된 심볼 처리
"""

import logging
import re
from typing import Any, Dict, List, Set, Union

logger = logging.getLogger(__name__)

# 중복 경고 방지를 위한 캐시
_warning_cache: Set[str] = set()


def normalize_symbol(symbol: Union[str, None]) -> str:
    """
    심볼을 소문자로 표준화 (강화된 정규화 규칙 적용)

    Args:
        symbol: 원본 심볼 (대문자/소문자/혼합)

    Returns:
        str: 소문자로 표준화된 심볼

    Examples:
        normalize_symbol("BTCUSDT") -> "btcusdt"
        normalize_symbol("ethusdt") -> "ethusdt"
        normalize_symbol("  SolUsDt  ") -> "solusdt"
    """
    if not symbol:
        return ""

    # 원본 심볼 보존 (로그용)
    raw_symbol = str(symbol)

    # 강화된 정규화 규칙 적용
    # 1. 양끝 공백 제거
    normalized = raw_symbol.strip()

    # 2. 유니코드 정규화 (NFKC)
    import unicodedata

    normalized = unicodedata.normalize("NFKC", normalized)

    # 3. 대소문자 통일 (소문자)
    normalized = normalized.lower()

    # 4. 허용 문자만 유지 ([a-z0-9] 외 문자 제거)
    import re

    normalized = re.sub(r"[^a-z0-9]", "", normalized)

    # 5. 거래소 심볼 기준 표기로 고정 (연속 소문자)
    # 이미 소문자이므로 추가 처리 불필요

    # 유효성 검사 (최소 3자)
    if len(normalized) < 3:
        logger.warning(f"심볼이 너무 짧음: {raw_symbol} -> {normalized}")
        return normalized

    # 실제 불일치가 있을 때만 경고 로그 출력 (중복 방지)
    if raw_symbol != normalized:
        warning_key = f"{raw_symbol}->{normalized}"
        if warning_key not in _warning_cache:
            logger.warning(f"심볼 패턴 불일치: {raw_symbol} -> {normalized}")
            _warning_cache.add(warning_key)

    return normalized


def clear_warning_cache():
    """경고 캐시 초기화 (테스트 또는 세션 재시작 시 사용)"""
    global _warning_cache
    _warning_cache.clear()


def get_warning_cache_size() -> int:
    """현재 경고 캐시 크기 반환"""
    return len(_warning_cache)


def normalize_symbol_list(symbols: List[str]) -> List[str]:
    """
    심볼 리스트를 일괄 표준화

    Args:
        symbols: 원본 심볼 리스트

    Returns:
        List[str]: 표준화된 심볼 리스트
    """
    if not symbols:
        return []

    normalized = []
    for symbol in symbols:
        norm_symbol = normalize_symbol(symbol)
        if norm_symbol and norm_symbol not in normalized:
            normalized.append(norm_symbol)

    return normalized


def display_symbol(symbol: str) -> str:
    """
    표시용 심볼 (대문자)

    Args:
        symbol: 표준화된 심볼 (소문자)

    Returns:
        str: 표시용 심볼 (대문자)

    Examples:
        display_symbol("btcusdt") -> "BTCUSDT"
    """
    if not symbol:
        return ""

    return str(symbol).strip().upper()


def validate_symbol(symbol: str) -> bool:
    """
    심볼 유효성 검사

    Args:
        symbol: 검사할 심볼

    Returns:
        bool: 유효성 여부
    """
    if not symbol:
        return False

    # 기본 패턴 검사
    pattern = r"^[a-zA-Z]{3,}USDT$"
    return bool(re.match(pattern, symbol.strip()))


def extract_symbols_from_text(text: str) -> List[str]:
    """
    텍스트에서 심볼 추출 및 표준화

    Args:
        text: 분석할 텍스트

    Returns:
        List[str]: 추출된 표준화된 심볼 리스트
    """
    # 대문자 심볼 패턴 매칭 (한글 텍스트에서도 작동하도록 수정)
    pattern = r"[A-Z]{3,}USDT"
    matches = re.findall(pattern, text)

    # 표준화
    normalized = []
    for match in matches:
        norm_symbol = normalize_symbol(match)
        if norm_symbol and norm_symbol not in normalized:
            normalized.append(norm_symbol)

    return normalized


def create_symbol_path(symbol: str, base_path: str = "shared_data") -> str:
    """
    심볼 기반 파일 경로 생성

    Args:
        symbol: 심볼 (자동 표준화됨)
        base_path: 기본 경로

    Returns:
        str: 표준화된 파일 경로
    """
    normalized_symbol = normalize_symbol(symbol)
    return f"{base_path}/history/{normalized_symbol}_history.jsonl"


def create_symbol_key(symbol: str, prefix: str = "") -> str:
    """
    심볼 기반 키 생성 (Redis, 캐시 등)

    Args:
        symbol: 심볼 (자동 표준화됨)
        prefix: 키 접두사

    Returns:
        str: 표준화된 키
    """
    normalized_symbol = normalize_symbol(symbol)
    if prefix:
        return f"{prefix}:{normalized_symbol}"
    return normalized_symbol


def normalize_symbol_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    딕셔너리의 키를 심볼 표준화

    Args:
        data: 원본 딕셔너리

    Returns:
        Dict[str, Any]: 키가 표준화된 딕셔너리
    """
    normalized = {}

    for key, value in data.items():
        # 키가 심볼인지 확인 (USDT로 끝나는지)
        if isinstance(key, str) and key.upper().endswith("USDT"):
            normalized_key = normalize_symbol(key)
        else:
            normalized_key = key

        normalized[normalized_key] = value

    return normalized


# 단위 테스트
if __name__ == "__main__":
    # 테스트 1: 기본 표준화
    assert normalize_symbol("BTCUSDT") == "btcusdt"
    assert normalize_symbol("ethusdt") == "ethusdt"
    assert normalize_symbol("  SolUsDt  ") == "solusdt"
    assert normalize_symbol("") == ""
    assert normalize_symbol(None) == ""

    # 테스트 1-1: 강화된 정규화 규칙 테스트
    assert normalize_symbol("  BTC-USDT  ") == "btcusdt"  # 공백 제거 + 특수문자 제거
    assert normalize_symbol("ETH/USDT") == "ethusdt"  # 슬래시 제거
    assert normalize_symbol("DOGE.USDT") == "dogeusdt"  # 점 제거

    # 테스트 2: 리스트 표준화
    symbols = ["BTCUSDT", "ethusdt", "SOLUSDT", "btcusdt"]
    normalized = normalize_symbol_list(symbols)
    assert normalized == ["btcusdt", "ethusdt", "solusdt"]

    # 테스트 3: 표시용 변환
    assert display_symbol("btcusdt") == "BTCUSDT"
    assert display_symbol("") == ""

    # 테스트 4: 유효성 검사
    assert validate_symbol("BTCUSDT") == True
    assert validate_symbol("btcusdt") == False  # 소문자는 False
    assert validate_symbol("BTC") == False  # USDT 없음
    assert validate_symbol("") == False

    # 테스트 5: 텍스트에서 추출
    text = "BTCUSDT 가격이 상승하고 ETHUSDT도 좋은 상태입니다."
    extracted = extract_symbols_from_text(text)
    assert extracted == ["btcusdt", "ethusdt"]

    # 테스트 6: 경로 생성
    path = create_symbol_path("BTCUSDT")
    assert path == "shared_data/history/btcusdt_history.jsonl"

    # 테스트 7: 키 생성
    key = create_symbol_key("BTCUSDT", "cache")
    assert key == "cache:btcusdt"

    # 테스트 8: 딕셔너리 표준화
    data = {"BTCUSDT": 50000, "ethusdt": 3000, "other": "value"}
    normalized_data = normalize_symbol_dict(data)
    assert normalized_data == {"btcusdt": 50000, "ethusdt": 3000, "other": "value"}

    # 테스트 9: 경고 캐시 기능
    clear_warning_cache()
    assert get_warning_cache_size() == 0

    # 중복 호출 시 경고가 한 번만 출력되는지 확인
    normalize_symbol("BTCUSDT")  # 첫 번째 호출
    normalize_symbol("BTCUSDT")  # 두 번째 호출 (같은 변환)
    assert get_warning_cache_size() == 1  # 캐시에 하나만 저장됨

    print("✅ 모든 심볼 표준화 테스트 통과")
