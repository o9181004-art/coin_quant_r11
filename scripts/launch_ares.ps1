# Coin Quant R11 - ARES Service Launcher

#Requires -Version 5.1

param(
    [string]$LogLevel = "INFO",
    [switch]$Debug = $false,
    [switch]$Help = $false
)

if ($Help) {
    Write-Host "Coin Quant R11 - ARES Service Launcher" -ForegroundColor Green
    Write-Host "Usage: .\launch_ares.ps1 [-LogLevel <level>] [-Debug] [-Help]" -ForegroundColor Yellow
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
$ScriptName = "launch_ares"
$ServiceName = "ares"
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

function Test-FeederDependency {
    Write-Info "Checking Feeder dependency..."
    
    $healthFile = Join-Path $ProjectRoot "shared_data\health\health.json"
    $maxWaitTime = 300  # 5 minutes
    $waitTime = 0
    
    while ($waitTime -lt $maxWaitTime) {
        if (Test-Path $healthFile) {
            try {
                $healthData = Get-Content $healthFile | ConvertFrom-Json
                $feederHealth = $healthData.components.feeder
                
                if ($feederHealth -and $feederHealth.status -eq "ok") {
                    $freshnessSec = $feederHealth.updated_within_sec
                    if ($freshnessSec -lt 30) {
                        Write-Info "Feeder dependency OK (freshness: $freshnessSec seconds)"
                        return
                    } else {
                        Write-Warning "Feeder data stale (freshness: $freshnessSec seconds)"
                    }
                } else {
                    Write-Warning "Feeder health status: $($feederHealth.status)"
                }
            } catch {
                Write-Warning "Failed to read Feeder health data"
            }
        } else {
            Write-Warning "Feeder health file not found"
        }
        
        Write-Info "Waiting for Feeder dependency... ($waitTime/$maxWaitTime seconds)"
        Start-Sleep -Seconds 10
        $waitTime += 10
    }
    
    Write-Error "Feeder dependency check timeout after $maxWaitTime seconds"
    Write-Error "Please ensure Feeder service is running and healthy"
    exit 1
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
    $testAllowDefault = $false
    
    foreach ($line in $configContent) {
        if ($line -match "^TEST_ALLOW_DEFAULT_SIGNAL\s*=\s*true") {
            $testAllowDefault = $true
            break
        }
    }
    
    if ($testAllowDefault) {
        Write-Warning "TEST_ALLOW_DEFAULT_SIGNAL is enabled - this is dangerous in production!"
        Write-Warning "Consider setting TEST_ALLOW_DEFAULT_SIGNAL=false"
    }
    
    Write-Info "Configuration validation passed"
}

function Start-AresService {
    Write-Info "Starting ARES service..."
    
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
        "-m", "coin_quant.ares.service"
    )
    
    Write-Info "Command: $PythonExe $($serviceArgs -join ' ')"
    Write-Info "Working directory: $ProjectRoot"
    Write-Info "Python path: $env:PYTHONPATH"
    Write-Info "Data directory: $env:COIN_QUANT_DATA_DIR"
    Write-Info "Log level: $env:LOG_LEVEL"
    
    # Start process
    $process = Start-Process -FilePath $PythonExe -ArgumentList $serviceArgs -WorkingDirectory $ProjectRoot -PassThru -NoNewWindow
    
    Write-Info "ARES service started with PID: $($process.Id)"
    Write-Info "Press Ctrl+C to stop the service"
    
    # Wait for process
    try {
        $process.WaitForExit()
    } catch {
        Write-Warning "Service interrupted"
    } finally {
        if (-not $process.HasExited) {
            Write-Info "Stopping ARES service..."
            $process.Kill()
            $process.WaitForExit(5000)
        }
        Write-Info "ARES service stopped"
    }
}

# Main execution
try {
    Write-Host "=" * 80 -ForegroundColor Cyan
    Write-Host "Coin Quant R11 - ARES Service Launcher" -ForegroundColor Cyan
    Write-Host "=" * 80 -ForegroundColor Cyan
    
    Test-PythonVersion
    Test-FeederDependency
    Test-Configuration
    Start-AresService
    
} catch {
    Write-Error "Launch failed: $($_.Exception.Message)"
    exit 1
}
