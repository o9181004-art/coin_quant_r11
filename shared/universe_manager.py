"""
자동 유니버스 관리 시스템
Top-N 코인 자동 선택 및 관리
"""

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import requests


@dataclass
class UniverseConfig:
    """유니버스 설정"""

    top_n: int = 40
    quote: str = "USDT"
    refresh_minutes: int = 10
    min_volume_24h: float = 1000000.0  # 최소 24시간 거래량 (USDT)
    min_price: float = 0.0001  # 최소 가격
    max_price: float = 1000000.0  # 최대 가격
    exclude_stablecoins: bool = True
    exclude_leveraged: bool = True


class AutoUniverseManager:
    """자동 유니버스 관리자"""

    def __init__(self, config_path: str = "config.env"):
        self.config = self._load_config(config_path)
        self.universe_config = UniverseConfig(
            top_n=int(os.getenv("UNIVERSE_TOP_N", "40")),
            quote=os.getenv("FEEDER_QUOTE", "USDT"),
            refresh_minutes=int(os.getenv("UNIVERSE_REFRESH_MIN", "10")),
        )

        self.watchlist_path = Path("shared_data/coin_watchlist.json")
        self.universe_cache_path = Path("shared_data/universe_cache.json")
        self.last_refresh_time = 0

        # 안정적인 코인 목록 (항상 포함)
        self.stable_coins = ["BTCUSDT", "ETHUSDT", "ADAUSDT", "SOLUSDT", "DOTUSDT"]

    def _load_config(self, config_path: str) -> Dict:
        """설정 로드"""
        config = {}
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        config[key.strip()] = value.strip()
        return config

    def _fetch_binance_symbols(self) -> List[Dict]:
        """Binance에서 심볼 정보 가져오기"""
        try:
            # 테스트넷/메인넷 URL 결정
            base_url = (
                "https://testnet.binance.vision"
                if os.getenv("BINANCE_USE_TESTNET", "true").lower() == "true"
                else "https://api.binance.com"
            )
            url = f"{base_url}/api/v3/exchangeInfo"

            response = requests.get(url, timeout=10)
            response.raise_for_status()

            data = response.json()
            return data.get("symbols", [])

        except Exception as e:
            print(f"Binance API 호출 실패: {e}")
            return []

    def _fetch_24h_ticker(self) -> List[Dict]:
        """24시간 티커 정보 가져오기"""
        try:
            base_url = (
                "https://testnet.binance.vision"
                if os.getenv("BINANCE_USE_TESTNET", "true").lower() == "true"
                else "https://api.binance.com"
            )
            url = f"{base_url}/api/v3/ticker/24hr"

            response = requests.get(url, timeout=10)
            response.raise_for_status()

            data = response.json()
            return data

        except Exception as e:
            print(f"24h 티커 API 호출 실패: {e}")
            return []

    def _filter_symbols(self, symbols: List[Dict], tickers: List[Dict]) -> List[Dict]:
        """심볼 필터링"""
        filtered = []

        # 티커 데이터를 딕셔너리로 변환
        ticker_dict = {t["symbol"]: t for t in tickers}

        for symbol in symbols:
            symbol_name = symbol["symbol"]

            # 기본 필터링
            if not symbol_name.endswith(self.universe_config.quote):
                continue

            if symbol["status"] != "TRADING":
                continue

            # 레버리지 토큰 제외
            if self.universe_config.exclude_leveraged and any(
                x in symbol_name for x in ["UP", "DOWN", "BULL", "BEAR"]
            ):
                continue

            # 스테이블코인 제외
            if self.universe_config.exclude_stablecoins and any(
                x in symbol_name for x in ["USDC", "BUSD", "TUSD", "USDP"]
            ):
                continue

            # 티커 데이터 확인
            ticker = ticker_dict.get(symbol_name)
            if not ticker:
                continue

            # 거래량 필터링
            volume_24h = float(ticker.get("quoteVolume", 0))
            if volume_24h < self.universe_config.min_volume_24h:
                continue

            # 가격 필터링
            price = float(ticker.get("lastPrice", 0))
            if (
                price < self.universe_config.min_price
                or price > self.universe_config.max_price
            ):
                continue

            filtered.append(
                {
                    "symbol": symbol_name,
                    "volume_24h": volume_24h,
                    "price": price,
                    "price_change_24h": float(ticker.get("priceChangePercent", 0)),
                    "count": int(ticker.get("count", 0)),
                }
            )

        return filtered

    def _select_top_symbols(self, filtered_symbols: List[Dict]) -> List[str]:
        """Top-N 심볼 선택"""
        # 거래량 기준으로 정렬
        sorted_symbols = sorted(
            filtered_symbols, key=lambda x: x["volume_24h"], reverse=True
        )

        # 안정적인 코인 우선 포함
        selected = []
        stable_added = set()

        # 안정적인 코인 먼저 추가
        for stable_coin in self.stable_coins:
            for symbol_data in sorted_symbols:
                if (
                    symbol_data["symbol"] == stable_coin
                    and stable_coin not in stable_added
                ):
                    selected.append(stable_coin)
                    stable_added.add(stable_coin)
                    break

        # 나머지 코인 추가
        for symbol_data in sorted_symbols:
            if len(selected) >= self.universe_config.top_n:
                break
            if symbol_data["symbol"] not in stable_added:
                selected.append(symbol_data["symbol"])

        return selected[: self.universe_config.top_n]

    def refresh_universe(self) -> List[str]:
        """유니버스 새로고침"""
        current_time = time.time()

        # 캐시 확인
        if (current_time - self.last_refresh_time) < (
            self.universe_config.refresh_minutes * 60
        ):
            if self.universe_cache_path.exists():
                try:
                    with open(self.universe_cache_path, "r", encoding="utf-8") as f:
                        cache_data = json.load(f)
                        if cache_data.get("timestamp", 0) > (
                            current_time - self.universe_config.refresh_minutes * 60
                        ):
                            return cache_data.get("symbols", [])
                except Exception:
                    pass

        print(f"유니버스 새로고침 시작... (Top {self.universe_config.top_n})")

        # 심볼 정보 가져오기
        symbols = self._fetch_binance_symbols()
        if not symbols:
            print("심볼 정보를 가져올 수 없습니다.")
            return []

        # 24시간 티커 정보 가져오기
        tickers = self._fetch_24h_ticker()
        if not tickers:
            print("24시간 티커 정보를 가져올 수 없습니다.")
            return []

        # 심볼 필터링
        filtered_symbols = self._filter_symbols(symbols, tickers)
        print(f"필터링된 심볼 수: {len(filtered_symbols)}")

        # Top-N 선택
        selected_symbols = self._select_top_symbols(filtered_symbols)
        print(f"선택된 심볼 수: {len(selected_symbols)}")

        # 캐시 저장
        cache_data = {
            "timestamp": current_time,
            "symbols": selected_symbols,
            "total_filtered": len(filtered_symbols),
            "config": {
                "top_n": self.universe_config.top_n,
                "quote": self.universe_config.quote,
                "min_volume": self.universe_config.min_volume_24h,
            },
        }

        try:
            with open(self.universe_cache_path, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"캐시 저장 실패: {e}")

        self.last_refresh_time = current_time
        return selected_symbols

    def update_watchlist(self, symbols: List[str]) -> bool:
        """워치리스트 업데이트"""
        try:
            # 소문자로 변환
            symbols_lower = [s.lower() for s in symbols]

            with open(self.watchlist_path, "w", encoding="utf-8") as f:
                json.dump(symbols_lower, f, ensure_ascii=False, indent=2)

            print(f"워치리스트 업데이트 완료: {len(symbols_lower)}개 심볼")
            return True

        except Exception as e:
            print(f"워치리스트 업데이트 실패: {e}")
            return False

    def get_universe_status(self) -> Dict:
        """유니버스 상태 반환"""
        status = {
            "auto_universe_enabled": True,
            "last_refresh_time": self.last_refresh_time,
            "next_refresh_in": max(
                0,
                (self.universe_config.refresh_minutes * 60)
                - (time.time() - self.last_refresh_time),
            ),
            "config": {
                "top_n": self.universe_config.top_n,
                "quote": self.universe_config.quote,
                "refresh_minutes": self.universe_config.refresh_minutes,
            },
        }

        # 현재 워치리스트 로드
        try:
            if self.watchlist_path.exists():
                with open(self.watchlist_path, "r", encoding="utf-8") as f:
                    current_watchlist = json.load(f)
                    status["current_symbols"] = len(current_watchlist)
                    status["symbols"] = current_watchlist[:10]  # 처음 10개만 표시
        except Exception:
            status["current_symbols"] = 0
            status["symbols"] = []

        return status


def main():
    """메인 함수"""
    manager = AutoUniverseManager()

    # 유니버스 새로고침
    symbols = manager.refresh_universe()

    if symbols:
        # 워치리스트 업데이트
        success = manager.update_watchlist(symbols)

        if success:
            print("✅ 자동 유니버스 업데이트 완료!")
            print(f"선택된 심볼: {symbols[:10]}...")  # 처음 10개만 표시
        else:
            print("❌ 워치리스트 업데이트 실패")
    else:
        print("❌ 유니버스 새로고침 실패")


if __name__ == "__main__":
    main()
