@echo off
setlocal EnableExtensions

cd /d "%~dp0"

set "HOST=127.0.0.1"
set "PORT=8024"
set "FRONTEND_PORT=5173"
set "FRONTEND_DIR=frontend"

echo Stopping Tianjun runtime processes...

echo Stopping dashboard frontend on port %FRONTEND_PORT%...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$projectFrontend = [regex]::Escape((Join-Path (Get-Location).Path '%FRONTEND_DIR%')); $port = %FRONTEND_PORT%; $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if (-not $conn) { exit 0 }; $process = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $conn.OwningProcess) -ErrorAction SilentlyContinue; if (-not $process) { exit 0 }; $cmd = [string]$process.CommandLine; if ($cmd -match $projectFrontend -and ($cmd -match 'vite' -or $cmd -match 'npm(\.cmd)?\s+run\s+dev')) { Write-Host ('Stopping Tianjun frontend process ' + $process.ProcessId + '...'); Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop } else { Write-Host ('Port ' + $port + ' is not owned by the Tianjun frontend. Skipping.'); exit 0 }; $limit = (Get-Date).AddSeconds(8); do { $busy = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue; if (-not $busy) { exit 0 }; Start-Sleep -Milliseconds 200 } while ((Get-Date) -lt $limit); Write-Error ('Frontend port ' + $port + ' did not become available in time.'); exit 1"
if errorlevel 1 (
  echo Tianjun frontend could not be stopped safely.
  pause
  exit /b 1
)

echo Stopping Tianjun simulation backend processes...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$server = [regex]::Escape('http://%HOST%:%PORT%'); $patterns = @('main\.py\s+sim-backend', 'python(\.exe)?\s+-B\s+main\.py\s+sim-backend'); $procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.Name -in @('python.exe', 'pythonw.exe', 'cmd.exe') }; foreach ($process in $procs) { $cmd = [string]$process.CommandLine; if (-not $cmd) { continue }; if (($patterns | Where-Object { $cmd -match $_ }) -and $cmd -match $server) { Write-Host ('Stopping Tianjun simulation backend ' + $process.ProcessId + '...'); Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop } }"
if errorlevel 1 (
  echo Tianjun simulation backend could not be stopped safely.
  pause
  exit /b 1
)

echo Stopping Tianjun control plane on port %PORT%...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$port = %PORT%; $listeners = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue); if (-not $listeners) { exit 0 }; foreach ($listener in $listeners) { $process = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $listener.OwningProcess) -ErrorAction SilentlyContinue; if (-not $process) { continue }; $cmd = [string]$process.CommandLine; if ($cmd -match 'main\.py\s+serve' -and $cmd -match ('--port\s+' + $port)) { Write-Host ('Stopping Tianjun control plane ' + $process.ProcessId + '...'); Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop } else { Write-Host ('Port ' + $port + ' is not owned by a Tianjun control plane. Skipping process ' + $listener.OwningProcess + '.'); exit 0 } }; $limit = (Get-Date).AddSeconds(8); do { $busy = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue; if (-not $busy) { exit 0 }; Start-Sleep -Milliseconds 200 } while ((Get-Date) -lt $limit); Write-Error ('Control plane port ' + $port + ' did not become available in time.'); exit 1"
if errorlevel 1 (
  echo Tianjun control plane could not be stopped safely.
  pause
  exit /b 1
)

echo Closing Tianjun command windows...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$frontend = [regex]::Escape((Join-Path (Get-Location).Path '%FRONTEND_DIR%')); $server = [regex]::Escape('http://%HOST%:%PORT%'); $cmds = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.Name -eq 'cmd.exe' }; foreach ($process in $cmds) { $cmd = [string]$process.CommandLine; if (-not $cmd) { continue }; if (($cmd -match 'main\.py\s+serve' -and $cmd -match ('--port\s+' + %PORT%)) -or ($cmd -match 'main\.py\s+sim-backend' -and $cmd -match $server) -or (($cmd -match 'npm(\.cmd)?\s+run\s+dev') -and $cmd -match $frontend)) { Write-Host ('Closing Tianjun command window ' + $process.ProcessId + '...'); Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue } }"

echo Tianjun runtime processes have been stopped.
pause
