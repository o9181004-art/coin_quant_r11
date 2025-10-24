#!/usr/bin/env python3
"""
Trade Status V2 - Split BUY/SELL Layout
Clean trade status display with cumulative PnL and fee calculations
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import streamlit as st

# Note: age_seconds, format_age_display imported but not used in current version

# Load environment variables from config.env
try:
    from dotenv import load_dotenv
    load_dotenv('config.env')
except ImportError:
    pass

# Feature flags
UI_TRADE_STATUS_ONLY = os.getenv("UI_TRADE_STATUS_ONLY", "true").lower() == "true"
UI_ALERT_INLINE = os.getenv("UI_ALERT_INLINE", "false").lower() == "true"
UI_TRADE_STATUS_V2 = os.getenv("UI_TRADE_STATUS_V2", "true").lower() == "true"
UI_TRADE_STATUS_V1 = os.getenv("UI_TRADE_STATUS_V1", "false").lower() == "true"

# Trading fee rate
FEE_RATE = 0.0005  # 0.05%


class TradeStatusV2:
    """Trade Status V2 - Clean split layout with PnL calculations"""
    
    def __init__(self):
        self.repo_root = Path(__file__).parent.parent.parent.parent.absolute()
        self.trading_logs_dir = self.repo_root / "logs" / "trading"
        self.state_bus_file = self.repo_root / "shared_data" / "state_bus.json"
        
        # Clear legacy session keys
        self._clear_legacy_session_keys()
    
    def _clear_legacy_session_keys(self):
        """Clear legacy session keys on tab load"""
        legacy_keys = [
            "legacy_trade_rows", "inline_alerts", "recent_fills_cards", 
            "v1_table_state", "trade_status_v1_data"
        ]
        
        for key in legacy_keys:
            if key in st.session_state:
                del st.session_state[key]
    
    def _load_trade_data(self) -> List[Dict[str, Any]]:
        """Load and normalize trade data from SSOT sources"""
        trades = []
        
        # Try trading logs first
        if self.trading_logs_dir.exists():
            trades.extend(self._load_from_trading_logs())
        
        # Fallback to state_bus.json
        if not trades and self.state_bus_file.exists():
            trades.extend(self._load_from_state_bus())
        
        return self._normalize_trades(trades)
    
    def _load_from_trading_logs(self) -> List[Dict[str, Any]]:
        """Load trades from trading logs directory"""
        trades = []
        
        try:
            # Look for today's trading log
            today = datetime.now().strftime("%Y%m%d")
            log_file = self.trading_logs_dir / f"trading_{today}.jsonl"
            
            if log_file.exists():
                with open(log_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        try:
                            trade = json.loads(line.strip())
                            if self._is_closed_trade(trade):
                                trades.append(trade)
                        except json.JSONDecodeError:
                            continue
            
            # Also check for other recent log files
            for log_file in self.trading_logs_dir.glob("trading_*.jsonl"):
                if log_file.name != f"trading_{today}.jsonl":
                    with open(log_file, 'r', encoding='utf-8') as f:
                        for line in f:
                            try:
                                trade = json.loads(line.strip())
                                if self._is_closed_trade(trade):
                                    trades.append(trade)
                            except json.JSONDecodeError:
                                continue
        
        except Exception as e:
            st.error(f"Error loading trading logs: {e}")
        
        return trades
    
    def _load_from_state_bus(self) -> List[Dict[str, Any]]:
        """Load trades from state_bus.json"""
        trades = []
        
        try:
            with open(self.state_bus_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Extract trades from state bus data
            if "trades" in data:
                for trade in data["trades"]:
                    if self._is_closed_trade(trade):
                        trades.append(trade)
            
            # Also check for position history
            if "position_history" in data:
                for _, positions in data["position_history"].items():  # symbol not used
                    for position in positions:
                        if self._is_closed_trade(position):
                            trades.append(position)
        
        except Exception as e:
            st.error(f"Error loading state bus: {e}")
        
        return trades
    
    def _is_closed_trade(self, trade: Dict[str, Any]) -> bool:
        """Check if trade is closed (has both entry and exit)"""
        required_fields = ["entry_price", "exit_price", "qty", "symbol"]
        return all(field in trade for field in required_fields)
    
    def _normalize_trades(self, raw_trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalize trades to standard format"""
        normalized = []
        
        for trade in raw_trades:
            try:
                # Extract basic fields
                symbol = trade.get("symbol", "UNKNOWN")
                qty = abs(float(trade.get("qty", 0)))
                entry_price = float(trade.get("entry_price", 0))
                exit_price = float(trade.get("exit_price", 0))
                
                # Determine side (BUY = long, SELL = short)
                side = trade.get("side", "BUY")
                if side.upper() not in ["BUY", "SELL"]:
                    side = "BUY"  # Default to BUY
                
                # Get close timestamp
                ts_close = trade.get("ts_close") or trade.get("exit_time") or trade.get("timestamp")
                if isinstance(ts_close, str):
                    # Parse ISO8601
                    try:
                        dt = datetime.fromisoformat(ts_close.replace('Z', '+00:00'))
                        ts_close = int(dt.timestamp() * 1000)
                    except (ValueError, AttributeError, TypeError):
                        # Fallback to current time if parse fails
                        ts_close = int(time.time() * 1000)
                elif ts_close is None:
                    ts_close = int(time.time() * 1000)
                else:
                    ts_close = int(ts_close)
                
                # Calculate notional values
                entry_notional = abs(qty * entry_price)
                exit_notional = abs(qty * exit_price)
                
                normalized_trade = {
                    "ts_close": ts_close,
                    "symbol": symbol,
                    "side": side.upper(),
                    "qty": qty,
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "entry_notional": entry_notional,
                    "exit_notional": exit_notional
                }
                
                normalized.append(normalized_trade)
            
                except (ValueError, TypeError):
                continue  # Skip invalid trades (e not used)
        
        return normalized
    
    def _calculate_pnl(self, trade: Dict[str, Any]) -> Tuple[float, float, float]:
        """Calculate PnL with fees"""
        qty = trade["qty"]
        entry_price = trade["entry_price"]
        exit_price = trade["exit_price"]
        entry_notional = trade["entry_notional"]
        exit_notional = trade["exit_notional"]
        side = trade["side"]
        
        # Calculate fees
        fees = FEE_RATE * (entry_notional + exit_notional)
        
        # Calculate gross PnL
        if side == "BUY":  # Long position
            gross_pnl = (exit_price - entry_price) * qty
        else:  # SELL (Short position)
            gross_pnl = (entry_price - exit_price) * qty
        
        # Calculate net PnL
        net_pnl = gross_pnl - fees
        
        # Calculate net PnL percentage
        net_pnl_pct = (net_pnl / entry_notional) * 100 if entry_notional > 0 else 0
        
        return net_pnl, net_pnl_pct, fees
    
    def _calculate_cumulative_pnl(self, trades: List[Dict[str, Any]]) -> Tuple[float, float, float]:
        """Calculate cumulative PnL metrics"""
        cum_notional = 0.0
        cum_pnl = 0.0
        
        for trade in trades:
            net_pnl, _, _ = self._calculate_pnl(trade)
            cum_notional += trade["entry_notional"]
            cum_pnl += net_pnl
        
        cum_pnl_pct = (cum_pnl / cum_notional) * 100 if cum_notional > 0 else 0
        
        return cum_pnl, cum_pnl_pct, cum_notional
    
    def _format_price(self, price: float, _symbol: str = "") -> str:
        """Format price with appropriate decimals"""
        # Default to 2 decimals, can be enhanced with symbol-specific tick sizes
        # _symbol reserved for future symbol-specific formatting
        return f"{price:.2f}"
    
    def _format_qty(self, qty: float) -> str:
        """Format quantity with appropriate decimals"""
        return f"{qty:.4f}"
    
    def _format_pnl(self, pnl: float) -> str:
        """Format PnL with 2 decimals"""
        return f"{pnl:.2f}"
    
    def _format_pnl_pct(self, pnl_pct: float) -> str:
        """Format PnL percentage with 2 decimals"""
        return f"{pnl_pct:.2f}"
    
    def _get_pnl_color(self, pnl: float) -> str:
        """Get color for PnL (red for positive, blue for negative)"""
        if pnl > 0:
            return "color: #ff4444"  # Red for positive
        elif pnl < 0:
            return "color: #4444ff"  # Blue for negative
        else:
            return "color: #ffffff"  # Default for zero
    
    def _format_timestamp(self, ts_close: int) -> str:
        """Format timestamp for display"""
        try:
            dt = datetime.fromtimestamp(ts_close / 1000, tz=timezone.utc)
            return dt.strftime("%H:%M:%S")
        except (ValueError, OSError, OverflowError):
            # Invalid timestamp or out of range
            return "N/A"
    
    def render_trade_table(self, trades: List[Dict[str, Any]], _side: str):
        """Render trade table for a specific side"""
        if not trades:
            st.info("기록 없음")
            return
        
        # Sort by ts_close descending (newest first)
        sorted_trades = sorted(trades, key=lambda x: x["ts_close"], reverse=True)
        
        # Create table data
        table_data = []
        for trade in sorted_trades:
            net_pnl, net_pnl_pct, _ = self._calculate_pnl(trade)  # fees not used in current version
            
            row = {
                "시간": self._format_timestamp(trade["ts_close"]),
                "종목": trade["symbol"],
                "수량": self._format_qty(trade["qty"]),
                "진입가": self._format_price(trade["entry_price"]),
                "체결가": self._format_price(trade["exit_price"]),
                "수익률(%)": self._format_pnl_pct(net_pnl_pct),
                "수익금": self._format_pnl(net_pnl)
            }
            table_data.append(row)
        
        # Display table
        if table_data:
            st.dataframe(  # Display only, return value not used
                table_data,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "시간": st.column_config.TextColumn("시간", width="small"),
                    "종목": st.column_config.TextColumn("종목", width="small"),
                    "수량": st.column_config.TextColumn("수량", width="small"),
                    "진입가": st.column_config.TextColumn("진입가", width="small"),
                    "체결가": st.column_config.TextColumn("체결가", width="small"),
                    "수익률(%)": st.column_config.TextColumn("수익률(%)", width="small"),
                    "수익금": st.column_config.TextColumn("수익금", width="small")
                }
            )
            
            # Apply color styling (Streamlit doesn't support direct cell coloring in dataframe)
            # We'll use CSS for this
            st.markdown(
                f"""
                <style>
                .stDataFrame {{
                    font-size: 0.8rem;
                }}
                </style>
                """,
                unsafe_allow_html=True
            )
    
    def render(self):
        """Render the complete trade status V2 interface"""
        if not UI_TRADE_STATUS_V2:
            st.info("Trade Status V2 is disabled")
            return
        
        # Load trade data
        trades = self._load_trade_data()
        
        if not trades:
            st.info("거래 기록이 없습니다.")
            return
        
        # Calculate cumulative PnL
        cum_pnl, cum_pnl_pct, _ = self._calculate_cumulative_pnl(trades)  # cum_notional not used
        
        # Top banner with cumulative PnL
        st.markdown("---")
        col1, col2 = st.columns(2)
        
        with col1:
            pnl_color = self._get_pnl_color(cum_pnl)
            st.markdown(
                f"""
                <div style="text-align: center; padding: 1rem; background-color: #1e1e1e; border-radius: 0.5rem;">
                    <h3 style="margin: 0; {pnl_color};">누적 수익금: {self._format_pnl(cum_pnl)} USDT</h3>
                </div>
                """,
                unsafe_allow_html=True
            )
        
        with col2:
            pnl_pct_color = self._get_pnl_color(cum_pnl_pct)
            st.markdown(
                f"""
                <div style="text-align: center; padding: 1rem; background-color: #1e1e1e; border-radius: 0.5rem;">
                    <h3 style="margin: 0; {pnl_pct_color};">누적 수익률: {self._format_pnl_pct(cum_pnl_pct)}%</h3>
                </div>
                """,
                unsafe_allow_html=True
            )
        
        st.markdown("---")
        
        # Split layout: BUY (left) and SELL (right)
        col1, col2 = st.columns([1, 1.2])  # SELL column slightly wider
        
        with col1:
            st.subheader("📈 BUY (Long)")
            buy_trades = [t for t in trades if t["side"] == "BUY"]
            self.render_trade_table(buy_trades, "BUY")
        
        with col2:
            st.subheader("📉 SELL (Short)")
            sell_trades = [t for t in trades if t["side"] == "SELL"]
            self.render_trade_table(sell_trades, "SELL")
        
        # Fee information
        st.caption(f"거래 수수료: {FEE_RATE*100:.2f}% (진입 + 청산)")


def render_trade_status_v2():
    """Main entry point for Trade Status V2"""
    if not UI_TRADE_STATUS_V2:
        return
    
    try:
        trade_status = TradeStatusV2()
        trade_status.render()
    except Exception as e:
        st.error(f"Trade Status V2 오류: {e}")
        import traceback
        st.code(traceback.format_exc())
