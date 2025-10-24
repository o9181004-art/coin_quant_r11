#!/usr/bin/env python3
"""
Trades Ledger Reader - Lightweight, robust JSONL parser
"""
import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime, timezone

try:
    from shared.environment_manager import EnvironmentManager
    from shared.path_registry import PathRegistry
except ImportError:
    print("Warning: EnvironmentManager or PathRegistry not available")


@dataclass
class TradeRecord:
    """Normalized trade record schema"""
    ts: float
    date: str
    time: str
    symbol: str
    side: str
    qty: float
    price: float
    notional: float
    fee: float
    pnl: float
    realized_pnl: float
    balance_after: float
    order_id: str
    strategy: str
    venue: str
    trace_id: str


@dataclass
class TradesSummary:
    """Trade summary statistics"""
    total_trades: int
    total_notional: float
    total_fees: float
    realized_pnl: float
    avg_price: float
    buy_count: int
    sell_count: int


class TradesReader:
    """Robust trades reader with lenient parsing"""
    
    def __init__(self):
        self._cache = {}
        self._last_signatures = {}
        
    def get_file_signature(self, file_path: Path) -> Tuple[str, int, int]:
        """Get file signature for change detection"""
        try:
            stat = file_path.stat()
            return str(file_path.absolute()), stat.st_mtime_ns, stat.st_size
        except (OSError, FileNotFoundError):
            return str(file_path.absolute()), 0, 0
    
    def get_trading_log_path(self, date: Optional[str] = None) -> Path:
        """Get trading log file path for given date (default: today)"""
        if date is None:
            date = datetime.now().strftime("%Y%m%d")
        
        # Try SSOT path first
        try:
            repo_root = PathRegistry.current().repo_root
            logs_dir = repo_root / "logs" / "trading"
            return logs_dir / f"trading_{date}.jsonl"
        except:
            # Fallback to relative path
            return Path(f"logs/trading/trading_{date}.jsonl")
    
    def get_fallback_paths(self) -> List[Path]:
        """Get fallback file paths for trade data"""
        try:
            repo_root = PathRegistry.current().repo_root
            fallbacks = [
                repo_root / "logs" / "orders" / "orders_log.ndjson",
                repo_root / "shared_data" / "positions_snapshot.json",
                repo_root / "shared_data" / "trades.jsonl"
            ]
        except:
            fallbacks = [
                Path("logs/orders/orders_log.ndjson"),
                Path("shared_data/positions_snapshot.json"),
                Path("shared_data/trades.jsonl")
            ]
        
        return [p for p in fallbacks if p.exists()]
    
    def _parse_jsonl_line(self, line: str, line_num: int) -> Optional[Dict[str, Any]]:
        """Parse a single JSONL line with error handling"""
        line = line.strip()
        if not line:
            return None
            
        try:
            return json.loads(line)
        except json.JSONDecodeError as e:
            # Log error but continue parsing
            if os.getenv("LEDGER_DEBUG"):
                print(f"JSON parse error at line {line_num}: {e}")
                print(f"Line content: {line[:100]}...")
            return None
    
    def _lenient_parse_array(self, content: str) -> List[Dict[str, Any]]:
        """Lenient parser for JSON arrays and concatenated JSON"""
        try:
            data = json.loads(content)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "trades" in data:
                return data["trades"]
            else:
                return [data] if data else []
        except json.JSONDecodeError:
            # Try to parse concatenated JSON objects
            if '}{' in content:
                try:
                    # Split by }{ and reconstruct
                    parts = content.split('}{')
                    trades = []
                    for i, part in enumerate(parts):
                        if i == 0:
                            json_str = part + '}'
                        elif i == len(parts) - 1:
                            json_str = '{' + part
                        else:
                            json_str = '{' + part + '}'
                        
                        try:
                            trade = json.loads(json_str)
                            if isinstance(trade, dict):
                                trades.append(trade)
                        except json.JSONDecodeError:
                            continue
                    return trades
                except Exception:
                    pass
            return []
    
    def _normalize_trade_record(self, raw_trade: Dict[str, Any]) -> Optional[TradeRecord]:
        """Normalize trade record to standard schema"""
        try:
            # Extract timestamp
            ts = raw_trade.get("timestamp", raw_trade.get("ts", raw_trade.get("time", 0)))
            if isinstance(ts, str):
                try:
                    ts = float(ts)
                except ValueError:
                    ts = 0
            
            # Convert to datetime
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            date = dt.strftime("%Y-%m-%d")
            time_str = dt.strftime("%H:%M:%S")
            
            # Extract basic fields
            symbol = str(raw_trade.get("symbol", "")).upper()
            side = str(raw_trade.get("side", raw_trade.get("action", ""))).upper()
            qty = float(raw_trade.get("quantity", raw_trade.get("qty", raw_trade.get("size", 0))))
            price = float(raw_trade.get("price", raw_trade.get("executedPrice", 0)))
            
            # Calculate derived fields
            notional = qty * price
            fee = float(raw_trade.get("fee", raw_trade.get("commission", 0)))
            pnl = float(raw_trade.get("pnl", raw_trade.get("realizedPnl", 0)))
            realized_pnl = pnl - fee
            balance_after = float(raw_trade.get("balance_after", raw_trade.get("balanceAfter", 0)))
            
            # Extract metadata
            order_id = str(raw_trade.get("orderId", raw_trade.get("clientOrderId", "")))
            strategy = str(raw_trade.get("strategy", raw_trade.get("strategy_id", "")))
            venue = str(raw_trade.get("venue", raw_trade.get("exchange", "BINANCE")))
            trace_id = str(raw_trade.get("trace_id", raw_trade.get("traceId", "")))
            
            return TradeRecord(
                ts=ts, date=date, time=time_str, symbol=symbol, side=side,
                qty=qty, price=price, notional=notional, fee=fee,
                pnl=pnl, realized_pnl=realized_pnl, balance_after=balance_after,
                order_id=order_id, strategy=strategy, venue=venue, trace_id=trace_id
            )
            
        except (ValueError, TypeError, KeyError) as e:
            if os.getenv("LEDGER_DEBUG"):
                print(f"Trade normalization error: {e}")
                print(f"Raw trade: {raw_trade}")
            return None
    
    def _read_file_content(self, file_path: Path, max_size_mb: int = 10) -> str:
        """Read file content with size limit"""
        try:
            file_size = file_path.stat().st_size
            max_size = max_size_mb * 1024 * 1024
            
            if file_size > max_size:
                # Read only the last portion of large files
                with open(file_path, 'r', encoding='utf-8') as f:
                    f.seek(file_size - max_size)
                    # Skip partial line
                    f.readline()
                    return f.read()
            else:
                return file_path.read_text(encoding='utf-8')
                
        except (OSError, UnicodeDecodeError) as e:
            if os.getenv("LEDGER_DEBUG"):
                print(f"File read error {file_path}: {e}")
            return ""
    
    def read_trades(self, file_path: Path, use_cache: bool = True) -> Tuple[List[TradeRecord], Dict[str, Any]]:
        """Read and parse trades from file with caching"""
        signature = self.get_file_signature(file_path)
        signature_key = f"{signature[0]}:{signature[1]}:{signature[2]}"
        
        # Check cache
        if use_cache and signature_key in self._cache:
            return self._cache[signature_key]
        
        trades = []
        diagnostics = {
            "file_path": str(file_path),
            "file_exists": file_path.exists(),
            "file_size": 0,
            "parse_errors": 0,
            "total_lines": 0,
            "valid_trades": 0,
            "dropped_lines": 0,
            "last_mtime": 0,
            "age_seconds": 0
        }
        
        if not file_path.exists():
            self._cache[signature_key] = (trades, diagnostics)
            return trades, diagnostics
        
        try:
            diagnostics["file_size"] = file_path.stat().st_size
            diagnostics["last_mtime"] = file_path.stat().st_mtime
            diagnostics["age_seconds"] = time.time() - file_path.stat().st_mtime
            
            content = self._read_file_content(file_path)
            if not content:
                self._cache[signature_key] = (trades, diagnostics)
                return trades, diagnostics
            
            lines = content.strip().split('\n')
            diagnostics["total_lines"] = len(lines)
            
            # Try JSONL parsing first
            for i, line in enumerate(lines, 1):
                trade_data = self._parse_jsonl_line(line, i)
                if trade_data:
                    trade = self._normalize_trade_record(trade_data)
                    if trade:
                        trades.append(trade)
                        diagnostics["valid_trades"] += 1
                    else:
                        diagnostics["parse_errors"] += 1
                else:
                    diagnostics["dropped_lines"] += 1
            
            # If JSONL parsing failed, try lenient array parsing
            if not trades and content.strip():
                array_data = self._lenient_parse_array(content)
                for trade_data in array_data:
                    if isinstance(trade_data, dict):
                        trade = self._normalize_trade_record(trade_data)
                        if trade:
                            trades.append(trade)
                            diagnostics["valid_trades"] += 1
                        else:
                            diagnostics["parse_errors"] += 1
            
        except Exception as e:
            diagnostics["parse_errors"] += 1
            if os.getenv("LEDGER_DEBUG"):
                print(f"Unexpected error reading {file_path}: {e}")
        
        # Deduplicate trades
        trades = self._deduplicate_trades(trades)
        
        # Cache result
        self._cache[signature_key] = (trades, diagnostics)
        
        return trades, diagnostics
    
    def _deduplicate_trades(self, trades: List[TradeRecord]) -> List[TradeRecord]:
        """Remove duplicate trades based on order_id or trade signature"""
        seen = set()
        unique_trades = []
        
        for trade in trades:
            # Create unique key
            if trade.order_id:
                key = trade.order_id
            else:
                key = f"{trade.symbol}:{trade.ts}:{trade.side}:{trade.price}"
            
            if key not in seen:
                seen.add(key)
                unique_trades.append(trade)
        
        return unique_trades
    
    def get_trades_summary(self, trades: List[TradeRecord]) -> TradesSummary:
        """Calculate trade summary statistics"""
        if not trades:
            return TradesSummary(0, 0, 0, 0, 0, 0, 0)
        
        total_notional = sum(trade.notional for trade in trades)
        total_fees = sum(trade.fee for trade in trades)
        realized_pnl = sum(trade.realized_pnl for trade in trades)
        
        buy_count = sum(1 for trade in trades if trade.side == "BUY")
        sell_count = sum(1 for trade in trades if trade.side == "SELL")
        
        avg_price = total_notional / len(trades) if trades else 0
        
        return TradesSummary(
            total_trades=len(trades),
            total_notional=total_notional,
            total_fees=total_fees,
            realized_pnl=realized_pnl,
            avg_price=avg_price,
            buy_count=buy_count,
            sell_count=sell_count
        )
    
    def clear_cache(self):
        """Clear reader cache"""
        self._cache.clear()
        self._last_signatures.clear()


# Global reader instance
_reader = None

def get_trades_reader() -> TradesReader:
    """Get global trades reader instance"""
    global _reader
    if _reader is None:
        _reader = TradesReader()
    return _reader
