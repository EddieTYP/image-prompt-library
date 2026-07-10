[CmdletBinding()]
param([Parameter(ValueFromRemainingArguments=$true)][string[]]$CommandArgs)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$script:ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

function Get-InstallContext {
    $scriptDir = $script:ScriptRoot
    $appRoot = Split-Path -Parent $scriptDir
    $prefix = if ($env:IMAGE_PROMPT_LIBRARY_PREFIX) {
        [IO.Path]::GetFullPath($env:IMAGE_PROMPT_LIBRARY_PREFIX)
    } else {
        [IO.Path]::GetFullPath((Join-Path $appRoot "..\..\.."))
    }
    [pscustomobject]@{
        Prefix = $prefix
        AppRoot = [IO.Path]::GetFullPath($appRoot)
        AppDir = Join-Path $prefix "app"
        EnvFile = Join-Path $prefix ".env"
        RunDir = Join-Path $prefix "run"
        LogDir = Join-Path $prefix "logs"
        BinDir = Join-Path $prefix "bin"
    }
}

function Read-AppEnvironment {
    param($Context)
    $values = @{}
    if (Test-Path -LiteralPath $Context.EnvFile -PathType Leaf) {
        foreach ($line in Get-Content -LiteralPath $Context.EnvFile) {
            if (-not $line -or $line.TrimStart().StartsWith("#") -or -not $line.Contains("=")) { continue }
            $parts = $line.Split(@("="), 2, [StringSplitOptions]::None)
            if ($parts[0] -in @("IMAGE_PROMPT_LIBRARY_PATH", "BACKEND_HOST", "BACKEND_PORT", "BACKUP_DIR")) {
                $values[$parts[0]] = $parts[1]
            }
        }
    }
    $libraryPath = if ($env:IMAGE_PROMPT_LIBRARY_PATH) { $env:IMAGE_PROMPT_LIBRARY_PATH } elseif ($values["IMAGE_PROMPT_LIBRARY_PATH"]) { $values["IMAGE_PROMPT_LIBRARY_PATH"] } else { Join-Path $env:USERPROFILE "ImagePromptLibrary" }
    $hostName = if ($env:BACKEND_HOST) { $env:BACKEND_HOST } elseif ($values["BACKEND_HOST"]) { $values["BACKEND_HOST"] } else { "127.0.0.1" }
    $portText = if ($env:BACKEND_PORT) { $env:BACKEND_PORT } elseif ($values["BACKEND_PORT"]) { $values["BACKEND_PORT"] } else { "8000" }
    [pscustomobject]@{ LibraryPath = $libraryPath; Host = $hostName; Port = [int]$portText }
}

function Get-CurrentVersion {
    param($Context)
    $pointer = Join-Path $Context.AppDir "current-version"
    if (-not (Test-Path -LiteralPath $pointer -PathType Leaf)) { throw "No installed version is selected." }
    $version = (Get-Content -LiteralPath $pointer -Raw).Trim()
    if (-not $version -or $version -eq "." -or $version -eq ".." -or $version -match '[\\/]') { throw "The current version pointer is invalid." }
    $versionsRoot = [IO.Path]::GetFullPath((Join-Path $Context.AppDir "versions"))
    $root = [IO.Path]::GetFullPath((Join-Path $versionsRoot $version))
    if (-not $root.StartsWith($versionsRoot + "\", [StringComparison]::OrdinalIgnoreCase)) { throw "The current version pointer is invalid." }
    if (-not (Test-Path -LiteralPath $root -PathType Container)) { throw "The current version directory is missing: $root" }
    [pscustomobject]@{ Version = $version; Root = $root; Python = Join-Path $root ".venv\Scripts\python.exe" }
}

function Read-ServerRecord {
    param($Context)
    $path = Join-Path $Context.RunDir "server.json"
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { return $null }
    try { return Get-Content -LiteralPath $path -Raw | ConvertFrom-Json }
    catch { throw "The runtime record is malformed: $path" }
}

function Get-RecordedProcess {
    param($Record)
    if (-not $Record -or -not $Record.PSObject.Properties["pid"]) { return $null }
    try { return Get-Process -Id ([int]$Record.pid) -ErrorAction SilentlyContinue }
    catch { return $null }
}

function Get-OwnedProcess {
    param($Record)
    if (-not $Record -or -not $Record.PSObject.Properties["pid"] -or -not $Record.PSObject.Properties["process_start_time_utc_ticks"] -or -not $Record.PSObject.Properties["process_executable_path"]) { return $null }
    $process = Get-RecordedProcess $Record
    if (-not $process) { return $null }
    try {
        $ticks = $process.StartTime.ToUniversalTime().Ticks
        $path = $process.Path
        $recordedTicks = [int64]$Record.process_start_time_utc_ticks
    } catch {
        return $null
    }
    if ($ticks -ne $recordedTicks) { return $null }
    if (-not [string]::Equals($path, [string]$Record.process_executable_path, [StringComparison]::OrdinalIgnoreCase)) { return $null }
    return $process
}

function Test-AppHealth {
    param([string]$HostName, [int]$Port, [string]$ExpectedVersion)
    $probeHost = if ($HostName -in @("0.0.0.0", "::")) { "127.0.0.1" } else { $HostName }
    try {
        $healthUri = ("http://{0}:{1}" -f $probeHost, $Port) + "/api/health"
        $health = Invoke-RestMethod -Uri $healthUri -TimeoutSec 2
        return $health.ok -eq $true -and [string]$health.version -eq $ExpectedVersion
    } catch {
        return $false
    }
}

function Test-PortInUse {
    param([string]$HostName, [int]$Port)
    $probeHost = if ($HostName -in @("0.0.0.0", "::")) { "127.0.0.1" } else { $HostName }
    $client = New-Object Net.Sockets.TcpClient
    try {
        $result = $client.BeginConnect($probeHost, $Port, $null, $null)
        if (-not $result.AsyncWaitHandle.WaitOne(500)) { return $false }
        $client.EndConnect($result)
        return $client.Connected
    } catch { return $false }
    finally { $client.Close() }
}

function Get-ServerRuntimeState {
    param($Context)
    try { $record = Read-ServerRecord $Context }
    catch { return "stale runtime record" }
    if (-not $record) { return "stopped" }

    $process = Get-OwnedProcess $record
    if (-not $process) { return "stale runtime record" }
    if (-not $record.PSObject.Properties["host"] -or -not $record.PSObject.Properties["port"] -or -not $record.PSObject.Properties["version"]) { return "stale runtime record" }
    try {
        if (Test-AppHealth -HostName ([string]$record.host) -Port ([int]$record.port) -ExpectedVersion ([string]$record.version)) { return "running" }
    } catch {}
    return "unhealthy"
}

function Get-AppStatusData {
    param($Context, $Environment, $Version)
    $runtime = Get-ServerRuntimeState $Context
    $statusScript = @'
import json, sqlite3, sys
from pathlib import Path

library = Path(sys.argv[1])
payload = {"items": None, "database": "missing", "generation": "unavailable"}
try:
    db = library / "db.sqlite"
    if db.exists():
        try:
            with sqlite3.connect(db) as conn:
                payload["items"] = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
            payload["database"] = "ok"
        except Exception:
            payload["database"] = "unavailable"
except Exception:
    payload["database"] = "unavailable"
try:
    from backend.services.openai_codex_native import CodexNativeAuthStore, configured_client_id
    if not configured_client_id():
        payload["generation"] = "not configured"
    elif CodexNativeAuthStore().path.is_file():
        payload["generation"] = "connected"
    else:
        payload["generation"] = "not connected"
except Exception:
    pass
print(json.dumps(payload))
'@
    if (-not (Test-Path -LiteralPath $Version.Python -PathType Leaf)) {
        return [pscustomobject]@{ Items = $null; Database = "unavailable"; Generation = "unavailable"; Runtime = $runtime }
    }
    $output = & $Version.Python @("-c", $statusScript, $Environment.LibraryPath) 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $output) {
        return [pscustomobject]@{ Items = $null; Database = "unavailable"; Generation = "unavailable"; Runtime = $runtime }
    }
    try {
        $payload = $output | ConvertFrom-Json
        return [pscustomobject]@{ Items = $payload.items; Database = $payload.database; Generation = $payload.generation; Runtime = $runtime }
    } catch {
        return [pscustomobject]@{ Items = $null; Database = "unavailable"; Generation = "unavailable"; Runtime = $runtime }
    }
}

function Show-Status {
    param($Context)
    $environment = Read-AppEnvironment $Context
    $version = Get-CurrentVersion $Context
    $status = Get-AppStatusData -Context $Context -Environment $environment -Version $version
    Write-Output "Image Prompt Library status"
    Write-Output ("Version: " + $version.Version)
    Write-Output ("Library: " + $environment.LibraryPath)
    Write-Output ("URL: http://{0}:{1}/" -f $environment.Host, $environment.Port)
    Write-Output ("App: " + $status.Runtime)
    Write-Output ("Items: " + $(if ($null -eq $status.Items) { "unavailable" } else { $status.Items }))
    Write-Output ("Generation: " + $status.Generation)
    Write-Output "Run image-prompt-library doctor for detailed diagnostics."
}

function Show-Doctor {
    param($Context)
    Write-Output "App"
    try {
        $version = Get-CurrentVersion $Context
        Write-Output ("  Current version: OK (" + $version.Version + ")")
        $runtime = Get-AppStatusData -Context $Context -Environment (Read-AppEnvironment $Context) -Version $version
        Write-Output ("  Process: " + $runtime.Runtime)
    } catch {
        $version = $null
        Write-Output ("  Current version: ERROR - " + $_.Exception.Message)
    }

    Write-Output "Library"
    try {
        $environment = Read-AppEnvironment $Context
        if (Test-Path -LiteralPath $environment.LibraryPath -PathType Container) { Write-Output "  Library path: OK" }
        else { Write-Output ("  Library path: MISSING - " + $environment.LibraryPath) }
    } catch { Write-Output ("  Library path: ERROR - " + $_.Exception.Message) }

    Write-Output "Database"
    try {
        $environment = Read-AppEnvironment $Context
        $database = Join-Path $environment.LibraryPath "db.sqlite"
        if (-not $version) { Write-Output "  Database: UNAVAILABLE" }
        else {
            $status = Get-AppStatusData -Context $Context -Environment $environment -Version $version
            if ($status.Database -eq "missing") { Write-Output ("  Database: MISSING - " + $database) }
            elseif ($status.Database -eq "ok" -and $null -ne $status.Items) { Write-Output ("  Database: OK ({0} items)" -f $status.Items) }
            else { Write-Output "  Database: UNAVAILABLE" }
        }
    } catch { Write-Output ("  Database: ERROR - " + $_.Exception.Message) }

    Write-Output "Generation"
    try {
        if ($version) {
            $generation = Get-AppStatusData -Context $Context -Environment (Read-AppEnvironment $Context) -Version $version
            Write-Output ("  Generation: " + $generation.Generation)
        } else { Write-Output "  Generation: unavailable until an app version is selected." }
    } catch { Write-Output ("  Generation: ERROR - " + $_.Exception.Message) }

    Write-Output "Updates / Runtime"
    try {
        if ($version -and (Test-Path -LiteralPath $version.Python -PathType Leaf)) { Write-Output "  Version-local Python: OK" }
        else { Write-Output "  Version-local Python: MISSING" }
    } catch { Write-Output ("  Version-local Python: ERROR - " + $_.Exception.Message) }
    try {
        $shim = Join-Path $Context.BinDir "image-prompt-library.ps1"
        if (Test-Path -LiteralPath $shim -PathType Leaf) { Write-Output "  Command shim: OK" }
        else { Write-Output ("  Command shim: MISSING - " + $shim) }
    } catch { Write-Output ("  Command shim: ERROR - " + $_.Exception.Message) }
    try {
        $userPath = [Environment]::GetEnvironmentVariable("Path", [EnvironmentVariableTarget]::User)
        $binDir = [IO.Path]::GetFullPath($Context.BinDir).TrimEnd('\')
        $pathEntries = @($userPath -split [IO.Path]::PathSeparator | ForEach-Object {
            $entry = $_.Trim().Trim('"')
            if ($entry) {
                try { [IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($entry)).TrimEnd('\') } catch {}
            }
        })
        if (@($pathEntries | Where-Object { [string]::Equals($_, $binDir, [StringComparison]::OrdinalIgnoreCase) }).Count -gt 0) { Write-Output "  User PATH: OK" }
        else { Write-Output ("  User PATH: MISSING - " + $Context.BinDir) }
    } catch { Write-Output ("  User PATH: ERROR - " + $_.Exception.Message) }
    try {
        if (Test-Path -LiteralPath $Context.LogDir -PathType Container) { Write-Output ("  Logs: OK - " + $Context.LogDir) }
        else { Write-Output ("  Logs: MISSING - " + $Context.LogDir) }
    } catch { Write-Output ("  Logs: ERROR - " + $_.Exception.Message) }

    Write-Output "Next steps"
    Write-Output "  Run image-prompt-library status for a concise summary."
}

function Start-App {
    param($Context, [string[]]$Arguments)
    $settings = Read-AppEnvironment -Context $Context
    $hostName = $settings.Host
    $portText = [string]$settings.Port
    $noBrowser = $false
    for ($index = 0; $index -lt $Arguments.Count; $index++) {
        switch ($Arguments[$index]) {
            "--host" {
                $index++
                if ($index -ge $Arguments.Count) { throw "--host requires a value." }
                $hostName = $Arguments[$index]
            }
            "--port" {
                $index++
                if ($index -ge $Arguments.Count) { throw "--port requires a value." }
                $portText = $Arguments[$index]
            }
            "--no-browser" { $noBrowser = $true }
            default { throw "Unknown start option: $($Arguments[$index])" }
        }
    }
    try { $port = [int]$portText }
    catch { throw "Port must be an integer from 1 to 65535." }
    if ($port -lt 1 -or $port -gt 65535) { throw "Port must be an integer from 1 to 65535." }

    $version = Get-CurrentVersion $Context
    try { $record = Read-ServerRecord $Context }
    catch { throw "Cannot start with a malformed runtime record. Run image-prompt-library doctor." }
    if ($record) {
        if (-not $record.PSObject.Properties["pid"]) { throw "The runtime record is incomplete. Run image-prompt-library doctor." }
        $ownedProcess = Get-OwnedProcess $record
        if ($ownedProcess) {
            try {
                $isHealthy = Test-AppHealth -HostName ([string]$record.host) -Port ([int]$record.port) -ExpectedVersion ([string]$record.version)
            } catch { $isHealthy = $false }
            if ($isHealthy) {
                $existingUrl = "http://{0}:{1}/" -f $record.host, $record.port
                Write-Output ("Image Prompt Library is already running at " + $existingUrl)
                if (-not $noBrowser) { Start-Process $existingUrl }
                return
            }
            throw "The managed app process is unhealthy; it was not replaced. Run image-prompt-library stop before starting again."
        } else {
            $recordedProcess = Get-RecordedProcess $record
            if ($recordedProcess) { throw "The runtime record conflicts with a live process. Run image-prompt-library doctor." }
            Remove-Item -LiteralPath (Join-Path $Context.RunDir "server.json") -Force
        }
    }
    if (Test-PortInUse -HostName $hostName -Port $port) {
        throw "Port $port is already in use by a process not managed by this install. Try image-prompt-library start --port <next-port>."
    }

    $env:IMAGE_PROMPT_LIBRARY_PATH = [IO.Path]::GetFullPath($settings.LibraryPath)
    $env:BACKEND_HOST = $hostName
    $env:BACKEND_PORT = [string]$port
    New-Item -ItemType Directory -Force -Path $Context.RunDir, $Context.LogDir | Out-Null
    $outLog = Join-Path $Context.LogDir "app.out.log"
    $errLog = Join-Path $Context.LogDir "app.err.log"
    $previousOut = Join-Path $Context.LogDir "app.previous.out.log"
    $previousErr = Join-Path $Context.LogDir "app.previous.err.log"
    if (Test-Path -LiteralPath $outLog) { Move-Item -LiteralPath $outLog -Destination $previousOut -Force }
    if (Test-Path -LiteralPath $errLog) { Move-Item -LiteralPath $errLog -Destination $previousErr -Force }

    $arguments = @("-m", "uvicorn", "backend.main:app", "--host", $hostName, "--port", [string]$port)
    $process = Start-Process -FilePath $version.Python -ArgumentList $arguments -WorkingDirectory $version.Root -WindowStyle Hidden -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru
    $process.Refresh()
    try {
        $startTime = $process.StartTime.ToUniversalTime()
        $executablePath = $process.Path
    } catch {
        throw "The app process identity could not be read. See logs in $($Context.LogDir)."
    }
    $record = [pscustomobject][ordered]@{
        pid = $process.Id
        process_start_time_utc = $startTime.ToString("o")
        process_start_time_utc_ticks = $startTime.Ticks
        process_executable_path = $executablePath
        version = $version.Version
        app_root = $version.Root
        host = $hostName
        port = $port
        stdout_log = $outLog
        stderr_log = $errLog
        created_at = [DateTime]::UtcNow.ToString("o")
    }
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    while ([DateTime]::UtcNow -lt $deadline) {
        if (Test-AppHealth -HostName $hostName -Port $port -ExpectedVersion $version.Version) {
            $record | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Context.RunDir "server.json") -Encoding UTF8
            $url = "http://{0}:{1}/" -f $hostName, $port
            Write-Output ("Image Prompt Library is running at " + $url)
            if (-not $noBrowser) { Start-Process $url }
            return
        }
        $process.Refresh()
        if ($process.HasExited) { break }
        Start-Sleep -Milliseconds 250
    }
    $ownedProcess = Get-OwnedProcess $record
    if ($ownedProcess) { Stop-Process -Id $ownedProcess.Id }
    throw "The app did not become healthy. See logs in $($Context.LogDir)."
}

function Stop-App {
    param($Context)
    $record = Read-ServerRecord $Context
    if (-not $record) {
        Write-Output "Image Prompt Library is already stopped."
        return
    }
    if (-not $record.PSObject.Properties["pid"]) { throw "The runtime record is incomplete; it was retained." }
    $process = Get-OwnedProcess $record
    if (-not $process) {
        $recordedProcess = Get-RecordedProcess $record
        if ($recordedProcess) { throw "The runtime record conflicts with a live process; it was not stopped." }
        Remove-Item -LiteralPath (Join-Path $Context.RunDir "server.json") -Force
        Write-Output "Image Prompt Library is stopped."
        return
    }
    Stop-Process -Id $process.Id
    $process.WaitForExit(10000) | Out-Null
    if (Get-Process -Id $process.Id -ErrorAction SilentlyContinue) { throw "The app process did not stop; the runtime record was retained." }
    Remove-Item -LiteralPath (Join-Path $Context.RunDir "server.json") -Force
    Write-Output "Image Prompt Library is stopped."
}

function Show-Usage {
    Write-Output "Usage: image-prompt-library <version|status|doctor|start|stop>"
}

try {
    $command = if ($CommandArgs.Count) { $CommandArgs[0].ToLowerInvariant() } else { "help" }
    $rest = if ($CommandArgs.Count -gt 1) { @($CommandArgs[1..($CommandArgs.Count - 1)]) } else { @() }
    $context = Get-InstallContext
    switch ($command) {
        "version" { (Get-CurrentVersion $context).Version }
        "status" { Show-Status -Context $context }
        "doctor" { Show-Doctor -Context $context }
        "start" { Start-App -Context $context -Arguments $rest }
        "stop" { Stop-App -Context $context }
        "help" { Show-Usage }
        default { [Console]::Error.WriteLine("Unknown command: $command"); Show-Usage; exit 2 }
    }
} catch {
    [Console]::Error.WriteLine("ERROR: " + $_.Exception.Message)
    exit 1
}
