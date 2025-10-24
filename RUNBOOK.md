# Coin Quant R11 - Operational Runbook

This runbook provides step-by-step procedures for operating Coin Quant R11 in production environments.

## Pre-Flight Checklist

Before starting any service, verify the following:

### 1. Environment Setup
- [ ] Python 3.11.x is installed and accessible
- [ ] Virtual environment is created and activated
- [ ] Package is installed in editable mode (`pip install -e .`)
- [ ] All required environment variables are set

### 2. Configuration Validation
- [ ] `BINANCE_API_KEY` is set and valid
- [ ] `BINANCE_API_SECRET` is set and valid
- [ ] `BINANCE_USE_TESTNET=true` for testnet mode
- [ ] `SIMULATION_MODE=true` for safety (unless live trading intended)
- [ ] `TEST_ALLOW_DEFAULT_SIGNAL=false` (unless testing)

### 3. Directory Structure
- [ ] `shared_data/` directory exists
- [ ] `shared_data/health/` directory exists
- [ ] `shared_data/memory/` directory exists
- [ ] `shared_data/logs/` directory exists

### 4. Network Connectivity
- [ ] Internet connection is stable
- [ ] Binance API endpoints are accessible
- [ ] No firewall blocking required ports

## Service Startup Procedures

### Starting Feeder Service

1. **Pre-flight Check**
   ```powershell
   .\scripts\run_feeder.ps1
   ```

2. **Verify Health**
   - Check `shared_data/health/feeder.json` exists
   - Verify status is "ok"
   - Confirm `updated_within_sec` < 10

3. **Monitor Logs**
   - Watch `shared_data/logs/feeder.log`
   - Look for "Feeder service started" message
   - Verify symbol updates are occurring

### Starting ARES Service

1. **Wait for Feeder**
   - Ensure Feeder is healthy and running
   - Wait for feeder health file to be fresh

2. **Start ARES**
   ```powershell
   .\scripts\run_ares.ps1
   ```

3. **Verify Health Gates**
   - Check `shared_data/health/ares.json`
   - Verify feeder dependency is satisfied
   - Confirm signal generation is working

### Starting Trader Service

1. **Wait for Dependencies**
   - Ensure Feeder and ARES are healthy
   - Verify account health is available

2. **Start Trader**
   ```powershell
   .\scripts\run_trader.ps1
   ```

3. **Verify Order Execution**
   - Check `shared_data/health/trader.json`
   - Monitor order execution logs
   - Verify balance updates

## Recovery Procedures

### Feeder Service Recovery

**Symptoms:**
- Feeder health status is "error" or "degraded"
- No symbol updates in logs
- ARES blocking due to stale feeder data

**Recovery Steps:**
1. Stop Feeder service (Ctrl+C)
2. Check logs for specific error messages
3. Verify API credentials and network connectivity
4. Restart Feeder service
5. Wait for health status to return to "ok"

**Common Issues:**
- API rate limiting: Wait and retry
- Network connectivity: Check internet connection
- Invalid symbols: Update symbol list in configuration

### ARES Service Recovery

**Symptoms:**
- ARES health status is "error"
- No signal generation
- Health gate failures

**Recovery Steps:**
1. Check feeder dependency status
2. Verify ARES configuration
3. Restart ARES service
4. Monitor signal generation

**Common Issues:**
- Feeder dependency not met: Fix feeder first
- Configuration errors: Check ARES config
- Memory issues: Restart with fresh memory

### Trader Service Recovery

**Symptoms:**
- Trader health status is "error"
- Order execution failures
- Balance update errors

**Recovery Steps:**
1. Check account health and balance
2. Verify order parameters
3. Check API rate limits
4. Restart Trader service

**Common Issues:**
- Insufficient balance: Check account funds
- Order size too large: Adjust position sizing
- API errors: Check Binance API status

### Memory Layer Recovery

**Symptoms:**
- Memory integrity check failures
- Corrupted event chain
- Snapshot store errors

**Recovery Steps:**
1. Stop all services
2. Run integrity check: `python -c "from coin_quant.memory.client import MemoryClient; client = MemoryClient(); print(client.verify())"`
3. If integrity fails, restore from backup
4. Restart services in order: Feeder → ARES → Trader

## Failure Drills

### Drill 1: Feeder Outage

**Objective:** Verify ARES blocks signals when feeder is unavailable

**Steps:**
1. Start Feeder and ARES services
2. Stop Feeder service (Ctrl+C)
3. Wait 15 seconds
4. Check ARES logs for "Waiting for Feeder" messages
5. Restart Feeder
6. Verify ARES resumes signal generation

**Expected Result:** ARES should block signals and log dependency failures

### Drill 2: Insufficient Balance

**Objective:** Verify Trader handles insufficient balance gracefully

**Steps:**
1. Set account balance to minimum
2. Generate large order signal
3. Monitor Trader logs for balance checks
4. Verify order scaling and retry logic
5. Check symbol quarantine after failures

**Expected Result:** Trader should scale down orders and quarantine symbols after repeated failures

### Drill 3: Memory Corruption

**Objective:** Verify memory layer integrity and recovery

**Steps:**
1. Corrupt memory files manually
2. Start services
3. Check integrity verification
4. Verify quarantine of affected components
5. Test recovery from snapshot

**Expected Result:** System should detect corruption and quarantine affected components

## Monitoring and Alerting

### Health Monitoring

**Key Metrics:**
- Service health status (ok/degraded/error)
- Data freshness (updated_within_sec)
- Signal generation rate
- Order execution success rate
- Memory integrity status

**Monitoring Commands:**
```powershell
# Check overall health
python -c "from coin_quant.shared.health import health_manager; print(health_manager.get_overall_health())"

# Check specific service
python -c "from coin_quant.shared.health import health_manager; print(health_manager.get_feeder_health())"
```

### Log Monitoring

**Critical Log Patterns:**
- `ERROR` messages require immediate attention
- `WARNING` messages indicate potential issues
- Health status changes
- Order execution failures
- Memory integrity violations

**Log Locations:**
- `shared_data/logs/feeder.log`
- `shared_data/logs/ares.log`
- `shared_data/logs/trader.log`

## Troubleshooting Guide

### Common Error Messages

**"Configuration validation failed"**
- Check required environment variables
- Verify API credentials
- Ensure safety flags are properly set

**"No feeder health status available"**
- Start Feeder service first
- Check Feeder logs for errors
- Verify health file permissions

**"Account has insufficient balance"**
- Check account balance
- Reduce order sizes
- Enable simulation mode for testing

**"Memory integrity check failed"**
- Stop all services
- Run integrity verification
- Restore from backup if needed

### Performance Issues

**High CPU Usage:**
- Check for infinite loops in logs
- Reduce service intervals
- Enable debug tracing

**High Memory Usage:**
- Check memory layer size
- Rotate logs more frequently
- Restart services periodically

**Slow Response:**
- Check network connectivity
- Verify API rate limits
- Monitor system resources

## Emergency Procedures

### Complete System Shutdown

1. Stop Trader service (Ctrl+C)
2. Stop ARES service (Ctrl+C)
3. Stop Feeder service (Ctrl+C)
4. Verify all processes are terminated
5. Check for orphaned PID files

### Emergency Configuration Changes

1. Stop all services
2. Update configuration files
3. Restart services in order
4. Verify configuration changes

### Data Recovery

1. Stop all services
2. Backup current state
3. Restore from known good backup
4. Verify data integrity
5. Restart services

## Maintenance Procedures

### Daily Maintenance

- [ ] Check service health status
- [ ] Review error logs
- [ ] Verify data freshness
- [ ] Monitor resource usage

### Weekly Maintenance

- [ ] Rotate log files
- [ ] Clean up old data
- [ ] Update configurations
- [ ] Run integrity checks

### Monthly Maintenance

- [ ] Full system backup
- [ ] Performance review
- [ ] Configuration audit
- [ ] Security updates

## Contact Information

**System Administrator:** [Your Name]
**Emergency Contact:** [Emergency Phone]
**Documentation:** [Documentation URL]
**Support:** [Support Email]
