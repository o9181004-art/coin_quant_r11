#!/usr/bin/env python3
"""
Memory-efficient positions and balances management
Compact data structures with __slots__ for CQ_LEAN mode
"""

import os
import time
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

from shared.lean_mode import is_lean, lean_cache
from shared.lean_json import write_json_lean, read_json_lean


@dataclass(slots=True)
class LeanPosition:
    """Memory-efficient position data structure"""
    symbol: str
    side: str  # 'long', 'short', 'flat'
    quantity: float
    avg_price: float
    unrealized_pnl: float
    timestamp: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'symbol': self.symbol,
            'side': self.side,
            'quantity': self.quantity,
            'avg_price': self.avg_price,
            'unrealized_pnl': self.unrealized_pnl,
            'timestamp': self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LeanPosition':
        """Create from dictionary"""
        return cls(
            symbol=data['symbol'],
            side=data['side'],
            quantity=data['quantity'],
            avg_price=data['avg_price'],
            unrealized_pnl=data['unrealized_pnl'],
            timestamp=data.get('timestamp', time.time())
        )


@dataclass(slots=True)
class LeanBalance:
    """Memory-efficient balance data structure"""
    asset: str
    free: float
    locked: float
    timestamp: float = field(default_factory=time.time)
    
    @property
    def total(self) -> float:
        """Total balance (free + locked)"""
        return self.free + self.locked
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'asset': self.asset,
            'free': self.free,
            'locked': self.locked,
            'timestamp': self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LeanBalance':
        """Create from dictionary"""
        return cls(
            asset=data['asset'],
            free=data['free'],
            locked=data['locked'],
            timestamp=data.get('timestamp', time.time())
        )


class LeanPositionManager:
    """Memory-efficient position manager"""
    
    def __init__(self):
        self.positions: Dict[str, LeanPosition] = {}
        self._cache_key = "positions_cache"
    
    def update_position(self, symbol: str, side: str, quantity: float, avg_price: float, unrealized_pnl: float = 0.0):
        """Update position data"""
        symbol = symbol.upper()
        
        if quantity == 0:
            # Close position
            self.positions.pop(symbol, None)
        else:
            # Update or create position
            self.positions[symbol] = LeanPosition(
                symbol=symbol,
                side=side,
                quantity=quantity,
                avg_price=avg_price,
                unrealized_pnl=unrealized_pnl
            )
        
        # Cache in lean mode
        if is_lean:
            lean_cache.set(self._cache_key, self.positions)
    
    def get_position(self, symbol: str) -> Optional[LeanPosition]:
        """Get position for symbol"""
        symbol = symbol.upper()
        return self.positions.get(symbol)
    
    def get_all_positions(self) -> Dict[str, LeanPosition]:
        """Get all positions"""
        return self.positions.copy()
    
    def get_active_positions(self) -> Dict[str, LeanPosition]:
        """Get only active (non-zero) positions"""
        return {symbol: pos for symbol, pos in self.positions.items() if pos.quantity != 0}
    
    def calculate_total_pnl(self) -> float:
        """Calculate total unrealized PnL"""
        return sum(pos.unrealized_pnl for pos in self.positions.values())
    
    def save_to_file(self, file_path: str) -> bool:
        """Save positions to file"""
        try:
            data = {
                'positions': {symbol: pos.to_dict() for symbol, pos in self.positions.items()},
                'timestamp': time.time(),
                'total_pnl': self.calculate_total_pnl()
            }
            return write_json_lean(file_path, data)
        except Exception as e:
            print(f"Position save error: {e}")
            return False
    
    def load_from_file(self, file_path: str) -> bool:
        """Load positions from file"""
        try:
            data = read_json_lean(file_path)
            if not data:
                return False
            
            self.positions.clear()
            for symbol, pos_data in data.get('positions', {}).items():
                self.positions[symbol] = LeanPosition.from_dict(pos_data)
            
            return True
        except Exception as e:
            print(f"Position load error: {e}")
            return False


class LeanBalanceManager:
    """Memory-efficient balance manager"""
    
    def __init__(self):
        self.balances: Dict[str, LeanBalance] = {}
        self._cache_key = "balances_cache"
    
    def update_balance(self, asset: str, free: float, locked: float = 0.0):
        """Update balance data"""
        asset = asset.upper()
        
        if free == 0 and locked == 0:
            # Remove zero balance
            self.balances.pop(asset, None)
        else:
            # Update or create balance
            self.balances[asset] = LeanBalance(
                asset=asset,
                free=free,
                locked=locked
            )
        
        # Cache in lean mode
        if is_lean:
            lean_cache.set(self._cache_key, self.balances)
    
    def get_balance(self, asset: str) -> Optional[LeanBalance]:
        """Get balance for asset"""
        asset = asset.upper()
        return self.balances.get(asset)
    
    def get_all_balances(self) -> Dict[str, LeanBalance]:
        """Get all balances"""
        return self.balances.copy()
    
    def get_non_zero_balances(self) -> Dict[str, LeanBalance]:
        """Get only non-zero balances"""
        return {asset: bal for asset, bal in self.balances.items() if bal.total > 0}
    
    def get_total_usdt_value(self, usdt_price: float = 1.0) -> float:
        """Calculate total USDT value"""
        total = 0.0
        for balance in self.balances.values():
            if balance.asset == 'USDT':
                total += balance.total
            elif balance.asset == 'BTC':
                total += balance.total * usdt_price
        
        return total
    
    def save_to_file(self, file_path: str) -> bool:
        """Save balances to file"""
        try:
            data = {
                'balances': {asset: bal.to_dict() for asset, bal in self.balances.items()},
                'timestamp': time.time(),
                'total_usdt_value': self.get_total_usdt_value()
            }
            return write_json_lean(file_path, data)
        except Exception as e:
            print(f"Balance save error: {e}")
            return False
    
    def load_from_file(self, file_path: str) -> bool:
        """Load balances from file"""
        try:
            data = read_json_lean(file_path)
            if not data:
                return False
            
            self.balances.clear()
            for asset, bal_data in data.get('balances', {}).items():
                self.balances[asset] = LeanBalance.from_dict(bal_data)
            
            return True
        except Exception as e:
            print(f"Balance load error: {e}")
            return False


class LeanAccountSnapshot:
    """Memory-efficient account snapshot"""
    
    def __init__(self):
        self.positions = LeanPositionManager()
        self.balances = LeanBalanceManager()
        self.timestamp = time.time()
        self.equity = 0.0
        self.total_balance = 0.0
    
    def update_equity(self, equity: float):
        """Update equity value"""
        self.equity = equity
        self.timestamp = time.time()
    
    def update_total_balance(self, total_balance: float):
        """Update total balance"""
        self.total_balance = total_balance
        self.timestamp = time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'positions': {symbol: pos.to_dict() for symbol, pos in self.positions.get_all_positions().items()},
            'balances': {asset: bal.to_dict() for asset, bal in self.balances.get_all_balances().items()},
            'equity': self.equity,
            'total_balance': self.total_balance,
            'timestamp': self.timestamp
        }
    
    def save_to_file(self, file_path: str) -> bool:
        """Save account snapshot to file"""
        try:
            return write_json_lean(file_path, self.to_dict())
        except Exception as e:
            print(f"Account snapshot save error: {e}")
            return False
    
    def load_from_file(self, file_path: str) -> bool:
        """Load account snapshot from file"""
        try:
            data = read_json_lean(file_path)
            if not data:
                return False
            
            # Load positions
            for symbol, pos_data in data.get('positions', {}).items():
                self.positions.positions[symbol] = LeanPosition.from_dict(pos_data)
            
            # Load balances
            for asset, bal_data in data.get('balances', {}).items():
                self.balances.balances[asset] = LeanBalance.from_dict(bal_data)
            
            self.equity = data.get('equity', 0.0)
            self.total_balance = data.get('total_balance', 0.0)
            self.timestamp = data.get('timestamp', time.time())
            
            return True
        except Exception as e:
            print(f"Account snapshot load error: {e}")
            return False


# Global instances
lean_position_manager = LeanPositionManager()
lean_balance_manager = LeanBalanceManager()
lean_account_snapshot = LeanAccountSnapshot()
