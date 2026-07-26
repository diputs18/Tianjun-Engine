param(
    [string]$CloudSimProject = "D:\Download from Github\cloudsimplus-examples",
    [string]$Config = "configs\cloudsim_core_experiments.json",
    [string]$Python = "python",
    [int]$BasePort = 8124,
    [int]$MaxRuns = 0,
    [string[]]$StrategyFilter = @(),
    [string[]]$ScenarioFilter = @(),
    [int]$SeedLimit = 0,
    [switch]$Resume,
    [switch]$SkipSourceSync
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$configPath = (Resolve-Path (Join-Path $projectRoot $Config)).Path
$settings = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$outputRoot = Join-Path $projectRoot $settings.output_directory
New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null

if (-not (Test-Path -LiteralPath (Join-Path $CloudSimProject "pom.xml"))) {
    throw "CloudSim Plus Examples project not found: $CloudSimProject"
}

if (-not $SkipSourceSync) {
    $archiveRoot = Join-Path $projectRoot "examples\cloudsimplus\src\main"
    $javaTargets = @(
        "java\org\cloudsimplus\examples\HuaweiDciTianjunExperiment.java",
        "java\org\cloudsimplus\examples\tianjun\TianjunHttpBridge.java"
    )
    $resourceTargets = @(
        "resources\huawei-dci-reference.brite",
        "resources\tianjun-power-profiles.json",
        "resources\tianjun-carbon-intensity-trace.csv"
    )
    foreach ($relative in @($javaTargets + $resourceTargets)) {
        $source = Join-Path $archiveRoot $relative
        $target = Join-Path (Join-Path $CloudSimProject "src\main") $relative
        $targetParent = Split-Path -Parent $target
        New-Item -ItemType Directory -Path $targetParent -Force | Out-Null
        Copy-Item -LiteralPath $source -Destination $target -Force
    }
}

$runIndex = 0
$strategies = @($settings.strategies)
if ($StrategyFilter.Count -gt 0) {
    $strategies = @($strategies | Where-Object { $StrategyFilter -contains $_ })
}
$seeds = @($settings.seeds)
if ($SeedLimit -gt 0) {
    $seeds = @($seeds | Select-Object -First $SeedLimit)
}
$scenarios = @($settings.scenarios)
if ($ScenarioFilter.Count -gt 0) {
    $scenarios = @($scenarios | Where-Object { $ScenarioFilter -contains $_ })
}
foreach ($strategy in $strategies) {
    foreach ($scenario in $scenarios) {
        foreach ($seed in $seeds) {
            if ($MaxRuns -gt 0 -and $runIndex -ge $MaxRuns) { break }
            $port = $BasePort + $runIndex
            $runDirectory = Join-Path $outputRoot (Join-Path $strategy (Join-Path $scenario ("seed-" + $seed)))
            New-Item -ItemType Directory -Path $runDirectory -Force | Out-Null
            $snapshot = Join-Path $runDirectory "topology-snapshots.jsonl"
            $metricsOutput = [System.IO.Path]::ChangeExtension($snapshot, ".metrics.json")
            if ($Resume -and (Test-Path -LiteralPath $metricsOutput)) {
                $runIndex++
                Write-Host "resumed $runIndex : $strategy / $scenario / seed $seed"
                continue
            }
            $stateDb = Join-Path $runDirectory "control-plane.sqlite3"
            foreach ($stateArtifact in @($stateDb, "$stateDb-shm", "$stateDb-wal")) {
                if (Test-Path -LiteralPath $stateArtifact) {
                    Remove-Item -LiteralPath $stateArtifact -Force
                }
            }
            $serverOut = Join-Path $runDirectory "control-plane.stdout.log"
            $serverErr = Join-Path $runDirectory "control-plane.stderr.log"
            $mavenLog = Join-Path $runDirectory "cloudsim-maven.log"
            $serverArgs = @(
                "main.py", "serve", "--host", "127.0.0.1", "--port", "$port",
                "--offline", "--state-db", $stateDb, "--heartbeat-timeout-seconds", "120"
            )
            $serverProcess = Start-Process -FilePath $Python -ArgumentList $serverArgs `
                -WorkingDirectory $projectRoot -PassThru -WindowStyle Hidden `
                -RedirectStandardOutput $serverOut -RedirectStandardError $serverErr
            try {
                $healthy = $false
                for ($attempt = 0; $attempt -lt 40; $attempt++) {
                    try {
                        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$port/health" -TimeoutSec 1
                        if ($health.status -eq "ok") { $healthy = $true; break }
                    } catch {
                        Start-Sleep -Milliseconds 250
                    }
                }
                if (-not $healthy) { throw "Tianjun control plane did not become healthy on port $port" }
                $execArgs = "http://127.0.0.1:$port $scenario $($settings.cloudlets) $seed `"$snapshot`" once $strategy"
                Push-Location $CloudSimProject
                try {
                    # CloudSim writes recoverable bridge warnings to stderr. Windows PowerShell
                    # converts redirected native stderr into ErrorRecord objects when Stop is active.
                    $previousErrorActionPreference = $ErrorActionPreference
                    $ErrorActionPreference = "Continue"
                    try {
                        & mvn -q -DskipTests compile org.codehaus.mojo:exec-maven-plugin:3.5.0:java `
                            "-Dexec.mainClass=org.cloudsimplus.examples.HuaweiDciTianjunExperiment" `
                            "-Dexec.args=$execArgs" *> $mavenLog
                        $mavenExitCode = $LASTEXITCODE
                    } finally {
                        $ErrorActionPreference = $previousErrorActionPreference
                    }
                    if ($mavenExitCode -ne 0) {
                        Get-Content -LiteralPath $mavenLog -Tail 80 | Write-Host
                        throw "CloudSim Maven execution failed with exit code $mavenExitCode"
                    }
                } finally {
                    Pop-Location
                }
            } finally {
                if ($serverProcess -and -not $serverProcess.HasExited) {
                    Stop-Process -Id $serverProcess.Id -Force
                    $serverProcess.WaitForExit()
                }
            }
            $runIndex++
            Write-Host "completed $runIndex : $strategy / $scenario / seed $seed"
        }
        if ($MaxRuns -gt 0 -and $runIndex -ge $MaxRuns) { break }
    }
    if ($MaxRuns -gt 0 -and $runIndex -ge $MaxRuns) { break }
}

& $Python (Join-Path $projectRoot "scripts\analyze_cloudsim_core.py") --input $outputRoot
if ($LASTEXITCODE -ne 0) { throw "CloudSim statistical analysis failed" }
Write-Host "CloudSim core experiment outputs: $outputRoot"
