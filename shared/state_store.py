#!/usr/bin/env python3
"""
State Store - SSOT-backed state management for AutoTrader
=========================================================

Manages positions, orders, fills, and PnL calculations with atomic writes.
All state changes are persisted to SSOT using canonical I/O.

Key Features:
- Atomic state updates with rollback capability
- Real-time PnL calculation (realized/unrealized)
- Position tracking with entry/exit history
- Order state management
- Daily PnL aggregation
"""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from decimal import Decimal, ROUND_HALF_UP

from .io_canonical import (
    artifact, get_ssot_dir, write_json_atomic, read_json_safe,
    append_ndjson_atomic
)


@dataclass
class Position:
    """Position data structure"""
    symbol: str
    side: str  # 'LONG' or 'SHORT'
    quantity: float
    entry_price: float
    entry_time: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    total_pnl: float = 0.0
    last_update: float = 0.0
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.last_update == 0.0:
            self.last_update = time.time()


@dataclass
class Order:
    """Order data structure"""
    order_id: str
    client_order_id: str
    symbol: str
    side: str  # 'BUY' or 'SELL'
    order_type: str  # 'LIMIT', 'MARKET', 'LIMIT_IOC'
    quantity: float
    price: Optional[float] = None
    status: str = 'NEW'  # NEW, PARTIALLY_FILLED, FILLED, CANCELLED, REJECTED
    filled_quantity: float = 0.0
    filled_price: float = 0.0
    timestamp: float = 0.0
    update_time: float = 0.0
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.timestamp == 0.0:
            self.timestamp = time.time()
        if self.update_time == 0.0:
            self.update_time = time.time()


@dataclass
class Fill:
    """Fill data structure"""
    fill_id: str
    order_id: str
    symbol: str
    side: str
    quantity: float
    price: float
    timestamp: float
    commission: float = 0.0
    commission_asset: str = 'USDT'
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class StateStore:
    """State management for AutoTrader"""
    
    def __init__(self):
        self.ssot_dir = get_ssot_dir()
        self.positions_file = self.ssot_dir / "positions.json"
        self.orders_file = self.ssot_dir / "orders.ndjson"
        self.fills_file = self.ssot_dir / "fills.ndjson"
        self.pnl_daily_file = self.ssot_dir / "pnl_daily.json"
        
        # In-memory state (loaded from SSOT)
        self.positions: Dict[str, Position] = {}
        self.open_orders: Dict[str, Order] = {}
        self.daily_pnl: Dict[str, float] = {}
        
        # Load initial state
        self._load_state()
    
    def _load_state(self):
        """Load state from SSOT files"""
        try:
            # Load positions
            if self.positions_file.exists():
                data = read_json_safe(self.positions_file)
                if data and 'positions' in data:
                    for symbol, pos_data in data['positions'].items():
                        self.positions[symbol] = Position(**pos_data)
            
            # Load open orders
            if self.orders_file.exists():
                with open(self.orders_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                order_data = json.loads(line)
                                if order_data.get('status') in ['NEW', 'PARTIALLY_FILLED']:
                                    order = Order(**order_data)
                                    self.open_orders[order.order_id] = order
                            except (json.JSONDecodeError, TypeError):
                                continue
            
            # Load daily PnL
            if self.pnl_daily_file.exists():
                data = read_json_safe(self.pnl_daily_file)
                if data and 'daily_pnl' in data:
                    self.daily_pnl = data['daily_pnl']
        
        except Exception as e:
            print(f"[ERROR] StateStore._load_state: {e}")
    
    def _save_positions(self):
        """Save positions to SSOT"""
        try:
            positions_data = {
                'positions': {symbol: asdict(pos) for symbol, pos in self.positions.items()},
                'last_update': time.time(),
                'position_count': len(self.positions)
            }
            return write_json_atomic("positions.json", positions_data)
        except Exception as e:
            print(f"[ERROR] StateStore._save_positions: {e}")
            return False
    
    def get_positions(self) -> Dict[str, Position]:
        """Get all current positions"""
        return self.positions.copy()
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for specific symbol"""
        return self.positions.get(symbol)
    
    def get_open_orders(self) -> Dict[str, Order]:
        """Get all open orders"""
        return self.open_orders.copy()
    
    def get_order(self, order_id: str) -> Optional[Order]:
        """Get specific order"""
        return self.open_orders.get(order_id)
    
    def add_order(self, order: Order) -> bool:
        """Add new order to state"""
        try:
            # Add to memory
            self.open_orders[order.order_id] = order
            
            # Persist to SSOT
            order_data = asdict(order)
            success = append_ndjson_atomic("orders.ndjson", order_data)
            
            if not success:
                # Rollback on failure
                self.open_orders.pop(order.order_id, None)
                return False
            
            return True
            
        except Exception as e:
            print(f"[ERROR] StateStore.add_order: {e}")
            return False
    
    def update_order(self, order_id: str, updates: Dict[str, Any]) -> bool:
        """Update existing order"""
        try:
            if order_id not in self.open_orders:
                return False
            
            order = self.open_orders[order_id]
            
            # Update fields
            for key, value in updates.items():
                if hasattr(order, key):
                    setattr(order, key, value)
            
            order.update_time = time.time()
            
            # Persist update
            order_data = asdict(order)
            success = append_ndjson_atomic("orders.ndjson", order_data)
            
            if not success:
                # Rollback - reload from SSOT
                self._load_state()
                return False
            
            # Remove from open orders if filled or cancelled
            if order.status in ['FILLED', 'CANCELLED', 'REJECTED']:
                self.open_orders.pop(order_id, None)
            
            return True
            
        except Exception as e:
            print(f"[ERROR] StateStore.update_order: {e}")
            return False
    
    def apply_fill(self, fill: Fill) -> bool:
        """Apply fill to position and order state"""
        try:
            # Update order
            order = self.open_orders.get(fill.order_id)
            if not order:
                print(f"[WARN] Fill for unknown order: {fill.order_id}")
                return False
            
            # Update order filled quantity and price
            order.filled_quantity += fill.quantity
            if order.filled_quantity > 0:
                # Update average filled price
                total_value = order.filled_price * (order.filled_quantity - fill.quantity) + fill.price * fill.quantity
                order.filled_price = total_value / order.filled_quantity
            
            # Update order status
            if order.filled_quantity >= order.quantity:
                order.status = 'FILLED'
            else:
                order.status = 'PARTIALLY_FILLED'
            
            # Update position
            self._update_position_from_fill(fill)
            
            # Persist fill
            fill_data = asdict(fill)
            success = append_ndjson_atomic("fills.ndjson", fill_data)
            
            if not success:
                # Rollback
                self._load_state()
                return False
            
            # Save updated state
            self._save_positions()
            
            return True
            
        except Exception as e:
            print(f"[ERROR] StateStore.apply_fill: {e}")
            return False
    
    def _update_position_from_fill(self, fill: Fill):
        """Update position based on fill"""
        symbol = fill.symbol
        current_pos = self.positions.get(symbol)
        
        if not current_pos:
            # Create new position
            side = 'LONG' if fill.side == 'BUY' else 'SHORT'
            self.positions[symbol] = Position(
                symbol=symbol,
                side=side,
                quantity=fill.quantity,
                entry_price=fill.price,
                entry_time=fill.timestamp
            )
        else:
            # Update existing position
            if current_pos.side == 'LONG':
                if fill.side == 'BUY':
                    # Add to long position
                    total_value = current_pos.quantity * current_pos.entry_price + fill.quantity * fill.price
                    current_pos.quantity += fill.quantity
                    current_pos.entry_price = total_value / current_pos.quantity
                else:
                    # Reduce long position
                    current_pos.quantity -= fill.quantity
                    if current_pos.quantity <= 0:
                        # Position closed
                        self.positions.pop(symbol, None)
                        return
            
            else:  # SHORT position
                if fill.side == 'SELL':
                    # Add to short position
                    total_value = current_pos.quantity * current_pos.entry_price + fill.quantity * fill.price
                    current_pos.quantity += fill.quantity
                    current_pos.entry_price = total_value / current_pos.quantity
                else:
                    # Reduce short position
                    current_pos.quantity -= fill.quantity
                    if current_pos.quantity <= 0:
                        # Position closed
                        self.positions.pop(symbol, None)
                        return
        
        # Update position metadata
        current_pos.last_update = time.time()
    
    def calc_pnl(self, symbol: str, current_price: float) -> Tuple[float, float]:
        """Calculate realized and unrealized PnL for symbol"""
        position = self.positions.get(symbol)
        if not position:
            return 0.0, 0.0
        
        # Calculate unrealized PnL
        if position.side == 'LONG':
            unrealized_pnl = (current_price - position.entry_price) * position.quantity
        else:  # SHORT
            unrealized_pnl = (position.entry_price - current_price) * position.quantity
        
        # Subtract commission (estimate 0.1%)
        unrealized_pnl *= 0.999
        
        return position.realized_pnl, unrealized_pnl
    
    def calc_portfolio_pnl(self, current_prices: Dict[str, float]) -> Dict[str, float]:
        """Calculate portfolio-wide PnL"""
        total_realized = 0.0
        total_unrealized = 0.0
        symbol_pnl = {}
        
        for symbol, position in self.positions.items():
            current_price = current_prices.get(symbol, position.entry_price)
            realized, unrealized = self.calc_pnl(symbol, current_price)
            
            total_realized += realized
            total_unrealized += unrealized
            symbol_pnl[symbol] = {
                'realized': realized,
                'unrealized': unrealized,
                'total': realized + unrealized
            }
        
        return {
            'total_realized': total_realized,
            'total_unrealized': total_unrealized,
            'total_pnl': total_realized + total_unrealized,
            'symbol_pnl': symbol_pnl,
            'position_count': len(self.positions)
        }
    
    def snapshot_daily_pnl(self) -> bool:
        """Snapshot daily PnL to SSOT"""
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            current_prices = self._get_current_prices()
            portfolio_pnl = self.calc_portfolio_pnl(current_prices)
            
            self.daily_pnl[today] = {
                'date': today,
                'realized_pnl': portfolio_pnl['total_realized'],
                'unrealized_pnl': portfolio_pnl['total_unrealized'],
                'total_pnl': portfolio_pnl['total_pnl'],
                'position_count': portfolio_pnl['position_count'],
                'snapshot_time': time.time()
            }
            
            # Persist daily PnL
            pnl_data = {
                'daily_pnl': self.daily_pnl,
                'last_snapshot': time.time(),
                'snapshot_count': len(self.daily_pnl)
            }
            
            return write_json_atomic("pnl_daily.json", pnl_data)
            
        except Exception as e:
            print(f"[ERROR] StateStore.snapshot_daily_pnl: {e}")
            return False
    
    def _get_current_prices(self) -> Dict[str, float]:
        """Get current prices from health.json or market data"""
        try:
            health_file = self.ssot_dir / "health.json"
            if health_file.exists():
                data = read_json_safe(health_file)
                if data and 'symbols' in data:
                    prices = {}
                    for symbol, symbol_data in data['symbols'].items():
                        if 'price' in symbol_data:
                            prices[symbol] = float(symbol_data['price'])
                    return prices
        except Exception as e:
            print(f"[ERROR] StateStore._get_current_prices: {e}")
        
        return {}
    
    def get_daily_pnl(self, date: str = None) -> Optional[Dict[str, Any]]:
        """Get daily PnL for specific date"""
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        
        return self.daily_pnl.get(date)
    
    def get_recent_pnl(self, days: int = 7) -> List[Dict[str, Any]]:
        """Get recent daily PnL records"""
        recent_pnl = []
        for i in range(days):
            date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
            pnl = self.daily_pnl.get(date)
            if pnl:
                recent_pnl.append(pnl)
        
        return recent_pnl
    
    def cancel_all_orders(self) -> bool:
        """Cancel all open orders"""
        try:
            cancelled_orders = []
            
            for order_id, order in self.open_orders.items():
                order.status = 'CANCELLED'
                order.update_time = time.time()
                
                order_data = asdict(order)
                success = append_ndjson_atomic("orders.ndjson", order_data)
                
                if success:
                    cancelled_orders.append(order_id)
                else:
                    # Rollback failed cancellations
                    self._load_state()
                    return False
            
            # Remove cancelled orders from memory
            for order_id in cancelled_orders:
                self.open_orders.pop(order_id, None)
            
            return True
            
        except Exception as e:
            print(f"[ERROR] StateStore.cancel_all_orders: {e}")
            return False
    
    def get_state_summary(self) -> Dict[str, Any]:
        """Get comprehensive state summary"""
        current_prices = self._get_current_prices()
        portfolio_pnl = self.calc_portfolio_pnl(current_prices)
        
        return {
            'timestamp': time.time(),
            'positions': {
                'count': len(self.positions),
                'symbols': list(self.positions.keys()),
                'total_value': sum(pos.quantity * current_prices.get(pos.symbol, pos.entry_price) 
                                 for pos in self.positions.values())
            },
            'orders': {
                'open_count': len(self.open_orders),
                'order_ids': list(self.open_orders.keys())
            },
            'pnl': portfolio_pnl,
            'daily_pnl_records': len(self.daily_pnl),
            'last_update': max([pos.last_update for pos in self.positions.values()] + [0])
        }


# Global state store instance
_state_store = None

def get_state_store() -> StateStore:
    """Get global state store instance"""
    global _state_store
    if _state_store is None:
        _state_store = StateStore()
    return _state_store


# Convenience functions
def get_positions() -> Dict[str, Position]:
    """Get all positions"""
    return get_state_store().get_positions()

def get_open_orders() -> Dict[str, Order]:
    """Get all open orders"""
    return get_state_store().get_open_orders()

def add_order(order: Order) -> bool:
    """Add new order"""
    return get_state_store().add_order(order)

def apply_fill(fill: Fill) -> bool:
    """Apply fill to state"""
    return get_state_store().apply_fill(fill)

def calc_portfolio_pnl(current_prices: Dict[str, float]) -> Dict[str, float]:
    """Calculate portfolio PnL"""
    return get_state_store().calc_portfolio_pnl(current_prices)


if __name__ == "__main__":
    # Test the state store
    print("Testing StateStore...")
    
    store = StateStore()
    print(f"Initial state: {store.get_state_summary()}")
    
    # Test order creation
    test_order = Order(
        order_id="test_001",
        client_order_id="client_001",
        symbol="BTCUSDT",
        side="BUY",
        order_type="LIMIT_IOC",
        quantity=0.001,
        price=50000.0
    )
    
    success = store.add_order(test_order)
    print(f"Add order: {'SUCCESS' if success else 'FAILED'}")
    
    # Test fill
    test_fill = Fill(
        fill_id="fill_001",
        order_id="test_001",
        symbol="BTCUSDT",
        side="BUY",
        quantity=0.001,
        price=50000.0,
        timestamp=time.time()
    )
    
    success = store.apply_fill(test_fill)
    print(f"Apply fill: {'SUCCESS' if success else 'FAILED'}")
    
    # Test PnL calculation
    current_prices = {"BTCUSDT": 51000.0}
    pnl = store.calc_portfolio_pnl(current_prices)
    print(f"Portfolio PnL: {pnl}")
    
    print("StateStore test completed!")
