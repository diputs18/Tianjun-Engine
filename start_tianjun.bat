@echo off
setlocal EnableExtensions

cd /d "%~dp0"

set "HOST=127.0.0.1"
set "PORT=8024"
set "FRONTEND_PORT=5173"
set "URL=http://127.0.0.1:%FRONTEND_PORT%"
set "CONFIG=configs\tianjun.example.toml"
set "INVENTORY=configs\sim_cluster.example.json"
set "FRONTEND_DIR=frontend"

set "BACKEND_RUNNING="
set "FRONTEND_STATE="
set "STARTING_FRONTEND_ONLY="

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$conn = Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if ($conn) { exit 1 } else { exit 0 }"
if errorlevel 1 (
  set "BACKEND_RUNNING=1"
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$conn = Get-NetTCPConnection -LocalPort %FRONTEND_PORT% -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if (-not $conn) { exit 0 }; $process = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $conn.OwningProcess) -ErrorAction SilentlyContinue; $cmd = [string]$process.CommandLine; if ($cmd -match [regex]::Escape('%FRONTEND_DIR%') -and ($cmd -match 'vite' -or $cmd -match 'npm(\.cmd)?\s+run\s+dev')) { exit 1 } else { exit 2 }"
if errorlevel 2 (
  echo Port %FRONTEND_PORT% is occupied by another process. Please free the port or update the frontend port before starting Tianjun.
  pause
  exit /b 1
)
if errorlevel 1 (
  set "FRONTEND_STATE=running"
)

if defined BACKEND_RUNNING (
  echo Tianjun control plane appears to be running already.
  if defined FRONTEND_STATE (
    echo Reusing existing dashboard frontend: %URL%
    start "" "%URL%"
    exit /b 0
  )
  echo Dashboard frontend is not running on port %FRONTEND_PORT%.
  echo Starting dashboard frontend only...
  set "STARTING_FRONTEND_ONLY=1"
  goto start_frontend
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
start "Tianjun Control Plane" cmd /k python -B main.py serve --config "%CONFIG%" --inventory "%INVENTORY%" --default-execution-mode simulation --host %HOST% --port %PORT%

echo Waiting for control plane health check...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$url = 'http://%HOST%:%PORT%/health'; $limit = (Get-Date).AddSeconds(20); do { try { Invoke-RestMethod $url -TimeoutSec 2 | Out-Null; exit 0 } catch { Start-Sleep -Milliseconds 500 } } while ((Get-Date) -lt $limit); exit 1"
if errorlevel 1 (
  echo Tianjun control plane did not become healthy in time.
  pause
  exit /b 1
)

echo Starting simulation backend...
start "Tianjun Simulation Backend" cmd /k python -B main.py sim-backend --server http://%HOST%:%PORT% --inventory "%INVENTORY%" --verbose

if defined FRONTEND_STATE (
  echo Reusing existing dashboard frontend: %URL%
  start "" "%URL%"
  echo Tianjun Engine full runtime is starting in separate windows.
  echo Close the Control Plane and Simulation Backend windows to stop it.
  exit /b 0
)

:start_frontend
echo Starting dashboard frontend...
start "Tianjun Dashboard Frontend" cmd /k "cd /d ""%CD%\%FRONTEND_DIR%"" && npm install && npm run dev"
start "" "%URL%"

if defined STARTING_FRONTEND_ONLY (
  echo Dashboard frontend is starting in a separate window.
  exit /b 0
)

echo Tianjun Engine full runtime is starting in separate windows.
echo Close the Control Plane and Simulation Backend windows to stop it.
