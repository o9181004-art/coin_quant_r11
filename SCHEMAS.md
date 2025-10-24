# Coin Quant R11 - Schema Documentation

This document defines the JSON schemas and data formats used throughout Coin Quant R11.

## Health Status Schemas

### Feeder Health Schema

**File:** `shared_data/health/feeder.json`

```json
{
  "service": "feeder",
  "status": "ok|degraded|error",
  "last_update_ts": 1640995200.0,
  "updated_within_sec": 5.2,
  "symbols": ["BTCUSDT", "ETHUSDT", "ADAUSDT"],
  "ws_connected": true,
  "rest_api_ok": true,
  "symbols_count": 3,
  "last_symbol_update": 1640995200.0
}
```

**Fields:**
- `service`: Always "feeder"
- `status`: Health status (ok, degraded, error)
- `last_update_ts`: Unix timestamp of last update
- `updated_within_sec`: Age of data in seconds
- `symbols`: List of monitored symbols
- `ws_connected`: WebSocket connection status
- `rest_api_ok`: REST API connectivity status
- `symbols_count`: Number of active symbols
- `last_symbol_update`: Timestamp of last symbol update

### ARES Health Schema

**File:** `shared_data/health/ares.json`

```json
{
  "service": "ares",
  "status": "ok|degraded|error",
  "last_update_ts": 1640995200.0,
  "updated_within_sec": 2.1,
  "signal_count": 15,
  "last_signal_time": 1640995195.0,
  "feeder_health_ok": true,
  "default_signals_blocked": false,
  "active_strategies": ["trend_multi_tf", "bb_mean_revert_v2"],
  "latency_ms_p50": 45.2
}
```

**Fields:**
- `service`: Always "ares"
- `status`: Health status (ok, degraded, error)
- `last_update_ts`: Unix timestamp of last update
- `updated_within_sec`: Age of data in seconds
- `signal_count`: Total signals generated
- `last_signal_time`: Timestamp of last signal
- `feeder_health_ok`: Feeder dependency status
- `default_signals_blocked`: Whether default signals are blocked
- `active_strategies`: List of active trading strategies
- `latency_ms_p50`: 50th percentile latency in milliseconds

### Trader Health Schema

**File:** `shared_data/health/trader.json`

```json
{
  "service": "trader",
  "status": "ok|degraded|error",
  "last_update_ts": 1640995200.0,
  "updated_within_sec": 1.5,
  "orders_count": 8,
  "fills_count": 6,
  "last_order_time": 1640995198.0,
  "account_balance_ok": true,
  "ares_health_ok": true,
  "quarantined_symbols": ["INVALIDUSDT"],
  "active_positions": 3
}
```

**Fields:**
- `service`: Always "trader"
- `status`: Health status (ok, degraded, error)
- `last_update_ts`: Unix timestamp of last update
- `updated_within_sec`: Age of data in seconds
- `orders_count`: Total orders attempted
- `fills_count`: Total orders filled
- `last_order_time`: Timestamp of last order
- `account_balance_ok`: Account balance status
- `ares_health_ok`: ARES dependency status
- `quarantined_symbols`: List of quarantined symbols
- `active_positions`: Number of active positions

### Memory Health Schema

**File:** `shared_data/health/memory.json`

```json
{
  "service": "memory",
  "status": "ok|degraded|error",
  "last_update_ts": 1640995200.0,
  "updated_within_sec": 0.8,
  "integrity_ok": true,
  "events_count": 1250,
  "snapshots_count": 45,
  "last_integrity_check": 1640995195.0,
  "merkle_root": "abc123def456...",
  "chain_length": 1250
}
```

**Fields:**
- `service`: Always "memory"
- `status`: Health status (ok, degraded, error)
- `last_update_ts`: Unix timestamp of last update
- `updated_within_sec`: Age of data in seconds
- `integrity_ok`: Memory integrity status
- `events_count`: Total events in chain
- `snapshots_count`: Total snapshots stored
- `last_integrity_check`: Timestamp of last integrity check
- `merkle_root`: Current Merkle root hash
- `chain_length`: Length of hash chain

## Event Chain Schema

### Event Schema

**File:** `shared_data/memory/event_chain.ndjson`

```json
{
  "event_id": "evt_1640995200_001",
  "timestamp": 1640995200.0,
  "event_type": "order_executed",
  "source": "trader",
  "data": {
    "symbol": "BTCUSDT",
    "side": "BUY",
    "size": 0.001,
    "price": 45000.0,
    "order_id": "123456789",
    "status": "FILLED"
  },
  "metadata": {
    "strategy": "trend_multi_tf",
    "confidence": 0.85,
    "risk_score": 0.2
  }
}
```

**Fields:**
- `event_id`: Unique event identifier
- `timestamp`: Unix timestamp of event
- `event_type`: Type of event (order_executed, signal_generated, etc.)
- `source`: Service that generated the event
- `data`: Event-specific data payload
- `metadata`: Additional event metadata

### Common Event Types

**Signal Generated:**
```json
{
  "event_type": "signal_generated",
  "data": {
    "symbol": "BTCUSDT",
    "side": "BUY",
    "entry_price": 45000.0,
    "stop_loss": 44000.0,
    "take_profit": 46000.0,
    "confidence": 0.85,
    "strategy": "trend_multi_tf"
  }
}
```

**Order Executed:**
```json
{
  "event_type": "order_executed",
  "data": {
    "symbol": "BTCUSDT",
    "side": "BUY",
    "size": 0.001,
    "price": 45000.0,
    "order_id": "123456789",
    "status": "FILLED",
    "commission": 0.0001
  }
}
```

**Health Status Changed:**
```json
{
  "event_type": "health_status_changed",
  "data": {
    "service": "feeder",
    "old_status": "ok",
    "new_status": "degraded",
    "reason": "high_latency"
  }
}
```

## Snapshot Store Schema

### Snapshot Schema

**File:** `shared_data/memory/snapshots/snapshot_1640995200.json`

```json
{
  "snapshot_id": "snapshot_1640995200",
  "timestamp": 1640995200.0,
  "schema_version": "1.0",
  "snapshot_type": "full",
  "data": {
    "account": {
      "total_balance": 1000.0,
      "available_balance": 950.0,
      "positions": {
        "BTCUSDT": {
          "size": 0.001,
          "entry_price": 45000.0,
          "unrealized_pnl": 5.0
        }
      }
    },
    "market_data": {
      "BTCUSDT": {
        "price": 45000.0,
        "volume": 1000000.0,
        "timestamp": 1640995200.0
      }
    },
    "system_state": {
      "active_services": ["feeder", "ares", "trader"],
      "health_status": "ok",
      "memory_usage": 125.5
    }
  }
}
```

**Fields:**
- `snapshot_id`: Unique snapshot identifier
- `timestamp`: Unix timestamp of snapshot
- `schema_version`: Schema version for compatibility
- `snapshot_type`: Type of snapshot (full, incremental)
- `data`: Snapshot data payload

## Hash Chain Schema

### Block Schema

**File:** `shared_data/memory/hash_chain.json`

```json
{
  "chain": [
    {
      "index": 0,
      "timestamp": 1640995200.0,
      "data": "Genesis Block",
      "previous_hash": "0",
      "hash": "abc123def456..."
    },
    {
      "index": 1,
      "timestamp": 1640995201.0,
      "data": {
        "event_id": "evt_1640995200_001",
        "event_type": "order_executed"
      },
      "previous_hash": "abc123def456...",
      "hash": "def456ghi789..."
    }
  ],
  "merkle_root": "xyz789abc123...",
  "chain_length": 2,
  "integrity_verified": true
}
```

**Fields:**
- `chain`: Array of hash chain blocks
- `merkle_root`: Current Merkle root hash
- `chain_length`: Length of chain
- `integrity_verified`: Whether chain integrity is verified

### Block Schema

```json
{
  "index": 1,
  "timestamp": 1640995201.0,
  "data": {
    "event_id": "evt_1640995200_001",
    "event_type": "order_executed"
  },
  "previous_hash": "abc123def456...",
  "hash": "def456ghi789..."
}
```

**Fields:**
- `index`: Block index in chain
- `timestamp`: Unix timestamp of block
- `data`: Block data payload
- `previous_hash`: Hash of previous block
- `hash`: Hash of current block

## Configuration Schema

### SSOT Configuration Schema

**File:** `shared_data/ssot/env.json`

```json
{
  "BINANCE_API_KEY": "your_api_key_here",
  "BINANCE_API_SECRET": "your_api_secret_here",
  "BINANCE_USE_TESTNET": true,
  "TRADING_MODE": "testnet",
  "SIMULATION_MODE": true,
  "PAPER_MODE": false,
  "LIVE_TRADING_ENABLED": false,
  "TEST_ALLOW_DEFAULT_SIGNAL": false,
  "ARES_FRESHNESS_THRESHOLD": 10.0,
  "FEEDER_HEARTBEAT_INTERVAL": 5.0,
  "TRADER_ORDER_COOLDOWN": 1.0,
  "DISABLE_ORDER_GUARDRAILS": false,
  "ENABLE_DEBUG_TRACING": false,
  "LOG_LEVEL": "INFO"
}
```

## Debug Bundle Schema

### Debug Bundle Schema

**File:** `shared_data/debug_bundle_1640995200.json`

```json
{
  "bundle_id": "debug_1640995200",
  "timestamp": 1640995200.0,
  "system_info": {
    "python_version": "3.11.0",
    "platform": "Windows-10",
    "memory_usage": 125.5,
    "cpu_usage": 15.2
  },
  "health_status": {
    "overall_status": "ok",
    "components": {
      "feeder": { "status": "ok", "updated_within_sec": 2.1 },
      "ares": { "status": "ok", "updated_within_sec": 1.5 },
      "trader": { "status": "ok", "updated_within_sec": 0.8 },
      "memory": { "status": "ok", "integrity_ok": true }
    }
  },
  "recent_events": [
    {
      "event_id": "evt_1640995200_001",
      "timestamp": 1640995200.0,
      "event_type": "order_executed",
      "source": "trader"
    }
  ],
  "memory_integrity": {
    "chain_valid": true,
    "merkle_root": "abc123def456...",
    "events_count": 1250,
    "snapshots_count": 45
  },
  "configuration": {
    "trading_mode": "testnet",
    "simulation_mode": true,
    "default_signals": false
  }
}
```

## Versioning

### Schema Versioning

- **Version 1.0**: Initial schema version
- **Version 1.1**: Added metadata fields to events
- **Version 1.2**: Enhanced health status fields

### Migration Notes

When upgrading schemas:
1. Maintain backward compatibility
2. Add new fields as optional
3. Provide migration scripts
4. Update documentation

## Validation

### JSON Schema Validation

All JSON files should be validated against their schemas:

```python
import jsonschema

# Validate health file
with open('shared_data/health/feeder.json') as f:
    data = json.load(f)
    jsonschema.validate(data, feeder_health_schema)
```

### Data Integrity Checks

- Timestamps should be monotonically increasing
- Hash chain should be valid
- Health status should be consistent
- Event IDs should be unique
