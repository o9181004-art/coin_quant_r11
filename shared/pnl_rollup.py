#!/usr/bin/env python3
"""
PnL Rollup and Daily Reducer
Metrics collection for trading performance
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class PnLRollup:
    """PnL rollup and daily metrics reducer"""
    
    def __init__(self):
        self.rollup_file = Path("shared_data/pnl_rollup.ndjson")
        self.daily_file = Path("shared_data/pnl_daily.json")
        self.rollup_file.parent.mkdir(parents=True, exist_ok=True)
    
    def append_trade(self, symbol: str, side: str, qty: float, avg_price: float, 
                    fee_usdt: float = 0.0, realized_pnl_usdt: float = 0.0, 
                    slippage_bps: float = 0.0, profile: str = None) -> bool:
        """Append a trade to the rollup"""
        try:
            # Get current risk profile if not provided
            if profile is None:
                try:
                    from shared.risk_profile_manager import \
                        get_risk_profile_manager
                    profile_manager = get_risk_profile_manager()
                    profile = profile_manager.get_current_profile()
                except Exception:
                    profile = "unknown"
            
            trade_record = {
                "ts": int(time.time() * 1000),  # milliseconds
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "avg_price": avg_price,
                "fee_usdt": fee_usdt,
                "realized_pnl_usdt": realized_pnl_usdt,
                "slippage_bps": slippage_bps,
                "profile": profile
            }
            
            # Append to NDJSON file
            with open(self.rollup_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(trade_record, ensure_ascii=False) + "\n")
            
            return True
            
        except Exception as e:
            print(f"Failed to append trade to rollup: {e}")
            return False
    
    def get_trades_for_date(self, date_str: str) -> List[Dict[str, Any]]:
        """Get all trades for a specific date (YYYY-MM-DD)"""
        trades = []
        
        if not self.rollup_file.exists():
            return trades
        
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            
            with open(self.rollup_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        trade = json.loads(line)
                        trade_date = datetime.fromtimestamp(trade["ts"] / 1000).date()
                        
                        if trade_date == target_date:
                            trades.append(trade)
                    except (json.JSONDecodeError, KeyError, ValueError):
                        continue  # Skip malformed lines
            
        except Exception as e:
            print(f"Error reading trades for date {date_str}: {e}")
        
        return trades
    
    def calculate_daily_metrics(self, date_str: str) -> Dict[str, Any]:
        """Calculate daily metrics for a specific date"""
        trades = self.get_trades_for_date(date_str)
        
        if not trades:
            return {
                "date": date_str,
                "total_trades": 0,
                "total_volume_usdt": 0.0,
                "total_fees_usdt": 0.0,
                "total_pnl_usdt": 0.0,
                "avg_slippage_bps": 0.0,
                "symbols_traded": [],
                "timestamp": time.time()
            }
        
        # Calculate metrics
        total_trades = len(trades)
        total_volume_usdt = sum(trade["qty"] * trade["avg_price"] for trade in trades)
        total_fees_usdt = sum(trade["fee_usdt"] for trade in trades)
        total_pnl_usdt = sum(trade["realized_pnl_usdt"] for trade in trades)
        
        # Average slippage
        slippages = [trade["slippage_bps"] for trade in trades if trade["slippage_bps"] > 0]
        avg_slippage_bps = sum(slippages) / len(slippages) if slippages else 0.0
        
        # Symbols traded
        symbols_traded = list(set(trade["symbol"] for trade in trades))
        
        # Buy/Sell breakdown
        buy_trades = [t for t in trades if t["side"] == "BUY"]
        sell_trades = [t for t in trades if t["side"] == "SELL"]
        
        return {
            "date": date_str,
            "total_trades": total_trades,
            "buy_trades": len(buy_trades),
            "sell_trades": len(sell_trades),
            "total_volume_usdt": total_volume_usdt,
            "total_fees_usdt": total_fees_usdt,
            "total_pnl_usdt": total_pnl_usdt,
            "avg_slippage_bps": avg_slippage_bps,
            "symbols_traded": symbols_traded,
            "timestamp": time.time()
        }
    
    def update_daily_metrics(self, date_str: Optional[str] = None) -> bool:
        """Update daily metrics file"""
        try:
            if date_str is None:
                date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            
            metrics = self.calculate_daily_metrics(date_str)
            
            # Save to daily file
            with open(self.daily_file, "w", encoding="utf-8") as f:
                json.dump(metrics, f, indent=2, ensure_ascii=False)
            
            return True
            
        except Exception as e:
            print(f"Failed to update daily metrics: {e}")
            return False
    
    def get_daily_metrics(self) -> Dict[str, Any]:
        """Get current daily metrics"""
        if not self.daily_file.exists():
            return {}
        
        try:
            with open(self.daily_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Failed to read daily metrics: {e}")
            return {}
    
    def cleanup_old_rollup_data(self, days_to_keep: int = 30) -> int:
        """Cleanup old rollup data, keeping only recent days"""
        if not self.rollup_file.exists():
            return 0
        
        try:
            cutoff_date = datetime.now().date()
            cutoff_ts = int(time.mktime(cutoff_date.timetuple()) * 1000)
            
            # Read all trades
            trades = []
            with open(self.rollup_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        trade = json.loads(line)
                        if trade["ts"] >= cutoff_ts:
                            trades.append(trade)
                    except (json.JSONDecodeError, KeyError, ValueError):
                        continue
            
            # Write back only recent trades
            with open(self.rollup_file, "w", encoding="utf-8") as f:
                for trade in trades:
                    f.write(json.dumps(trade, ensure_ascii=False) + "\n")
            
            return len(trades)
            
        except Exception as e:
            print(f"Failed to cleanup rollup data: {e}")
            return 0

def get_pnl_rollup() -> PnLRollup:
    """Get PnL rollup instance"""
    return PnLRollup()

def append_trade_to_rollup(symbol: str, side: str, qty: float, avg_price: float,
                          fee_usdt: float = 0.0, realized_pnl_usdt: float = 0.0,
                          slippage_bps: float = 0.0, profile: str = None) -> bool:
    """Convenience function to append trade to rollup"""
    rollup = get_pnl_rollup()
    return rollup.append_trade(symbol, side, qty, avg_price, fee_usdt, realized_pnl_usdt, slippage_bps, profile)

def update_daily_pnl_metrics(date_str: Optional[str] = None) -> bool:
    """Convenience function to update daily metrics"""
    rollup = get_pnl_rollup()
    return rollup.update_daily_metrics(date_str)

if __name__ == "__main__":
    # Command line interface
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python pnl_rollup.py <command> [args]")
        print("Commands:")
        print("  update [date] - Update daily metrics")
        print("  cleanup [days] - Cleanup old data")
        print("  show [date] - Show daily metrics")
        sys.exit(1)
    
    command = sys.argv[1]
    rollup = get_pnl_rollup()
    
    if command == "update":
        date_str = sys.argv[2] if len(sys.argv) > 2 else None
        success = rollup.update_daily_metrics(date_str)
        print(f"Daily metrics update: {'✅' if success else '❌'}")
        
    elif command == "cleanup":
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 30
        count = rollup.cleanup_old_rollup_data(days)
        print(f"Cleanup complete: {count} trades kept")
        
    elif command == "show":
        date_str = sys.argv[2] if len(sys.argv) > 2 else None
        if date_str:
            metrics = rollup.calculate_daily_metrics(date_str)
        else:
            metrics = rollup.get_daily_metrics()
        
        print(json.dumps(metrics, indent=2, ensure_ascii=False))
        
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
