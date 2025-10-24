# Coin Quant R11

Clean, minimal, and stable Python 3.11 trading runtime with canonical module entry points and operational readiness.

## Quick Start

### Prerequisites

- Python 3.11+ (required)
- Virtual environment
- Binance API credentials (testnet recommended)

### Installation

```bash
# Clone repository
git clone <repository-url>
cd coin_quant_r11

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install package in development mode
pip install -e .
```

### Configuration

1. Copy configuration template:
```bash
cp config.env.template config.env
```

2. Edit `config.env` with your settings:
```env
# Binance API Configuration (REQUIRED)
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_api_secret_here
BINANCE_USE_TESTNET=true

# Trading Configuration
TRADING_MODE=testnet
SIMULATION_MODE=true
LIVE_TRADING_ENABLED=false
TEST_ALLOW_DEFAULT_SIGNAL=false  # CRITICAL: Keep false for safety

# Service Configuration
ARES_FRESHNESS_THRESHOLD=10.0
FEEDER_HEARTBEAT_INTERVAL=5.0
TRADER_ORDER_COOLDOWN=1.0
```

### Running Services

#### Windows (PowerShell)

```powershell
# Launch individual services
.\scripts\launch_feeder.ps1
.\scripts\launch_ares.ps1
.\scripts\launch_trader.ps1

# Launch all services in dependency order
.\scripts\launch_all.ps1
```

#### Cross-Platform

```bash
# Start individual services
coin-quant-feeder
coin-quant-ares
coin-quant-trader

# Start all services
python launch.py
```

### Acceptance Checklist

Before running in production:

- [ ] Python 3.11+ installed
- [ ] Virtual environment activated
- [ ] Configuration validated (`config.env` present)
- [ ] API credentials configured
- [ ] `TEST_ALLOW_DEFAULT_SIGNAL=false`
- [ ] Testnet mode enabled
- [ ] All services start without errors
- [ ] Health checks pass
- [ ] Readiness gates function correctly

## Architecture

### Core Services

- **Feeder**: Multi-symbol data ingestion with health reporting
- **ARES**: Signal generation with health gating and dependency checks
- **Trader**: Order execution with balance checks and failsafe logic
- **Memory**: Immutable audit trail and integrity verification

### Health Contracts & Readiness Gates

Each service implements health contracts with freshness thresholds:

- **Feeder**: 10 seconds freshness threshold
- **ARES**: 30 seconds freshness threshold (blocks on stale Feeder data)
- **Trader**: 60 seconds freshness threshold (blocks on stale ARES data)
- **Memory**: 5 seconds freshness threshold

### Readiness Gates

Services implement readiness gates that prevent unsafe operation:

- **ARES**: Blocks signal generation if Feeder is unhealthy or stale
- **Trader**: Blocks order execution if ARES is unhealthy or account balance insufficient

## Configuration Management

### SSOT (Single Source of Truth)

Configuration precedence order:

1. Environment variables (highest priority)
2. `shared_data/ssot/env.json`
3. Default values (lowest priority)

### Required Configuration

- `BINANCE_API_KEY`: Binance API key
- `BINANCE_API_SECRET`: Binance API secret
- `BINANCE_USE_TESTNET`: Use testnet (recommended: true)

### Critical Safety Settings

- `TEST_ALLOW_DEFAULT_SIGNAL=false`: Disable default signals (CRITICAL)
- `LIVE_TRADING_ENABLED=false`: Disable live trading for safety
- `DISABLE_ORDER_GUARDRAILS=false`: Keep safety checks enabled

## Operational Features

### Health Monitoring

- Real-time health status reporting
- Freshness threshold monitoring
- Dependency health checks
- Automatic service blocking on unhealthy dependencies

### Memory Layer

- Immutable event chain
- Snapshot store for state reconstruction
- Hash chain for integrity verification
- Automatic quarantine on corruption detection

### Failure Drills

Automated testing of system resilience:

- **Feeder Outage**: Tests ARES blocking and recovery
- **Insufficient Balance**: Tests order scaling and quarantine
- **Memory Corruption**: Tests integrity checks and recovery

### Debug Bundle Export

One-command troubleshooting:

```bash
python -c "from coin_quant.shared.observability import create_debug_bundle; print(create_debug_bundle())"
```

## Development

### Project Structure

```
coin_quant_r11/
├── src/coin_quant/          # Main package
│   ├── shared/              # Shared utilities
│   │   ├── health_contracts.py    # Health & readiness gates
│   │   ├── config_ssot.py         # Configuration management
│   │   ├── memory_validator.py   # Memory integrity
│   │   ├── observability.py      # Logging & monitoring
│   │   └── failure_drills.py     # Resilience testing
│   ├── feeder/              # Feeder service
│   ├── ares/                # ARES service
│   ├── trader/              # Trader service
│   └── memory/              # Memory layer
├── scripts/                 # Launch scripts
├── tests/                   # Test files
├── docs/                    # Documentation
└── shared_data/             # Runtime data
```

### Running Tests

```bash
# Run comprehensive acceptance tests
python test_acceptance.py

# Run smoke tests (quick)
python test_smoke.py

# Run failure drills
python -c "from coin_quant.shared.failure_drills import run_failure_drills; run_failure_drills()"

# Run specific tests
python -m pytest tests/
```

### Code Quality

```bash
# Lint code
flake8 src/

# Type check
mypy src/

# Format code
black src/
```

## Troubleshooting

### Common Issues

1. **Import Errors**: Ensure virtual environment is activated and PYTHONPATH includes `src/`
2. **Configuration Errors**: Run `python validate.py` to check configuration
3. **Service Startup Failures**: Check logs in `shared_data/logs/`
4. **Health Check Failures**: Verify service dependencies and freshness thresholds
5. **Readiness Gate Blocks**: Check dependency health and configuration

### Debug Bundle

Export debug bundle for troubleshooting:

```bash
python -c "from coin_quant.shared.observability import create_debug_bundle; print(create_debug_bundle())"
```

### Logs

Service logs are stored in `shared_data/logs/` with rotation:

- `feeder.log`: Feeder service logs
- `ares.log`: ARES service logs  
- `trader.log`: Trader service logs

### Health Status

Check service health:

```bash
# View health status
cat shared_data/health/health.json

# Check readiness summary
python -c "from coin_quant.shared.health_contracts import get_health_manager; print(get_health_manager().get_readiness_summary())"
```

## Release Information

- **Version**: 1.0.0-rc1
- **Python**: 3.11+ required
- **Status**: Release Candidate
- **Acceptance**: All operational requirements met

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and linting
5. Submit a pull request

## License

This project is licensed under the MIT License.

## Support

For support and questions:

- Create an issue on GitHub
- Check the documentation
- Review the troubleshooting guide
- Export debug bundle for analysis