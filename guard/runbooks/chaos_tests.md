# Chaos Tests - Fail-Safe Trading Runtime

## Overview

This runbook describes chaos test scenarios to verify the Auto-Heal v2 system's ability to recover from failures and maintain safe trading operations.

## Prerequisites

- System running in testnet mode (`BINANCE_USE_TESTNET=true`)
- Auto-Heal v2 enabled and running
- Health Check v2 configured
- All services (Feeder, Trader, ARES) initially healthy

## Test Scenarios

### Scenario 1: Kill Feeder

**Objective**: Verify Auto-Heal detects and restarts Feeder service.

**Steps**:
1. Verify system is healthy (DOR=true)
   ```powershell
   .\.venv\Scripts\python.exe guard\health\healthcheck_v2.py
   ```

2. Kill Feeder process
   ```powershell
   # Find Feeder PID
   Get-Content shared_data\feeder.pid

   # Kill process
   Stop-Process -Id <PID> -Force
   ```

3. Monitor Auto-Heal logs
   ```powershell
   Get-Content logs\autoheal.log -Wait -Tail 20
   ```

**Expected Behavior**:
- **T+0s**: Feeder process killed
- **T+15s**: Auto-Heal detects failure (health_v2.json shows `failing_components=['Feeder']`)
- **T+30s**: Auto-Heal attempts restart (Stage 1: RESTART)
- **T+45s**: Feeder restarted, WS stream reconnects
- **T+90s**: DOR=true verified, Auto-Heal returns to OBSERVE stage

**Success Criteria**:
- Feeder automatically restarted within 90s
- WS stream freshness restored (age < 60s)
- DOR=true after recovery
- No manual intervention required

**Failure Handling**:
- If restart fails 3 times → Failsafe mode activated
- STOP.TXT created
- Trading halted (SIGNAL_READ_ONLY mode)

---

### Scenario 2: Cut Internet Connection

**Objective**: Verify system handles network failures gracefully.

**Steps**:
1. Verify system is healthy (DOR=true)

2. Disable network adapter
   ```powershell
   # Disable Wi-Fi (adjust adapter name as needed)
   Disable-NetAdapter -Name "Wi-Fi" -Confirm:$false
   ```

3. Monitor health status
   ```powershell
   .\.venv\Scripts\python.exe guard\health\healthcheck_v2.py
   ```

4. Re-enable network after 60s
   ```powershell
   Enable-NetAdapter -Name "Wi-Fi" -Confirm:$false
   ```

**Expected Behavior**:
- **T+0s**: Network disabled
- **T+15s**: Health check shows CONN_TIMEOUT errors
- **T+15s**: DOR=false, failing_components=['REST_API', 'Feeder']
- **T+30s**: Auto-Heal detects failures but cannot restart (network issue)
- **T+60s**: Network restored
- **T+75s**: Services reconnect automatically
- **T+90s**: DOR=true restored

**Success Criteria**:
- System detects network failure (CONN_TIMEOUT)
- No crashes or silent failures
- Automatic recovery when network restored
- All services healthy within 60s of network restoration

---

### Scenario 3: Corrupt state_bus.json

**Objective**: Verify atomic write protection prevents corruption.

**Steps**:
1. Verify system is healthy

2. Corrupt state_bus.json
   ```powershell
   # Backup first
   Copy-Item shared_data\state_bus.json shared_data\state_bus.json.backup

   # Corrupt file (write invalid JSON)
   Set-Content shared_data\state_bus.json -Value "{ invalid json"
   ```

3. Monitor system behavior
   ```powershell
   Get-Content logs\state_bus.log -Wait -Tail 20
   ```

4. Trigger state write
   ```powershell
   # Any operation that writes state
   .\.venv\Scripts\python.exe -c "from shared.state_bus import get_state_bus; get_state_bus().save_state()"
   ```

**Expected Behavior**:
- **T+0s**: state_bus.json corrupted
- **T+5s**: Next read attempt fails, loads from backup or creates default
- **T+10s**: Schema validation rejects invalid write attempts
- **T+15s**: Alert created in `shared_data/alerts/state_bus_invalid.json`
- **T+20s**: System continues with valid state (no crash)

**Success Criteria**:
- Invalid JSON rejected by schema validation
- Alert emitted for invalid write attempt
- System continues operating with valid state
- No partial writes or corruption

---

### Scenario 4: REST API Timeouts

**Objective**: Verify system handles slow/timeout REST responses.

**Steps**:
1. Verify system is healthy

2. Simulate slow REST API (using proxy or firewall rules)
   ```powershell
   # Add firewall rule to delay packets (requires admin)
   # Or use Fiddler/Charles Proxy to add delays
   ```

3. Monitor REST latency probe
   ```powershell
   .\.venv\Scripts\python.exe guard\health\healthcheck_v2.py
   ```

**Expected Behavior**:
- **T+0s**: REST API slowed/delayed
- **T+15s**: Health check shows high latency (> 1500ms)
- **T+30s**: DOR=false, failing_components=['REST_API']
- **T+45s**: System continues with cached data (degraded mode)
- **T+60s**: REST API restored
- **T+75s**: DOR=true restored

**Success Criteria**:
- High latency detected (p95 > 1.5s)
- System enters degraded mode (uses cached data)
- No crashes or order failures
- Automatic recovery when latency improves

---

### Scenario 5: Rapid Duplicate Signals

**Objective**: Verify order idempotency prevents duplicate orders.

**Steps**:
1. Verify system is healthy

2. Generate rapid duplicate signals
   ```powershell
   # Inject duplicate signals
   .\.venv\Scripts\python.exe -c "
   from orders.idempotency import check_and_record
   for i in range(10):
       is_dup, sig = check_and_record('BTCUSDT', 'BUY', 0.001, 50000.0)
       print(f'Signal {i+1}: duplicate={is_dup}')
   "
   ```

3. Check order logs
   ```powershell
   Get-Content shared_data\runtime\order_sigs.json
   ```

**Expected Behavior**:
- **Signal 1**: Not duplicate, order signature recorded
- **Signals 2-10**: Detected as duplicates, blocked
- Only 1 order placed for identical parameters

**Success Criteria**:
- First signal processed normally
- Subsequent duplicates blocked (within 2min TTL)
- Only one live order per unique signature
- No duplicate orders at exchange

---

### Scenario 6: SELL Without Position

**Objective**: Verify inventory gate blocks SELL orders without holdings.

**Steps**:
1. Verify system is healthy

2. Clear positions
   ```powershell
   Set-Content shared_data\positions_snapshot.json -Value "{}"
   ```

3. Attempt SELL order
   ```powershell
   .\.venv\Scripts\python.exe -c "
   from orders.inventory_gate import validate_order
   allowed, reason = validate_order('BTCUSDT', 'SELL', 0.001)
   print(f'SELL allowed: {allowed}, reason: {reason}')
   "
   ```

**Expected Behavior**:
- SELL order blocked
- Reason: `SKIP_NO_POSITION`
- No API call to exchange
- Log entry created

**Success Criteria**:
- SELL order rejected before API call
- Clear error message logged
- No failed orders at exchange
- Position check performed correctly

---

### Scenario 7: Circuit Breaker Trip

**Objective**: Verify circuit breaker trips after repeated failures.

**Steps**:
1. Verify system is healthy

2. Simulate repeated order failures
   ```powershell
   .\.venv\Scripts\python.exe -c "
   from orders.circuit_breaker import record_failure, is_tripped
   for i in range(5):
       tripped = record_failure('BTCUSDT', f'Error {i+1}')
       print(f'Failure {i+1}: tripped={tripped}')
   print(f'Circuit tripped: {is_tripped(\"BTCUSDT\")}')
   "
   ```

3. Check circuit breaker state
   ```powershell
   Get-Content shared_data\circuit_breaker.json
   ```

**Expected Behavior**:
- **Failures 1-2**: Circuit remains CLOSED
- **Failure 3**: Circuit trips to OPEN
- **T+0 to T+120s**: Circuit remains OPEN (no orders)
- **T+120s**: Circuit moves to HALF_OPEN (test order allowed)
- **Success**: Circuit resets to CLOSED

**Success Criteria**:
- Circuit trips after 3 failures in 60s
- No orders placed while circuit OPEN
- Automatic reset after 120s steady state
- Monitor-only mode while tripped

---

## Auto-Heal Stage Transitions

### Stage 0: OBSERVE
- **Condition**: DOR=true, all systems healthy
- **Action**: Monitor only, refresh heartbeat
- **Duration**: Continuous

### Stage 1: RESTART
- **Condition**: Component failing for 2+ consecutive checks
- **Action**: Restart service, clean stale locks
- **Duration**: Immediate

### Stage 2: REWIRE & BACKOFF
- **Condition**: After restart
- **Action**: Verify DOR within 90s, exponential backoff
- **Backoff**: 15s → 30s → 60s → 120s → 300s (max)
- **Duration**: 90s verification window

### Stage 3: FAILSAFE
- **Condition**: 3 restart attempts failed
- **Action**: Set global_flags.json, write STOP.TXT, enter SIGNAL_READ_ONLY
- **Duration**: Until manual intervention

### Stage 4: NOTIFY
- **Condition**: Failsafe entered
- **Action**: Append to notifications.log, alert operators
- **Duration**: Immediate

---

## Verification Commands

### Check DOR Status
```powershell
.\.venv\Scripts\python.exe guard\health\healthcheck_v2.py
type .\logs\health\health_v2.json
```

### Check Auto-Heal Status
```powershell
Get-Content shared_data\autoheal_state.json
```

### Check Component Heartbeats
```powershell
Get-Content shared_data\feeder.heartbeat.json
Get-Content shared_data\trader.heartbeat.json
Get-Content shared_data\auto_heal.heartbeat.json
```

### Check Failsafe Status
```powershell
Get-Content shared_data\global_flags.json
Test-Path STOP.TXT
```

### View Metrics
```powershell
.\.venv\Scripts\python.exe -c "from guard.health.metrics import print_summary; print_summary()"
```

---

## Recovery Procedures

### Manual Service Restart
```powershell
# Restart Feeder
.\.venv\Scripts\python.exe guard\services\restart.py restart feeder

# Restart Trader
.\.venv\Scripts\python.exe guard\services\restart.py restart trader
```

### Clear Failsafe Mode
```powershell
# Remove STOP.TXT
Remove-Item STOP.TXT

# Reset global flags
Set-Content shared_data\global_flags.json -Value '{"failsafe_active": false}'

# Reset circuit breakers
.\.venv\Scripts\python.exe -c "from orders.circuit_breaker import reset_all; reset_all()"
```

### Force Health Check
```powershell
.\.venv\Scripts\python.exe guard\health\healthcheck_v2.py
```

---

## Success Metrics

### System is "Shippable" When:

1. ✅ **Auto-Recovery**: Killing Feeder or Trader results in automatic restart and DOR=true within 90s, or Failsafe if 3 attempts fail

2. ✅ **Inventory Safety**: No SELLs are attempted without inventory (SKIP_NO_POSITION logged)

3. ✅ **Idempotency**: Zero duplicate orders under rapid signals (order_sig deduplication working)

4. ✅ **UI Stability**: UI status matches health_v2.json and doesn't push the dashboard down (non-intrusive alerts)

5. ✅ **Failsafe Protection**: System enters failsafe mode after max retries, writes STOP.TXT, and halts new orders

6. ✅ **Circuit Breaker**: Circuit trips after 3 failures in 60s, resets after 120s steady state

7. ✅ **State Integrity**: state_bus.json remains valid even during mid-write crashes (atomic swap)

---

## Troubleshooting

### Auto-Heal Not Restarting Services
- Check Auto-Heal is running: `Get-Content shared_data\auto_heal.heartbeat.json`
- Check health_v2.json exists: `Test-Path shared_data\health_v2.json`
- Check restart permissions: Ensure process can kill/start services

### DOR Always False
- Run health check manually: `.\.venv\Scripts\python.exe guard\health\healthcheck_v2.py`
- Check individual probe failures in `logs\health\health_v2.json`
- Verify all services are running: `Get-Process python`

### Failsafe Mode Stuck
- Check STOP.TXT exists: `Test-Path STOP.TXT`
- Check global_flags.json: `Get-Content shared_data\global_flags.json`
- Follow recovery procedures above

---

## Notes

- All tests should be run in **testnet mode** (`BINANCE_USE_TESTNET=true`)
- Monitor logs in real-time during tests: `Get-Content logs\*.log -Wait -Tail 20`
- Keep backup of critical files before chaos tests
- Document any unexpected behaviors for improvement

---

**Last Updated**: 2025-01-XX
**Version**: 1.0.0
**Owner**: Auto-Heal v2 Team
