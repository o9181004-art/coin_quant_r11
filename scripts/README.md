# Coin Quant R11 - Windows Service Launcher Scripts

This directory contains Windows-specific launcher scripts for Coin Quant R11 services.

## Scripts Overview

### `launch_feeder.ps1`
Launches the Feeder service with proper environment setup and logging.

### `launch_ares.ps1`
Launches the ARES service with dependency checks and readiness gates.

### `launch_trader.ps1`
Launches the Trader service with balance checks and order execution.

### `launch_all.ps1`
Launches all services in dependency order with readiness waits.

### `launch_dev.ps1`
Development launcher with hot reload and debug logging.

## Usage

```powershell
# Launch individual service
.\scripts\launch_feeder.ps1

# Launch all services
.\scripts\launch_all.ps1

# Development mode
.\scripts\launch_dev.ps1
```

## Prerequisites

- Python 3.11+ installed
- Virtual environment activated
- Configuration file (`config.env`) present
- Required dependencies installed

## Environment Variables

The scripts automatically set:
- `PYTHONPATH` to include the `src` directory
- `COIN_QUANT_DATA_DIR` to the project data directory
- `LOG_LEVEL` based on the launch mode

## Error Handling

All scripts include:
- Python version validation
- Virtual environment checks
- Configuration validation
- Graceful error handling
- Process cleanup on exit
