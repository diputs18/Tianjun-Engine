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
if /I "%ACTION%"=="smoke" goto :smoke

echo Usage: tianjun.bat start^|restart^|stop^|open^|smoke
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
  echo.
  echo DeepSeek connection check failed.
  echo Full startup requires a working OpenAI-compatible LLM configuration.
  echo Configure it with:
  echo   python -B main.py secrets --config "%TJ_CONFIG%" set deepseek --api-key "your_api_key_here"
  echo.
  echo For local offline verification only, run:
  echo   tianjun.bat smoke
  pause
  exit /b 1
)
exit /b 0

:wait_health
echo Waiting for control plane health check...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$url = '%TJ_BASE_URL%/health'; $limit = (Get-Date).AddSeconds(25); do { try { Invoke-RestMethod $url -TimeoutSec 2 | Out-Null; exit 0 } catch { Start-Sleep -Milliseconds 500 } } while ((Get-Date) -lt $limit); exit 1"
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
  exit /b 10
)
exit /b 0

:stop
call :check_python
echo Stopping Tianjun Engine processes...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$patterns = @('main\.py\s+serve.*--port\s+%TJ_PORT%', 'main\.py\s+sim-backend.*%TJ_BASE_URL%', 'main\.py\s+mcp-server.*%TJ_BASE_URL%');" ^
  "Get-CimInstance Win32_Process | ForEach-Object { $cmd = [string]$_.CommandLine; foreach ($p in $patterns) { if ($cmd -match $p) { Write-Host ('Stopping ' + $_.ProcessId + ': ' + $_.Name); Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop; break } } }"
exit /b %ERRORLEVEL%


:restart
call :check_python
call :stop
if errorlevel 1 (
  echo Tianjun could not be restarted cleanly.
  pause
  exit /b 1
)
goto :start_checked_python

:start
call :check_python
call :ensure_free
if errorlevel 10 exit /b 0

:start_checked_python
call :check_llm

echo Starting Tianjun Engine control plane...
echo Dashboard: %TJ_URL%
start "Tianjun Control Plane" cmd /k python -B main.py serve --config "%TJ_CONFIG%" --default-execution-mode simulation --host %TJ_HOST% --port %TJ_PORT%

call :wait_health

if "%TJ_START_MCP%"=="1" (
  start "Tianjun MCP Server" cmd /k python -B main.py mcp-server --config "%TJ_CONFIG%" --server "%TJ_BASE_URL%"
)

if "%TJ_OPEN_DASHBOARD%"=="1" (
  start "" "%TJ_URL%"
)

echo.
echo Tianjun Engine control plane is running:
echo   Control plane: %TJ_BASE_URL%
echo   Dashboard:     %TJ_URL%
if "%TJ_START_MCP%"=="1" echo   MCP server:    enabled
echo.
echo Sim backend is an optional manual process.
echo See README.md for its command.
exit /b 0

:smoke
call :check_python
echo Running offline smoke test...
python scripts\smoke_test.py --port 8135
exit /b %ERRORLEVEL%
