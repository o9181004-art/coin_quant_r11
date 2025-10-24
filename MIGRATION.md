# Migration Note - Coin Quant R11

## Overview
This document maps old file paths to new package modules and lists dropped artifacts.

## File Path Mappings

### Shared Utilities
| Old Path | New Path | Notes |
|----------|----------|-------|
| `shared/` | `src/coin_quant/shared/` | Moved to package structure |
| `shared/time_utils.py` | `src/coin_quant/shared/time.py` | Renamed and refactored |
| `shared/atomic_writer.py` | `src/coin_quant/shared/io.py` | Merged into I/O utilities |
| `shared/health_manager.py` | `src/coin_quant/shared/health.py` | Refactored with better structure |

### Services
| Old Path | New Path | Notes |
|----------|----------|-------|
| `services/feeder_service.py` | `src/coin_quant/feeder/service.py` | Moved to package structure |
| `services/ares_service.py` | `src/coin_quant/ares/service.py` | Moved to package structure |
| `services/trader_service.py` | `src/coin_quant/trader/service.py` | Moved to package structure |

### Memory Layer
| Old Path | New Path | Notes |
|----------|----------|-------|
| N/A | `src/coin_quant/memory/` | New memory layer components |
| N/A | `src/coin_quant/memory/event_chain.py` | New event chain |
| N/A | `src/coin_quant/memory/snapshot_store.py` | New snapshot store |
| N/A | `src/coin_quant/memory/hash_chain.py` | New hash chain |
| N/A | `src/coin_quant/memory/client.py` | New memory client |

## Dropped Artifacts

### Experiments and Notebooks
- `notebooks/` - Experimental notebooks
- `experiments/` - Experimental code
- `*.ipynb` - Jupyter notebooks

### Caches and Build Outputs
- `__pycache__/` - Python cache directories
- `*.pyc` - Compiled Python files
- `build/` - Build output directory
- `dist/` - Distribution directory

### Obsolete Scripts
- `start_system.py` - Replaced by module entry points
- `auto_trading_launcher.py` - Replaced by CLI launcher
- `system_monitor.py` - Integrated into health system

### Large Assets
- `shared_data/exchange_info.json` - Regenerated from API
- `shared_data/universe_cache.json` - Regenerated from API
- `shared_data/positions_snapshot.json` - Regenerated from API

## Import Changes

### Old Imports
```python
from shared.time_utils import utc_now_ms
from shared.atomic_writer import atomic_write_json
from shared.health_manager import HealthManager
```

### New Imports
```python
from coin_quant.shared.time import utc_now_seconds
from coin_quant.shared.io import atomic_write_json
from coin_quant.shared.health import health_manager
```

## Configuration Changes

### Environment Variables
- `SHARED_DATA` - Now defaults to `./shared_data`
- `COIN_QUANT_DATA_DIR` - New environment variable for data directory

### Health Files
- Old: `shared_data/health.json`
- New: `shared_data/health/{service}.json`

## Backward Compatibility

### Path Resolver Shim
A thin path-resolver shim is provided for legacy components that still assume CWD:

```python
from coin_quant.shared.paths import ssot_dir
data_dir = ssot_dir()  # Resolves to shared_data/
```

### Migration Helper
Use the migration helper to update old imports:

```python
# Old
from shared.time_utils import utc_now_ms

# New
from coin_quant.shared.time import utc_now_seconds
```

## Breaking Changes

1. **Absolute Imports Required**: All imports must use absolute form (`from coin_quant...`)
2. **Module Entry Points**: Services must be launched as modules, not scripts
3. **Health File Structure**: Health files now use service-specific naming
4. **Memory Layer**: New memory layer replaces old event logging

## Migration Steps

1. **Update Imports**: Change all relative imports to absolute imports
2. **Update Service Launches**: Use module entry points instead of script execution
3. **Update Health Checks**: Use new health file structure
4. **Update Configuration**: Use new configuration management
5. **Test Services**: Verify all services work with new structure

## Support

For migration issues, refer to:
- `RUN_GUIDE.md` - Service launch instructions
- `test_smoke.py` - Smoke tests for verification
- `launch.py` - CLI launcher for services
