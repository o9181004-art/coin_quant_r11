#!/usr/bin/env python3
"""
Trade Status Enhanced - Single Source of Truth with Robust JSONL Reader
Implements all requirements from Cursor Instructions
"""

import json
import os
import time
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from enum import Enum

import streamlit as st

# Single Source of Truth - Lock the data source
TRADE_HISTORY_PATH = Path("shared_data/trades.jsonl")

# Trading fee rate
FEE_RATE = 0.0005  # 0.05%

class ZeroRowReason(Enum):
    """Reasons for zero rows in trade display"""
    MISSING_FILE = "MISSING_FILE"
    EMPTY_FILE = "EMPTY_FILE"
    ALL_MALFORMED = "ALL_MALFORMED"
    ALL_FILTERED = "ALL_FILTERED"
    TIME_WINDOW_EMPTY = "TIME_WINDOW_EMPTY"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    UNKNOWN = "UNKNOWN"

class TradeStatusEnhanced:
    """Enhanced Trade Status with SSOT and robust error handling"""
    
    def __init__(self):
        self.trade_file = TRADE_HISTORY_PATH
        self.telemetry = {
            "total_lines": 0,
            "valid_lines": 0,
            "bad_lines": 0,
            "filtered_lines": 0,
            "repairs_total": 0,
            "file_size_bytes": 0,
            "file_mtime": 0,
            "first_error_line": None,
            "first_error_col": None,
            "first_error_char": None,
            "min_timestamp": None,
            "max_timestamp": None,
            "permission_error": False
        }
        
        # Clear legacy session keys
        self._clear_legacy_session_keys()
    
    def _clear_legacy_session_keys(self):
        """Clear legacy session keys on tab load"""
        legacy_keys = [
            "legacy_trade_rows", "v1_table_state", "inline_alerts", 
            "recent_fills_cards", "trade_status_v1_data", "trade_status_v2_data"
        ]
        
        for key in legacy_keys:
            if key in st.session_state:
                del st.session_state[key]
    
    def _get_file_info(self) -> Dict[str, Any]:
        """Get detailed file information"""
        info = {
            "path": str(self.trade_file),
            "exists": False,
            "size_bytes": 0,
            "mtime": 0,
            "readable": False,
            "permission_error": False
        }
        
        try:
            if self.trade_file.exists():
                info["exists"] = True
                stat = self.trade_file.stat()
                info["size_bytes"] = stat.st_size
                info["mtime"] = stat.st_mtime
                
                # Test readability
                try:
                    with open(self.trade_file, 'r', encoding='utf-8') as f:
                        f.read(1)  # Try to read one byte
                    info["readable"] = True
                except PermissionError:
                    info["permission_error"] = True
                    self.telemetry["permission_error"] = True
                except Exception:
                    pass
                    
        except Exception as e:
            if "Permission" in str(e) or "WinError 5" in str(e):
                info["permission_error"] = True
                self.telemetry["permission_error"] = True
        
        return info
    
    def _self_healing_converter(self) -> bool:
        """Self-healing converter: fix malformed JSONL files"""
        try:
            with open(self.trade_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            
            # Case 1: JSON array format [...]
            if content.startswith('[') and content.endswith(']'):
                try:
                    data = json.loads(content)
                    if isinstance(data, list):
                        self._repair_jsonl_from_list(data)
                        self.telemetry["repairs_total"] += 1
                        return True
                except json.JSONDecodeError:
                    pass
            
            # Case 2: {"trades": [...]} format
            if '{"trades":[' in content or '"trades":[' in content:
                try:
                    data = json.loads(content)
                    if isinstance(data, dict) and 'trades' in data:
                        self._repair_jsonl_from_list(data['trades'])
                        self.telemetry["repairs_total"] += 1
                        return True
                except json.JSONDecodeError:
                    pass
            
            # Case 3: Concatenated JSON objects (}{ pattern)
            if '}{' in content:
                self._repair_concatenated_json(content)
                self.telemetry["repairs_total"] += 1
                return True
                
        except Exception as e:
            print(f"Self-healing converter 실패: {e}")
        
        return False
    
    def _repair_jsonl_from_list(self, data_list: list):
        """Convert JSON array to JSONL format"""
        # Create backup
        backup_path = self.trade_file.with_suffix('.bak')
        if self.trade_file.exists():
            self.trade_file.rename(backup_path)
        
        # Write to temp file
        temp_path = self.trade_file.with_suffix('.tmp')
        with open(temp_path, 'w', encoding='utf-8', newline='\n') as f:
            for item in data_list:
                if isinstance(item, dict):
                    json_str = json.dumps(item, ensure_ascii=False, separators=(',', ':'))
                    f.write(json_str + '\n')
        
        # Atomic replace
        os.replace(temp_path, self.trade_file)
    
    def _repair_concatenated_json(self, content: str):
        """Repair concatenated JSON objects"""
        # Create backup
        backup_path = self.trade_file.with_suffix('.bak')
        if self.trade_file.exists():
            self.trade_file.rename(backup_path)
        
        # Split by }{ pattern
        chunks = content.replace('}{', '}\n{').split('\n')
        
        # Write to temp file
        temp_path = self.trade_file.with_suffix('.tmp')
        with open(temp_path, 'w', encoding='utf-8', newline='\n') as f:
            for chunk in chunks:
                chunk = chunk.strip()
                if chunk:
                    try:
                        # Validate JSON
                        json.loads(chunk)
                        f.write(chunk + '\n')
                    except json.JSONDecodeError:
                        continue
        
        # Atomic replace
        os.replace(temp_path, self.trade_file)
    
    def _load_trades_robust(self) -> Tuple[List[Dict[str, Any]], ZeroRowReason]:
        """Load trades with robust error handling and explicit zero-row reasons"""
        trades = []
        reason = ZeroRowReason.UNKNOWN
        
        # Get file info
        file_info = self._get_file_info()
        self.telemetry.update({
            "file_size_bytes": file_info["size_bytes"],
            "file_mtime": file_info["mtime"]
        })
        
        # Check for missing file
        if not file_info["exists"]:
            return trades, ZeroRowReason.MISSING_FILE
        
        # Check for empty file
        if file_info["size_bytes"] == 0:
            return trades, ZeroRowReason.EMPTY_FILE
        
        # Check for permission errors
        if file_info["permission_error"]:
            return trades, ZeroRowReason.PERMISSION_DENIED
        
        # Try to read file
        try:
            # UTF-8 read with BOM fallback
            try:
                with open(self.trade_file, 'r', encoding='utf-8') as f:
                    content = f.read()
            except UnicodeDecodeError:
                with open(self.trade_file, 'r', encoding='utf-8-sig') as f:
                    content = f.read()
            
            # Check for malformed format
            first_line = content.split('\n')[0].strip() if content else ""
            if first_line.startswith('[') or '{"trades":[' in first_line or '}{' in content:
                if self._self_healing_converter():
                    # Re-read after repair
                    with open(self.trade_file, 'r', encoding='utf-8') as f:
                        content = f.read()
            
            # Parse line by line
            lines = content.split('\n')
            self.telemetry["total_lines"] = len(lines)
            
            for line_num, line in enumerate(lines, 1):
                line = line.strip()
                if not line:
                    continue
                
                try:
                    trade_data = json.loads(line)
                    if isinstance(trade_data, dict):
                        trades.append(trade_data)
                        self.telemetry["valid_lines"] += 1
                        
                        # Track timestamp range
                        ts = trade_data.get("ts_close") or trade_data.get("timestamp") or trade_data.get("ts")
                        if ts:
                            if self.telemetry["min_timestamp"] is None or ts < self.telemetry["min_timestamp"]:
                                self.telemetry["min_timestamp"] = ts
                            if self.telemetry["max_timestamp"] is None or ts > self.telemetry["max_timestamp"]:
                                self.telemetry["max_timestamp"] = ts
                    else:
                        self.telemetry["bad_lines"] += 1
                        if self.telemetry["first_error_line"] is None:
                            self.telemetry["first_error_line"] = line_num
                            self.telemetry["first_error_col"] = 0
                            self.telemetry["first_error_char"] = str(trade_data)[:20]
                            
                except json.JSONDecodeError as e:
                    self.telemetry["bad_lines"] += 1
                    if self.telemetry["first_error_line"] is None:
                        self.telemetry["first_error_line"] = line_num
                        self.telemetry["first_error_col"] = getattr(e, 'colno', 0)
                        self.telemetry["first_error_char"] = getattr(e, 'pos', 0)
            
            # Determine reason for zero rows
            if not trades:
                if self.telemetry["bad_lines"] > 0 and self.telemetry["valid_lines"] == 0:
                    reason = ZeroRowReason.ALL_MALFORMED
                elif self.telemetry["valid_lines"] > 0:
                    # All trades were filtered out
                    reason = ZeroRowReason.ALL_FILTERED
                else:
                    reason = ZeroRowReason.EMPTY_FILE
            else:
                reason = None  # Success
                
        except Exception as e:
            if "Permission" in str(e) or "WinError 5" in str(e):
                reason = ZeroRowReason.PERMISSION_DENIED
            else:
                reason = ZeroRowReason.UNKNOWN
                print(f"Unexpected error loading trades: {e}")
        
        return trades, reason
    
    def _apply_filters(self, trades: List[Dict[str, Any]], 
                      show_all: bool = False,
                      date_window: str = "7d",
                      min_pnl: Optional[float] = None) -> List[Dict[str, Any]]:
        """Apply filters to trades"""
        filtered_trades = []
        
        # Date window filter
        now = datetime.now(timezone.utc)
        if date_window == "24h":
            cutoff = now - timedelta(hours=24)
        elif date_window == "7d":
            cutoff = now - timedelta(days=7)
        elif date_window == "30d":
            cutoff = now - timedelta(days=30)
        else:  # "All"
            cutoff = None
        
        for trade in trades:
            # Closed trades filter (unless show_all is True)
            if not show_all:
                if not self._is_closed_trade(trade):
                    continue
            
            # Date window filter
            if cutoff:
                ts = trade.get("ts_close") or trade.get("timestamp") or trade.get("ts")
                if ts:
                    try:
                        if isinstance(ts, str):
                            trade_dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                        else:
                            trade_dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                        
                        if trade_dt < cutoff:
                            self.telemetry["filtered_lines"] += 1
                            continue
                    except:
                        pass
            
            # PnL filter
            if min_pnl is not None:
                pnl = self._calculate_pnl(trade)[0]
                if pnl < min_pnl:
                    self.telemetry["filtered_lines"] += 1
                    continue
            
            filtered_trades.append(trade)
        
        return filtered_trades
    
    def _is_closed_trade(self, trade: Dict[str, Any]) -> bool:
        """Check if trade is closed (has both entry and exit)"""
        required_fields = ["entry_price", "exit_price", "qty", "symbol"]
        return all(field in trade for field in required_fields)
    
    def _calculate_pnl(self, trade: Dict[str, Any]) -> Tuple[float, float, float]:
        """Calculate PnL with fees"""
        qty = trade.get("qty", 0)
        entry_price = trade.get("entry_price", 0)
        exit_price = trade.get("exit_price", 0)
        side = trade.get("side", "BUY")
        
        if not all([qty, entry_price, exit_price]):
            return 0.0, 0.0, 0.0
        
        entry_notional = abs(qty * entry_price)
        exit_notional = abs(qty * exit_price)
        
        # Calculate fees
        fees = FEE_RATE * (entry_notional + exit_notional)
        
        # Calculate gross PnL
        if side.upper() == "BUY":  # Long position
            gross_pnl = (exit_price - entry_price) * qty
        else:  # SELL (Short position)
            gross_pnl = (entry_price - exit_price) * qty
        
        # Calculate net PnL
        net_pnl = gross_pnl - fees
        
        # Calculate net PnL percentage
        net_pnl_pct = (net_pnl / entry_notional) * 100 if entry_notional > 0 else 0
        
        return net_pnl, net_pnl_pct, fees
    
    def _render_zero_row_reason(self, reason: ZeroRowReason):
        """Render explicit reason for zero rows"""
        if reason == ZeroRowReason.MISSING_FILE:
            st.error(f"❌ **MISSING_FILE**: `{self.trade_file}` 파일을 찾을 수 없습니다.")
            st.info("💡 **해결 방법**: 거래 데이터가 생성되지 않았거나 경로가 잘못되었습니다.")
            
        elif reason == ZeroRowReason.EMPTY_FILE:
            st.warning(f"⚠️ **EMPTY_FILE**: `{self.trade_file}` 파일이 비어있습니다.")
            st.info("💡 **해결 방법**: 거래가 아직 실행되지 않았습니다.")
            
        elif reason == ZeroRowReason.ALL_MALFORMED:
            st.error(f"❌ **ALL_MALFORMED**: 모든 라인이 잘못된 JSON 형식입니다.")
            if self.telemetry["first_error_line"]:
                st.error(f"첫 번째 오류: 라인 {self.telemetry['first_error_line']}, "
                        f"컬럼 {self.telemetry['first_error_col']}")
                if self.telemetry["first_error_char"]:
                    st.code(f"오류 문자: {self.telemetry['first_error_char']}")
            st.info("💡 **해결 방법**: 자동 복구를 시도했지만 실패했습니다. 파일을 수동으로 확인하세요.")
            
        elif reason == ZeroRowReason.ALL_FILTERED:
            st.warning(f"⚠️ **ALL_FILTERED**: 모든 거래가 필터에 의해 제외되었습니다.")
            st.info("💡 **해결 방법**: 필터 설정을 확인하거나 '모든 거래 표시'를 활성화하세요.")
            
        elif reason == ZeroRowReason.TIME_WINDOW_EMPTY:
            st.warning(f"⚠️ **TIME_WINDOW_EMPTY**: 선택된 시간 범위에 거래가 없습니다.")
            if self.telemetry["min_timestamp"] and self.telemetry["max_timestamp"]:
                min_dt = datetime.fromtimestamp(self.telemetry["min_timestamp"] / 1000)
                max_dt = datetime.fromtimestamp(self.telemetry["max_timestamp"] / 1000)
                st.info(f"데이터 범위: {min_dt.strftime('%Y-%m-%d')} ~ {max_dt.strftime('%Y-%m-%d')}")
            st.info("💡 **해결 방법**: 더 넓은 시간 범위를 선택하세요.")
            
        elif reason == ZeroRowReason.PERMISSION_DENIED:
            st.error(f"❌ **PERMISSION_DENIED**: `{self.trade_file}` 파일에 접근할 수 없습니다.")
            st.info("💡 **해결 방법**:")
            st.info("1. 파일을 사용 중인 에디터나 tail 명령을 종료하세요")
            st.info("2. 바이러스 백신 실시간 스캔에서 `shared_data/*.jsonl` 제외")
            st.info("3. 파일 속성이 읽기 전용인지 확인하세요")
            
        else:  # UNKNOWN
            st.error(f"❌ **UNKNOWN**: 알 수 없는 오류가 발생했습니다.")
            st.info("💡 **해결 방법**: 시스템 관리자에게 문의하세요.")
    
    def _render_debug_info(self):
        """Render debug information"""
        with st.expander("🔧 디버그 정보", expanded=False):
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("파일 정보")
                st.json({
                    "경로": str(self.trade_file),
                    "존재": self.trade_file.exists(),
                    "크기": f"{self.telemetry['file_size_bytes']} bytes",
                    "수정시간": f"{self.telemetry['file_mtime']:.1f}초 전",
                    "읽기 가능": not self.telemetry["permission_error"]
                })
            
            with col2:
                st.subheader("파싱 통계")
                st.json({
                    "총 라인": self.telemetry["total_lines"],
                    "유효 라인": self.telemetry["valid_lines"],
                    "오류 라인": self.telemetry["bad_lines"],
                    "필터링됨": self.telemetry["filtered_lines"],
                    "복구 횟수": self.telemetry["repairs_total"]
                })
            
            if self.telemetry["min_timestamp"] and self.telemetry["max_timestamp"]:
                min_dt = datetime.fromtimestamp(self.telemetry["min_timestamp"] / 1000)
                max_dt = datetime.fromtimestamp(self.telemetry["max_timestamp"] / 1000)
                st.subheader("타임스탬프 범위")
                st.json({
                    "최소": f"{min_dt.strftime('%Y-%m-%d %H:%M:%S')}",
                    "최대": f"{max_dt.strftime('%Y-%m-%d %H:%M:%S')}"
                })
    
    def render(self):
        """Render the enhanced trade status interface"""
        st.subheader("📋 거래 현황 (Enhanced)")
        
        # Check if wrong source path is being used
        if str(self.trade_file) != str(TRADE_HISTORY_PATH):
            st.error(f"❌ **Wrong source path**: Expected `{TRADE_HISTORY_PATH}`, got `{self.trade_file}`")
            return
        
        # Filter controls
        col1, col2, col3 = st.columns(3)
        
        with col1:
            show_all = st.checkbox("모든 거래 표시", value=False, 
                                 help="진행 중인 거래도 포함하여 표시")
        
        with col2:
            date_window = st.selectbox("시간 범위", ["24h", "7d", "30d", "All"], 
                                     index=1, help="거래 시간 범위 선택")
        
        with col3:
            min_pnl = st.number_input("최소 수익금 (USDT)", value=0.0, 
                                    help="이 수익금 이상인 거래만 표시")
        
        # Load trades with robust error handling
        trades, zero_reason = self._load_trades_robust()
        
        # Apply filters
        if trades:
            filtered_trades = self._apply_filters(trades, show_all, date_window, min_pnl)
        else:
            filtered_trades = []
        
        # Handle zero rows with explicit reasons
        if not filtered_trades:
            if trades:  # Raw trades exist but all filtered
                self._render_zero_row_reason(ZeroRowReason.ALL_FILTERED)
            else:  # No raw trades
                self._render_zero_row_reason(zero_reason)
            
            # Show debug info
            self._render_debug_info()
            return
        
        # Calculate cumulative PnL
        cum_pnl = 0.0
        cum_notional = 0.0
        for trade in filtered_trades:
            net_pnl, _, _ = self._calculate_pnl(trade)
            cum_pnl += net_pnl
            qty = trade.get("qty", 0)
            entry_price = trade.get("entry_price", 0)
            cum_notional += abs(qty * entry_price)
        
        cum_pnl_pct = (cum_pnl / cum_notional) * 100 if cum_notional > 0 else 0
        
        # Top banner with cumulative PnL
        st.markdown("---")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            pnl_color = "color: #ff4444" if cum_pnl > 0 else "color: #4444ff" if cum_pnl < 0 else "color: #ffffff"
            st.markdown(
                f"""
                <div style="text-align: center; padding: 1rem; background-color: #1e1e1e; border-radius: 0.5rem;">
                    <h3 style="margin: 0; {pnl_color};">누적 수익금: {cum_pnl:.2f} USDT</h3>
                </div>
                """,
                unsafe_allow_html=True
            )
        
        with col2:
            pnl_pct_color = "color: #ff4444" if cum_pnl_pct > 0 else "color: #4444ff" if cum_pnl_pct < 0 else "color: #ffffff"
            st.markdown(
                f"""
                <div style="text-align: center; padding: 1rem; background-color: #1e1e1e; border-radius: 0.5rem;">
                    <h3 style="margin: 0; {pnl_pct_color};">누적 수익률: {cum_pnl_pct:.2f}%</h3>
                </div>
                """,
                unsafe_allow_html=True
            )
        
        with col3:
            st.markdown(
                f"""
                <div style="text-align: center; padding: 1rem; background-color: #1e1e1e; border-radius: 0.5rem;">
                    <h3 style="margin: 0; color: #ffffff;">총 거래: {len(filtered_trades)}건</h3>
                </div>
                """,
                unsafe_allow_html=True
            )
        
        st.markdown("---")
        
        # Split layout: BUY (left) and SELL (right)
        col1, col2 = st.columns([1, 1.2])
        
        with col1:
            st.subheader("🟢 BUY (Long)")
            buy_trades = [t for t in filtered_trades if t.get("side", "").upper() == "BUY"]
            self._render_trade_table(buy_trades)
        
        with col2:
            st.subheader("🔴 SELL (Short)")
            sell_trades = [t for t in filtered_trades if t.get("side", "").upper() == "SELL"]
            self._render_trade_table(sell_trades)
        
        # Fee information
        st.caption(f"거래 수수료: {FEE_RATE*100:.2f}% (진입 + 청산)")
        
        # Show debug info
        self._render_debug_info()
    
    def _render_trade_table(self, trades: List[Dict[str, Any]]):
        """Render trade table for a specific side"""
        if not trades:
            st.info("기록 없음")
            return
        
        # Sort by timestamp descending (newest first)
        sorted_trades = sorted(trades, key=lambda x: x.get("ts_close") or x.get("timestamp") or x.get("ts") or 0, reverse=True)
        
        # Create table data
        table_data = []
        for trade in sorted_trades[:20]:  # Limit to 20 most recent
            net_pnl, net_pnl_pct, fees = self._calculate_pnl(trade)
            
            # Format timestamp
            ts = trade.get("ts_close") or trade.get("timestamp") or trade.get("ts")
            if ts:
                try:
                    if isinstance(ts, str):
                        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                    else:
                        dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                    time_str = dt.strftime("%H:%M:%S")
                except:
                    time_str = "N/A"
            else:
                time_str = "N/A"
            
            row = {
                "시간": time_str,
                "종목": trade.get("symbol", "N/A"),
                "수량": f"{trade.get('qty', 0):.4f}",
                "진입가": f"{trade.get('entry_price', 0):.2f}",
                "체결가": f"{trade.get('exit_price', 0):.2f}",
                "수익률(%)": f"{net_pnl_pct:.2f}",
                "수익금": f"{net_pnl:.2f}"
            }
            table_data.append(row)
        
        # Display table
        if table_data:
            st.dataframe(
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


def render_trade_status_enhanced():
    """Main entry point for Enhanced Trade Status"""
    try:
        trade_status = TradeStatusEnhanced()
        trade_status.render()
    except Exception as e:
        st.error(f"Trade Status Enhanced 오류: {e}")
        import traceback
        st.code(traceback.format_exc())
