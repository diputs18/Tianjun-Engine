@echo off
setlocal

cd /d "%~dp0"

set "HOST=127.0.0.1"
set "PORT=8024"
set "URL=http://%HOST%:%PORT%/dashboard"

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

echo Starting Tianjun Engine...
echo Dashboard: %URL%

echo Checking DeepSeek connection for Hermes...
python -B main.py llm-check --config configs\tianjun.example.toml
if errorlevel 1 (
  echo DeepSeek connection check failed. Tianjun was not started in fallback mode.
  pause
  exit /b 1
)

start "" "%URL%"
python -B main.py serve --config configs\tianjun.example.toml --inventory configs/sim_cluster.example.json --default-execution-mode simulation --host %HOST% --port %PORT%

pause
