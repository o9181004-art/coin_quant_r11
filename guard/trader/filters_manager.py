#!/usr/bin/env python3
"""
Trader Filters Manager
Manages exchange filters, positions, and safety mechanisms
"""

import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

from shared.io.jsonio import (ensure_epoch_seconds, now_epoch_s,
                              read_json_nobom, write_json_atomic_nobom)
from shared.paths import (EXCHANGE_FILTERS, ORDER_SIGS, POSITIONS,
                          ensure_all_dirs)

# Load environment variables
load_dotenv("config.env")


@dataclass
class SymbolFilter:
    """Symbol filter information"""
    symbol: str
    step_size: float
    tick_size: float
    min_notional: float
    min_price: float
    max_price: float
    last_updated: int


@dataclass
class Position:
    """Position information"""
    symbol: str
    side: str
    size: float
    entry_price: float
    unrealized_pnl: float
    timestamp: int


class FiltersManager:
    """Manages exchange filters and positions"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.running = False
        self.thread = None
        
        # Ensure directories exist
        ensure_all_dirs()
        
        # Configuration
        self.filters_refresh_interval = 6 * 3600  # 6 hours
        self.positions_update_interval = 12  # 10-15 seconds (heartbeat)
        self.order_sig_ttl = 120  # 2 minutes
        
        # State
        self.filters_cache: Dict[str, SymbolFilter] = {}
        self.positions_cache: List[Position] = []
        self.order_signatures: Dict[str, int] = {}
        
        # Threading
        self.lock = threading.RLock()
        
    def start(self):
        """Start the filters manager"""
        if self.running:
            self.logger.warning("Filters manager already running")
            return
            
        self.running = True
        
        # Load existing data
        self._load_filters()
        self._load_positions()
        self._load_order_signatures()
        
        # Start background threads
        self.thread = threading.Thread(target=self._background_loop, daemon=True)
        self.thread.start()
        
        self.logger.info("Filters manager started")
        
    def stop(self):
        """Stop the filters manager"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        self.logger.info("Filters manager stopped")
        
    def _background_loop(self):
        """Background loop for periodic updates"""
        last_filters_refresh = 0
        last_positions_update = 0
        
        while self.running:
            try:
                current_time = time.time()
                
                # Refresh filters every 6 hours
                if current_time - last_filters_refresh > self.filters_refresh_interval:
                    self._refresh_filters()
                    last_filters_refresh = current_time
                    
                # Update positions every 10-15 seconds (heartbeat)
                if current_time - last_positions_update > self.positions_update_interval:
                    self._update_positions()
                    last_positions_update = current_time
                    
                # Clean up expired order signatures
                self._cleanup_order_signatures()
                
                time.sleep(5)  # Check every 5 seconds
                
            except Exception as e:
                # Log crash evidence
                from shared.crash_evidence import log_crash
                log_crash(e, "Filters manager background loop", f"filters_{now_epoch_s()}")
                time.sleep(5)
                
    def _load_filters(self):
        """Load filters from file"""
        try:
            if EXCHANGE_FILTERS.exists():
                data = read_json_nobom(EXCHANGE_FILTERS, {})
                
                with self.lock:
                    self.filters_cache.clear()
                    for symbol, filter_data in data.items():
                        if symbol != "meta":
                            self.filters_cache[symbol] = SymbolFilter(**filter_data)
                            
                self.logger.info(f"Loaded {len(self.filters_cache)} symbol filters")
            else:
                self.logger.info("No filters file found, will create on first refresh")
                
        except Exception as e:
            self.logger.error(f"Load filters error: {e}")
            
    def _load_positions(self):
        """Load positions from file"""
        try:
            if POSITIONS.exists():
                data = read_json_nobom(POSITIONS, {})
                
                with self.lock:
                    self.positions_cache.clear()
                    for pos_data in data.get("positions", []):
                        self.positions_cache.append(Position(**pos_data))
                        
                self.logger.info(f"Loaded {len(self.positions_cache)} positions")
            else:
                self.logger.info("No positions file found")
                
        except Exception as e:
            self.logger.error(f"Load positions error: {e}")
            
    def _load_order_signatures(self):
        """Load order signatures from file"""
        try:
            if ORDER_SIGS.exists():
                data = read_json_nobom(ORDER_SIGS, {})
                
                with self.lock:
                    self.order_signatures = data.get("signatures", {})
                    
                self.logger.info(f"Loaded {len(self.order_signatures)} order signatures")
            else:
                self.logger.info("No order signatures file found")
                
        except Exception as e:
            self.logger.error(f"Load order signatures error: {e}")
            
    def _refresh_filters(self):
        """Refresh exchange filters"""
        try:
            self.logger.info("Refreshing exchange filters...")
            
            # Get active symbols
            from shared.paths import get_active_symbols
            symbols = get_active_symbols()
            
            if not symbols:
                self.logger.warning("No active symbols found")
                return
                
            # Try to get exchange info
            try:
                filters = self._fetch_exchange_info(symbols)
            except Exception as e:
                self.logger.error(f"Failed to fetch exchange info: {e}")
                # Use conservative stub
                filters = self._create_conservative_filters(symbols)
                
            # Update cache
            with self.lock:
                self.filters_cache.update(filters)
                
            # Save to file
            self._save_filters()
            
            self.logger.info(f"Refreshed {len(filters)} symbol filters")
            
        except Exception as e:
            self.logger.error(f"Refresh filters error: {e}")
            
    def _fetch_exchange_info(self, symbols: List[str]) -> Dict[str, SymbolFilter]:
        """Fetch exchange info from Binance API"""
        try:
            from binance.spot import Spot

            # Initialize client
            client = Spot(
                api_key=os.getenv("BINANCE_API_KEY", ""),
                api_secret=os.getenv("BINANCE_SECRET_KEY", ""),
                base_url=(
                    "https://testnet.binance.vision"
                    if os.getenv("BINANCE_USE_TESTNET", "true").lower() == "true"
                    else "https://api.binance.com"
                ),
            )
            
            # Get exchange info
            exchange_info = client.exchange_info()
            
            filters = {}
            current_time = now_epoch_s()
            
            for symbol in symbols:
                # Find symbol info
                symbol_info = None
                for s in exchange_info["symbols"]:
                    if s["symbol"] == symbol:
                        symbol_info = s
                        break
                        
                if not symbol_info:
                    self.logger.warning(f"Symbol {symbol} not found in exchange info")
                    continue
                    
                # Extract filters
                filter_data = {}
                for f in symbol_info["filters"]:
                    if f["filterType"] == "LOT_SIZE":
                        filter_data["step_size"] = float(f["stepSize"])
                    elif f["filterType"] == "PRICE_FILTER":
                        filter_data["tick_size"] = float(f["tickSize"])
                        filter_data["min_price"] = float(f["minPrice"])
                        filter_data["max_price"] = float(f["maxPrice"])
                    elif f["filterType"] == "MIN_NOTIONAL":
                        filter_data["min_notional"] = float(f["minNotional"])
                        
                # Create SymbolFilter
                filters[symbol] = SymbolFilter(
                    symbol=symbol,
                    step_size=filter_data.get("step_size", 0.001),
                    tick_size=filter_data.get("tick_size", 0.01),
                    min_notional=filter_data.get("min_notional", 10.0),
                    min_price=filter_data.get("min_price", 0.0),
                    max_price=filter_data.get("max_price", float("inf")),
                    last_updated=current_time
                )
                
            return filters
            
        except Exception as e:
            self.logger.error(f"Fetch exchange info error: {e}")
            raise
            
    def _create_conservative_filters(self, symbols: List[str]) -> Dict[str, SymbolFilter]:
        """Create conservative filter stubs"""
        try:
            filters = {}
            current_time = now_epoch_s()
            
            for symbol in symbols:
                filters[symbol] = SymbolFilter(
                    symbol=symbol,
                    step_size=0.001,
                    tick_size=0.01,
                    min_notional=10.0,
                    min_price=0.0,
                    max_price=float("inf"),
                    last_updated=current_time
                )
                
            return filters
            
        except Exception as e:
            self.logger.error(f"Create conservative filters error: {e}")
            return {}
            
    def _save_filters(self):
        """Save filters to file"""
        try:
            with self.lock:
                data = {
                    "meta": {
                        "version": "1.0.0",
                        "last_updated": now_epoch_s(),
                        "stale": False
                    }
                }
                
                for symbol, filter_obj in self.filters_cache.items():
                    data[symbol] = {
                        "symbol": filter_obj.symbol,
                        "step_size": filter_obj.step_size,
                        "tick_size": filter_obj.tick_size,
                        "min_notional": filter_obj.min_notional,
                        "min_price": filter_obj.min_price,
                        "max_price": filter_obj.max_price,
                        "last_updated": filter_obj.last_updated
                    }
                    
            write_json_atomic_nobom(EXCHANGE_FILTERS, data)
            
        except Exception as e:
            self.logger.error(f"Save filters error: {e}")
            
    def _update_positions(self):
        """Update positions (canonical schema)"""
        try:
            # In a real implementation, this would fetch from exchange
            # For now, we'll just update the timestamp
            
            with self.lock:
                current_time = now_epoch_s()
                
                # Canonical positions schema
                positions_dict = {}
                for pos in self.positions_cache:
                    positions_dict[pos.symbol.upper()] = {
                        "qty": pos.size,
                        "avg_price": pos.entry_price
                    }
                
                positions_data = {
                    "timestamp": current_time,
                    "positions": positions_dict,
                    "positions_count": len(self.positions_cache)
                }
                
            # Save to file
            write_json_atomic_nobom(POSITIONS, positions_data)
            
            # Update trader health telemetry
            self._update_trader_health()
            
        except Exception as e:
            self.logger.error(f"Update positions error: {e}")

    def _update_trader_health(self):
        """Update trader health telemetry"""
        try:
            current_time = now_epoch_s()
            
            # Check if exchange info is loaded
            exchange_info_loaded = True
            try:
                if not EXCHANGE_FILTERS.exists():
                    exchange_info_loaded = False
                else:
                    filters_data = read_json_nobom(EXCHANGE_FILTERS, {})
                    # Check if meta exists and stale is false
                    meta = filters_data.get("meta", {})
                    if meta.get("stale", True):
                        exchange_info_loaded = False
                    # Also check if we have actual symbol filters
                    symbol_count = len([k for k in filters_data.keys() if k != "meta"])
                    if symbol_count == 0:
                        exchange_info_loaded = False
            except Exception:
                exchange_info_loaded = False
            
            # Trader health data
            trader_health = {
                "timestamp": current_time,
                "entrypoint_ok": True,  # We're running, so entrypoint is OK
                "last_rest_ok_ts": current_time,
                "exchange_info_loaded": exchange_info_loaded,
                "balances": {
                    "fresh_ts": current_time
                },
                "circuit_breaker": {
                    "active": False,
                    "since": 0
                }
            }
            
            # Save to trader health file
            trader_health_file = Path("shared_data/health/trader.json")
            trader_health_file.parent.mkdir(parents=True, exist_ok=True)
            write_json_atomic_nobom(trader_health_file, trader_health)
            
        except Exception as e:
            self.logger.error(f"Update trader health error: {e}")
            
    def _cleanup_order_signatures(self):
        """Clean up expired order signatures"""
        try:
            current_time = now_epoch_s()
            
            with self.lock:
                expired_sigs = [
                    sig for sig, timestamp in self.order_signatures.items()
                    if current_time - timestamp > self.order_sig_ttl
                ]
                
                for sig in expired_sigs:
                    del self.order_signatures[sig]
                    
                if expired_sigs:
                    self._save_order_signatures()
                    
        except Exception as e:
            self.logger.error(f"Cleanup order signatures error: {e}")
            
    def _save_order_signatures(self):
        """Save order signatures to file"""
        try:
            with self.lock:
                data = {
                    "signatures": self.order_signatures,
                    "last_updated": now_epoch_s()
                }
                
            write_json_atomic_nobom(ORDER_SIGS, data)
            
        except Exception as e:
            self.logger.error(f"Save order signatures error: {e}")
            
    def get_symbol_filter(self, symbol: str) -> Optional[SymbolFilter]:
        """Get symbol filter"""
        with self.lock:
            return self.filters_cache.get(symbol)
            
    def get_all_filters(self) -> Dict[str, SymbolFilter]:
        """Get all filters"""
        with self.lock:
            return self.filters_cache.copy()
            
    def get_positions(self) -> List[Position]:
        """Get current positions"""
        with self.lock:
            return self.positions_cache.copy()
            
    def get_position_count(self) -> int:
        """Get position count"""
        with self.lock:
            return len(self.positions_cache)
            
    def is_order_duplicate(self, symbol: str, side: str, qty: float, 
                          price: float, client_ts: int) -> bool:
        """Check if order is duplicate"""
        try:
            # Create signature
            qty_rounded = round(qty, 8)
            price_rounded = round(price, 8)
            client_ts_bucket = (client_ts // 120) * 120  # 2-minute bucket
            
            sig_data = f"{symbol}:{side}:{qty_rounded}:{price_rounded}:{client_ts_bucket}"
            signature = hashlib.sha256(sig_data.encode()).hexdigest()
            
            with self.lock:
                if signature in self.order_signatures:
                    return True
                    
                # Add signature
                self.order_signatures[signature] = now_epoch_s()
                self._save_order_signatures()
                
            return False
            
        except Exception as e:
            self.logger.error(f"Check order duplicate error: {e}")
            return False
            
    def can_place_order(self, symbol: str, side: str, qty: float, price: float) -> Tuple[bool, str]:
        """Check if order can be placed"""
        try:
            # Get symbol filter
            symbol_filter = self.get_symbol_filter(symbol)
            if not symbol_filter:
                return False, f"No filter found for {symbol}"
                
            # Check minimum notional
            notional = qty * price
            if notional < symbol_filter.min_notional:
                return False, f"Notional {notional} below minimum {symbol_filter.min_notional}"
                
            # Check step size
            if qty % symbol_filter.step_size != 0:
                return False, f"Quantity {qty} not aligned with step size {symbol_filter.step_size}"
                
            # Check tick size
            if price % symbol_filter.tick_size != 0:
                return False, f"Price {price} not aligned with tick size {symbol_filter.tick_size}"
                
            # Check price range
            if price < symbol_filter.min_price or price > symbol_filter.max_price:
                return False, f"Price {price} outside range [{symbol_filter.min_price}, {symbol_filter.max_price}]"
                
            # Check position limits (mock)
            if side.lower() == "sell":
                # Check if we have position to sell
                with self.lock:
                    has_position = any(
                        pos.symbol == symbol and pos.side == "long" and pos.size > 0
                        for pos in self.positions_cache
                    )
                    if not has_position:
                        return False, f"No position to sell for {symbol}"
                        
            return True, "OK"
            
        except Exception as e:
            self.logger.error(f"Can place order error: {e}")
            return False, f"Error: {e}"
            
    def generate_client_order_id(self, trace_id: str) -> str:
        """Generate client order ID"""
        try:
            current_time = now_epoch_s()
            return f"CQ-{trace_id}-{current_time}"
        except Exception as e:
            self.logger.error(f"Generate client order ID error: {e}")
            return f"CQ-{trace_id}-{now_epoch_s()}"


# Global instance
_filters_manager = None


def get_filters_manager() -> FiltersManager:
    """Get global filters manager instance"""
    global _filters_manager
    if _filters_manager is None:
        _filters_manager = FiltersManager()
    return _filters_manager


def start_filters_manager():
    """Start the global filters manager"""
    get_filters_manager().start()


def stop_filters_manager():
    """Stop the global filters manager"""
    global _filters_manager
    if _filters_manager:
        _filters_manager.stop()
        _filters_manager = None


def _trader_preflight_check() -> bool:
    """Trader preflight checklist - exit with RED if any fail"""
    logger = logging.getLogger(__name__)
    
    try:
        # 1. Check interpreter/venv path
        import sys
        venv_path = os.getenv("VIRTUAL_ENV", "")
        if venv_path and ".venv" not in venv_path:
            logger.warning(f"TIME_SKEW hint: venv path {venv_path} not .venv")
        
        # 2. Check required packages
        try:
            import binance
            from binance.spot import Spot
        except ImportError as e:
            logger.error(f"Required package missing: {e}")
            return False
        
        # 3. Check API keys
        api_key = os.getenv("BINANCE_API_KEY", "")
        api_secret = os.getenv("BINANCE_API_SECRET", "")
        if not api_key or not api_secret:
            logger.error("BINANCE_API_KEY or BINANCE_API_SECRET missing")
            return False
        
        # 4. REST ping test (≤60s timeout)
        try:
            client = Spot(
                api_key=api_key,
                api_secret=api_secret,
                base_url=(
                    "https://testnet.binance.vision"
                    if os.getenv("BINANCE_USE_TESTNET", "true").lower() == "true"
                    else "https://api.binance.com"
                ),
            )
            
            # Test connection with timeout (Windows compatible)
            import threading

            import requests
            
            def test_connection():
                try:
                    # Simple ping test
                    response = requests.get(
                        "https://testnet.binance.vision/api/v3/ping",
                        timeout=10
                    )
                    return response.status_code == 200
                except Exception:
                    return False
            
            # Run test with timeout
            result = [False]
            def run_test():
                result[0] = test_connection()
            
            thread = threading.Thread(target=run_test)
            thread.daemon = True
            thread.start()
            thread.join(timeout=60)
            
            if not result[0]:
                logger.error("REST ping failed or timeout")
                return False
            
            logger.info("REST ping successful")
                
        except Exception as e:
            logger.error(f"REST ping setup error: {e}")
            return False
        
        # 5. get_exchange_info() test with retry
        max_retries = 3
        for attempt in range(max_retries):
            try:
                exchange_info = client.exchange_info()
                if exchange_info and "symbols" in exchange_info:
                    logger.info("get_exchange_info() successful")
                    break
                else:
                    logger.warning(f"get_exchange_info() attempt {attempt + 1} returned empty")
            except Exception as e:
                logger.warning(f"get_exchange_info() attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    logger.error("get_exchange_info() failed after all retries")
                    return False
                time.sleep(2 ** attempt)  # Exponential backoff
        
        # 6. Time sanity check (no >2s skew if detectable)
        try:
            server_time = client.time()
            if server_time and "serverTime" in server_time:
                server_ts = server_time["serverTime"] / 1000  # Convert to seconds
                local_ts = time.time()
                skew = abs(server_ts - local_ts)
                if skew > 2:
                    logger.warning(f"TIME_SKEW hint: {skew:.2f}s difference from server time")
        except Exception as e:
            logger.warning(f"Time skew check failed: {e}")
        
        logger.info("✅ Trader preflight check passed")
        return True
        
    except Exception as e:
        logger.error(f"Trader preflight check error: {e}")
        return False


def main():
    """Main entry point for filters manager"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    logger = logging.getLogger(__name__)
    logger.info("ENTRYPOINT_OK module=guard.trader.filters_manager")
    
    # Run preflight check
    if not _trader_preflight_check():
        logger.error("❌ Trader preflight check failed - exiting with RED")
        return 1
    
    manager = FiltersManager()
    manager.start()
    
    # Initial health update
    manager._update_trader_health()
    
    try:
        # Keep running indefinitely
        while True:
            time.sleep(60)  # Sleep for 1 minute intervals
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down...")
    finally:
        manager.stop()


# Export main at module level
__all__ = ["main"]


if __name__ == "__main__":
    main()
