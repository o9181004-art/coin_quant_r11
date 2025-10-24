# Coin Quant R11 - Feeder Service Launcher

#Requires -Version 5.1

param(
    [string]$LogLevel = "INFO",
    [switch]$Debug = $false,
    [switch]$Help = $false
)

if ($Help) {
    Write-Host "Coin Quant R11 - Feeder Service Launcher" -ForegroundColor Green
    Write-Host "Usage: .\launch_feeder.ps1 [-LogLevel <level>] [-Debug] [-Help]" -ForegroundColor Yellow
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
$ScriptName = "launch_feeder"
$ServiceName = "feeder"
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

function Test-Configuration {
    Write-Info "Validating configuration..."
    
    if (-not (Test-Path $ConfigFile)) {
        Write-Error "Configuration file not found: $ConfigFile"
        Write-Error "Please create config.env with required settings"
        exit 1
    }
    
    # Validate required environment variables
    $requiredVars = @("BINANCE_API_KEY", "BINANCE_API_SECRET")
    $missingVars = @()
    
    foreach ($var in $requiredVars) {
        $value = [System.Environment]::GetEnvironmentVariable($var)
        if (-not $value) {
            $missingVars += $var
        }
    }
    
    if ($missingVars.Count -gt 0) {
        Write-Error "Missing required environment variables:"
        foreach ($var in $missingVars) {
            Write-Error "  - $var"
        }
        Write-Error "Please set these variables in config.env"
        exit 1
    }
    
    Write-Info "Configuration validation passed"
}

function Test-Dependencies {
    Write-Info "Checking dependencies..."
    
    $requiredPackages = @("psutil", "numpy", "pandas", "python-dotenv", "requests", "websockets", "binance-connector")
    $missingPackages = @()
    
    foreach ($package in $requiredPackages) {
        $result = & $PythonExe -c "import $package" 2>&1
        if ($LASTEXITCODE -ne 0) {
            $missingPackages += $package
        }
    }
    
    if ($missingPackages.Count -gt 0) {
        Write-Error "Missing required packages:"
        foreach ($package in $missingPackages) {
            Write-Error "  - $package"
        }
        Write-Error "Please install missing packages: pip install $($missingPackages -join ' ')"
        exit 1
    }
    
    Write-Info "Dependencies check passed"
}

function Start-FeederService {
    Write-Info "Starting Feeder service..."
    
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
        "-m", "coin_quant.feeder.service"
    )
    
    Write-Info "Command: $PythonExe $($serviceArgs -join ' ')"
    Write-Info "Working directory: $ProjectRoot"
    Write-Info "Python path: $env:PYTHONPATH"
    Write-Info "Data directory: $env:COIN_QUANT_DATA_DIR"
    Write-Info "Log level: $env:LOG_LEVEL"
    
    # Start process
    $process = Start-Process -FilePath $PythonExe -ArgumentList $serviceArgs -WorkingDirectory $ProjectRoot -PassThru -NoNewWindow
    
    Write-Info "Feeder service started with PID: $($process.Id)"
    Write-Info "Press Ctrl+C to stop the service"
    
    # Wait for process
    try {
        $process.WaitForExit()
    } catch {
        Write-Warning "Service interrupted"
    } finally {
        if (-not $process.HasExited) {
            Write-Info "Stopping Feeder service..."
            $process.Kill()
            $process.WaitForExit(5000)
        }
        Write-Info "Feeder service stopped"
    }
}

# Main execution
try {
    Write-Host "=" * 80 -ForegroundColor Cyan
    Write-Host "Coin Quant R11 - Feeder Service Launcher" -ForegroundColor Cyan
    Write-Host "=" * 80 -ForegroundColor Cyan
    
    Test-PythonVersion
    Test-Configuration
    Test-Dependencies
    Start-FeederService
    
} catch {
    Write-Error "Launch failed: $($_.Exception.Message)"
    exit 1
}
