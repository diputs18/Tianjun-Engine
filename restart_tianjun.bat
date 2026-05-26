@echo off
setlocal EnableExtensions

cd /d "%~dp0"

set "HOST=127.0.0.1"
set "PORT=8024"
set "URL=http://%HOST%:%PORT%/dashboard"
set "CONFIG=configs\tianjun.example.toml"
set "INVENTORY=configs\sim_cluster.example.json"

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found in PATH. Please install Python or add it to PATH.
  pause
  exit /b 1
)

echo Checking DeepSeek connection for Hermes before restart...
python -B main.py llm-check --config "%CONFIG%"
if errorlevel 1 (
  echo DeepSeek connection check failed. The existing service was left untouched.
  pause
  exit /b 1
)

echo Restarting Tianjun Engine on %HOST%:%PORT%...
echo Note: active in-memory CloudSim task state will be reset by this restart.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$port = %PORT%; $listeners = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue); foreach ($listener in $listeners) { $process = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $listener.OwningProcess) -ErrorAction SilentlyContinue; if (-not $process) { continue }; $cmd = [string]$process.CommandLine; if ($cmd -match 'main\.py\s+serve' -and $cmd -match ('--port\s+' + $port)) { Write-Host ('Stopping Tianjun process ' + $process.ProcessId + '...'); Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop } else { Write-Error ('Port ' + $port + ' is occupied by another process: ' + $process.Name + ' (' + $process.ProcessId + ').'); exit 2 } }; $limit = (Get-Date).AddSeconds(8); do { $busy = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue; if (-not $busy) { exit 0 }; Start-Sleep -Milliseconds 200 } while ((Get-Date) -lt $limit); Write-Error ('Port ' + $port + ' did not become available in time.'); exit 3"
if errorlevel 1 (
  echo Tianjun could not be restarted because the port could not be safely released.
  pause
  exit /b 1
)

echo Starting Tianjun Engine...
echo Dashboard: %URL%
start "" "%URL%"
python -B main.py serve --config "%CONFIG%" --inventory "%INVENTORY%" --default-execution-mode simulation --host %HOST% --port %PORT%

echo Tianjun Engine exited.
pause
