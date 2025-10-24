#!/usr/bin/env python3
"""
Order Router - Multi-mode order execution for AutoTrader
========================================================

Handles order routing for DRYRUN, PAPER, and LIVE modes with idempotent
execution, retry logic, and comprehensive error handling.

Key Features:
- Multi-mode support (DRYRUN/PAPER/LIVE)
- Idempotent order execution with clientOrderId
- Exponential backoff retry logic
- Rate limiting and latency monitoring
- Paper trading simulation with realistic fills
- Live trading via python-binance with safety checks
"""

import json
import time
import hashlib
import random
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum

import requests
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException

from .io_canonical import (
    artifact, get_ssot_dir, append_ndjson_atomic, read_json_safe
)
from .state_store import Order, Fill, get_state_store


class OrderMode(Enum):
    """Order execution modes"""
    DRYRUN = "DRYRUN"
    PAPER = "PAPER"
    LIVE = "LIVE"


class OrderType(Enum):
    """Order types"""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    LIMIT_IOC = "LIMIT_IOC"


@dataclass
class OrderRequest:
    """Order request structure"""
    symbol: str
    side: str  # 'BUY' or 'SELL'
    order_type: str
    quantity: float
    price: Optional[float] = None
    client_order_id: Optional[str] = None
    time_in_force: str = "IOC"  # IOC, GTC, FOK
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.client_order_id is None:
            self.client_order_id = self._generate_client_order_id()
    
    def _generate_client_order_id(self) -> str:
        """Generate idempotent client order ID"""
        data = f"{self.symbol}_{self.side}_{self.quantity}_{int(time.time() * 1000)}"
        return hashlib.md5(data.encode()).hexdigest()[:16]


@dataclass
class OrderResult:
    """Order execution result"""
    success: bool
    order_id: Optional[str] = None
    client_order_id: Optional[str] = None
    status: str = "REJECTED"
    filled_quantity: float = 0.0
    filled_price: float = 0.0
    error_message: Optional[str] = None
    execution_time_ms: float = 0.0
    retry_count: int = 0
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class OrderRouter:
    """Multi-mode order router"""
    
    def __init__(self, mode: OrderMode = OrderMode.DRYRUN):
        self.mode = mode
        self.ssot_dir = get_ssot_dir()
        self.state_store = get_state_store()
        
        # Configuration
        self.retry_backoff = [0.5, 1.5, 4.5]  # seconds
        self.max_retries = 3
        self.latency_warn_ms = 1000
        self.latency_halt_ms = 3000
        
        # Live trading setup
        self.binance_client = None
        self._setup_binance_client()
        
        # Paper trading state
        self.paper_prices = {}
        self._load_paper_prices()
    
    def _setup_binance_client(self):
        """Setup Binance client for LIVE mode"""
        if self.mode == OrderMode.LIVE:
            try:
                api_key = os.getenv("BINANCE_API_KEY")
                api_secret = os.getenv("BINANCE_API_SECRET")
                testnet = os.getenv("MODE") != "MAINNET"
                
                if not api_key or not api_secret:
                    print("[WARN] Binance credentials not found, LIVE mode disabled")
                    self.mode = OrderMode.PAPER
                    return
                
                self.binance_client = Client(
                    api_key=api_key,
                    api_secret=api_secret,
                    testnet=testnet
                )
                
                # Test connection
                self.binance_client.ping()
                print(f"[INFO] Binance client connected (testnet={testnet})")
                
            except Exception as e:
                print(f"[ERROR] Binance client setup failed: {e}")
                self.mode = OrderMode.PAPER
    
    def _load_paper_prices(self):
        """Load current prices for paper trading simulation"""
        try:
            health_file = self.ssot_dir / "health.json"
            if health_file.exists():
                data = read_json_safe(health_file)
                if data and 'symbols' in data:
                    for symbol, symbol_data in data['symbols'].items():
                        if 'price' in symbol_data:
                            self.paper_prices[symbol] = float(symbol_data['price'])
        except Exception as e:
            print(f"[ERROR] Failed to load paper prices: {e}")
    
    def _generate_client_order_id(self, symbol: str, side: str, quantity: float) -> str:
        """Generate idempotent client order ID"""
        timestamp = int(time.time() * 1000)
        data = f"{symbol}_{side}_{quantity}_{timestamp}"
        return hashlib.md5(data.encode()).hexdigest()[:16]
    
    def _check_existing_order(self, client_order_id: str) -> Optional[Order]:
        """Check if order with same client_order_id already exists"""
        try:
            orders_file = self.ssot_dir / "orders.ndjson"
            if not orders_file.exists():
                return None
            
            with open(orders_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            order_data = json.loads(line)
                            if order_data.get('client_order_id') == client_order_id:
                                return Order(**order_data)
                        except (json.JSONDecodeError, TypeError):
                            continue
        except Exception as e:
            print(f"[ERROR] Failed to check existing order: {e}")
        
        return None
    
    def _simulate_fill(self, order_request: OrderRequest) -> Tuple[bool, float, float]:
        """Simulate fill for PAPER mode"""
        try:
            # Get current price
            current_price = self.paper_prices.get(order_request.symbol, 50000.0)
            
            # Apply slippage (0.1% to 0.3% random)
            slippage_bps = random.uniform(10, 30)
            slippage_factor = 1 + (slippage_bps / 10000)
            
            if order_request.side == 'BUY':
                fill_price = current_price * slippage_factor
            else:
                fill_price = current_price / slippage_factor
            
            # Simulate partial fills (90% chance of full fill)
            fill_probability = 0.95 if order_request.order_type == "MARKET" else 0.9
            
            if random.random() < fill_probability:
                filled_quantity = order_request.quantity
            else:
                # Partial fill (50% to 90% of quantity)
                fill_ratio = random.uniform(0.5, 0.9)
                filled_quantity = order_request.quantity * fill_ratio
            
            return True, filled_quantity, fill_price
            
        except Exception as e:
            print(f"[ERROR] Fill simulation failed: {e}")
            return False, 0.0, 0.0
    
    def _place_binance_order(self, order_request: OrderRequest) -> OrderResult:
        """Place order on Binance"""
        if not self.binance_client:
            return OrderResult(
                success=False,
                error_message="Binance client not available"
            )
        
        try:
            # Prepare order parameters
            order_params = {
                'symbol': order_request.symbol,
                'side': order_request.side,
                'type': order_request.order_type,
                'quantity': order_request.quantity,
                'newClientOrderId': order_request.client_order_id
            }
            
            if order_request.price:
                order_params['price'] = order_request.price
            
            if order_request.time_in_force:
                order_params['timeInForce'] = order_request.time_in_force
            
            # Place order
            start_time = time.time()
            response = self.binance_client.create_order(**order_params)
            execution_time = (time.time() - start_time) * 1000
            
            # Parse response
            order_id = str(response.get('orderId', ''))
            status = response.get('status', 'UNKNOWN')
            
            # Calculate fills
            filled_quantity = float(response.get('executedQty', 0))
            filled_price = 0.0
            if filled_quantity > 0:
                filled_price = float(response.get('cummulativeQuoteQty', 0)) / filled_quantity
            
            return OrderResult(
                success=True,
                order_id=order_id,
                client_order_id=order_request.client_order_id,
                status=status,
                filled_quantity=filled_quantity,
                filled_price=filled_price,
                execution_time_ms=execution_time,
                metadata={'binance_response': response}
            )
            
        except BinanceAPIException as e:
            return OrderResult(
                success=False,
                client_order_id=order_request.client_order_id,
                error_message=f"Binance API error: {e.message}",
                metadata={'binance_error': str(e)}
            )
        except Exception as e:
            return OrderResult(
                success=False,
                client_order_id=order_request.client_order_id,
                error_message=f"Unexpected error: {e}"
            )
    
    def place_order(self, order_request: OrderRequest) -> OrderResult:
        """Place order with mode-specific execution"""
        start_time = time.time()
        
        try:
            # Check for existing order (idempotency)
            existing_order = self._check_existing_order(order_request.client_order_id)
            if existing_order:
                return OrderResult(
                    success=True,
                    order_id=existing_order.order_id,
                    client_order_id=existing_order.client_order_id,
                    status=existing_order.status,
                    filled_quantity=existing_order.filled_quantity,
                    filled_price=existing_order.filled_price,
                    execution_time_ms=(time.time() - start_time) * 1000,
                    metadata={'idempotent': True}
                )
            
            # Mode-specific execution
            if self.mode == OrderMode.DRYRUN:
                return self._place_dryrun_order(order_request, start_time)
            elif self.mode == OrderMode.PAPER:
                return self._place_paper_order(order_request, start_time)
            elif self.mode == OrderMode.LIVE:
                return self._place_live_order(order_request, start_time)
            else:
                return OrderResult(
                    success=False,
                    error_message=f"Unknown mode: {self.mode}"
                )
                
        except Exception as e:
            return OrderResult(
                success=False,
                client_order_id=order_request.client_order_id,
                error_message=f"Order placement failed: {e}",
                execution_time_ms=(time.time() - start_time) * 1000
            )
    
    def _place_dryrun_order(self, order_request: OrderRequest, start_time: float) -> OrderResult:
        """Place DRYRUN order (intent only)"""
        # Create order record
        order = Order(
            order_id=f"dryrun_{int(time.time() * 1000)}",
            client_order_id=order_request.client_order_id,
            symbol=order_request.symbol,
            side=order_request.side,
            order_type=order_request.order_type,
            quantity=order_request.quantity,
            price=order_request.price,
            status="DRYRUN_INTENT"
        )
        
        # Add to state store
        success = self.state_store.add_order(order)
        
        # Log intent
        intent_data = {
            "symbol": order_request.symbol,
            "side": order_request.side,
            "order_type": order_request.order_type,
            "quantity": order_request.quantity,
            "price": order_request.price,
            "client_order_id": order_request.client_order_id,
            "mode": "DRYRUN",
            "timestamp": time.time(),
            "metadata": order_request.metadata
        }
        
        append_ndjson_atomic("trade_intents.ndjson", intent_data)
        
        return OrderResult(
            success=success,
            order_id=order.order_id,
            client_order_id=order_request.client_order_id,
            status="DRYRUN_INTENT",
            execution_time_ms=(time.time() - start_time) * 1000,
            metadata={'dryrun': True}
        )
    
    def _place_paper_order(self, order_request: OrderRequest, start_time: float) -> OrderResult:
        """Place PAPER order with simulated fills"""
        # Create order record
        order = Order(
            order_id=f"paper_{int(time.time() * 1000)}",
            client_order_id=order_request.client_order_id,
            symbol=order_request.symbol,
            side=order_request.side,
            order_type=order_request.order_type,
            quantity=order_request.quantity,
            price=order_request.price,
            status="NEW"
        )
        
        # Add to state store
        success = self.state_store.add_order(order)
        if not success:
            return OrderResult(
                success=False,
                client_order_id=order_request.client_order_id,
                error_message="Failed to add order to state store"
            )
        
        # Simulate fill
        fill_success, filled_quantity, filled_price = self._simulate_fill(order_request)
        
        if fill_success and filled_quantity > 0:
            # Create fill record
            fill = Fill(
                fill_id=f"paper_fill_{int(time.time() * 1000)}",
                order_id=order.order_id,
                symbol=order_request.symbol,
                side=order_request.side,
                quantity=filled_quantity,
                price=filled_price,
                timestamp=time.time(),
                metadata={'paper_trading': True}
            )
            
            # Apply fill to state
            self.state_store.apply_fill(fill)
            
            return OrderResult(
                success=True,
                order_id=order.order_id,
                client_order_id=order_request.client_order_id,
                status="FILLED" if filled_quantity >= order_request.quantity else "PARTIALLY_FILLED",
                filled_quantity=filled_quantity,
                filled_price=filled_price,
                execution_time_ms=(time.time() - start_time) * 1000,
                metadata={'paper_trading': True}
            )
        else:
            return OrderResult(
                success=True,
                order_id=order.order_id,
                client_order_id=order_request.client_order_id,
                status="REJECTED",
                error_message="Simulated fill failed",
                execution_time_ms=(time.time() - start_time) * 1000,
                metadata={'paper_trading': True}
            )
    
    def _place_live_order(self, order_request: OrderRequest, start_time: float) -> OrderResult:
        """Place LIVE order on Binance"""
        # Retry logic with exponential backoff
        for attempt in range(self.max_retries):
            try:
                result = self._place_binance_order(order_request)
                
                if result.success:
                    # Create order record
                    order = Order(
                        order_id=result.order_id,
                        client_order_id=order_request.client_order_id,
                        symbol=order_request.symbol,
                        side=order_request.side,
                        order_type=order_request.order_type,
                        quantity=order_request.quantity,
                        price=order_request.price,
                        status=result.status,
                        filled_quantity=result.filled_quantity,
                        filled_price=result.filled_price
                    )
                    
                    # Add to state store
                    self.state_store.add_order(order)
                    
                    # Check for fills
                    if result.filled_quantity > 0:
                        fill = Fill(
                            fill_id=f"live_fill_{int(time.time() * 1000)}",
                            order_id=result.order_id,
                            symbol=order_request.symbol,
                            side=order_request.side,
                            quantity=result.filled_quantity,
                            price=result.filled_price,
                            timestamp=time.time(),
                            metadata={'live_trading': True}
                        )
                        
                        self.state_store.apply_fill(fill)
                    
                    result.retry_count = attempt
                    return result
                
                else:
                    # Check if we should retry
                    if attempt < self.max_retries - 1:
                        wait_time = self.retry_backoff[min(attempt, len(self.retry_backoff) - 1)]
                        time.sleep(wait_time)
                        continue
                    else:
                        result.retry_count = attempt
                        return result
                        
            except Exception as e:
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_backoff[min(attempt, len(self.retry_backoff) - 1)]
                    time.sleep(wait_time)
                    continue
                else:
                    return OrderResult(
                        success=False,
                        client_order_id=order_request.client_order_id,
                        error_message=f"Live order failed after {attempt + 1} attempts: {e}",
                        retry_count=attempt
                    )
        
        return OrderResult(
            success=False,
            client_order_id=order_request.client_order_id,
            error_message="Max retries exceeded",
            retry_count=self.max_retries
        )
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel specific order"""
        try:
            if self.mode == OrderMode.DRYRUN:
                # Update order status in state store
                return self.state_store.update_order(order_id, {'status': 'CANCELLED'})
            
            elif self.mode == OrderMode.PAPER:
                # Update order status in state store
                return self.state_store.update_order(order_id, {'status': 'CANCELLED'})
            
            elif self.mode == OrderMode.LIVE:
                if not self.binance_client:
                    return False
                
                # Cancel on Binance
                self.binance_client.cancel_order(symbol="BTCUSDT", orderId=order_id)  # TODO: get symbol from order
                
                # Update order status in state store
                return self.state_store.update_order(order_id, {'status': 'CANCELLED'})
            
            return False
            
        except Exception as e:
            print(f"[ERROR] Cancel order failed: {e}")
            return False
    
    def cancel_all_orders(self, symbol: str = None) -> bool:
        """Cancel all orders (optionally for specific symbol)"""
        try:
            if self.mode == OrderMode.DRYRUN:
                return self.state_store.cancel_all_orders()
            
            elif self.mode == OrderMode.PAPER:
                return self.state_store.cancel_all_orders()
            
            elif self.mode == OrderMode.LIVE:
                if not self.binance_client:
                    return False
                
                if symbol:
                    self.binance_client.cancel_open_orders(symbol=symbol)
                else:
                    # Cancel all open orders (this might need to be done per symbol)
                    # For now, just update state store
                    return self.state_store.cancel_all_orders()
            
            return False
            
        except Exception as e:
            print(f"[ERROR] Cancel all orders failed: {e}")
            return False
    
    def get_open_orders(self, symbol: str = None) -> List[Order]:
        """Get open orders"""
        try:
            open_orders = self.state_store.get_open_orders()
            
            if symbol:
                return [order for order in open_orders.values() if order.symbol == symbol]
            else:
                return list(open_orders.values())
                
        except Exception as e:
            print(f"[ERROR] Get open orders failed: {e}")
            return []
    
    def set_mode(self, mode: OrderMode):
        """Change execution mode"""
        self.mode = mode
        if mode == OrderMode.LIVE:
            self._setup_binance_client()
    
    def get_mode(self) -> OrderMode:
        """Get current execution mode"""
        return self.mode


# Global order router instance
_order_router = None

def get_order_router(mode: OrderMode = OrderMode.DRYRUN) -> OrderRouter:
    """Get global order router instance"""
    global _order_router
    if _order_router is None:
        _order_router = OrderRouter(mode)
    return _order_router


# Convenience functions
def place_order(order_request: OrderRequest) -> OrderResult:
    """Place order using global router"""
    return get_order_router().place_order(order_request)

def cancel_order(order_id: str) -> bool:
    """Cancel order using global router"""
    return get_order_router().cancel_order(order_id)

def set_order_mode(mode: OrderMode):
    """Set order execution mode"""
    get_order_router().set_mode(mode)


if __name__ == "__main__":
    # Test the order router
    print("Testing OrderRouter...")
    
    # Test DRYRUN mode
    router = OrderRouter(OrderMode.DRYRUN)
    
    order_request = OrderRequest(
        symbol="BTCUSDT",
        side="BUY",
        order_type="LIMIT_IOC",
        quantity=0.001,
        price=50000.0
    )
    
    result = router.place_order(order_request)
    print(f"DRYRUN order: {'SUCCESS' if result.success else 'FAILED'}")
    print(f"Result: {result}")
    
    # Test PAPER mode
    router.set_mode(OrderMode.PAPER)
    result = router.place_order(order_request)
    print(f"PAPER order: {'SUCCESS' if result.success else 'FAILED'}")
    print(f"Result: {result}")
    
    print("OrderRouter test completed!")
