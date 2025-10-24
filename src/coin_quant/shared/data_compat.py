#!/usr/bin/env python3
"""
Data Compatibility Adapter for Classic UI

Provides the same data interface that the original Classic UI expects,
while using the new robust pathing and DAL under the hood.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from .pathing import get_paths
from .data_access import get_data_bus

logger = logging.getLogger(__name__)


def get_price(symbol: str) -> Optional[Dict[str, Any]]:
    """Get price data for a symbol in classic UI format"""
    try:
        data_bus = get_data_bus()
        price_repo = data_bus.prices
        
        # Try to get latest price data
        price_data = price_repo.get_latest(symbol)
        if price_data:
            return price_data
        
        # Fallback to direct file read for compatibility
        paths = get_paths()
        price_files = [
            paths.snapshots_dir / f"prices_{symbol.lower()}.json",
            paths.snapshots_dir / f"prices_{symbol.upper()}.json",
        ]
        
        for price_file in price_files:
            if price_file.exists():
                try:
                    with open(price_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        return data
                except (json.JSONDecodeError, IOError) as e:
                    logger.warning(f"Failed to read price file {price_file}: {e}")
                    continue
        
        return None
        
    except Exception as e:
        logger.error(f"Error getting price for {symbol}: {e}")
        return None


def get_signal(symbol: str) -> Optional[Dict[str, Any]]:
    """Get signal data for a symbol in classic UI format"""
    try:
        data_bus = get_data_bus()
        signal_repo = data_bus.signals
        
        # Try to get latest signal data
        signal_data = signal_repo.get_latest(symbol)
        if signal_data:
            return signal_data
        
        # Fallback to direct file read for compatibility
        paths = get_paths()
        
        # Try ARES signals file
        ares_file = paths.shared_data_dir / "ares_signals.json"
        if ares_file.exists():
            try:
                with open(ares_file, 'r', encoding='utf-8') as f:
                    signals = json.load(f)
                    if isinstance(signals, dict) and symbol in signals:
                        return signals[symbol]
                    elif isinstance(signals, list):
                        # Find signal for this symbol
                        for signal in signals:
                            if signal.get('symbol', '').upper() == symbol.upper():
                                return signal
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to read ARES signals: {e}")
        
        # Try individual ARES files
        ares_dir = paths.shared_data_dir / "ares"
        if ares_dir.exists():
            signal_file = ares_dir / f"{symbol.lower()}.json"
            if signal_file.exists():
                try:
                    with open(signal_file, 'r', encoding='utf-8') as f:
                        return json.load(f)
                except (json.JSONDecodeError, IOError) as e:
                    logger.warning(f"Failed to read signal file {signal_file}: {e}")
        
        return None
        
    except Exception as e:
        logger.error(f"Error getting signal for {symbol}: {e}")
        return None


def get_position(symbol: str) -> Optional[Dict[str, Any]]:
    """Get position data for a symbol in classic UI format"""
    try:
        data_bus = get_data_bus()
        position_repo = data_bus.positions
        
        # Try to get position data
        position_data = position_repo.get_by_symbol(symbol)
        if position_data:
            return position_data
        
        # Fallback to direct file read for compatibility
        paths = get_paths()
        positions_file = paths.shared_data / "positions_snapshot.json"
        
        if positions_file.exists():
            try:
                with open(positions_file, 'r', encoding='utf-8') as f:
                    positions = json.load(f)
                    if isinstance(positions, dict) and symbol in positions:
                        return positions[symbol]
                    elif isinstance(positions, list):
                        # Find position for this symbol
                        for position in positions:
                            if position.get('symbol', '').upper() == symbol.upper():
                                return position
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to read positions file: {e}")
        
        return None
        
    except Exception as e:
        logger.error(f"Error getting position for {symbol}: {e}")
        return None


def get_ages(symbol: str) -> Dict[str, Optional[int]]:
    """Get age data for a symbol in classic UI format"""
    try:
        data_bus = get_data_bus()
        
        # Get price age
        price_age = None
        try:
            price_repo = data_bus.prices
            price_age = price_repo.get_age_seconds(symbol)
        except Exception as e:
            logger.warning(f"Failed to get price age for {symbol}: {e}")
        
        # Get signal age
        signal_age = None
        try:
            signal_repo = data_bus.signals
            signal_age = signal_repo.get_age_seconds(symbol)
        except Exception as e:
            logger.warning(f"Failed to get signal age for {symbol}: {e}")
        
        return {
            "price_age": price_age,
            "ares_age": signal_age
        }
        
    except Exception as e:
        logger.error(f"Error getting ages for {symbol}: {e}")
        return {"price_age": None, "ares_age": None}


def get_health() -> Dict[str, Any]:
    """Get health data in classic UI format"""
    try:
        data_bus = get_data_bus()
        health_repo = data_bus.health
        
        # Get overall health status
        health_data = health_repo.get_all()
        
        # Format for classic UI compatibility
        formatted_health = {}
        for component, status in health_data.items():
            formatted_health[component] = {
                "status": status.get("status", "UNKNOWN"),
                "last_update": status.get("last_update"),
                "message": status.get("message", "")
            }
        
        return formatted_health
        
    except Exception as e:
        logger.error(f"Error getting health data: {e}")
        return {}


def get_exposure() -> Dict[str, Any]:
    """Get exposure data in classic UI format"""
    try:
        paths = get_paths()
        exposure_file = paths.shared_data / "exposure.json"
        
        if exposure_file.exists():
            try:
                with open(exposure_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to read exposure file: {e}")
        
        return {}
        
    except Exception as e:
        logger.error(f"Error getting exposure data: {e}")
        return {}


def get_account_info() -> Dict[str, Any]:
    """Get account information in classic UI format"""
    try:
        paths = get_paths()
        account_file = paths.shared_data / "account_info.json"
        
        if account_file.exists():
            try:
                with open(account_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to read account info file: {e}")
        
        return {}
        
    except Exception as e:
        logger.error(f"Error getting account info: {e}")
        return {}


def get_trading_state() -> Dict[str, Any]:
    """Get trading state in classic UI format"""
    try:
        paths = get_paths()
        state_file = paths.shared_data / "auto_trading_state.json"
        
        if state_file.exists():
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to read trading state file: {e}")
        
        return {}
        
    except Exception as e:
        logger.error(f"Error getting trading state: {e}")
        return {}


def get_symbols() -> List[str]:
    """Get list of symbols to display in classic UI format"""
    try:
        # Try to get symbols from watchlist
        paths = get_paths()
        watchlist_file = paths.shared_data / "coin_watchlist.json"
        
        if watchlist_file.exists():
            try:
                with open(watchlist_file, 'r', encoding='utf-8') as f:
                    watchlist = json.load(f)
                    if isinstance(watchlist, list):
                        return [symbol.upper() for symbol in watchlist]
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to read watchlist file: {e}")
        
        # Fallback to default symbols
        return [
            "BTCUSDT", "ETHUSDT", "ADAUSDT", "SOLUSDT", "FDUSDUSDT",
            "DOGEUSDT", "XRPUSDT", "EURUSDT", "TAOUSDT", "KDAUSDT"
        ]
        
    except Exception as e:
        logger.error(f"Error getting symbols: {e}")
        return ["BTCUSDT", "ETHUSDT", "ADAUSDT", "SOLUSDT", "FDUSDUSDT"]


def format_age(age_seconds: Optional[int]) -> str:
    """Format age in seconds to human-readable string"""
    if age_seconds is None:
        return "999s"
    
    if age_seconds < 60:
        return f"{age_seconds}s"
    elif age_seconds < 3600:
        minutes = age_seconds // 60
        return f"{minutes}m"
    else:
        hours = age_seconds // 3600
        return f"{hours}h"


def format_price(price: Optional[float]) -> str:
    """Format price for display"""
    if price is None:
        return "N/A"
    
    if price >= 1:
        return f"{price:.2f}"
    else:
        return f"{price:.6f}"


def format_percentage(value: Optional[float]) -> str:
    """Format percentage for display"""
    if value is None:
        return "N/A"
    
    return f"{value:.2f}%"
