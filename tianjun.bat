@echo off
setlocal EnableExtensions

cd /d "%~dp0"
call scripts\windows\common.bat

set "ACTION=%~1"
if "%ACTION%"=="" set "ACTION=start"

if /I "%ACTION%"=="open" (
  start "" "%TJ_URL%"
  exit /b 0
)

if /I "%ACTION%"=="stop" goto :stop
if /I "%ACTION%"=="restart" goto :restart
if /I "%ACTION%"=="start" goto :start

echo Usage: tianjun.bat start^|restart^|stop^|open
exit /b 2

:check_python
where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found in PATH. Please install Python or add it to PATH.
  pause
  exit /b 1
)
exit /b 0

:check_llm
echo Checking DeepSeek connection for Hermes...
python -B main.py llm-check --config "%TJ_CONFIG%"
if errorlevel 1 (
  echo DeepSeek connection check failed. Use "python -B main.py serve --offline" for local-only verification.
  pause
  exit /b 1
)
exit /b 0

:wait_health
echo Waiting for control plane health check...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$url = 'http://%TJ_HOST%:%TJ_PORT%/health'; $limit = (Get-Date).AddSeconds(20); do { try { Invoke-RestMethod $url -TimeoutSec 2 | Out-Null; exit 0 } catch { Start-Sleep -Milliseconds 500 } } while ((Get-Date) -lt $limit); exit 1"
if errorlevel 1 (
  echo Tianjun control plane did not become healthy in time.
  pause
  exit /b 1
)
exit /b 0

:ensure_free
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$conn = Get-NetTCPConnection -LocalPort %TJ_PORT% -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if ($conn) { exit 1 } else { exit 0 }"
if errorlevel 1 (
  echo Tianjun Engine appears to be running already.
  echo Opening dashboard: %TJ_URL%
  start "" "%TJ_URL%"
  exit /b 0
)
exit /b 0

:stop
call :check_python
echo Stopping Tianjun control plane on %TJ_HOST%:%TJ_PORT%...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$port = %TJ_PORT%; $listeners = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue); foreach ($listener in $listeners) { $process = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $listener.OwningProcess) -ErrorAction SilentlyContinue; if (-not $process) { continue }; $cmd = [string]$process.CommandLine; if ($cmd -match 'main\.py\s+serve' -and $cmd -match ('--port\s+' + $port)) { Write-Host ('Stopping Tianjun process ' + $process.ProcessId + '...'); Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop } else { Write-Error ('Port ' + $port + ' is occupied by another process: ' + $process.Name + ' (' + $process.ProcessId + ').'); exit 2 } }; exit 0"
exit /b %ERRORLEVEL%

:restart
call :check_python
call :check_llm
echo Restarting Tianjun Engine on %TJ_HOST%:%TJ_PORT%...
call :stop
if errorlevel 1 (
  echo Tianjun could not be restarted because the port could not be safely released.
  pause
  exit /b 1
)
goto :launch

:start
call :check_python
call :ensure_free
call :check_llm
goto :launch

:launch
echo Starting Tianjun Engine control plane...
echo Dashboard: %TJ_URL%
start "Tianjun Control Plane" cmd /k python -B main.py serve --config "%TJ_CONFIG%" --default-execution-mode simulation --host %TJ_HOST% --port %TJ_PORT%
call :wait_health
start "" "%TJ_URL%"
echo Tianjun Engine control plane is running in a separate window.
echo No simulated nodes are started automatically.
echo Start CloudSim Plus, sim-backend, or a node agent manually when you want nodes to appear.
exit /b 0
