# Coin Quant R11 - PowerShell Launcher
# Launches services in the correct order

Write-Host "=== Coin Quant R11 Launcher ===" -ForegroundColor Green
Write-Host ""

# Check if virtual environment exists
if (-not (Test-Path "venv\Scripts\Activate.ps1")) {
    Write-Host "Error: Virtual environment not found" -ForegroundColor Red
    Write-Host "Please run setup.py first" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# Activate virtual environment
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
. .\venv\Scripts\Activate.ps1

# Check Python version
python --version
Write-Host ""

# Show menu
do {
    Write-Host "Select service to launch:" -ForegroundColor Cyan
    Write-Host "1. Feeder Service"
    Write-Host "2. ARES Service"
    Write-Host "3. Trader Service"
    Write-Host "4. Run All Services (in order)"
    Write-Host "5. Run Validation Tests"
    Write-Host "6. Exit"
    Write-Host ""
    $choice = Read-Host "Enter your choice (1-6)"

    switch ($choice) {
        "1" {
            Write-Host ""
            Write-Host "Starting Feeder Service..." -ForegroundColor Green
            python launch.py feeder
            Read-Host "Press Enter to continue"
        }
        "2" {
            Write-Host ""
            Write-Host "Starting ARES Service..." -ForegroundColor Green
            python launch.py ares
            Read-Host "Press Enter to continue"
        }
        "3" {
            Write-Host ""
            Write-Host "Starting Trader Service..." -ForegroundColor Green
            python launch.py trader
            Read-Host "Press Enter to continue"
        }
        "4" {
            Write-Host ""
            Write-Host "Starting all services in order..." -ForegroundColor Green
            Write-Host ""
            Write-Host "1. Starting Feeder Service..." -ForegroundColor Yellow
            Start-Process -FilePath "python" -ArgumentList "launch.py", "feeder" -WindowStyle Normal
            Start-Sleep -Seconds 5

            Write-Host "2. Starting ARES Service..." -ForegroundColor Yellow
            Start-Process -FilePath "python" -ArgumentList "launch.py", "ares" -WindowStyle Normal
            Start-Sleep -Seconds 5

            Write-Host "3. Starting Trader Service..." -ForegroundColor Yellow
            Start-Process -FilePath "python" -ArgumentList "launch.py", "trader" -WindowStyle Normal
            Start-Sleep -Seconds 5

            Write-Host ""
            Write-Host "All services started!" -ForegroundColor Green
            Write-Host "Check the opened windows for service status." -ForegroundColor Yellow
            Read-Host "Press Enter to continue"
        }
        "5" {
            Write-Host ""
            Write-Host "Running validation tests..." -ForegroundColor Green
            python validate.py
            Read-Host "Press Enter to continue"
        }
        "6" {
            Write-Host ""
            Write-Host "Goodbye!" -ForegroundColor Green
            exit 0
        }
        default {
            Write-Host "Invalid choice. Please try again." -ForegroundColor Red
        }
    }
} while ($true)
