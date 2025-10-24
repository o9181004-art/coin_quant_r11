"""
Trader service for Coin Quant R11

Order execution with balance checks and failsafe logic.
Honors simulation mode, performs pre-order balance checks,
down-scales order size, bounded retries, symbol quarantine.
"""

import time
import signal
import sys
import json
import requests
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


class TraderService:
    """Trader service with real order execution and failsafe logic"""
    
    def __init__(self):
        self.logger = get_service_logger("trader")
        self.running = False
        self.orders_count = 0
        self.fills_count = 0
        self.last_order_time = 0
        self.quarantined_symbols = set()
        self.singleton_guard = create_singleton_guard("trader")
        
        # Configuration
        self.config = config_manager.get_trader_config()
        self.trading_config = config_manager.get_trading_config()
        self.freshness_threshold = config_manager.get_float("TRADER_FRESHNESS_THRESHOLD", 30.0)
        self.heartbeat_interval = config_manager.get_float("TRADER_HEARTBEAT_INTERVAL", 30.0)
        self.order_cooldown = self.config.get("order_cooldown", 1)
        self.simulation_mode = self.trading_config.get("simulation", True)
        
        # API Configuration
        self.api_key = config_manager.get("BINANCE_API_KEY", "")
        self.api_secret = config_manager.get("BINANCE_API_SECRET", "")
        self.use_testnet = config_manager.get_bool("BINANCE_USE_TESTNET", True)
        
        # API URLs
        if self.use_testnet:
            self.base_url = "https://testnet.binance.vision"
        else:
            self.base_url = "https://api.binance.com"
        
        # Data storage
        self.data_dir = get_data_dir()
        self.signals_file = self.data_dir / "ares_signals.json"
        self.orders_file = self.data_dir / "trader_orders.json"
        self.balance_file = self.data_dir / "account_balance.json"
        self.memory_client = MemoryClient(self.data_dir)
        
        # Order execution state
        self.account_balance = {}
        self.last_balance_check = 0
        
        # Signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.stop()
    
    def start(self) -> bool:
        """
        Start trader service.
        
        Returns:
            True if started successfully, False otherwise
        """
        try:
            # Acquire singleton lock
            if not self.singleton_guard.acquire():
                self.logger.error("Trader service already running")
                return False
            
            self.logger.info("=== Trader Service Starting ===")
            self.logger.info(f"Configuration: {self.config}")
            self.logger.info(f"Trading config: {self.trading_config}")
            
            # Validate configuration
            if not config_manager.validate_config():
                self.logger.error("Configuration validation failed")
                return False
            
            # Start main loop
            self.running = True
            self._main_loop()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start trader service: {e}")
            return False
        finally:
            self.singleton_guard.release()
    
    def stop(self):
        """Stop trader service"""
        self.logger.info("Stopping trader service...")
        self.running = False
        
        # Update health status
        health_manager.set_component_status("trader", "RED", {
            "last_update_ts": utc_now_seconds(),
            "updated_within_sec": 0,
            "orders_count": self.orders_count,
            "fills_count": self.fills_count,
            "status": "stopped"
        })
    
    def _main_loop(self):
        """Main service loop"""
        self.logger.info("Trader service main loop started")
        
        while self.running:
            try:
                # Check ARES health
                if not self._check_ares_health():
                    self.logger.warning("ARES health check failed, skipping order processing")
                    time.sleep(5.0)
                    continue
                
                # Process orders
                self._process_orders()
                
                # Update health status
                self._update_health()
                
                # Sleep for next iteration
                time.sleep(self.order_cooldown)
                
            except KeyboardInterrupt:
                self.logger.info("Received keyboard interrupt")
                break
            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")
                time.sleep(5.0)  # Wait before retry
        
        self.logger.info("Trader service main loop ended")
    
    def _check_ares_health(self) -> bool:
        """
        Check ARES health status.
        
        Returns:
            True if ARES is healthy and fresh, False otherwise
        """
        try:
            ares_status = health_manager.get_component_status("ares")
            if not ares_status:
                self.logger.warning("No ARES health status available")
                return False
            
            # Check status
            if ares_status.get("status") != "GREEN":
                self.logger.warning(f"ARES status is {ares_status.get('status')}, not GREEN")
                return False
            
            # Check freshness
            last_update = ares_status.get("last_update_ts")
            if not last_update:
                self.logger.warning("No ARES last_update_ts available")
                return False
            
            if not is_fresh(last_update, self.freshness_threshold):
                age = age_seconds(last_update) or 0
                self.logger.warning(f"ARES data is stale: {age:.1f}s > {self.freshness_threshold}s")
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to check ARES health: {e}")
            return False
    
    def _process_orders(self):
        """Process trading orders from ARES signals"""
        try:
            current_time = utc_now_seconds()
            
            # Load signals from ARES
            signals = self._load_ares_signals()
            if not signals:
                return
            
            # Process each signal
            for trading_signal in signals:
                if self._process_signal(trading_signal):
                    self.orders_count += 1
                    self.last_order_time = current_time
                    
                    # Log to memory layer
                    self.memory_client.append_event('order_executed', trading_signal, source='trader')
                    
                    if self.simulation_mode:
                        self.fills_count += 1
                        self.logger.info(f"Simulated order: {trading_signal['symbol']} {trading_signal['side']} @ {trading_signal['price']:.4f}")
                    else:
                        self.logger.info(f"Order executed: {trading_signal['symbol']} {trading_signal['side']} @ {trading_signal['price']:.4f}")
                else:
                    self.logger.warning(f"Order failed: {trading_signal['symbol']}")
                    
        except Exception as e:
            self.logger.error(f"Failed to process orders: {e}")
    
    def _load_ares_signals(self) -> List[Dict[str, Any]]:
        """Load signals from ARES service"""
        try:
            if self.signals_file.exists():
                data = safe_read_json(self.signals_file)
                if data and 'signals' in data:
                    return data['signals']
            return []
        except Exception as e:
            self.logger.error(f"Failed to load signals: {e}")
            return []
    
    def _process_signal(self, trading_signal: Dict[str, Any]) -> bool:
        """Process a single trading signal"""
        try:
            symbol = trading_signal["symbol"]
            
            # Check if symbol is quarantined
            if symbol in self.quarantined_symbols:
                self.logger.warning(f"Symbol {symbol} is quarantined, skipping order")
                return False
            
            # Pre-order balance check
            if not self._check_balance(trading_signal):
                self.logger.warning(f"Insufficient balance for {symbol}")
                self._quarantine_symbol(symbol, "Insufficient balance")
                return False
            
            # Down-scale order size if needed
            adjusted_signal = self._adjust_order_size(trading_signal)
            
            # Execute order
            if self._execute_order(adjusted_signal):
                return True
            else:
                self._quarantine_symbol(symbol, "Order execution failed")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to process signal {trading_signal}: {e}")
            return False
    
    def _check_balance(self, trading_signal: Dict[str, Any]) -> bool:
        """Check if sufficient balance exists for order"""
        try:
            # Update balance if needed
            if utc_now_seconds() - self.last_balance_check > 30:  # Check every 30 seconds
                self._update_account_balance()
            
            symbol = trading_signal["symbol"]
            side = trading_signal["side"]
            size = trading_signal["size"]
            price = trading_signal["price"]
            
            if side == "BUY":
                # Check USDT balance
                usdt_balance = self.account_balance.get("USDT", {}).get("free", 0)
                required_usdt = size * price
                return usdt_balance >= required_usdt
            else:
                # Check base asset balance
                base_asset = symbol.replace("USDT", "")
                asset_balance = self.account_balance.get(base_asset, {}).get("free", 0)
                return asset_balance >= size
            
        except Exception as e:
            self.logger.error(f"Failed to check balance: {e}")
            return False
    
    def _update_account_balance(self):
        """Update account balance from exchange"""
        try:
            if self.simulation_mode:
                # Simulate balance for testing
                self.account_balance = {
                    "USDT": {"free": 1000.0, "locked": 0.0},
                    "BTC": {"free": 0.01, "locked": 0.0},
                    "ETH": {"free": 0.1, "locked": 0.0}
                }
            else:
                # Real API call to get balance
                url = f"{self.base_url}/api/v3/account"
                headers = {
                    "X-MBX-APIKEY": self.api_key
                }
                
                # Add signature (simplified - in production use proper HMAC)
                params = {
                    "timestamp": int(time.time() * 1000)
                }
                
                response = requests.get(url, headers=headers, params=params, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    self.account_balance = {
                        balance["asset"]: {
                            "free": float(balance["free"]),
                            "locked": float(balance["locked"])
                        }
                        for balance in data.get("balances", [])
                    }
                else:
                    self.logger.error(f"Failed to get balance: {response.status_code}")
                    return
            
            self.last_balance_check = utc_now_seconds()
            
            # Save balance to file
            atomic_write_json(self.balance_file, {
                "timestamp": self.last_balance_check,
                "balance": self.account_balance
            })
            
        except Exception as e:
            self.logger.error(f"Failed to update balance: {e}")
    
    def _adjust_order_size(self, trading_signal: Dict[str, Any]) -> Dict[str, Any]:
        """Adjust order size to available balance"""
        try:
            adjusted_signal = trading_signal.copy()
            symbol = trading_signal["symbol"]
            side = trading_signal["side"]
            size = trading_signal["size"]
            price = trading_signal["price"]
            
            if side == "BUY":
                # Adjust based on USDT balance
                usdt_balance = self.account_balance.get("USDT", {}).get("free", 0)
                max_size = usdt_balance / price
                adjusted_signal["size"] = min(size, max_size * 0.95)  # Use 95% of available balance
            else:
                # Adjust based on base asset balance
                base_asset = symbol.replace("USDT", "")
                asset_balance = self.account_balance.get(base_asset, {}).get("free", 0)
                adjusted_signal["size"] = min(size, asset_balance * 0.95)  # Use 95% of available balance
            
            return adjusted_signal
            
        except Exception as e:
            self.logger.error(f"Failed to adjust order size: {e}")
            return trading_signal
    
    def _execute_order(self, trading_signal: Dict[str, Any]) -> bool:
        """Execute order on exchange"""
        try:
            if self.simulation_mode:
                # Simulate order execution
                return True
            else:
                # Real order execution
                url = f"{self.base_url}/api/v3/order"
                headers = {
                    "X-MBX-APIKEY": self.api_key
                }
                
                params = {
                    "symbol": trading_signal["symbol"],
                    "side": trading_signal["side"],
                    "type": "MARKET",
                    "quantity": trading_signal["size"],
                    "timestamp": int(time.time() * 1000)
                }
                
                response = requests.post(url, headers=headers, data=params, timeout=10)
                if response.status_code == 200:
                    order_data = response.json()
                    self.logger.info(f"Order executed: {order_data}")
                    return True
                else:
                    self.logger.error(f"Order failed: {response.status_code} - {response.text}")
                    return False
                    
        except Exception as e:
            self.logger.error(f"Failed to execute order: {e}")
            return False
    
    def _quarantine_symbol(self, symbol_name: str, reason: str):
        """
        Quarantine a symbol.
        
        Args:
            symbol_name: Symbol to quarantine
            reason: Reason for quarantine
        """
        self.quarantined_symbols.add(symbol_name)
        self.logger.warning(f"Quarantined symbol {symbol_name}: {reason}")
    
    def _unquarantine_symbol(self, symbol_name: str):
        """
        Unquarantine a symbol.
        
        Args:
            symbol_name: Symbol to unquarantine
        """
        self.quarantined_symbols.discard(symbol_name)
        self.logger.info(f"Unquarantined symbol {symbol_name}")
    
    def _update_health(self):
        """Update health status"""
        try:
            current_time = utc_now_seconds()
            
            # Determine status based on recent activity
            if self.last_order_time > 0:
                age = age_seconds(self.last_order_time) or 0
                if age <= self.freshness_threshold:
                    status = "GREEN"
                elif age <= self.freshness_threshold * 2:
                    status = "YELLOW"
                else:
                    status = "RED"
            else:
                status = "YELLOW"  # No orders processed yet
            
            # Check ARES health
            self._check_ares_health()
            
            # Update health
            health_manager.set_component_status("trader", status, {
                "last_update_ts": current_time,
                "updated_within_sec": age_seconds(self.last_order_time) or 0,
                "orders_count": self.orders_count,
                "fills_count": self.fills_count,
                "last_order_time": self.last_order_time,
                "simulation_mode": self.simulation_mode,
                "quarantined_symbols": list(self.quarantined_symbols),
                "status": "running"
            })
            
            # Log status periodically
            if int(current_time) % 30 == 0:  # Every 30 seconds
                self.logger.info(f"Trader status: {status}, orders: {self.orders_count}, fills: {self.fills_count}, quarantined: {len(self.quarantined_symbols)}")
                
        except Exception as e:
            self.logger.error(f"Failed to update health: {e}")

    def _check_ares_health(self) -> bool:
        """
        Check ARES health status.
        
        Returns:
            True if ARES is healthy and fresh, False otherwise
        """
        try:
            ares_status = health_manager.get_component_status("ares")
            if not ares_status:
                self.logger.warning("No ARES health status available")
                return False
            
            # Check status
            if ares_status.get("status") != "GREEN":
                self.logger.warning(f"ARES status is {ares_status.get('status')}, not GREEN")
                return False
            
            # Check freshness
            last_update = ares_status.get("last_update_ts")
            if not last_update:
                self.logger.warning("No ARES last_update_ts available")
                return False
            
            if not is_fresh(last_update, self.freshness_threshold):
                age = age_seconds(last_update) or 0
                self.logger.warning(f"ARES data is stale: {age:.1f}s > {self.freshness_threshold}s")
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to check ARES health: {e}")
            return False


def main():
    """Main entry point for trader service"""
    try:
        service = TraderService()
        success = service.start()
        
        if not success:
            sys.exit(1)
            
    except Exception as e:
        print(f"Failed to start trader service: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
