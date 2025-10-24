# Coin Quant R11 - Release Candidate 1

## 🎯 Release Summary

**Version**: 1.0.0-rc1  
**Release Date**: January 24, 2025  
**Status**: Release Candidate  
**Python Requirement**: 3.11+

This release candidate implements all operational requirements for production readiness, delivering a clean, minimal, and stable Python 3.11 trading runtime with comprehensive health contracts, configuration management, memory layer validation, and failure recovery procedures.

## ✅ Operational Requirements Completed

### 1. Health Contracts & Readiness Gates
- **Canonical Health Schema**: Standardized health reporting for all services
- **Feeder Health Writer**: Periodic updates with accurate freshness tracking
- **ARES HealthGate**: Blocks signal emission on stale/missing Feeder data
- **Trader Readiness**: Account balance checks with exponential backoff
- **Centralized Logging**: Structured readiness decisions with clear reasons

### 2. Configuration SSOT Hardening
- **Authoritative Configuration**: Environment variables → SSOT → defaults precedence
- **Strict Validation**: Required field checks with early exit on failure
- **Default Signal Control**: `TEST_ALLOW_DEFAULT_SIGNAL` defaults to "off"
- **Configuration Hash**: Startup banners include config summary for reproducibility
- **Validation Reports**: Clear error messages with remediation hints

### 3. Memory Layer Validation
- **MemoryClient Façade**: Complete API for append, snapshot, verify, replay, quarantine
- **Integrity Checks**: Lightweight periodic validation with non-blocking operation
- **Quarantine Management**: Scope-limited isolation on corruption detection
- **Deterministic Replay**: State reconstruction from snapshots plus deltas
- **Debug Bundle Export**: One-command troubleshooting data collection

### 4. Observability & Logs
- **Standardized Banners**: Service name, version, config hash, thresholds
- **Structured Logging**: Consistent fields for health, readiness, orders, failures
- **Log Rotation**: Size/time-based rotation with retention policies
- **Debug Bundle**: Last N minutes of logs, health files, integrity summary
- **Incident Timeline**: Concise event sequence for troubleshooting

### 5. Run Scripts & Developer Ergonomics
- **Windows PowerShell Scripts**: Individual and combined service launchers
- **Dependency Order**: Feeder → ARES → Trader with readiness waits
- **VS Code Integration**: Workspace pinned to 3.11 venv with launch profiles
- **Cross-Platform**: Makefile targets for Unix/Linux parity
- **3-Minute Quickstart**: Complete setup and launch guide

### 6. Failure Drills & Recovery
- **Feeder Outage Drill**: ARES blocks with stale-health reason, Trader waits
- **Insufficient Balance Drill**: Order scaling, retry limits, symbol quarantine
- **Memory Corruption Drill**: Integrity failure injection, debug bundle export
- **Automated Recovery**: Deterministic success conditions and revert procedures
- **Drill Documentation**: Scripted steps with expected log snippets

### 7. Documentation Updates
- **Complete README**: Quickstart, configuration, troubleshooting
- **Comprehensive RUNBOOK**: Procedures, decision trees, failure recovery
- **Versioned Schemas**: JSON examples for health, events, snapshots
- **Migration Guide**: Legacy system to R11 transition
- **Troubleshooting**: Common issues and resolution steps

### 8. CI/Lint Refinements
- **Python 3.11 Enforcement**: Interpreter version validation
- **Readiness Gates**: Smoke tests for health contracts
- **Memory Integrity**: Smoke tests for validation system
- **Offline CI**: Fast execution without external dependencies
- **Startup Banner Validation**: Configuration hash verification

## 🚀 New Features

### Health Contracts System
```python
from coin_quant.shared.health_contracts import get_health_manager, create_readiness_gate

# Health management
health_manager = get_health_manager()
health_manager.update_feeder_health(symbols=["BTCUSDT"], ws_connected=True)

# Readiness gates
ares_gate = create_readiness_gate("ares")
if ares_gate.wait_for_readiness(timeout=300):
    print("ARES is ready")
```

### Configuration SSOT
```python
from coin_quant.shared.config_ssot import get_config, validate_and_exit_on_error

# Configuration management
config = get_config()
validate_and_exit_on_error(config)

# Get configuration summary
summary = config.get_config_summary()
print(f"Config hash: {summary['config_hash']}")
```

### Memory Validation
```python
from coin_quant.shared.memory_validator import get_memory_validator

# Memory integrity
validator = get_memory_validator()
report = validator.validate_integrity()
print(f"Memory status: {report.status}")

# Debug bundle export
bundle_path = validator.export_debug_bundle()
print(f"Debug bundle: {bundle_path}")
```

### Observability
```python
from coin_quant.shared.observability import create_structured_logger, create_debug_bundle

# Structured logging
logger = create_structured_logger("feeder")
logger.log_health_update("ok", freshness_sec=5.2)

# Debug bundle
bundle_path = create_debug_bundle(minutes_back=30)
```

### Failure Drills
```python
from coin_quant.shared.failure_drills import run_failure_drills

# Run all drills
results = run_failure_drills()
for result in results:
    print(f"{result.drill_type.value}: {'PASS' if result.success else 'FAIL'}")
```

## 📦 Installation

### Prerequisites
- Python 3.11+
- Virtual environment
- Binance API credentials

### Quick Install
```bash
# Clone and setup
git clone <repository-url>
cd coin_quant_r11
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install
pip install -r requirements.txt
pip install -e .
```

### Configuration
```bash
# Copy template
cp config.env.template config.env

# Edit with your settings
# BINANCE_API_KEY=your_key
# BINANCE_API_SECRET=your_secret
# BINANCE_USE_TESTNET=true
```

## 🎮 Usage

### Windows (PowerShell)
```powershell
# Launch all services
.\scripts\launch_all.ps1

# Launch individual services
.\scripts\launch_feeder.ps1
.\scripts\launch_ares.ps1
.\scripts\launch_trader.ps1
```

### Cross-Platform
```bash
# Launch all services
python launch.py

# Launch individual services
coin-quant-feeder
coin-quant-ares
coin-quant-trader
```

## ✅ Acceptance Criteria

All acceptance criteria have been met:

- [x] Feeder writes health within freshness threshold
- [x] ARES blocks until Feeder is healthy; no default signals under stale data
- [x] Trader respects simulation mode, performs balance checks, scales down, retries, quarantines on failure
- [x] Memory integrity passes; debug bundle exports; replay reconstructs state
- [x] Documentation walkthrough succeeds without ambiguity
- [x] System can be started from scratch using only documented steps
- [x] Readiness gates prevent unsafe operation
- [x] Integrity checks and drills demonstrate resilience
- [x] Operators can diagnose issues using runbook and debug bundle

## 🧪 Testing

### Acceptance Tests (Comprehensive)
```bash
python test_acceptance.py
```
Runs all 8 operational requirement tests and validates RC readiness.

### Smoke Tests (Quick)
```bash
python test_smoke.py
```
Basic functionality tests for package structure and imports.

### Failure Drills
```bash
python -c "from coin_quant.shared.failure_drills import run_failure_drills; run_failure_drills()"
```
Simulates failure scenarios and validates recovery procedures.

### Health Checks
```bash
python -c "from coin_quant.shared.health_contracts import get_health_manager; print(get_health_manager().get_readiness_summary())"
```
Validates health contracts and readiness gates.

## 🔄 Migration

### From Legacy System
1. Update import statements to use `coin_quant.*` modules
2. Replace `shared.*` imports with `coin_quant.shared.*`
3. Update configuration to use SSOT system
4. Migrate health monitoring to new contracts

### Configuration Migration
```python
# Legacy
from shared.config import get_config

# New
from coin_quant.shared.config_ssot import get_config
```

## 🐛 Known Issues

None. This is a release candidate with all known issues resolved.

## 🆘 Support

- **GitHub Issues**: [Create issue](https://github.com/your-repo/issues)
- **Documentation**: See README.md and RUNBOOK.md
- **Debug Bundle**: Use `create_debug_bundle()` for troubleshooting

## 🎯 Next Steps

1. **Testing**: Run acceptance tests in your environment
2. **Configuration**: Set up your API credentials and preferences
3. **Monitoring**: Set up health monitoring and alerting
4. **Production**: Deploy with confidence after testing

## 👥 Contributors

- Coin Quant Team

## 📄 License

MIT License - see LICENSE file for details.

---

**Coin Quant R11 - Ready for Production** 🚀
