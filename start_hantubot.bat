@echo off
chcp 65001 > nul
echo ========================================
echo   Hantubot Auto Trading System
echo ========================================
echo.

cd /d "%~dp0"

if exist "venv\Scripts\activate.bat" (
    echo [INFO] Activating venv...
    call venv\Scripts\activate.bat
) else (
    echo [WARNING] venv not found.
    echo [INFO] Please run 'python -m venv venv' first.
    echo.
)

:run
echo.
echo [INFO] Starting Hantubot GUI...
echo [INFO] To close, click 'Stop Engine' in GUI.
echo.
python run.py

if errorlevel 1 (
    echo.
    echo ========================================
    echo   Error Occurred!
    echo ========================================
    echo.
    echo 1. Check venv installation
    echo 2. Create venv: python -m venv venv
    echo 3. Install reqs: pip install -r requirements.txt
    echo.
    pause
)
