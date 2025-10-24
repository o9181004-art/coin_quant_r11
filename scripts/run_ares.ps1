# Coin Quant R11 - ARES Service Launcher
# PowerShell script to launch the ARES service with proper environment setup

param(
    [switch]$Debug,
    [switch]$Verbose
)

# Set error action preference
$ErrorActionPreference = "Stop"

# Get script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

# Set working directory
Set-Location $ProjectRoot

Write-Host "Coin Quant R11 - ARES Service Launcher" -ForegroundColor Green
Write-Host "=======================================" -ForegroundColor Green

# Check Python version
Write-Host "Checking Python version..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    if ($pythonVersion -match "Python 3\.11") {
        Write-Host "✅ Python 3.11 detected: $pythonVersion" -ForegroundColor Green
    } else {
        Write-Host "❌ Python 3.11 required, found: $pythonVersion" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "❌ Python not found in PATH" -ForegroundColor Red
    exit 1
}

# Check virtual environment
$VenvPath = Join-Path $ProjectRoot "venv"
if (-not (Test-Path $VenvPath)) {
    Write-Host "❌ Virtual environment not found at: $VenvPath" -ForegroundColor Red
    Write-Host "Please run: python -m venv venv" -ForegroundColor Yellow
    exit 1
}

# Activate virtual environment
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
$ActivateScript = Join-Path $VenvPath "Scripts\Activate.ps1"
if (Test-Path $ActivateScript) {
    & $ActivateScript
    Write-Host "✅ Virtual environment activated" -ForegroundColor Green
} else {
    Write-Host "❌ Virtual environment activation script not found" -ForegroundColor Red
    exit 1
}

# Check package installation
Write-Host "Checking package installation..." -ForegroundColor Yellow
try {
    python -c "import coin_quant; print('Package imported successfully')" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Coin Quant package is installed" -ForegroundColor Green
    } else {
        Write-Host "❌ Coin Quant package not found" -ForegroundColor Red
        Write-Host "Please run: pip install -e ." -ForegroundColor Yellow
        exit 1
    }
} catch {
    Write-Host "❌ Package check failed" -ForegroundColor Red
    exit 1
}

# Create logs directory
$LogsDir = Join-Path $ProjectRoot "shared_data\logs"
if (-not (Test-Path $LogsDir)) {
    New-Item -ItemType Directory -Path $LogsDir -Force | Out-Null
    Write-Host "✅ Created logs directory: $LogsDir" -ForegroundColor Green
}

# Set log file path
$LogFile = Join-Path $LogsDir "ares.log"
$Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

Write-Host "Starting ARES service..." -ForegroundColor Yellow
Write-Host "Log file: $LogFile" -ForegroundColor Cyan
Write-Host "Timestamp: $Timestamp" -ForegroundColor Cyan

# Build command arguments
$Args = @("-m", "coin_quant.ares.service")

if ($Debug) {
    $Args += "--debug"
}

if ($Verbose) {
    $Args += "--verbose"
}

# Start the service
try {
    Write-Host "Command: python $($Args -join ' ')" -ForegroundColor Cyan
    
    # Redirect output to log file and console
    python $Args 2>&1 | Tee-Object -FilePath $LogFile
    
    $ExitCode = $LASTEXITCODE
    
    if ($ExitCode -eq 0) {
        Write-Host "✅ ARES service completed successfully" -ForegroundColor Green
    } else {
        Write-Host "❌ ARES service exited with code: $ExitCode" -ForegroundColor Red
    }
    
    exit $ExitCode
    
} catch {
    Write-Host "❌ Failed to start ARES service: $_" -ForegroundColor Red
    exit 1
}
