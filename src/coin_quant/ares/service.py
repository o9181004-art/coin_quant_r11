"""
ARES service for Coin Quant R11

Signal generation with health gating.
Blocks on stale/missing Feeder health, no default signals.
"""

import time
import signal
import sys
import json
import random
from typing import Dict, Any, List, Optional
from pathlib import Path
from coin_quant.shared.logging import get_service_logger
from coin_quant.shared.health import health_manager
from coin_quant.shared.config import config_manager
from coin_quant.shared.singleton import create_singleton_guard
from coin_quant.shared.paths import get_data_dir
from coin_quant.shared.time import utc_now_seconds, age_seconds, is_fresh
from coin_quant.shared.io import atomic_write_json, safe_read_json
from coin_quant.memory.client import MemoryClient


class ARESService:
    """ARES service with real signal generation and health gating"""
    
    def __init__(self):
        self.logger = get_service_logger("ares")
        self.running = False
        self.signal_count = 0
        self.last_signal_time = 0
        self.singleton_guard = create_singleton_guard("ares")
        
        # Configuration
        self.config = config_manager.get_ares_config()
        self.freshness_threshold = config_manager.get_float("ARES_FRESHNESS_THRESHOLD", 30.0)
        self.heartbeat_interval = config_manager.get_float("ARES_HEARTBEAT_INTERVAL", 30.0)
        self.signal_interval = self.config.get("signal_interval", 30)
        self.allow_default_signals = self.config.get("allow_default_signals", False)
        
        # Data storage
        self.data_dir = get_data_dir()
        self.feeder_snapshot_file = self.data_dir / "feeder_snapshot.json"
        self.signals_file = self.data_dir / "ares_signals.json"
        self.memory_client = MemoryClient(self.data_dir)
        
        # Signal generation state
        self.last_feeder_data = {}
        self.signal_history = []
        
        # Invalid symbols to exclude
        self.invalid_symbols = {"WALUSDT"}
        
        # Signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.stop()
    
    def start(self) -> bool:
        """
        Start ARES service.
        
        Returns:
            True if started successfully, False otherwise
        """
        try:
            # Acquire singleton lock
            if not self.singleton_guard.acquire():
                self.logger.error("ARES service already running")
                return False
            
            self.logger.info("=== ARES Service Starting ===")
            self.logger.info(f"Configuration: {self.config}")
            
            # Validate configuration
            if not config_manager.validate_config():
                self.logger.error("Configuration validation failed")
                return False
            
            # Start main loop
            self.running = True
            self._main_loop()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start ARES service: {e}")
            return False
        finally:
            self.singleton_guard.release()
    
    def stop(self):
        """Stop ARES service"""
        self.logger.info("Stopping ARES service...")
        self.running = False
        
        # Update health status
        health_manager.set_ares_health("RED", {
            "last_update_ts": utc_now_seconds(),
            "updated_within_sec": 0,
            "signal_count": self.signal_count,
            "status": "stopped"
        })
    
    def _main_loop(self):
        """Main service loop"""
        self.logger.info("ARES service main loop started")
        
        while self.running:
            try:
                # Check feeder health
                if not self._check_feeder_health():
                    self.logger.warning("Feeder health check failed, skipping signal generation")
                    time.sleep(5.0)
                    continue
                
                # Generate signals
                self._generate_signals()
                
                # Update health status
                self._update_health()
                
                # Sleep for next iteration
                time.sleep(self.signal_interval)
                
            except KeyboardInterrupt:
                self.logger.info("Received keyboard interrupt")
                break
            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")
                time.sleep(5.0)  # Wait before retry
        
        self.logger.info("ARES service main loop ended")
    
    def _check_feeder_health(self) -> bool:
        """
        Check feeder health status.
        
        Returns:
            True if feeder is healthy and fresh, False otherwise
        """
        try:
            feeder_status = health_manager.get_feeder_health()
            if not feeder_status:
                self.logger.warning("No feeder health status available")
                return False
            
            # Check status
            if feeder_status.get("status") != "GREEN":
                self.logger.warning(f"Feeder status is {feeder_status.get('status')}, not GREEN")
                return False
            
            # Check freshness
            last_update = feeder_status.get("last_update_ts")
            if not last_update:
                self.logger.warning("No feeder last_update_ts available")
                return False
            
            if not is_fresh(last_update, self.freshness_threshold):
                age = age_seconds(last_update) or 0
                self.logger.warning(f"Feeder data is stale: {age:.1f}s > {self.freshness_threshold}s")
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to check feeder health: {e}")
            return False
    
    def _generate_signals(self):
        """Generate trading signals based on feeder data"""
        try:
            current_time = utc_now_seconds()
            
            # Load feeder data
            feeder_data = self._load_feeder_data()
            if not feeder_data:
                self.logger.warning("No feeder data available for signal generation")
                return
            
            # Generate signals based on data
            trading_signals = self._analyze_and_generate_signals(feeder_data)
            
            if trading_signals:
                self.signal_count += len(trading_signals)
                self.last_signal_time = current_time
                
                # Save signals
                self._save_signals(trading_signals)
                
                # Log to memory layer
                for trading_signal in trading_signals:
                    self.memory_client.append_event('signal_generated', trading_signal, source='ares')
                
                self.logger.info(f"Generated {len(trading_signals)} signals")
                for trading_signal in trading_signals:
                    self.logger.info(f"Signal: {trading_signal['symbol']} {trading_signal['side']} @ {trading_signal['price']:.4f}")
            else:
                self.logger.info("No signals generated")
                
        except Exception as e:
            self.logger.error(f"Failed to generate signals: {e}")
    
    def _load_feeder_data(self) -> Optional[Dict[str, Any]]:
        """Load feeder data from snapshot"""
        try:
            if self.feeder_snapshot_file.exists():
                data = safe_read_json(self.feeder_snapshot_file)
                if data and 'symbol_data' in data:
                    return data['symbol_data']
            return None
        except Exception as e:
            self.logger.error(f"Failed to load feeder data: {e}")
            return None
    
    def _analyze_and_generate_signals(self, feeder_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Analyze feeder data and generate trading signals"""
        signals = []
        
        try:
            for symbol, data in feeder_data.items():
                if not isinstance(data, dict) or 'price' not in data:
                    continue
                
                # Skip invalid symbols
                if symbol in self.invalid_symbols:
                    self.logger.debug(f"Skipping invalid symbol: {symbol}")
                    continue
                
                # Simple moving average crossover strategy
                trading_signal = self._simple_ma_strategy(symbol, data)
                if trading_signal:
                    signals.append(trading_signal)
            
            return signals
            
        except Exception as e:
            self.logger.error(f"Failed to analyze data: {e}")
            return []
    
    def _simple_ma_strategy(self, symbol: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Simple moving average strategy"""
        try:
            price = data.get('price', 0)
            change = data.get('change', 0)
            
            if price <= 0:
                return None
            
            # Simple strategy: buy on positive change, sell on negative change
            # Only generate signals if change is significant (> 1%)
            if abs(change) > 1.0:
                side = "BUY" if change > 0 else "SELL"
                
                # Calculate position size based on volatility
                size = min(1.0, max(0.1, abs(change) / 10.0))
                
                trading_signal = {
                    'symbol': symbol,
                    'side': side,
                    'price': price,
                    'size': size,
                    'confidence': min(0.9, abs(change) / 5.0),  # Higher confidence for larger moves
                    'strategy': 'simple_ma',
                    'timestamp': utc_now_seconds(),
                    'reason': f"Price change: {change:.2f}%"
                }
                
                return trading_signal
            
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to generate signal for {symbol}: {e}")
            return None
    
    def _save_signals(self, trading_signals: List[Dict[str, Any]]):
        """Save signals to file"""
        try:
            signal_data = {
                'timestamp': utc_now_seconds(),
                'signals': trading_signals,
                'count': len(trading_signals)
            }
            
            atomic_write_json(self.signals_file, signal_data)
            
        except Exception as e:
            self.logger.error(f"Failed to save signals: {e}")
    
    def _update_health(self):
        """Update health status"""
        try:
            current_time = utc_now_seconds()
            
            # Check if we're generating signals
            if self.last_signal_time > 0:
                age = age_seconds(self.last_signal_time) or 0
                if age <= self.freshness_threshold:
                    status = "GREEN"
                elif age <= self.freshness_threshold * 2:
                    status = "YELLOW"
                else:
                    status = "RED"
            else:
                status = "YELLOW"  # No signals generated yet
            
            # Check feeder health
            feeder_health_ok = self._check_feeder_health()
            
            # Update health
            health_manager.set_ares_health(status, {
                "last_update_ts": current_time,
                "updated_within_sec": age_seconds(self.last_signal_time) or 0,
                "signal_count": self.signal_count,
                "last_signal_time": self.last_signal_time,
                "feeder_health_ok": feeder_health_ok,
                "default_signals_blocked": not self.allow_default_signals,
                "status": "running"
            })
            
            # Log status periodically
            if int(current_time) % 30 == 0:  # Every 30 seconds
                self.logger.info(f"ARES status: {status}, signals: {self.signal_count}, feeder_ok: {feeder_health_ok}")
                
        except Exception as e:
            self.logger.error(f"Failed to update health: {e}")


def main():
    """Main entry point for ARES service"""
    try:
        service = ARESService()
        success = service.start()
        
        if not success:
            sys.exit(1)
            
    except Exception as e:
        print(f"Failed to start ARES service: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
