# Migration Notes - UI Refactoring

## Overview

This migration refactors the oversized `app.py` (6276 lines) into a clean, modular architecture with proper data access patterns.

## Key Changes

### 1. New Module Structure

```
src/coin_quant/
├── shared/
│   ├── pathing.py          # Robust path resolution
│   └── data_access.py      # Data Access Layer with pluggable backends
└── guard/ui/
    ├── app_main.py         # Main application entry point
    ├── config.py           # UI configuration management
    ├── state.py            # Streamlit session state management
    ├── layout.py           # Page layout and tab structure
    ├── views/
    │   └── symbol_cards.py # Symbol card rendering
    └── widgets/
        └── common.py       # Reusable UI components
```

### 2. Data Access Layer (DAL)

The new DAL provides a unified interface for accessing data from different backends:

- **FileBackend**: Reads from JSON/NDJSON files with graceful error handling
- **HTTPBackend**: Placeholder for future HTTP-based data access
- **DataBus**: Unified interface that composes repositories

### 3. Path Resolution

All paths are now resolved relative to project root with environment overrides:

```python
from coin_quant.shared.pathing import get_paths
paths = get_paths()
```

### 4. Configuration

Environment variables with sensible defaults:

- `MONITORING_BACKEND`: "file" | "http" (default: "file")
- `HEALTH_DIR`: Override health directory path
- `UI_SHOW_DEBUG`: Show debug information (default: false)
- `SNAPSHOT_AGE_WARN`: Warning threshold for data age (default: 300s)
- `SNAPSHOT_AGE_HALT`: Critical threshold for data age (default: 900s)

## Data Sources Mapped

### Symbol Cards
- **Price Data**: `shared_data/snapshots/prices_{symbol}.json`
- **Signal Data**: `shared_data/ares_signals.json` or `shared_data/ares/*.json`
- **Position Data**: `shared_data/positions_snapshot.json`

### Health Monitoring
- **Feeder Health**: `shared_data/health/feeder_health.json`
- **ARES Health**: `shared_data/health/ares_health.json`
- **Trader Health**: `shared_data/health/trader_health.json`
- **Memory Health**: `shared_data/health/memory_health.json`

### System Data
- **Account Info**: `shared_data/account_info.json`
- **Account Snapshot**: `shared_data/account_snapshot.json`
- **Auto Trading State**: `shared_data/auto_trading_state.json`

## Environment Variables

### Required
- `COIN_QUANT_ROOT`: Project root directory (optional, auto-detected)

### Optional
- `MONITORING_BACKEND`: Data backend type (default: "file")
- `MONITORING_ENDPOINT`: HTTP endpoint for HTTP backend
- `UI_SHOW_DEBUG`: Show debug information (default: false)
- `UI_SHOW_ADVANCED`: Show advanced features (default: false)
- `UI_CARDS_ONLY`: Show only symbol cards (default: false)
- `AUTO_REFRESH_ENABLED`: Enable auto-refresh (default: true)
- `AUTO_REFRESH_SEC`: Auto-refresh interval (default: 5)

### Data Path Overrides
- `SHARED_DATA_DIR`: Override shared data directory
- `HEALTH_DIR`: Override health directory
- `SNAPSHOTS_DIR`: Override snapshots directory
- `SIGNALS_DIR`: Override signals directory
- `PRICES_DIR`: Override prices directory

### Thresholds
- `SNAPSHOT_AGE_WARN`: Warning threshold for snapshot age (default: 300)
- `SNAPSHOT_AGE_HALT`: Critical threshold for snapshot age (default: 900)
- `SIGNAL_AGE_WARN`: Warning threshold for signal age (default: 600)
- `SIGNAL_AGE_HALT`: Critical threshold for signal age (default: 1800)

## Usage

### Running the Dashboard

```bash
# Basic usage
streamlit run app.py

# With custom configuration
MONITORING_BACKEND=file UI_SHOW_DEBUG=true streamlit run app.py
```

### File Backend (Default)

The file backend reads from the local file system. All data files are expected to be in the `shared_data` directory structure.

### HTTP Backend (Future)

```bash
MONITORING_BACKEND=http MONITORING_ENDPOINT=http://localhost:8080 streamlit run app.py
```

## Testing

Run the test suite to verify the refactoring:

```bash
python tests/test_ui_paths.py
```

## Benefits

1. **Maintainability**: Code is now split into focused, testable modules
2. **Reliability**: Graceful handling of missing data files
3. **Flexibility**: Pluggable backends for different data sources
4. **Portability**: No hardcoded paths, works from any directory
5. **Configuration**: Environment-driven configuration with sensible defaults

## Breaking Changes

- The old `app.py` has been replaced with a new streamlined version
- Direct file path access has been replaced with the DAL
- Some internal functions have been moved to separate modules

## Migration Checklist

- [x] Create robust path resolver
- [x] Implement Data Access Layer
- [x] Split app.py into modules
- [x] Add configuration management
- [x] Implement graceful error handling
- [x] Add comprehensive tests
- [x] Update documentation
