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
echo Checking Python version in virtual environment...
venv\Scripts\python.exe --version
echo.

REM Show menu
:menu
echo Select service to launch:
echo 1. Feeder Service
echo 2. ARES Service  
echo 3. Trader Service
echo 4. Dashboard (Streamlit)
echo 5. Run All Services (in order)
echo 6. Run Validation Tests
echo 7. Exit
echo.
set /p choice="Enter your choice (1-7): "

if "%choice%"=="1" goto feeder
if "%choice%"=="2" goto ares
if "%choice%"=="3" goto trader
if "%choice%"=="4" goto dashboard
if "%choice%"=="5" goto all
if "%choice%"=="6" goto validate
if "%choice%"=="7" goto exit
goto menu

:feeder
echo.
echo Starting Feeder Service...
venv\Scripts\python.exe launch.py feeder
pause
goto menu

:ares
echo.
echo Starting ARES Service...
venv\Scripts\python.exe launch.py ares
pause
goto menu

:trader
echo.
echo Starting Trader Service...
venv\Scripts\python.exe launch.py trader
pause
goto menu

:dashboard
echo.
echo Starting Dashboard...
echo Opening Streamlit dashboard in your browser...
venv\Scripts\streamlit.exe run app.py
pause
goto menu

:all
echo.
echo Starting all services in order...
echo.
echo 1. Starting Feeder Service...
start "Feeder" venv\Scripts\python.exe launch.py feeder
timeout /t 5 /nobreak >nul

echo 2. Starting ARES Service...
start "ARES" venv\Scripts\python.exe launch.py ares
timeout /t 5 /nobreak >nul

echo 3. Starting Trader Service...
start "Trader" venv\Scripts\python.exe launch.py trader
timeout /t 5 /nobreak >nul

echo.
echo All services started!
echo Check the opened windows for service status.
pause
goto menu

:validate
echo.
echo Running validation tests...
venv\Scripts\python.exe validate.py
pause
goto menu

:exit
echo.
echo Goodbye!
exit /b 0
