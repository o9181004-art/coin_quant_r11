# Legacy Dashboard - Required Files and Setup

## Overview

The legacy dashboard (`app_old.py`) has been restored and is now accessible via the `app.py` wrapper. The dashboard runs exactly as before with the same layout, text, and functionality.

## Required Files Structure

The dashboard expects the following files in the `shared_data` directory:

```
shared_data/
├── health/
│   ├── feeder_health.json
│   ├── ares_health.json
│   ├── trader_health.json
│   └── memory_health.json
├── snapshots/
│   ├── prices_btcusdt.json
│   ├── prices_ethusdt.json
│   ├── prices_adausdt.json
│   └── ... (other symbol price files)
├── signals/
│   ├── ares_btcusdt.json
│   ├── ares_ethusdt.json
│   └── ... (other symbol signal files)
├── positions_snapshot.json
├── account_info.json
├── account_snapshot.json
├── auto_trading_state.json
├── exposure.json
├── databus_snapshot.json
└── coin_watchlist.json
```

## How to Generate Required Files

### 1. Start Feeder Service
```bash
python launch.py feeder
```
This will generate:
- `shared_data/snapshots/prices_*.json` files
- `shared_data/health/feeder_health.json`

### 2. Start ARES Service
```bash
python launch.py ares
```
This will generate:
- `shared_data/signals/ares_*.json` files
- `shared_data/health/ares_health.json`

### 3. Start Trader Service
```bash
python launch.py trader
```
This will generate:
- `shared_data/positions_snapshot.json`
- `shared_data/account_info.json`
- `shared_data/account_snapshot.json`
- `shared_data/auto_trading_state.json`
- `shared_data/health/trader_health.json`

### 4. Start Memory Service
```bash
python launch.py memory
```
This will generate:
- `shared_data/health/memory_health.json`

## File Formats

### Price Snapshot Files (`prices_*.json`)
```json
{
  "symbol": "BTCUSDT",
  "price": 45000.00,
  "change": 1000.00,
  "change_percent": 2.27,
  "timestamp": "2025-10-24T13:00:00Z"
}
```

### Signal Files (`ares_*.json`)
```json
{
  "symbol": "BTCUSDT",
  "status": "ACTIVE",
  "entry": 44000.00,
  "target": 46000.00,
  "stop_loss": 42000.00,
  "timestamp": "2025-10-24T13:00:00Z"
}
```

### Position Snapshot (`positions_snapshot.json`)
```json
{
  "BTCUSDT": {
    "symbol": "BTCUSDT",
    "side": "LONG",
    "size": 0.1,
    "entry_price": 44000.00,
    "current_price": 45000.00,
    "unrealized_pnl": 100.00,
    "unrealized_pnl_percent": 2.27
  }
}
```

### Account Info (`account_info.json`)
```json
{
  "current_capital": 100000.00,
  "initial_capital": 100000.00,
  "today_profit": 0.00,
  "total_profit": 0.00,
  "today_return": 0.00,
  "total_return": 0.00
}
```

### Health Files (`health/*.json`)
```json
{
  "status": "HEALTHY",
  "last_update": "2025-10-24T13:00:00Z",
  "message": "Service running normally"
}
```

## Running the Dashboard

### Default (Legacy Dashboard)
```bash
streamlit run app.py
```
This runs the exact same dashboard as before with no changes to layout or functionality.

### Environment Variables
- `UI_MODE=classic` (default) - Runs legacy dashboard
- `UI_MODE=modular` - Runs new modular dashboard
- `COIN_QUANT_ROOT` - Project root directory
- `MONITORING_BACKEND=file` (default) - Use file backend
- `HEALTH_DIR` - Health directory override

## Troubleshooting

### Missing Files
If any files are missing, the dashboard will show "NO DATA" warnings instead of crashing. This is the expected behavior.

### Service Status
The dashboard will show the status of each service:
- ✅ **HEALTHY** - Service is running normally
- ❌ **ERROR** - Service has issues
- ⚠️ **UNKNOWN** - Service status unknown

### Data Age
The dashboard shows data age for each symbol:
- Price data age (from snapshots)
- ARES signal age (from signals)

## Notes

- The legacy dashboard maintains exact backward compatibility
- No changes to UI layout, text, or functionality
- All path issues have been resolved
- Works without setting PYTHONPATH
- Graceful handling of missing data files