"""
Feeder service for Coin Quant R11

Multi-symbol data ingestion with self-healing capabilities.
Publishes health status and maintains data freshness.
"""

import time
import signal
import sys
import json
import asyncio
import websockets
from typing import Dict, Any
from coin_quant.shared.logging import get_service_logger
from coin_quant.shared.health import health_manager
from coin_quant.shared.config import config_manager
from coin_quant.shared.singleton import create_singleton_guard
from coin_quant.shared.paths import get_data_dir
from coin_quant.shared.time import utc_now_seconds, age_seconds
from coin_quant.shared.io import atomic_write_json
from coin_quant.memory.client import MemoryClient


class FeederService:
    """Feeder service with real market data ingestion"""
    
    def __init__(self):
        self.logger = get_service_logger("feeder")
        self.running = False
        self.symbols = []
        self.last_update = 0
        self.ws_connected = False
        self.rest_api_ok = False
        self.singleton_guard = create_singleton_guard("feeder")
        
        # Configuration
        self.config = config_manager.get_feeder_config()
        self.freshness_threshold = config_manager.get_float("FEEDER_FRESHNESS_THRESHOLD", 30.0)
        self.heartbeat_interval = config_manager.get_float("FEEDER_HEARTBEAT_INTERVAL", 5.0)
        self.use_testnet = config_manager.get_bool("BINANCE_USE_TESTNET", True)
        
        # WebSocket configuration
        if self.use_testnet:
            self.ws_url = "wss://testnet.binance.vision/ws"
            self.rest_url = "https://testnet.binance.vision"
        else:
            self.ws_url = "wss://stream.binance.com:9443/ws"
            self.rest_url = "https://api.binance.com"
        
        # Data storage
        self.data_dir = get_data_dir()
        self.snapshot_file = self.data_dir / "feeder_snapshot.json"
        self.symbol_data = {}
        self.memory_client = MemoryClient(self.data_dir)
        
        # Signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.stop()
    
    def start(self) -> bool:
        """
        Start feeder service.
        
        Returns:
            True if started successfully, False otherwise
        """
        try:
            # Acquire singleton lock
            if not self.singleton_guard.acquire():
                self.logger.error("Feeder service already running")
                return False
            
            self.logger.info("=== Feeder Service Starting ===")
            self.logger.info(f"Configuration: {self.config}")
            
            # Validate configuration
            if not config_manager.validate_config():
                self.logger.error("Configuration validation failed")
                return False
            
            # Initialize symbols
            self._initialize_symbols()
            
            # Start main loop
            self.running = True
            self._main_loop()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start feeder service: {e}")
            return False
        finally:
            self.singleton_guard.release()
    
    def stop(self):
        """Stop feeder service"""
        self.logger.info("Stopping feeder service...")
        self.running = False
        self.ws_connected = False
        
        # Update health status
        health_manager.set_component_status("feeder", "RED", {
            "last_update_ts": utc_now_seconds(),
            "updated_within_sec": 0,
            "symbols_count": 0,
            "ws_connected": False,
            "rest_api_ok": False,
            "status": "stopped"
        })
    
    def _initialize_symbols(self):
        """Initialize symbol list"""
        # Default symbols for testing
        default_symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT", "SOLUSDT", "XRPUSDT"]
        
        # Load from configuration if available
        universe_top_n = self.config.get("top_n", 5)
        self.symbols = default_symbols[:universe_top_n]
        
        self.logger.info(f"Initialized {len(self.symbols)} symbols: {self.symbols}")
    
    def _main_loop(self):
        """Main service loop with WebSocket connection"""
        self.logger.info("Feeder service main loop started")
        
        # Start WebSocket connection
        try:
            asyncio.run(self._websocket_loop())
        except Exception as e:
            self.logger.error(f"WebSocket loop failed: {e}")
        
        self.logger.info("Feeder service main loop ended")
    
    async def _websocket_loop(self):
        """WebSocket connection loop"""
        retry_count = 0
        max_retries = 5
        
        while self.running and retry_count < max_retries:
            try:
                # Build WebSocket URL for multiple symbols
                streams = [f"{symbol.lower()}@ticker" for symbol in self.symbols]
                stream_names = "/".join(streams)
                ws_url = f"{self.ws_url}/{stream_names}"
                
                self.logger.info(f"Connecting to WebSocket: {ws_url}")
                
                async with websockets.connect(ws_url) as websocket:
                    self.ws_connected = True
                    self.logger.info("WebSocket connected successfully")
                    
                    # Reset retry count on successful connection
                    retry_count = 0
                    
                    # Start health update task
                    health_task = asyncio.create_task(self._health_update_loop())
                    
                    try:
                        # Process messages
                        async for message in websocket:
                            if not self.running:
                                break
                            
                            try:
                                data = json.loads(message)
                                await self._process_ticker_data(data)
                            except json.JSONDecodeError as e:
                                self.logger.error(f"Failed to parse WebSocket message: {e}")
                            except Exception as e:
                                self.logger.error(f"Error processing message: {e}")
                    
                    finally:
                        health_task.cancel()
                        try:
                            await health_task
                        except asyncio.CancelledError:
                            pass
                    
            except websockets.exceptions.ConnectionClosed:
                self.logger.warning("WebSocket connection closed")
                self.ws_connected = False
                retry_count += 1
            except Exception as e:
                self.logger.error(f"WebSocket error: {e}")
                self.ws_connected = False
                retry_count += 1
            
            if retry_count < max_retries:
                wait_time = min(2 ** retry_count, 30)  # Exponential backoff, max 30s
                self.logger.info(f"Retrying connection in {wait_time}s (attempt {retry_count + 1}/{max_retries})")
                await asyncio.sleep(wait_time)
            else:
                self.logger.error("Max retries reached, stopping WebSocket connection")
                break
    
    async def _health_update_loop(self):
        """Periodic health update loop"""
        while self.running:
            try:
                self._update_health()
                await asyncio.sleep(self.heartbeat_interval)
            except Exception as e:
                self.logger.error(f"Health update error: {e}")
                await asyncio.sleep(5.0)
    
    async def _process_ticker_data(self, data: Dict[str, Any]):
        """Process ticker data from WebSocket"""
        try:
            if 'stream' in data and 'data' in data:
                stream_name = data['stream']
                ticker_data = data['data']
                
                # Extract symbol from stream name (e.g., "btcusdt@ticker" -> "BTCUSDT")
                symbol = stream_name.split('@')[0].upper()
                
                # Process ticker data
                processed_data = {
                    'symbol': symbol,
                    'price': float(ticker_data.get('c', 0)),  # Close price
                    'volume': float(ticker_data.get('v', 0)),  # Volume
                    'change': float(ticker_data.get('P', 0)),  # Price change percent
                    'timestamp': int(ticker_data.get('E', 0)),  # Event time
                    'received_at': utc_now_seconds()
                }
                
                # Store data
                self.symbol_data[symbol] = processed_data
                self.last_update = utc_now_seconds()
                
                # Save snapshot
                self._save_snapshot()
                
                # Log to memory layer
                self.memory_client.append_event('ticker_update', {
                    'symbol': symbol,
                    'price': processed_data['price'],
                    'volume': processed_data['volume'],
                    'timestamp': processed_data['timestamp']
                }, source='feeder')
                
                self.logger.debug(f"Updated {symbol}: ${processed_data['price']:.4f}")
                
        except Exception as e:
            self.logger.error(f"Failed to process ticker data: {e}")
    
    def _save_snapshot(self):
        """Save current data snapshot"""
        try:
            snapshot = {
                'timestamp': utc_now_seconds(),
                'symbols': self.symbols,
                'symbol_data': self.symbol_data,
                'ws_connected': self.ws_connected,
                'rest_api_ok': self.rest_api_ok,
                'last_update': self.last_update
            }
            
            atomic_write_json(self.snapshot_file, snapshot)
            
        except Exception as e:
            self.logger.error(f"Failed to save snapshot: {e}")
    
    def _update_health(self):
        """Update health status"""
        try:
            current_time = utc_now_seconds()
            age = age_seconds(self.last_update) or 0
            
            # Determine status based on freshness and connection
            if self.ws_connected and age <= self.freshness_threshold:
                status = "GREEN"
            elif self.ws_connected and age <= self.freshness_threshold * 2:
                status = "YELLOW"
            else:
                status = "RED"
            
            # Update health
            health_manager.set_component_status("feeder", status, {
                "last_update_ts": self.last_update,
                "updated_within_sec": age,
                "symbols_count": len(self.symbols),
                "ws_connected": self.ws_connected,
                "rest_api_ok": self.rest_api_ok,
                "freshness_threshold": self.freshness_threshold,
                "status": "running"
            })
            
            # Log status periodically
            if int(current_time) % 30 == 0:  # Every 30 seconds
                self.logger.info(f"Feeder status: {status}, age: {age:.1f}s, symbols: {len(self.symbols)}, ws: {self.ws_connected}")
                
        except Exception as e:
            self.logger.error(f"Failed to update health: {e}")


def main():
    """Main entry point for feeder service"""
    try:
        service = FeederService()
        success = service.start()
        
        if not success:
            sys.exit(1)
            
    except Exception as e:
        print(f"Failed to start feeder service: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
