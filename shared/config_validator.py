#!/usr/bin/env python3
"""
Configuration Validator and Loader (UM-Futures Testnet SSOT)
===========================================================
Single source of truth for environment configuration.

Features:
- Fail-fast validation with clear error messages
- Uppercase symbol normalization
- Secret masking in logs
- Sensible defaults for Binance UM Futures Testnet
- Zero implicit fallbacks that could cause mainnet execution

Contract:
- ENV: prod | dev (default: prod)
- TESTNET: true | false (default: true)
- EXCHANGE: binance (only supported for now)
- MARKET: umfutures | spot (default: umfutures)
- WATCHLIST: comma-separated symbols (default: BTCUSDT)
- DATA_DIR: ./shared_data (default)
- LOG_LEVEL: DEBUG | INFO | WARNING | ERROR (default: INFO)
- BINANCE_API_KEY: required when EXCHANGE=binance
- BINANCE_API_SECRET: required when EXCHANGE=binance
- BINANCE_TESTNET: must mirror TESTNET when TESTNET=true
"""

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple


@dataclass
class TradingConfig:
    """Validated trading configuration"""
    
    # Environment
    env: str  # prod | dev
    testnet: bool
    exchange: str  # binance
    market: str  # umfutures | spot
    watchlist: List[str]  # uppercase symbols
    data_dir: Path
    log_level: str
    
    # Binance API
    binance_api_key: str
    binance_api_secret: str
    binance_testnet: bool
    
    # WebSocket endpoints
    binance_um_testnet_ws_base: str
    binance_um_ws_base: str
    binance_spot_testnet_ws_base: str
    binance_spot_ws_base: str
    
    # REST endpoints
    binance_um_testnet_rest_base: str
    binance_um_rest_base: str
    binance_spot_testnet_rest_base: str
    binance_spot_rest_base: str
    
    def get_active_ws_endpoint(self) -> str:
        """Get active WebSocket endpoint based on market and testnet flag"""
        if self.market == "umfutures":
            return self.binance_um_testnet_ws_base if self.testnet else self.binance_um_ws_base
        elif self.market == "spot":
            return self.binance_spot_testnet_ws_base if self.testnet else self.binance_spot_ws_base
        else:
            raise ValueError(f"Unsupported market: {self.market}")
    
    def get_active_rest_endpoint(self) -> str:
        """Get active REST endpoint based on market and testnet flag"""
        if self.market == "umfutures":
            return self.binance_um_testnet_rest_base if self.testnet else self.binance_um_rest_base
        elif self.market == "spot":
            return self.binance_spot_testnet_rest_base if self.testnet else self.binance_spot_rest_base
        else:
            raise ValueError(f"Unsupported market: {self.market}")
    
    def mask_secret(self, secret: str) -> str:
        """Mask secret showing only last 4 chars"""
        if not secret:
            return "****"
        if len(secret) <= 4:
            return "****"
        return f"****{secret[-4:]}"
    
    def get_config_summary(self) -> str:
        """Get one-line config summary (with secrets masked)"""
        return (
            f"exchange={self.exchange} • "
            f"market={self.market} • "
            f"testnet={self.testnet} • "
            f"watchlist={','.join(self.watchlist)} • "
            f"data_dir={self.data_dir} • "
            f"api_key={self.mask_secret(self.binance_api_key)} • "
            f"api_secret={self.mask_secret(self.binance_api_secret)}"
        )
    
    def log_config(self):
        """Log configuration (safe - no raw secrets)"""
        print("=" * 60)
        print(" Trading System Configuration")
        print("=" * 60)
        print(f"  Environment:        {self.env}")
        print(f"  Testnet:            {self.testnet}")
        print(f"  Exchange:           {self.exchange}")
        print(f"  Market:             {self.market}")
        print(f"  Watchlist:          {', '.join(self.watchlist)}")
        print(f"  Data Directory:     {self.data_dir}")
        print(f"  Log Level:          {self.log_level}")
        print(f"  API Key:            {self.mask_secret(self.binance_api_key)}")
        print(f"  API Secret:         {self.mask_secret(self.binance_api_secret)}")
        print(f"  Active WS:          {self.get_active_ws_endpoint()}")
        print(f"  Active REST:        {self.get_active_rest_endpoint()}")
        print("=" * 60)


def normalize_symbol(symbol: str) -> str:
    """Normalize symbol to uppercase and strip whitespace"""
    return symbol.strip().upper()


def validate_and_load_config(fail_fast: bool = True) -> Tuple[Optional[TradingConfig], Optional[str]]:
    """
    Validate and load configuration from environment.
    
    Args:
        fail_fast: If True, exit immediately on error. If False, return error message.
    
    Returns:
        (config, error_message) - config is None if validation failed
    """
    errors = []
    
    # =========================================================================
    # Load and validate core settings
    # =========================================================================
    
    env = os.getenv("ENV", "prod").lower().strip()
    if env not in ("prod", "dev"):
        errors.append(f"ENV={env} invalid (must be 'prod' or 'dev')")
    
    testnet_str = os.getenv("TESTNET", "true").lower().strip()
    testnet = testnet_str in ("true", "1", "yes", "on")
    
    exchange = os.getenv("EXCHANGE", "binance").lower().strip()
    if exchange != "binance":
        errors.append(f"EXCHANGE={exchange} unsupported (only 'binance' supported)")
    
    market = os.getenv("MARKET", "umfutures").lower().strip()
    if market not in ("umfutures", "spot"):
        errors.append(f"MARKET={market} invalid (must be 'umfutures' or 'spot')")
    
    # Watchlist with normalization
    watchlist_raw = os.getenv("WATCHLIST", "BTCUSDT").strip()
    if not watchlist_raw:
        errors.append("WATCHLIST is empty (must contain at least one symbol)")
        watchlist = []
    else:
        watchlist_original = [s.strip() for s in watchlist_raw.split(",") if s.strip()]
        watchlist = [normalize_symbol(s) for s in watchlist_original]
        
        # Log normalization if any symbol was lowercase
        if any(orig != norm for orig, norm in zip(watchlist_original, watchlist)):
            print(f"[CONFIG] Normalized symbols: {watchlist_original} → {watchlist}")
    
    data_dir_str = os.getenv("DATA_DIR", "./shared_data").strip()
    data_dir = Path(data_dir_str).resolve()
    
    log_level = os.getenv("LOG_LEVEL", "INFO").upper().strip()
    if log_level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        errors.append(f"LOG_LEVEL={log_level} invalid")
    
    # =========================================================================
    # Binance-specific validation
    # =========================================================================
    
    if exchange == "binance":
        binance_api_key = os.getenv("BINANCE_API_KEY", "").strip()
        binance_api_secret = os.getenv("BINANCE_API_SECRET", "").strip()
        
        if not binance_api_key:
            errors.append(
                "BINANCE_API_KEY is required when EXCHANGE=binance\n"
                "  Hint: Set BINANCE_API_KEY in .env file"
            )
        
        if not binance_api_secret:
            errors.append(
                "BINANCE_API_SECRET is required when EXCHANGE=binance\n"
                "  Hint: Set BINANCE_API_SECRET in .env file"
            )
        
        # Check for hidden unicode/whitespace in keys
        if binance_api_key and (binance_api_key != binance_api_key.strip() or not binance_api_key.isprintable()):
            errors.append("BINANCE_API_KEY contains invalid whitespace or non-printable characters")
        
        if binance_api_secret and (binance_api_secret != binance_api_secret.strip() or not binance_api_secret.isprintable()):
            errors.append("BINANCE_API_SECRET contains invalid whitespace or non-printable characters")
        
        # BINANCE_TESTNET must mirror TESTNET
        binance_testnet_str = os.getenv("BINANCE_TESTNET", "").lower().strip()
        if binance_testnet_str:
            binance_testnet = binance_testnet_str in ("true", "1", "yes", "on")
            if binance_testnet != testnet:
                errors.append(
                    f"BINANCE_TESTNET={binance_testnet} conflicts with TESTNET={testnet}\n"
                    f"  Hint: Set BINANCE_TESTNET={str(testnet).lower()} or remove BINANCE_TESTNET"
                )
        else:
            binance_testnet = testnet  # Mirror TESTNET
    else:
        binance_api_key = ""
        binance_api_secret = ""
        binance_testnet = testnet
    
    # =========================================================================
    # WebSocket and REST endpoints (with sensible defaults)
    # =========================================================================
    
    # UM Futures (USDⓈ-M)
    binance_um_testnet_ws_base = os.getenv(
        "BINANCE_UM_TESTNET_WS_BASE",
        "wss://stream.binancefuture.com/ws"
    ).strip()
    
    binance_um_ws_base = os.getenv(
        "BINANCE_UM_WS_BASE",
        "wss://fstream.binance.com/ws"
    ).strip()
    
    binance_um_testnet_rest_base = os.getenv(
        "BINANCE_UM_TESTNET_REST_BASE",
        "https://testnet.binancefuture.com"
    ).strip()
    
    binance_um_rest_base = os.getenv(
        "BINANCE_UM_REST_BASE",
        "https://fapi.binance.com"
    ).strip()
    
    # Spot
    binance_spot_testnet_ws_base = os.getenv(
        "BINANCE_SPOT_TESTNET_WS_BASE",
        "wss://testnet.binance.vision/ws"
    ).strip()
    
    binance_spot_ws_base = os.getenv(
        "BINANCE_SPOT_WS_BASE",
        "wss://stream.binance.com:9443/ws"
    ).strip()
    
    binance_spot_testnet_rest_base = os.getenv(
        "BINANCE_SPOT_TESTNET_REST_BASE",
        "https://testnet.binance.vision"
    ).strip()
    
    binance_spot_rest_base = os.getenv(
        "BINANCE_SPOT_REST_BASE",
        "https://api.binance.com"
    ).strip()
    
    # =========================================================================
    # Fail-fast or return errors
    # =========================================================================
    
    if errors:
        error_msg = "\n".join([f"  ❌ {err}" for err in errors])
        full_error = f"Configuration validation failed:\n{error_msg}"
        
        if fail_fast:
            print(full_error, file=sys.stderr)
            sys.exit(1)
        else:
            return None, full_error
    
    # =========================================================================
    # Create DATA_DIR if it doesn't exist
    # =========================================================================
    
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "health").mkdir(exist_ok=True)
        (data_dir / "accounts").mkdir(exist_ok=True)
        (data_dir / "runtime").mkdir(exist_ok=True)
    except Exception as e:
        error_msg = f"Failed to create DATA_DIR: {data_dir}\n  Error: {e}"
        if fail_fast:
            print(f"❌ {error_msg}", file=sys.stderr)
            sys.exit(1)
        else:
            return None, error_msg
    
    # =========================================================================
    # Build config object
    # =========================================================================
    
    config = TradingConfig(
        env=env,
        testnet=testnet,
        exchange=exchange,
        market=market,
        watchlist=watchlist,
        data_dir=data_dir,
        log_level=log_level,
        binance_api_key=binance_api_key,
        binance_api_secret=binance_api_secret,
        binance_testnet=binance_testnet,
        binance_um_testnet_ws_base=binance_um_testnet_ws_base,
        binance_um_ws_base=binance_um_ws_base,
        binance_spot_testnet_ws_base=binance_spot_testnet_ws_base,
        binance_spot_ws_base=binance_spot_ws_base,
        binance_um_testnet_rest_base=binance_um_testnet_rest_base,
        binance_um_rest_base=binance_um_rest_base,
        binance_spot_testnet_rest_base=binance_spot_testnet_rest_base,
        binance_spot_rest_base=binance_spot_rest_base,
    )
    
    return config, None


def load_config() -> TradingConfig:
    """
    Load and validate configuration (fail-fast mode).
    
    Returns:
        TradingConfig instance
    
    Raises:
        SystemExit: If validation fails
    """
    config, error = validate_and_load_config(fail_fast=True)
    return config


# ============================================================================
# CLI helper for diagnostics
# ============================================================================

def print_config_summary():
    """Print configuration summary (for diagnostics)"""
    config, error = validate_and_load_config(fail_fast=False)
    
    if error:
        print(error, file=sys.stderr)
        sys.exit(1)
    
    config.log_config()


if __name__ == "__main__":
    # Test configuration
    import argparse
    
    parser = argparse.ArgumentParser(description="Config Validator & Diagnostic Tool")
    parser.add_argument("--summary", action="store_true", help="Print config summary")
    args = parser.parse_args()
    
    if args.summary:
        print_config_summary()
    else:
        # Default: validate and show one-liner
        config = load_config()
        print(f"✅ Config OK: {config.get_config_summary()}")

