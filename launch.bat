@echo off
title BEL Edge-AI AMR Fleet Launcher
color 0b

echo ========================================================
echo   BHARAT ELECTRONICS LIMITED - EDGE-AI AMR FLEET (SIH)
echo ========================================================

cd /d "%~dp0"

echo [*] Verifying Virtual Environment...
if not exist "venv\Scripts\python.exe" (
    echo [!] ERROR: venv not found. Please run: python -m venv venv
    pause
    exit /b 1
)

set PYTHON="%~dp0venv\Scripts\python.exe"

echo [*] Verifying Dependencies...
%PYTHON% -c "import numpy; import onnxruntime; import fastapi; import websockets" 2>nul
if errorlevel 1 (
    echo [!] ERROR: Missing core dependencies. Run: pip install -r requirements.txt
    pause
    exit /b 1
)

echo [*] Checking for Mosquitto MQTT Broker...
tasklist /fi "imagename eq mosquitto.exe" | find /i "mosquitto.exe" > nul
if errorlevel 1 (
    if exist "C:\Program Files\mosquitto\mosquitto.exe" (
        echo [*] Starting Mosquitto from default location...
        start "Mosquitto Broker" "C:\Program Files\mosquitto\mosquitto.exe"
        timeout /t 2 /nobreak >nul
    ) else (
        echo [!] Mosquitto not installed. Running in UDP-only fallback mode.
    )
) else (
    echo [*] Mosquitto is already running.
)

echo [*] Generating/Verifying ML Models...
%PYTHON% "%~dp0edge-agent\core\ml\generate_models.py"

echo [*] Killing stale Python processes on ports 5000-5004, 8000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING" 2^>nul') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo [*] Starting Mission Control Observer Server...
start "Observer-API" %PYTHON% "%~dp0observer-api\main.py"

echo [*] Waiting for Observer to be ready...
timeout /t 4 /nobreak >nul

echo [*] Launching Edge Agents...
start "Robot-R01" %PYTHON% "%~dp0edge-agent\main.py" R01
start "Robot-R02" %PYTHON% "%~dp0edge-agent\main.py" R02
start "Robot-R03" %PYTHON% "%~dp0edge-agent\main.py" R03
start "Robot-R04" %PYTHON% "%~dp0edge-agent\main.py" R04

timeout /t 3 /nobreak >nul
echo [*] Opening Live Mission Control Dashboard...
start http://localhost:8000/

echo ========================================================
echo [*] Launch sequence complete.
echo [*] Observer:  http://localhost:8000/
echo [*] Robots:    R01 R02 R03 R04
echo [*] Check individual terminal windows for status.
echo ========================================================
pause