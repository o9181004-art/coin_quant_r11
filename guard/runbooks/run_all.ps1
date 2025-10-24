# One-click runner for E2E Stabilization & Auto-Trading Verification
# Sets PYTHONPATH, kills stale processes, launches services, runs healthcheck and E2E orchestrator

param(
    [string]$Symbols = "BTCUSDT,ETHUSDT,SOLUSDT",
    [int]$MaxAttempts = 5,
    [switch]$PlaceOrder = $false,
    [switch]$SkipHealthCheck = $false
)

# Set error action preference
$ErrorActionPreference = "Stop"

# Get script directory and project root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$ProjectRoot = Split-Path -Parent $ProjectRoot

Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host "E2E Stabilization & Auto-Trading Verification" -ForegroundColor Cyan
Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host "Project Root: $ProjectRoot" -ForegroundColor Green
Write-Host "Symbols: $Symbols" -ForegroundColor Green
Write-Host "Max Attempts: $MaxAttempts" -ForegroundColor Green
Write-Host "Place Order: $PlaceOrder" -ForegroundColor Green
Write-Host "=" * 70 -ForegroundColor Cyan

# Set PYTHONPATH
$env:PYTHONPATH = $ProjectRoot
Write-Host "✅ PYTHONPATH set to: $env:PYTHONPATH" -ForegroundColor Green

# Kill stale Python processes
Write-Host "`n🔍 Killing stale Python processes..." -ForegroundColor Yellow
try {
    Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -like "*feeder*" -or 
        $_.CommandLine -like "*trader*" -or 
        $_.CommandLine -like "*ares*" -or
        $_.CommandLine -like "*state_bus*" -or
        $_.CommandLine -like "*filters_manager*"
    } | ForEach-Object {
        Write-Host "Killing process: $($_.Id) - $($_.ProcessName)" -ForegroundColor Red
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2
    Write-Host "✅ Stale processes cleaned up" -ForegroundColor Green
}
catch {
    Write-Host "⚠️ Error killing processes: $($_.Exception.Message)" -ForegroundColor Yellow
}

# Change to project directory
Set-Location $ProjectRoot
Write-Host "✅ Changed to project directory: $ProjectRoot" -ForegroundColor Green

# Launch core services
Write-Host "`n🚀 Launching core services..." -ForegroundColor Yellow

# Start State Bus Writer
Write-Host "Starting State Bus Writer..." -ForegroundColor Cyan
try {
    Start-Process -FilePath "python" -ArgumentList "-m", "guard.feeder.state_bus_writer" -WindowStyle Hidden -PassThru | Out-Null
    Start-Sleep -Seconds 2
    Write-Host "✅ State Bus Writer started" -ForegroundColor Green
}
catch {
    Write-Host "❌ Failed to start State Bus Writer: $($_.Exception.Message)" -ForegroundColor Red
}

# Start Filters Manager
Write-Host "Starting Filters Manager..." -ForegroundColor Cyan
try {
    Start-Process -FilePath "python" -ArgumentList "-m", "guard.trader.filters_manager" -WindowStyle Hidden -PassThru | Out-Null
    Start-Sleep -Seconds 2
    Write-Host "✅ Filters Manager started" -ForegroundColor Green
}
catch {
    Write-Host "❌ Failed to start Filters Manager: $($_.Exception.Message)" -ForegroundColor Red
}

# Start ARES Service
Write-Host "Starting ARES Service..." -ForegroundColor Cyan
try {
    Start-Process -FilePath "python" -ArgumentList "-m", "guard.optimizer.ares_service" -WindowStyle Hidden -PassThru | Out-Null
    Start-Sleep -Seconds 2
    Write-Host "✅ ARES Service started" -ForegroundColor Green
}
catch {
    Write-Host "❌ Failed to start ARES Service: $($_.Exception.Message)" -ForegroundColor Red
}

# Start Feeder
Write-Host "Starting Feeder..." -ForegroundColor Cyan
try {
    Start-Process -FilePath "python" -ArgumentList "-m", "services.feeder_service" -WindowStyle Hidden -PassThru | Out-Null
    Start-Sleep -Seconds 3
    Write-Host "✅ Feeder started" -ForegroundColor Green
}
catch {
    Write-Host "❌ Failed to start Feeder: $($_.Exception.Message)" -ForegroundColor Red
}

# Start Trader
Write-Host "Starting Trader..." -ForegroundColor Cyan
try {
    Start-Process -FilePath "python" -ArgumentList "-m", "services.trader_service" -WindowStyle Hidden -PassThru | Out-Null
    Start-Sleep -Seconds 3
    Write-Host "✅ Trader started" -ForegroundColor Green
}
catch {
    Write-Host "❌ Failed to start Trader: $($_.Exception.Message)" -ForegroundColor Red
}

# Wait for services to initialize
Write-Host "`n⏳ Waiting for services to initialize..." -ForegroundColor Yellow
Start-Sleep -Seconds 10

# Run Health Check
if (-not $SkipHealthCheck) {
    Write-Host "`n🏥 Running Health Check v2..." -ForegroundColor Yellow
    try {
        $HealthResult = & python -m guard.health.healthcheck_v2
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ Health Check passed" -ForegroundColor Green
        }
        else {
            Write-Host "❌ Health Check failed (exit code: $LASTEXITCODE)" -ForegroundColor Red
        }
    }
    catch {
        Write-Host "❌ Health Check error: $($_.Exception.Message)" -ForegroundColor Red
    }
}
else {
    Write-Host "`n⏭️ Skipping Health Check" -ForegroundColor Yellow
}

# Run E2E Orchestrator
Write-Host "`n🎯 Running E2E Orchestrator..." -ForegroundColor Yellow
try {
    $E2EArgs = @(
        "-m", "guard.e2e.e2e_orchestrator",
        "--symbols", $Symbols,
        "--max-attempts", $MaxAttempts
    )
    
    if ($PlaceOrder) {
        $E2EArgs += "--place-order"
    }
    
    $E2EResult = & python @E2EArgs
    $E2EExitCode = $LASTEXITCODE
    
    if ($E2EExitCode -eq 0) {
        Write-Host "✅ E2E Orchestrator completed successfully" -ForegroundColor Green
    }
    else {
        Write-Host "❌ E2E Orchestrator failed (exit code: $E2EExitCode)" -ForegroundColor Red
    }
}
catch {
    Write-Host "❌ E2E Orchestrator error: $($_.Exception.Message)" -ForegroundColor Red
    $E2EExitCode = 1
}

# Display results
Write-Host "`n📊 Results Summary" -ForegroundColor Cyan
Write-Host "=" * 50 -ForegroundColor Cyan

# Show Health Check results
if (-not $SkipHealthCheck) {
    $HealthFile = Join-Path $ProjectRoot "logs\health\health_v2.json"
    if (Test-Path $HealthFile) {
        try {
            $HealthData = Get-Content $HealthFile | ConvertFrom-Json
            $DorStatus = if ($HealthData.dor) { "✅ TRUE" } else { "❌ FALSE" }
            Write-Host "DOR Status: $DorStatus" -ForegroundColor $(if ($HealthData.dor) { "Green" } else { "Red" })
            Write-Host "Failing Components: $($HealthData.failing_components -join ', ')" -ForegroundColor Yellow
        }
        catch {
            Write-Host "❌ Could not read health results" -ForegroundColor Red
        }
    }
    else {
        Write-Host "❌ Health results file not found" -ForegroundColor Red
    }
}

# Show E2E results
$E2ESummaryFile = Join-Path $ProjectRoot "logs\e2e\summary.json"
$E2ERCAFile = Join-Path $ProjectRoot "logs\e2e\rca.json"

if (Test-Path $E2ESummaryFile) {
    try {
        $E2EData = Get-Content $E2ESummaryFile | ConvertFrom-Json
        $PassStatus = if ($E2EData.pass) { "✅ PASS" } else { "❌ FAIL" }
        Write-Host "E2E Status: $PassStatus" -ForegroundColor $(if ($E2EData.pass) { "Green" } else { "Red" })
        Write-Host "Duration: $($E2EData.duration_seconds) seconds" -ForegroundColor Cyan
        Write-Host "Attempts: $($E2EData.attempts)" -ForegroundColor Cyan
    }
    catch {
        Write-Host "❌ Could not read E2E summary" -ForegroundColor Red
    }
}
elseif (Test-Path $E2ERCAFile) {
    try {
        $RCAData = Get-Content $E2ERCAFile | ConvertFrom-Json
        Write-Host "E2E Status: ❌ FAIL" -ForegroundColor Red
        Write-Host "Reason: $($RCAData.reason)" -ForegroundColor Red
        Write-Host "Attempts: $($RCAData.attempts)" -ForegroundColor Cyan
    }
    catch {
        Write-Host "❌ Could not read E2E RCA" -ForegroundColor Red
    }
}
else {
    Write-Host "❌ E2E results not found" -ForegroundColor Red
}

Write-Host "=" * 50 -ForegroundColor Cyan

# Tail important logs
Write-Host "`n📋 Recent Log Activity" -ForegroundColor Cyan
Write-Host "=" * 50 -ForegroundColor Cyan

# Show recent health logs
$HealthLogFile = Join-Path $ProjectRoot "logs\health\health_v2.json"
if (Test-Path $HealthLogFile) {
    Write-Host "`n🏥 Health Check Results:" -ForegroundColor Yellow
    try {
        Get-Content $HealthLogFile | ConvertFrom-Json | ConvertTo-Json -Depth 3 | Write-Host -ForegroundColor White
    }
    catch {
        Write-Host "Could not display health results" -ForegroundColor Red
    }
}

# Show E2E summary
if (Test-Path $E2ESummaryFile) {
    Write-Host "`n🎯 E2E Summary:" -ForegroundColor Yellow
    try {
        Get-Content $E2ESummaryFile | ConvertFrom-Json | ConvertTo-Json -Depth 3 | Write-Host -ForegroundColor White
    }
    catch {
        Write-Host "Could not display E2E summary" -ForegroundColor Red
    }
}

Write-Host "`n" + "=" * 70 -ForegroundColor Cyan
Write-Host "E2E Stabilization & Auto-Trading Verification Complete" -ForegroundColor Cyan
Write-Host "=" * 70 -ForegroundColor Cyan

# Exit with E2E result code
if ($E2EExitCode -eq 0) {
    Write-Host "🎉 All systems operational!" -ForegroundColor Green
    exit 0
}
else {
    Write-Host "⚠️ Issues detected - check logs for details" -ForegroundColor Yellow
    exit $E2EExitCode
}
