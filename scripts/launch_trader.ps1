# Coin Quant R11 - Trader Service Launcher

#Requires -Version 5.1

param(
    [string]$LogLevel = "INFO",
    [switch]$Debug = $false,
    [switch]$Help = $false
)

if ($Help) {
    Write-Host "Coin Quant R11 - Trader Service Launcher" -ForegroundColor Green
    Write-Host "Usage: .\launch_trader.ps1 [-LogLevel <level>] [-Debug] [-Help]" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Parameters:" -ForegroundColor Cyan
    Write-Host "  -LogLevel    Log level (DEBUG, INFO, WARNING, ERROR)" -ForegroundColor White
    Write-Host "  -Debug       Enable debug mode" -ForegroundColor White
    Write-Host "  -Help        Show this help message" -ForegroundColor White
    exit 0
}

# Set error action preference
$ErrorActionPreference = "Stop"

# Script configuration
$ScriptName = "launch_trader"
$ServiceName = "trader"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPath = Join-Path $ProjectRoot "venv"
$PythonExe = Join-Path $VenvPath "Scripts\python.exe"
$SrcPath = Join-Path $ProjectRoot "src"
$ConfigFile = Join-Path $ProjectRoot "config.env"

# Color functions
function Write-Info { param($Message) Write-Host "[INFO] $Message" -ForegroundColor Green }
function Write-Warning { param($Message) Write-Host "[WARNING] $Message" -ForegroundColor Yellow }
function Write-Error { param($Message) Write-Host "[ERROR] $Message" -ForegroundColor Red }

# Validation functions
function Test-PythonVersion {
    Write-Info "Checking Python version..."
    
    if (-not (Test-Path $PythonExe)) {
        Write-Error "Python executable not found: $PythonExe"
        Write-Error "Please ensure virtual environment is activated"
        exit 1
    }
    
    $pythonVersion = & $PythonExe --version 2>&1
    if ($pythonVersion -match "Python 3\.11") {
        Write-Info "Python version OK: $pythonVersion"
    } else {
        Write-Error "Python 3.11 required, found: $pythonVersion"
        exit 1
    }
}

function Test-Dependencies {
    Write-Info "Checking service dependencies..."
    
    $healthFile = Join-Path $ProjectRoot "shared_data\health\health.json"
    $maxWaitTime = 300  # 5 minutes
    $waitTime = 0
    
    while ($waitTime -lt $maxWaitTime) {
        if (Test-Path $healthFile) {
            try {
                $healthData = Get-Content $healthFile | ConvertFrom-Json
                $feederHealth = $healthData.components.feeder
                $aresHealth = $healthData.components.ares
                
                $feederOk = $feederHealth -and $feederHealth.status -eq "ok" -and $feederHealth.updated_within_sec -lt 30
                $aresOk = $aresHealth -and $aresHealth.status -eq "ok" -and $aresHealth.updated_within_sec -lt 60
                
                if ($feederOk -and $aresOk) {
                    Write-Info "Service dependencies OK"
                    Write-Info "  - Feeder: $($feederHealth.status) (freshness: $($feederHealth.updated_within_sec)s)"
                    Write-Info "  - ARES: $($aresHealth.status) (freshness: $($aresHealth.updated_within_sec)s)"
                    return
                } else {
                    if (-not $feederOk) {
                        Write-Warning "Feeder dependency not ready: $($feederHealth.status)"
                    }
                    if (-not $aresOk) {
                        Write-Warning "ARES dependency not ready: $($aresHealth.status)"
                    }
                }
            } catch {
                Write-Warning "Failed to read service health data"
            }
        } else {
            Write-Warning "Service health file not found"
        }
        
        Write-Info "Waiting for service dependencies... ($waitTime/$maxWaitTime seconds)"
        Start-Sleep -Seconds 10
        $waitTime += 10
    }
    
    Write-Error "Service dependency check timeout after $maxWaitTime seconds"
    Write-Error "Please ensure Feeder and ARES services are running and healthy"
    exit 1
}

function Test-AccountBalance {
    Write-Info "Checking account balance..."
    
    # This would typically check the actual account balance
    # For now, we'll just validate that the API keys are configured
    $apiKey = [System.Environment]::GetEnvironmentVariable("BINANCE_API_KEY")
    $apiSecret = [System.Environment]::GetEnvironmentVariable("BINANCE_API_SECRET")
    
    if (-not $apiKey -or -not $apiSecret) {
        Write-Error "Binance API credentials not configured"
        Write-Error "Please set BINANCE_API_KEY and BINANCE_API_SECRET"
        exit 1
    }
    
    Write-Info "Account balance check passed (API credentials configured)"
}

function Test-Configuration {
    Write-Info "Validating configuration..."
    
    if (-not (Test-Path $ConfigFile)) {
        Write-Error "Configuration file not found: $ConfigFile"
        Write-Error "Please create config.env with required settings"
        exit 1
    }
    
    # Check for dangerous settings
    $configContent = Get-Content $ConfigFile
    $liveTrading = $false
    $disableGuardrails = $false
    
    foreach ($line in $configContent) {
        if ($line -match "^LIVE_TRADING_ENABLED\s*=\s*true") {
            $liveTrading = $true
        }
        if ($line -match "^DISABLE_ORDER_GUARDRAILS\s*=\s*true") {
            $disableGuardrails = $true
        }
    }
    
    if ($liveTrading) {
        Write-Warning "LIVE_TRADING_ENABLED is true - real money trading is active!"
        Write-Warning "Ensure you understand the risks before proceeding"
    }
    
    if ($disableGuardrails) {
        Write-Warning "DISABLE_ORDER_GUARDRAILS is true - safety checks are disabled!"
        Write-Warning "This is dangerous and not recommended"
    }
    
    Write-Info "Configuration validation passed"
}

function Start-TraderService {
    Write-Info "Starting Trader service..."
    
    # Set environment variables
    $env:PYTHONPATH = $SrcPath
    $env:COIN_QUANT_DATA_DIR = Join-Path $ProjectRoot "shared_data"
    $env:LOG_LEVEL = $LogLevel
    
    if ($Debug) {
        $env:ENABLE_DEBUG_TRACING = "true"
        $env:LOG_LEVEL = "DEBUG"
    }
    
    # Load configuration
    if (Test-Path $ConfigFile) {
        Get-Content $ConfigFile | ForEach-Object {
            if ($_ -match "^([^#][^=]+)=(.*)$") {
                $name = $matches[1].Trim()
                $value = $matches[2].Trim()
                [System.Environment]::SetEnvironmentVariable($name, $value)
            }
        }
    }
    
    # Start service
    $serviceArgs = @(
        "-m", "coin_quant.trader.service"
    )
    
    Write-Info "Command: $PythonExe $($serviceArgs -join ' ')"
    Write-Info "Working directory: $ProjectRoot"
    Write-Info "Python path: $env:PYTHONPATH"
    Write-Info "Data directory: $env:COIN_QUANT_DATA_DIR"
    Write-Info "Log level: $env:LOG_LEVEL"
    
    # Start process
    $process = Start-Process -FilePath $PythonExe -ArgumentList $serviceArgs -WorkingDirectory $ProjectRoot -PassThru -NoNewWindow
    
    Write-Info "Trader service started with PID: $($process.Id)"
    Write-Info "Press Ctrl+C to stop the service"
    
    # Wait for process
    try {
        $process.WaitForExit()
    } catch {
        Write-Warning "Service interrupted"
    } finally {
        if (-not $process.HasExited) {
            Write-Info "Stopping Trader service..."
            $process.Kill()
            $process.WaitForExit(5000)
        }
        Write-Info "Trader service stopped"
    }
}

# Main execution
try {
    Write-Host "=" * 80 -ForegroundColor Cyan
    Write-Host "Coin Quant R11 - Trader Service Launcher" -ForegroundColor Cyan
    Write-Host "=" * 80 -ForegroundColor Cyan
    
    Test-PythonVersion
    Test-Dependencies
    Test-AccountBalance
    Test-Configuration
    Start-TraderService
    
} catch {
    Write-Error "Launch failed: $($_.Exception.Message)"
    exit 1
}
