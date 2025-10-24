import json
import pathlib
import time

from jsonschema import ValidationError, validate


def validate_trade_schema(trade_data):
    """
    거래 데이터 스키마 검증

    Args:
        trade_data: 거래 데이터 (dict)

    Returns:
        Tuple[bool, str]: (검증 통과 여부, 오류 메시지)
    """
    try:
        # 통합 거래 스키마 로드
        schema_path = pathlib.Path("shared_data/reports/trade_schema.json")
        if not schema_path.exists():
            return False, "스키마 파일이 존재하지 않음"

        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)

        # 스키마 검증
        validate(instance=trade_data, schema=schema)

        # 추가 비즈니스 로직 검증
        if trade_data.get("strategy_id") == "UNKNOWN":
            return False, "UNKNOWN 전략 ID"

        if trade_data.get("notional", 0) <= 0:
            return False, "거래 금액이 0 이하"

        if trade_data.get("ts_ns", 0) <= 0:
            return False, "유효하지 않은 타임스탬프"

        return True, "검증 통과"

    except ValidationError as e:
        return False, f"스키마 검증 실패: {e.message}"
    except Exception as e:
        return False, f"검증 오류: {str(e)}"


def normalize_trade_data(trade_data):
    """
    거래 데이터 정규화 (스키마 준수 + SOT PnL 계산)

    Args:
        trade_data: 원본 거래 데이터

    Returns:
        dict: 정규화된 거래 데이터
    """
    try:
        # 타임스탬프 정규화 (나노초)
        ts_ns = int(time.time() * 1e9)
        if "ts" in trade_data:
            # 밀리초를 나노초로 변환
            ts_ns = int(trade_data["ts"] * 1e6)

        # 기본 거래 정보
        qty = float(trade_data.get("qty", 0))
        price = float(trade_data.get("price", 0))
        notional = trade_data.get("notional", qty * price)
        if notional == 0:
            notional = qty * price

        # SOT PnL 계산
        from shared.pnl_calculator import calculate_net_pnl

        gross_pnl = float(trade_data.get("gross_pnl", 0))
        maker_taker = trade_data.get("maker_taker", "TAKER")

        # 단일 소스에서 NetPnL 계산
        pnl_components = calculate_net_pnl(gross_pnl, notional, maker_taker)

        # 필수 필드 기본값 설정
        normalized = {
            "strategy_id": trade_data.get("strategy_id", ""),
            "strategy_name": trade_data.get("strategy_name", ""),
            "regime": trade_data.get("regime", "unknown"),
            "signal_id": trade_data.get("signal_id", ""),
            "order_id": trade_data.get("orderId") or trade_data.get("order_id", ""),
            "trade_id": trade_data.get("tradeId") or trade_data.get("trade_id", ""),
            "is_replay": trade_data.get("is_replay", False),
            "ts_ns": ts_ns,
            "notional": float(notional),
            "side": trade_data.get("side", "").upper(),
            "maker_taker": pnl_components.maker_taker,
            "symbol": trade_data.get("symbol", ""),
            "qty": qty,
            "price": price,
            # SOT에서 계산된 PnL 구성 요소 사용
            "gross_pnl": pnl_components.gross_pnl,
            "fee": pnl_components.fee,
            "slippage_bps": pnl_components.slippage_bps,
            "slippage_cost": pnl_components.slippage_cost,
            "net_pnl": pnl_components.net_pnl,
            "fee_rate_bps": pnl_components.fee_rate_bps,
            "calculation_source": pnl_components.calculation_source,
            "integrity_hash": trade_data.get("integrity_hash", ""),
            "source_file": trade_data.get("source_file", ""),
            "line_number": trade_data.get("line_number", 0),
        }

        return normalized

    except Exception as e:
        print(f"[TradeLogger] 데이터 정규화 오류: {e}")
        return trade_data


def log_trade_to_file(trade_data):
    """거래 실행 시 shared_data/trades/trades.jsonl에 기록 (스키마 검증 + 무결성 필터 포함)"""
    try:
        # 데이터 정규화
        normalized_data = normalize_trade_data(trade_data)

        # 무결성 필터 적용 (FAIL-CLOSE)
        from shared.integrity_filters import apply_integrity_filters

        filters_passed, filter_results = apply_integrity_filters(normalized_data)

        if not filters_passed:
            print("[TradeLogger] 무결성 필터 실패 - 체결 금지")
            for result in filter_results:
                if result.action == "BLOCK":
                    print(
                        f"[TradeLogger] 차단 필터: {result.filter_name} - {result.reason}"
                    )
            return False  # 체결 금지

        # 스키마 검증 (검증 실패 시 기록만, 체결 금지)
        is_valid, error_msg = validate_trade_schema(normalized_data)

        if not is_valid:
            print(f"[TradeLogger] 스키마 검증 실패 - 기록만: {error_msg}")
            print(f"[TradeLogger] 원본 데이터: {trade_data}")
            return False  # 체결 금지

        # shared_data/trades 디렉토리 생성
        trades_dir = pathlib.Path("shared_data/trades")
        trades_dir.mkdir(parents=True, exist_ok=True)

        # trades.jsonl 파일 경로
        trades_file = trades_dir / "trades.jsonl"

        # 정규화된 거래 데이터 기록
        with open(trades_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(normalized_data, ensure_ascii=False) + "\n")
            f.flush()

        print(
            f"[TradeLogger] 거래 기록 완료: {normalized_data.get('symbol', 'Unknown')} {normalized_data.get('side', 'Unknown')} | strategy_id={normalized_data.get('strategy_id', 'Unknown')}"
        )
        return True  # 체결 허용

    except Exception as e:
        print(f"[TradeLogger] 거래 기록 실패: {e}")
        return False  # 체결 금지


def log_position_snapshot(position_data):
    """포지션 스냅샷을 shared_data/positions_snapshot.json에 기록"""
    try:
        # shared_data 디렉토리 생성
        shared_data_dir = pathlib.Path("shared_data")
        shared_data_dir.mkdir(parents=True, exist_ok=True)

        # positions_snapshot.json 파일 경로
        positions_file = shared_data_dir / "positions_snapshot.json"

        # 포지션 데이터에 타임스탬프 추가
        position_record = {
            "ts": int(time.time() * 1000),  # 밀리초 타임스탬프
            **position_data,
        }

        # 파일에 쓰기 (덮어쓰기)
        with open(positions_file, "w", encoding="utf-8") as f:
            json.dump(position_record, f, ensure_ascii=False, indent=2)

        print("[PositionLogger] 포지션 스냅샷 기록 완료")

    except Exception as e:
        print(f"[PositionLogger] 포지션 스냅샷 기록 실패: {e}")


def log_price_snapshot(price_data):
    """가격 스냅샷을 shared_data/prices_snapshot.json에 기록"""
    try:
        # shared_data 디렉토리 생성
        shared_data_dir = pathlib.Path("shared_data")
        shared_data_dir.mkdir(parents=True, exist_ok=True)

        # prices_snapshot.json 파일 경로
        prices_file = shared_data_dir / "prices_snapshot.json"

        # 가격 데이터에 타임스탬프 추가
        price_record = {
            "ts": int(time.time() * 1000),  # 밀리초 타임스탬프
            **price_data,
        }

        # 파일에 쓰기 (덮어쓰기)
        with open(prices_file, "w", encoding="utf-8") as f:
            json.dump(price_record, f, ensure_ascii=False, indent=2)

        print("[PriceLogger] 가격 스냅샷 기록 완료")

    except Exception as e:
        print(f"[PriceLogger] 가격 스냅샷 기록 실패: {e}")
