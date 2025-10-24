#!/usr/bin/env python3
"""
Explicit Order Gate Checker
Makes all order gates explicit and user-visible with structured skip reasons
"""

import json
import logging
import time
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .environment_manager import get_env
from .path_registry import get_absolute_path


class GateResult(Enum):
    """Gate check results"""
    PASS = "pass"
    SKIP = "skip"
    ERROR = "error"


@dataclass
class GateCheckResult:
    """Result of a gate check"""
    gate_name: str
    result: GateResult
    reason_code: Optional[str] = None
    reason_detail: Optional[str] = None
    latency_ms: float = 0.0


@dataclass
class OrderSkipEvent:
    """Structured event when order is skipped"""
    event: str = "order_skipped"
    reason_code: str = ""
    reason_detail: str = ""
    signal_ref: str = ""
    symbol: str = ""
    side: str = ""
    ts: float = 0.0
    gate_results: list = None


class OrderGateChecker:
    """
    Explicit order gate checker
    Evaluates gates in order and stops at first failure
    """
    
    def __init__(self):
        self.logger = logging.getLogger('OrderGates')
        self.ssot_path = get_absolute_path('shared_data') / 'order_gates_ssot.json'
        self.skipped_orders_path = get_absolute_path('shared_data') / 'orders_skipped.jsonl'
        
        # Ensure directories exist
        self.ssot_path.parent.mkdir(parents=True, exist_ok=True)
        self.skipped_orders_path.parent.mkdir(parents=True, exist_ok=True)
    
    def check_all_gates(
        self, 
        symbol: str, 
        side: str, 
        quantity: float, 
        price: float,
        signal_ref: str = "",
        exchange_info: Optional[Dict] = None,
        current_positions: Optional[Dict] = None,
        account_state: Optional[Dict] = None
    ) -> Tuple[bool, Optional[OrderSkipEvent]]:
        """
        Check all order gates in sequence
        Returns: (can_place_order, skip_event_if_any)
        """
        start_time = time.time()
        gate_results = []
        
        # Gate 1: Symbol normalization
        result = self._check_symbol_normalization(symbol)
        gate_results.append(result)
        if result.result != GateResult.PASS:
            return False, self._create_skip_event(
                symbol, side, signal_ref, result, gate_results
            )
        
        # Gate 2: Exchange filters
        if exchange_info:
            result = self._check_exchange_filters(
                symbol, quantity, price, exchange_info
            )
            gate_results.append(result)
            if result.result != GateResult.PASS:
                return False, self._create_skip_event(
                    symbol, side, signal_ref, result, gate_results
                )
        
        # Gate 3: Risk limits
        result = self._check_risk_limits(
            symbol, quantity, price, current_positions, account_state
        )
        gate_results.append(result)
        if result.result != GateResult.PASS:
            return False, self._create_skip_event(
                symbol, side, signal_ref, result, gate_results
            )
        
        # Gate 4: Slippage guard
        result = self._check_slippage_guard(symbol, price)
        gate_results.append(result)
        if result.result != GateResult.PASS:
            return False, self._create_skip_event(
                symbol, side, signal_ref, result, gate_results
            )
        
        # Gate 5: Position conflict policy
        result = self._check_position_conflict(
            symbol, side, current_positions
        )
        gate_results.append(result)
        if result.result != GateResult.PASS:
            return False, self._create_skip_event(
                symbol, side, signal_ref, result, gate_results
            )
        
        # Gate 6: Dry run / simulation guard
        result = self._check_simulation_mode()
        gate_results.append(result)
        if result.result != GateResult.PASS:
            return False, self._create_skip_event(
                symbol, side, signal_ref, result, gate_results
            )
        
        # All gates passed
        total_latency = (time.time() - start_time) * 1000
        self.logger.info(
            f"✅ All gates PASSED for {symbol} {side} (latency: {total_latency:.1f}ms)"
        )
        return True, None
    
    def _check_symbol_normalization(self, symbol: str) -> GateCheckResult:
        """Gate 1: Symbol normalization"""
        start_time = time.time()
        
        # Check if symbol is uppercase
        if symbol != symbol.upper():
            latency = (time.time() - start_time) * 1000
            return GateCheckResult(
                gate_name="symbol_normalization",
                result=GateResult.SKIP,
                reason_code="SYMBOL_NOT_UPPERCASE",
                reason_detail=f"Symbol must be uppercase: {symbol}",
                latency_ms=latency
            )
        
        # Check if symbol is valid format (e.g., BTCUSDT)
        if not symbol or len(symbol) < 6:
            latency = (time.time() - start_time) * 1000
            return GateCheckResult(
                gate_name="symbol_normalization",
                result=GateResult.SKIP,
                reason_code="INVALID_SYMBOL_FORMAT",
                reason_detail=f"Invalid symbol format: {symbol}",
                latency_ms=latency
            )
        
        latency = (time.time() - start_time) * 1000
        return GateCheckResult(
            gate_name="symbol_normalization",
            result=GateResult.PASS,
            latency_ms=latency
        )
    
    def _check_exchange_filters(
        self, 
        symbol: str, 
        quantity: float, 
        price: float,
        exchange_info: Dict
    ) -> GateCheckResult:
        """Gate 2: Exchange filters"""
        start_time = time.time()
        
        # Get symbol filters
        symbol_filters = exchange_info.get('filters', {})
        
        # Check minNotional
        min_notional = symbol_filters.get('minNotional', 0)
        notional = quantity * price
        if notional < min_notional:
            latency = (time.time() - start_time) * 1000
            return GateCheckResult(
                gate_name="exchange_filters",
                result=GateResult.SKIP,
                reason_code="NOTIONAL_TOO_SMALL",
                reason_detail=f"Notional {notional:.2f} < min {min_notional}",
                latency_ms=latency
            )
        
        # Check stepSize (quantity precision)
        step_size = symbol_filters.get('stepSize', 0.00000001)
        if step_size > 0:
            # Ensure quantity is a multiple of stepSize
            remainder = quantity % step_size
            if remainder > step_size * 0.001:  # Allow tiny rounding error
                latency = (time.time() - start_time) * 1000
                return GateCheckResult(
                    gate_name="exchange_filters",
                    result=GateResult.SKIP,
                    reason_code="INVALID_QUANTITY_STEP",
                    reason_detail=f"Quantity {quantity} not multiple of {step_size}",
                    latency_ms=latency
                )
        
        latency = (time.time() - start_time) * 1000
        return GateCheckResult(
            gate_name="exchange_filters",
            result=GateResult.PASS,
            latency_ms=latency
        )
    
    def _check_risk_limits(
        self, 
        symbol: str, 
        quantity: float, 
        price: float,
        current_positions: Optional[Dict],
        account_state: Optional[Dict]
    ) -> GateCheckResult:
        """Gate 3: Risk limits"""
        start_time = time.time()
        
        # Get risk limits from environment
        max_position_usdt = get_env('MAX_POSITION_USDT', '1000', float)
        max_total_exposure = get_env('MAX_TOTAL_EXPOSURE_USDT', '5000', float)
        max_daily_loss_pct = get_env('MAX_DAILY_LOSS_PCT', '3.0', float)
        
        # Check position size limit
        position_value = quantity * price
        if position_value > max_position_usdt:
            latency = (time.time() - start_time) * 1000
            return GateCheckResult(
                gate_name="risk_limits",
                result=GateResult.SKIP,
                reason_code="POSITION_TOO_LARGE",
                reason_detail=f"Position value {position_value:.2f} > max {max_position_usdt}",
                latency_ms=latency
            )
        
        # Check total exposure if positions available
        if current_positions and account_state:
            total_exposure = sum(
                abs(pos.get('size', 0) * pos.get('entry_price', 0))
                for pos in current_positions.values()
            )
            
            if total_exposure + position_value > max_total_exposure:
                latency = (time.time() - start_time) * 1000
                return GateCheckResult(
                    gate_name="risk_limits",
                    result=GateResult.SKIP,
                    reason_code="TOTAL_EXPOSURE_EXCEEDED",
                    reason_detail=f"Total exposure would be {total_exposure + position_value:.2f} > max {max_total_exposure}",
                    latency_ms=latency
                )
        
        latency = (time.time() - start_time) * 1000
        return GateCheckResult(
            gate_name="risk_limits",
            result=GateResult.PASS,
            latency_ms=latency
        )
    
    def _check_slippage_guard(self, symbol: str, price: float) -> GateCheckResult:
        """Gate 4: Slippage guard"""
        start_time = time.time()
        
        # For now, always pass (implement actual slippage check later)
        latency = (time.time() - start_time) * 1000
        return GateCheckResult(
            gate_name="slippage_guard",
            result=GateResult.PASS,
            latency_ms=latency
        )
    
    def _check_position_conflict(
        self, 
        symbol: str, 
        side: str,
        current_positions: Optional[Dict]
    ) -> GateCheckResult:
        """Gate 5: Position conflict policy"""
        start_time = time.time()
        
        # Check if we already have a position in the opposite direction
        if current_positions and symbol in current_positions:
            existing_pos = current_positions[symbol]
            existing_side = existing_pos.get('side', '')
            
            # If we have opposite side position, check policy
            if (side == 'BUY' and existing_side == 'SELL') or \
               (side == 'SELL' and existing_side == 'BUY'):
                # For now, allow netting (default behavior)
                # Could be configured to SKIP based on policy
                pass
        
        latency = (time.time() - start_time) * 1000
        return GateCheckResult(
            gate_name="position_conflict",
            result=GateResult.PASS,
            latency_ms=latency
        )
    
    def _check_simulation_mode(self) -> GateCheckResult:
        """Gate 6: Dry run / simulation guard"""
        start_time = time.time()
        
        dry_run = get_env('DRY_RUN', 'false', bool)
        simulation_mode = get_env('SIMULATION_MODE', 'false', bool)
        
        if dry_run or simulation_mode:
            latency = (time.time() - start_time) * 1000
            return GateCheckResult(
                gate_name="simulation_mode",
                result=GateResult.SKIP,
                reason_code="DRY_RUN_MODE",
                reason_detail="System is in dry run or simulation mode",
                latency_ms=latency
            )
        
        latency = (time.time() - start_time) * 1000
        return GateCheckResult(
            gate_name="simulation_mode",
            result=GateResult.PASS,
            latency_ms=latency
        )
    
    def _create_skip_event(
        self, 
        symbol: str, 
        side: str, 
        signal_ref: str,
        failed_gate: GateCheckResult,
        all_gates: list
    ) -> OrderSkipEvent:
        """Create structured skip event"""
        event = OrderSkipEvent(
            event="order_skipped",
            reason_code=failed_gate.reason_code or "UNKNOWN",
            reason_detail=failed_gate.reason_detail or "Unknown reason",
            signal_ref=signal_ref,
            symbol=symbol,
            side=side,
            ts=time.time(),
            gate_results=[asdict(g) for g in all_gates]
        )
        
        # Log the skip event
        self._log_skip_event(event)
        
        return event
    
    def _log_skip_event(self, event: OrderSkipEvent):
        """Log skip event to JSONL file"""
        try:
            with open(self.skipped_orders_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(asdict(event), ensure_ascii=False) + '\n')
            
            self.logger.warning(
                f"⚠️ Order SKIPPED: {event.symbol} {event.side} - {event.reason_code}: {event.reason_detail}"
            )
        except Exception as e:
            self.logger.error(f"Failed to log skip event: {e}")
    
    def get_recent_skipped_orders(self, limit: int = 100) -> list:
        """Get recent skipped orders for UI display"""
        if not self.skipped_orders_path.exists():
            return []
        
        try:
            with open(self.skipped_orders_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                # Get last N lines
                recent_lines = lines[-limit:] if len(lines) > limit else lines
                return [json.loads(line) for line in recent_lines if line.strip()]
        except Exception as e:
            self.logger.error(f"Failed to read skipped orders: {e}")
            return []


# Global instance
_gate_checker = OrderGateChecker()


def check_order_gates(
    symbol: str, 
    side: str, 
    quantity: float, 
    price: float,
    **kwargs
) -> Tuple[bool, Optional[OrderSkipEvent]]:
    """Check all order gates"""
    return _gate_checker.check_all_gates(symbol, side, quantity, price, **kwargs)


def get_recent_skipped_orders(limit: int = 100) -> list:
    """Get recent skipped orders"""
    return _gate_checker.get_recent_skipped_orders(limit)

