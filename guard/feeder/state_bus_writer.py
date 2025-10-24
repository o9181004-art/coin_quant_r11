#!/usr/bin/env python3
"""
State Bus Writer - SSOT for system state
Writes STATE_BUS every 5 seconds with epoch seconds timestamps
"""

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List

from shared.io.jsonio import (ensure_epoch_seconds, now_epoch_s,
                              write_json_atomic_nobom)
from shared.io.symbol_utils import normalize_symbols
from shared.paths import STATE_BUS, ensure_all_dirs


class StateBusWriter:
    """State Bus Writer - Single Source of Truth for system state"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.running = False
        self.thread = None
        
        # Ensure directories exist
        ensure_all_dirs()
        
        # Load ACTIVE_SYMBOLS from .env and normalize to uppercase
        self.active_symbols = normalize_symbols(self._load_active_symbols())
        
        # State data
        self.state_data = {
            "prices": {
                "age_s": 0,
                "last_ts": 0,
                "symbols": self.active_symbols
            },
            "ares": {
                "candidate_age_s": 0,
                "last_ts": 0
            },
            "trader": {
                "positions_age_s": 0,
                "last_ts": 0
            },
            "health": {
                "dor": False,
                "failing_components": []
            }
        }
        
        # Logging control
        self.last_log_time = 0
        self.log_interval = 30  # Log every 30 seconds for symbols
        self.symbols_log_time = 0
        
    def _load_active_symbols(self) -> List[str]:
        """Load ACTIVE_SYMBOLS from .env and uppercase them"""
        try:
            # Try to load from .env file first
            env_file = Path(".env")
            if env_file.exists():
                with open(env_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("ACTIVE_SYMBOLS="):
                            symbols_str = line.split("=", 1)[1].strip()
                            if symbols_str:
                                symbols = [s.strip().upper() for s in symbols_str.split(",") if s.strip()]
                                self.logger.info(f"Loaded symbols from .env: {symbols}")
                                return symbols
            
            # Fallback to environment variable
            symbols_str = os.getenv("ACTIVE_SYMBOLS", "BTCUSDT,ETHUSDT,SOLUSDT")
            symbols = [s.strip().upper() for s in symbols_str.split(",") if s.strip()]
            self.logger.info(f"Loaded symbols from env: {symbols}")
            return symbols
            
        except Exception as e:
            self.logger.error(f"Error loading ACTIVE_SYMBOLS: {e}")
            # Default fallback
            default_symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
            self.logger.info(f"Using default symbols: {default_symbols}")
            return default_symbols
        
    def start(self):
        """Start the state bus writer"""
        if self.running:
            self.logger.warning("State bus writer already running")
            return
            
        self.running = True
        self.thread = threading.Thread(target=self._write_loop, daemon=True)
        self.thread.start()
        self.logger.info("State bus writer started")
        
    def stop(self):
        """Stop the state bus writer"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        self.logger.info("State bus writer stopped")
        
    def _write_loop(self):
        """Main write loop - runs every 5 seconds"""
        while self.running:
            try:
                self._update_state()
                self._write_state_bus()
                self._log_status()
                
                # Wait 5 seconds
                time.sleep(5)
                
            except Exception as e:
                # Log crash evidence
                from shared.crash_evidence import log_crash
                log_crash(e, "State bus write loop", f"state_bus_{now_epoch_s()}")
                time.sleep(5)
                
    def _update_state(self):
        """Update state data from various sources"""
        try:
            current_time = now_epoch_s()
            
            # Update prices state
            self._update_prices_state(current_time)
            
            # Update ARES state
            self._update_ares_state(current_time)
            
            # Update trader state
            self._update_trader_state(current_time)
            
            # Update health state
            self._update_health_state(current_time)
            
        except Exception as e:
            self.logger.error(f"State update error: {e}")
            
    def _update_prices_state(self, current_time: int):
        """Update prices state from feeder data"""
        try:
            # Get active symbols and normalize to uppercase
            from shared.paths import get_active_symbols
            symbols = normalize_symbols(get_active_symbols())
            self.state_data["prices"]["symbols"] = symbols
            
            # Check for price data files
            from shared.paths import SHARED_DATA
            snapshots_dir = SHARED_DATA / "snapshots"
            
            if snapshots_dir.exists():
                price_files = list(snapshots_dir.glob("prices_*.json"))
                last_ts = 0
                
                for price_file in price_files:
                    try:
                        import json
                        with open(price_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            
                        file_ts = data.get('last_update', 0)
                        if file_ts > last_ts:
                            last_ts = file_ts
                            
                    except Exception as e:
                        self.logger.debug(f"Error reading price file {price_file}: {e}")
                        continue
                
                # Convert milliseconds to seconds if needed
                if last_ts > 1e10:
                    last_ts = last_ts // 1000
                    
                self.state_data["prices"]["last_ts"] = last_ts
                self.state_data["prices"]["age_s"] = current_time - last_ts if last_ts > 0 else 999
            else:
                # No snapshots directory - use current time
                self.state_data["prices"]["last_ts"] = current_time
                self.state_data["prices"]["age_s"] = 0
                
        except Exception as e:
            self.logger.error(f"Prices state update error: {e}")
            
    def _update_ares_state(self, current_time: int):
        """Update ARES state from candidates file"""
        try:
            from shared.io.jsonio import get_last_ndjson_line
            from shared.paths import CANDIDATES
            
            if CANDIDATES.exists():
                last_candidate = get_last_ndjson_line(CANDIDATES)
                if last_candidate and 'timestamp' in last_candidate:
                    last_ts = ensure_epoch_seconds(last_candidate['timestamp'])
                    self.state_data["ares"]["last_ts"] = last_ts
                    self.state_data["ares"]["candidate_age_s"] = current_time - last_ts
                else:
                    self.state_data["ares"]["last_ts"] = 0
                    self.state_data["ares"]["candidate_age_s"] = 999
            else:
                self.state_data["ares"]["last_ts"] = 0
                self.state_data["ares"]["candidate_age_s"] = 999
                
        except Exception as e:
            self.logger.error(f"ARES state update error: {e}")
            
    def _update_trader_state(self, current_time: int):
        """Update trader state from positions file"""
        try:
            from shared.io.jsonio import read_json_nobom
            from shared.paths import POSITIONS
            
            if POSITIONS.exists():
                positions_data = read_json_nobom(POSITIONS, {})
                if positions_data and 'timestamp' in positions_data:
                    last_ts = ensure_epoch_seconds(positions_data['timestamp'])
                    self.state_data["trader"]["last_ts"] = last_ts
                    self.state_data["trader"]["positions_age_s"] = current_time - last_ts
                else:
                    self.state_data["trader"]["last_ts"] = 0
                    self.state_data["trader"]["positions_age_s"] = 999
            else:
                self.state_data["trader"]["last_ts"] = 0
                self.state_data["trader"]["positions_age_s"] = 999
                
        except Exception as e:
            self.logger.error(f"Trader state update error: {e}")
            
    def _update_health_state(self, current_time: int):
        """Update health state from health check results"""
        try:
            from shared.io.jsonio import read_json_nobom
            from shared.paths import HEALTH_V2
            
            if HEALTH_V2.exists():
                health_data = read_json_nobom(HEALTH_V2, {})
                if health_data:
                    self.state_data["health"]["dor"] = health_data.get("dor", False)
                    self.state_data["health"]["failing_components"] = health_data.get("failing_components", [])
                else:
                    self.state_data["health"]["dor"] = False
                    self.state_data["health"]["failing_components"] = ["health_check_missing"]
            else:
                self.state_data["health"]["dor"] = False
                self.state_data["health"]["failing_components"] = ["health_check_missing"]
                
        except Exception as e:
            self.logger.error(f"Health state update error: {e}")
            
    def _write_state_bus(self):
        """Write state bus to file"""
        try:
            # Ensure all timestamps are UTC epoch seconds
            current_time = now_epoch_s()
            
            # Set freshness guarantees - writer sets age_s=0
            self.state_data["prices"]["last_ts"] = current_time
            self.state_data["prices"]["age_s"] = 0
            
            # Add metadata
            state_with_meta = {
                **self.state_data,
                "meta": {
                    "version": "1.0.0",
                    "last_updated": current_time,
                    "writer": "state_bus_writer"
                }
            }
            
            # Write atomically
            write_json_atomic_nobom(STATE_BUS, state_with_meta)
            
        except Exception as e:
            self.logger.error(f"State bus write error: {e}")
            
    def _log_status(self):
        """Log status every 30 seconds"""
        try:
            current_time = time.time()
            
            # Log symbols every 30 seconds
            if current_time - self.symbols_log_time >= 30:
                symbols = self.state_data["prices"]["symbols"]
                self.logger.info(f"STATE_BUS_SYMBOLS: {symbols}")
                self.symbols_log_time = current_time
            
            # Log general status every 30 seconds
            if current_time - self.last_log_time >= self.log_interval:
                symbols_count = len(self.state_data["prices"]["symbols"])
                dor_status = "✅" if self.state_data["health"]["dor"] else "❌"
                
                self.logger.info(f"STATE_BUS_WRITE ok symbols={symbols_count} dor={dor_status}")
                self.last_log_time = current_time
                
        except Exception as e:
            self.logger.error(f"Status logging error: {e}")
            
    def get_state(self) -> Dict[str, Any]:
        """Get current state data"""
        return self.state_data.copy()
        
    def update_prices(self, symbols: List[str], last_ts: int):
        """Update prices state manually"""
        try:
            self.state_data["prices"]["symbols"] = symbols
            self.state_data["prices"]["last_ts"] = ensure_epoch_seconds(last_ts)
            self.state_data["prices"]["age_s"] = now_epoch_s() - ensure_epoch_seconds(last_ts)
        except Exception as e:
            self.logger.error(f"Manual prices update error: {e}")
            
    def update_ares(self, last_ts: int):
        """Update ARES state manually"""
        try:
            self.state_data["ares"]["last_ts"] = ensure_epoch_seconds(last_ts)
            self.state_data["ares"]["candidate_age_s"] = now_epoch_s() - ensure_epoch_seconds(last_ts)
        except Exception as e:
            self.logger.error(f"Manual ARES update error: {e}")
            
    def update_trader(self, last_ts: int):
        """Update trader state manually"""
        try:
            self.state_data["trader"]["last_ts"] = ensure_epoch_seconds(last_ts)
            self.state_data["trader"]["positions_age_s"] = now_epoch_s() - ensure_epoch_seconds(last_ts)
        except Exception as e:
            self.logger.error(f"Manual trader update error: {e}")


# Global instance
_state_bus_writer = None


def get_state_bus_writer() -> StateBusWriter:
    """Get global state bus writer instance"""
    global _state_bus_writer
    if _state_bus_writer is None:
        _state_bus_writer = StateBusWriter()
    return _state_bus_writer


def start_state_bus_writer():
    """Start the global state bus writer"""
    get_state_bus_writer().start()


def stop_state_bus_writer():
    """Stop the global state bus writer"""
    global _state_bus_writer
    if _state_bus_writer:
        _state_bus_writer.stop()
        _state_bus_writer = None


def main():
    """Main entry point for state bus writer"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    logger = logging.getLogger(__name__)
    logger.info("ENTRYPOINT_OK module=guard.feeder.state_bus_writer")
    
    writer = StateBusWriter()
    writer.start()
    
    try:
        # Keep running indefinitely
        while True:
            time.sleep(60)  # Sleep for 1 minute intervals
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down...")
    finally:
        writer.stop()


# Export main at module level
__all__ = ["main"]


if __name__ == "__main__":
    main()
