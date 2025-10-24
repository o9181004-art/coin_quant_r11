# Coin Quant R11 - All Services Launcher

#Requires -Version 5.1

param(
    [string]$LogLevel = "INFO",
    [switch]$Debug = $false,
    [switch]$Help = $false
)

if ($Help) {
    Write-Host "Coin Quant R11 - All Services Launcher" -ForegroundColor Green
    Write-Host "Usage: .\launch_all.ps1 [-LogLevel <level>] [-Debug] [-Help]" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "This script launches all services in dependency order:" -ForegroundColor Cyan
    Write-Host "  1. Feeder service" -ForegroundColor White
    Write-Host "  2. ARES service (waits for Feeder)" -ForegroundColor White
    Write-Host "  3. Trader service (waits for ARES)" -ForegroundColor White
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
$ScriptName = "launch_all"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPath = Join-Path $ProjectRoot "venv"
$PythonExe = Join-Path $VenvPath "Scripts\python.exe"
$SrcPath = Join-Path $ProjectRoot "src"
$ConfigFile = Join-Path $ProjectRoot "config.env"

# Color functions
function Write-Info { param($Message) Write-Host "[INFO] $Message" -ForegroundColor Green }
function Write-Warning { param($Message) Write-Host "[WARNING] $Message" -ForegroundColor Yellow }
function Write-Error { param($Message) Write-Host "[ERROR] $Message" -ForegroundColor Red }

# Service management
$Services = @()

function Start-Service {
    param(
        [string]$ServiceName,
        [string]$ScriptPath,
        [int]$WaitTime = 30
    )
    
    Write-Info "Starting $ServiceName service..."
    
    # Start service in background
    $process = Start-Process -FilePath "powershell.exe" -ArgumentList "-File", $ScriptPath, "-LogLevel", $LogLevel -PassThru -WindowStyle Hidden
    
    if ($Debug) {
        $process = Start-Process -FilePath "powershell.exe" -ArgumentList "-File", $ScriptPath, "-LogLevel", $LogLevel, "-Debug" -PassThru -WindowStyle Hidden
    }
    
    $Services += @{
        Name = $ServiceName
        Process = $process
        ScriptPath = $ScriptPath
    }
    
    Write-Info "$ServiceName service started with PID: $($process.Id)"
    
    # Wait for service to be ready
    if ($WaitTime -gt 0) {
        Write-Info "Waiting for $ServiceName to be ready... ($WaitTime seconds)"
        Start-Sleep -Seconds $WaitTime
    }
    
    return $process
}

function Stop-AllServices {
    Write-Info "Stopping all services..."
    
    foreach ($service in $Services) {
        if ($service.Process -and -not $service.Process.HasExited) {
            Write-Info "Stopping $($service.Name) service..."
            $service.Process.Kill()
            $service.Process.WaitForExit(5000)
        }
    }
    
    Write-Info "All services stopped"
}

function Test-SystemHealth {
    Write-Info "Checking system health..."
    
    $healthFile = Join-Path $ProjectRoot "shared_data\health\health.json"
    $maxWaitTime = 60
    $waitTime = 0
    
    while ($waitTime -lt $maxWaitTime) {
        if (Test-Path $healthFile) {
            try {
                $healthData = Get-Content $healthFile | ConvertFrom-Json
                $components = $healthData.components
                
                $allHealthy = $true
                foreach ($component in $components.PSObject.Properties) {
                    $name = $component.Name
                    $status = $component.Value.status
                    $freshness = $component.Value.updated_within_sec
                    
                    if ($status -eq "ok" -and $freshness -lt 60) {
                        Write-Info "  ✓ $name: $status (freshness: $freshness seconds)"
                    } else {
                        Write-Warning "  ✗ $name: $status (freshness: $freshness seconds)"
                        $allHealthy = $false
                    }
                }
                
                if ($allHealthy) {
                    Write-Info "All services are healthy!"
                    return $true
                }
            } catch {
                Write-Warning "Failed to read health data"
            }
        }
        
        Write-Info "Waiting for system health... ($waitTime/$maxWaitTime seconds)"
        Start-Sleep -Seconds 5
        $waitTime += 5
    }
    
    Write-Warning "System health check timeout"
    return $false
}

# Cleanup on exit
Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action {
    Stop-AllServices
}

# Main execution
try {
    Write-Host "=" * 80 -ForegroundColor Cyan
    Write-Host "Coin Quant R11 - All Services Launcher" -ForegroundColor Cyan
    Write-Host "=" * 80 -ForegroundColor Cyan
    
    # Validate Python version
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
    
    # Validate configuration
    if (-not (Test-Path $ConfigFile)) {
        Write-Error "Configuration file not found: $ConfigFile"
        Write-Error "Please create config.env with required settings"
        exit 1
    }
    
    Write-Info "Configuration file found: $ConfigFile"
    
    # Start services in dependency order
    Write-Info "Starting services in dependency order..."
    
    # 1. Start Feeder service
    $feederScript = Join-Path $PSScriptRoot "launch_feeder.ps1"
    Start-Service -ServiceName "Feeder" -ScriptPath $feederScript -WaitTime 30
    
    # 2. Start ARES service
    $aresScript = Join-Path $PSScriptRoot "launch_ares.ps1"
    Start-Service -ServiceName "ARES" -ScriptPath $aresScript -WaitTime 30
    
    # 3. Start Trader service
    $traderScript = Join-Path $PSScriptRoot "launch_trader.ps1"
    Start-Service -ServiceName "Trader" -ScriptPath $traderScript -WaitTime 30
    
    # Check system health
    if (Test-SystemHealth) {
        Write-Host "=" * 80 -ForegroundColor Green
        Write-Host "🎉 All services started successfully!" -ForegroundColor Green
        Write-Host "=" * 80 -ForegroundColor Green
        Write-Host "Services running:" -ForegroundColor Cyan
        foreach ($service in $Services) {
            Write-Host "  - $($service.Name): PID $($service.Process.Id)" -ForegroundColor White
        }
        Write-Host ""
        Write-Host "Press Ctrl+C to stop all services" -ForegroundColor Yellow
        Write-Host "=" * 80 -ForegroundColor Green
        
        # Keep script running
        try {
            while ($true) {
                Start-Sleep -Seconds 10
                
                # Check if any service has exited
                foreach ($service in $Services) {
                    if ($service.Process.HasExited) {
                        Write-Warning "$($service.Name) service has exited with code $($service.Process.ExitCode)"
                    }
                }
            }
        } catch {
            Write-Warning "Service monitoring interrupted"
        }
    } else {
        Write-Error "System health check failed"
        Stop-AllServices
        exit 1
    }
    
} catch {
    Write-Error "Launch failed: $($_.Exception.Message)"
    Stop-AllServices
    exit 1
} finally {
    Stop-AllServices
}
