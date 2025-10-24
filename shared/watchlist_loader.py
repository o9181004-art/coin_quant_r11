#!/usr/bin/env python3
"""
워치리스트 로더 및 관리
멀티심볼 실운영을 위한 코인 워치리스트 관리
"""

import json
import logging
import os
from typing import List


class WatchlistLoader:
    """워치리스트 로더 및 관리자"""

    def __init__(
        self,
        watchlist_path: str = "shared_data/coin_watchlist.json",
        max_symbols: int = 40,
    ):
        self.watchlist_path = watchlist_path
        self.max_symbols = max_symbols
        self.logger = logging.getLogger(__name__)

    def load_watchlist(self) -> List[str]:
        """워치리스트 로드 (폴백 포함)"""
        try:
            if not os.path.exists(self.watchlist_path):
                self.logger.warning(f"워치리스트 파일이 없음: {self.watchlist_path}")
                return self._create_default_watchlist()

            with open(self.watchlist_path, "r", encoding="utf-8") as f:
                symbols = json.load(f)

            # 유효성 검증
            if not isinstance(symbols, list):
                self.logger.error("워치리스트가 배열이 아님")
                return self._create_default_watchlist()

            # 심볼 정규화 및 검증
            normalized_symbols = []
            for symbol in symbols:
                if isinstance(symbol, str):
                    normalized = symbol.lower().strip()
                    if normalized and normalized not in normalized_symbols:
                        normalized_symbols.append(normalized)

            if not normalized_symbols:
                self.logger.error("유효한 심볼이 없음")
                return self._create_default_watchlist()

            # 최대 심볼 수 제한
            if len(normalized_symbols) > self.max_symbols:
                self.logger.warning(
                    f"심볼 수가 최대 한도({self.max_symbols}) 초과, 처음 {self.max_symbols}개만 사용"
                )
                normalized_symbols = normalized_symbols[: self.max_symbols]

            self.logger.info(f"워치리스트 로드 완료: {len(normalized_symbols)}개 심볼")
            return normalized_symbols

        except Exception as e:
            self.logger.error(f"워치리스트 로드 실패: {e}")
            return self._create_default_watchlist()

    def _create_default_watchlist(self) -> List[str]:
        """기본 워치리스트 생성"""
        default_symbols = ["btcusdt"]
        self.logger.warning(f"기본 워치리스트 사용: {default_symbols}")

        # 기본 워치리스트 파일 생성
        try:
            os.makedirs(os.path.dirname(self.watchlist_path), exist_ok=True)
            with open(self.watchlist_path, "w", encoding="utf-8") as f:
                json.dump(default_symbols, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"기본 워치리스트 파일 생성 실패: {e}")

        return default_symbols

    def save_watchlist(self, symbols: List[str]) -> bool:
        """워치리스트 저장"""
        try:
            # 심볼 정규화
            normalized_symbols = []
            for symbol in symbols:
                if isinstance(symbol, str):
                    normalized = symbol.lower().strip()
                    if normalized and normalized not in normalized_symbols:
                        normalized_symbols.append(normalized)

            # 최대 심볼 수 제한
            if len(normalized_symbols) > self.max_symbols:
                self.logger.warning(f"심볼 수가 최대 한도({self.max_symbols}) 초과")
                return False

            # 파일 저장
            os.makedirs(os.path.dirname(self.watchlist_path), exist_ok=True)
            with open(self.watchlist_path, "w", encoding="utf-8") as f:
                json.dump(normalized_symbols, f, indent=2, ensure_ascii=False)

            self.logger.info(f"워치리스트 저장 완료: {len(normalized_symbols)}개 심볼")
            return True

        except Exception as e:
            self.logger.error(f"워치리스트 저장 실패: {e}")
            return False

    def add_symbol(self, symbol: str) -> bool:
        """심볼 추가"""
        current_symbols = self.load_watchlist()
        normalized = symbol.lower().strip()

        if normalized in current_symbols:
            self.logger.warning(f"심볼이 이미 존재함: {normalized}")
            return False

        if len(current_symbols) >= self.max_symbols:
            self.logger.error(f"최대 심볼 수({self.max_symbols}) 초과")
            return False

        current_symbols.append(normalized)
        return self.save_watchlist(current_symbols)

    def remove_symbol(self, symbol: str) -> bool:
        """심볼 제거"""
        current_symbols = self.load_watchlist()
        normalized = symbol.lower().strip()

        if normalized not in current_symbols:
            self.logger.warning(f"심볼이 존재하지 않음: {normalized}")
            return False

        current_symbols.remove(normalized)
        return self.save_watchlist(current_symbols)

    def get_symbol_count(self) -> int:
        """현재 심볼 수 반환"""
        return len(self.load_watchlist())

    def is_symbol_valid(self, symbol: str) -> bool:
        """심볼 유효성 검증"""
        normalized = symbol.lower().strip()
        return (
            isinstance(symbol, str)
            and len(normalized) >= 6  # 최소 길이 (예: btcusdt)
            and normalized.endswith("usdt")  # USDT 페어만 허용
            and normalized.isalnum()
        )


if __name__ == "__main__":
    # 테스트
    logging.basicConfig(level=logging.INFO)
    loader = WatchlistLoader()

    print("=== 워치리스트 로더 테스트 ===")
    symbols = loader.load_watchlist()
    print(f"로드된 심볼: {symbols}")
    print(f"심볼 수: {loader.get_symbol_count()}")

    # 심볼 추가 테스트
    if loader.add_symbol("ethusdt"):
        print("ETHUSDT 추가 성공")

    # 최종 상태 확인
    final_symbols = loader.load_watchlist()
    print(f"최종 심볼: {final_symbols}")
