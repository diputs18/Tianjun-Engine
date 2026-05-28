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

echo Stopping Tianjun simulation backend processes...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.Name -in @('python.exe', 'pythonw.exe') }; foreach ($process in $procs) { $cmd = [string]$process.CommandLine; if ($cmd -match 'main\.py\s+sim-backend' -and $cmd -match [regex]::Escape('http://%HOST%:%PORT%')) { Write-Host ('Stopping Tianjun simulation backend ' + $process.ProcessId + '...'); Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop } }"
if errorlevel 1 (
  echo Tianjun simulation backend could not be stopped safely.
  pause
  exit /b 1
)

echo Stopping Tianjun control plane...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$port = %PORT%; $listeners = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue); foreach ($listener in $listeners) { $process = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $listener.OwningProcess) -ErrorAction SilentlyContinue; if (-not $process) { continue }; $cmd = [string]$process.CommandLine; if ($cmd -match 'main\.py\s+serve' -and $cmd -match ('--port\s+' + $port)) { Write-Host ('Stopping Tianjun process ' + $process.ProcessId + '...'); Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop } else { Write-Error ('Port ' + $port + ' is occupied by another process: ' + $process.Name + ' (' + $process.ProcessId + ').'); exit 2 } }; $limit = (Get-Date).AddSeconds(8); do { $busy = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue; if (-not $busy) { exit 0 }; Start-Sleep -Milliseconds 200 } while ((Get-Date) -lt $limit); Write-Error ('Port ' + $port + ' did not become available in time.'); exit 3"
if errorlevel 1 (
  echo Tianjun could not be restarted because the port could not be safely released.
  pause
  exit /b 1
)

echo Starting Tianjun Engine full runtime...
echo Dashboard: %URL%
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

start "" "%URL%"

echo Tianjun Engine full runtime is starting in separate windows.
echo Close the Control Plane and Simulation Backend windows to stop it.
pause
