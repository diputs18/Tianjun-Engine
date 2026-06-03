@echo off
setlocal EnableExtensions

cd /d "%~dp0"

set "HOST=127.0.0.1"
set "PORT=8024"
set "URL=http://%HOST%:%PORT%/dashboard"
set "CONFIG=configs\tianjun.example.toml"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$conn = Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if ($conn) { exit 1 } else { exit 0 }"
if errorlevel 1 (
  echo Tianjun Engine appears to be running already.
  echo Opening dashboard: %URL%
  start "" "%URL%"
  exit /b 0
)

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found in PATH. Please install Python or add it to PATH.
  pause
  exit /b 1
)

echo Starting Tianjun Engine control plane...
echo Dashboard: %URL%

echo Checking DeepSeek connection for Hermes...
python -B main.py llm-check --config "%CONFIG%"
if errorlevel 1 (
  echo DeepSeek connection check failed. Tianjun full runtime was not started.
  pause
  exit /b 1
)

echo Starting control plane...
start "Tianjun Control Plane" cmd /k python -B main.py serve --config "%CONFIG%" --default-execution-mode simulation --host %HOST% --port %PORT%

echo Waiting for control plane health check...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$url = 'http://%HOST%:%PORT%/health'; $limit = (Get-Date).AddSeconds(20); do { try { Invoke-RestMethod $url -TimeoutSec 2 | Out-Null; exit 0 } catch { Start-Sleep -Milliseconds 500 } } while ((Get-Date) -lt $limit); exit 1"
if errorlevel 1 (
  echo Tianjun control plane did not become healthy in time.
  pause
  exit /b 1
)

start "" "%URL%"

echo Tianjun Engine control plane is running in a separate window.
echo No simulated nodes are started automatically.
echo Start CloudSim Plus, sim-backend, or a node agent manually when you want nodes to appear.
