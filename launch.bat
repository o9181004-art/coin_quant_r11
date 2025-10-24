@echo off
REM Coin Quant R11 - Windows Launcher
REM Launches services in the correct order

echo === Coin Quant R11 Launcher ===
echo.

REM Check if virtual environment exists
if not exist "venv\Scripts\activate.bat" (
    echo Error: Virtual environment not found
    echo Please run setup.py first
    pause
    exit /b 1
)

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Check Python version
python --version
echo.

REM Show menu
:menu
echo Select service to launch:
echo 1. Feeder Service
echo 2. ARES Service  
echo 3. Trader Service
echo 4. Run All Services (in order)
echo 5. Run Validation Tests
echo 6. Exit
echo.
set /p choice="Enter your choice (1-6): "

if "%choice%"=="1" goto feeder
if "%choice%"=="2" goto ares
if "%choice%"=="3" goto trader
if "%choice%"=="4" goto all
if "%choice%"=="5" goto validate
if "%choice%"=="6" goto exit
goto menu

:feeder
echo.
echo Starting Feeder Service...
python launch.py feeder
pause
goto menu

:ares
echo.
echo Starting ARES Service...
python launch.py ares
pause
goto menu

:trader
echo.
echo Starting Trader Service...
python launch.py trader
pause
goto menu

:all
echo.
echo Starting all services in order...
echo.
echo 1. Starting Feeder Service...
start "Feeder" python launch.py feeder
timeout /t 5 /nobreak >nul

echo 2. Starting ARES Service...
start "ARES" python launch.py ares
timeout /t 5 /nobreak >nul

echo 3. Starting Trader Service...
start "Trader" python launch.py trader
timeout /t 5 /nobreak >nul

echo.
echo All services started!
echo Check the opened windows for service status.
pause
goto menu

:validate
echo.
echo Running validation tests...
python validate.py
pause
goto menu

:exit
echo.
echo Goodbye!
exit /b 0
