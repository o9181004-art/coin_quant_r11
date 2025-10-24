# Coin Quant R11 - Run Guide

## Quick Start

### Prerequisites
- Python 3.11+
- Virtual environment (recommended)

### Setup
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Install package in editable mode
pip install -e .
```

### Running Services

#### Feeder Service
```bash
# Using module entry point
python -m coin_quant.feeder.service

# Using CLI launcher
python launch.py feeder

# Using console script (after install)
coin-quant-feeder
```

#### ARES Service
```bash
# Using module entry point
python -m coin_quant.ares.service

# Using CLI launcher
python launch.py ares

# Using console script (after install)
coin-quant-ares
```

#### Trader Service
```bash
# Using module entry point
python -m coin_quant.trader.service

# Using CLI launcher
python launch.py trader

# Using console script (after install)
coin-quant-trader
```

### Service Order
Services must be started in order:
1. **Feeder** - Data ingestion
2. **ARES** - Signal generation (waits for Feeder health)
3. **Trader** - Order execution (waits for ARES health)

### Health Monitoring
Each service writes health status to:
- `shared_data/health/feeder.json`
- `shared_data/health/ares.json`
- `shared_data/health/trader.json`

### Configuration
Configuration is loaded from `config.env` in the project root.

### Data Directory
All runtime data is stored in `shared_data/`:
- `shared_data/health/` - Service health status
- `shared_data/memory/` - Memory layer data
- `shared_data/logs/` - Service logs

### Smoke Tests
Run smoke tests to verify package integrity:
```bash
python test_smoke.py
```

### Troubleshooting

#### Service Won't Start
- Check Python version (3.11+ required)
- Verify virtual environment is activated
- Check configuration in `config.env`

#### Health Check Failures
- Verify service order (Feeder → ARES → Trader)
- Check freshness thresholds in configuration
- Review service logs

#### Memory Layer Issues
- Verify data directory permissions
- Check disk space
- Review integrity with `verify_chain()`

### Recovery
1. Stop all services
2. Check health files for errors
3. Restart in correct order
4. Monitor health status
5. Check logs for issues
