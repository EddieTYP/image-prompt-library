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
    try {
        $record = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
        if (-not $record -or $record -is [Array]) { throw "invalid structure" }
        foreach ($name in @("pid", "process_start_time_utc", "process_start_time_utc_ticks", "process_executable_path", "version", "app_root", "host", "port", "stdout_log", "stderr_log", "created_at")) {
            if (-not $record.PSObject.Properties[$name]) { throw "missing field" }
        }
        if (-not (Test-JsonInteger -Value $record.pid -Minimum 1 -Maximum ([int]::MaxValue))) { throw "invalid pid" }
        if (-not (Test-JsonInteger -Value $record.process_start_time_utc_ticks -Minimum 1 -Maximum ([long]::MaxValue))) { throw "invalid ticks" }
        if (-not (Test-JsonInteger -Value $record.port -Minimum 1 -Maximum 65535)) { throw "invalid port" }
        foreach ($name in @("process_start_time_utc", "process_executable_path", "version", "app_root", "host", "stdout_log", "stderr_log", "created_at")) {
            if ($record.$name -isnot [string] -or -not $record.$name.Trim()) { throw "invalid string field" }
        }
        if (-not (Test-UtcTimestamp -Value $record.process_start_time_utc)) { throw "invalid process timestamp" }
        if (-not (Test-UtcTimestamp -Value $record.created_at)) { throw "invalid creation timestamp" }
        $startTime = [DateTime]::ParseExact($record.process_start_time_utc, "o", [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::RoundtripKind)
        if ($startTime.Ticks -ne [long]$record.process_start_time_utc_ticks) { throw "inconsistent process timestamp" }
        if (-not (Test-BindHost -HostName $record.host)) { throw "invalid host" }
        return $record
    } catch {
        throw "The runtime record is malformed and was retained: $path"
    }
}

function Test-JsonInteger {
    param($Value, [long]$Minimum, [long]$Maximum)
    if ($Value -isnot [int] -and $Value -isnot [long]) { return $false }
    return [long]$Value -ge $Minimum -and [long]$Value -le $Maximum
}

function Test-UtcTimestamp {
    param($Value)
    if ($Value -isnot [string] -or -not $Value) { return $false }
    $parsed = [DateTime]::MinValue
    return [DateTime]::TryParseExact($Value, "o", [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::RoundtripKind, [ref]$parsed) -and $parsed.Kind -eq [DateTimeKind]::Utc
}

function Test-BindHost {
    param([string]$HostName)
    if (-not $HostName -or $HostName.Length -gt 253 -or $HostName.StartsWith("[") -or $HostName.EndsWith("]")) { return $false }
    $address = $null
    if ([Net.IPAddress]::TryParse($HostName, [ref]$address)) { return $true }
    if ($HostName -notmatch '^[A-Za-z0-9.-]+$') { return $false }
    $dnsName = $HostName.TrimEnd('.')
    if (-not $dnsName) { return $false }
    foreach ($label in $dnsName.Split('.')) {
        if ($label.Length -lt 1 -or $label.Length -gt 63 -or $label -notmatch '^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$') { return $false }
    }
    return $true
}

function Get-ProbeHost {
    param([string]$HostName)
    if ($HostName -in @("0.0.0.0", "::")) { return "127.0.0.1" }
    return $HostName
}

function Get-AppUrl {
    param([string]$HostName, [int]$Port)
    if (-not (Test-BindHost -HostName $HostName) -or $Port -lt 1 -or $Port -gt 65535) { throw "The app endpoint is invalid." }
    $HostName = Get-ProbeHost -HostName $HostName
    $urlHost = if ($HostName.Contains(":")) { "[" + $HostName.Replace("%", "%25") + "]" } else { $HostName }
    return "http://{0}:{1}/" -f $urlHost, $Port
}

function Write-ServerRecordFileAtomically {
    param([string]$Path, $Record)
    $directory = Split-Path -Parent $Path
    $temporaryPath = Join-Path $directory ((Split-Path -Leaf $Path) + ".{0}.tmp" -f [Guid]::NewGuid().ToString("N"))
    try {
        $encoding = New-Object Text.UTF8Encoding($false)
        [IO.File]::WriteAllText($temporaryPath, ($Record | ConvertTo-Json), $encoding)
        [IO.File]::Move($temporaryPath, $Path)
    } finally {
        if ([IO.File]::Exists($temporaryPath)) { [IO.File]::Delete($temporaryPath) }
    }
}

function Write-ServerRecordAtomically {
    param($Context, $Record)
    Write-ServerRecordFileAtomically -Path (Join-Path $Context.RunDir "server.json") -Record $Record
}

function Write-RecoveryServerRecord {
    param($Context, $Record)
    $path = Join-Path $Context.RunDir ("server.recovery.{0}.json" -f [Guid]::NewGuid().ToString("N"))
    Write-ServerRecordFileAtomically -Path $path -Record $Record
    return $path
}

function Test-ServerRecordMatches {
    param($Expected, $Actual)
    return [long]$Expected.pid -eq [long]$Actual.pid -and
        [long]$Expected.process_start_time_utc_ticks -eq [long]$Actual.process_start_time_utc_ticks -and
        [string]::Equals([string]$Expected.process_executable_path, [string]$Actual.process_executable_path, [StringComparison]::OrdinalIgnoreCase) -and
        [string]::Equals([string]$Expected.created_at, [string]$Actual.created_at, [StringComparison]::Ordinal)
}

function Remove-ServerRecordIfMatches {
    param($Context, $ExpectedRecord)
    try { $actualRecord = Read-ServerRecord $Context }
    catch { return $false }
    if (-not $actualRecord -or -not (Test-ServerRecordMatches -Expected $ExpectedRecord -Actual $actualRecord)) { return $false }
    Remove-Item -LiteralPath (Join-Path $Context.RunDir "server.json") -Force
    return $true
}

function Enter-LifecycleLock {
    param($Context)
    New-Item -ItemType Directory -Force -Path $Context.RunDir | Out-Null
    $path = Join-Path $Context.RunDir "start.lock"
    $deadline = [DateTime]::UtcNow.AddSeconds(60)
    while ([DateTime]::UtcNow -lt $deadline) {
        try {
            return [IO.File]::Open($path, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
        } catch [IO.IOException] {
            Start-Sleep -Milliseconds 100
        }
    }
    throw "Another lifecycle operation did not finish within 60 seconds."
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
    try { $lease = New-ProcessLease -Process $process }
    catch {
        $process.Dispose()
        return $null
    }
    if (-not (Test-ProcessIdentity -Process $lease.Process -Record $Record)) {
        Close-ProcessLease -Lease $lease
        return $null
    }
    return $lease
}

function Get-OwnedRuntimeState {
    param($Context)
    $record = Read-ServerRecord -Context $Context
    if (-not $record) {
        return [pscustomobject]@{ running = $false; host = $null; port = $null }
    }
    $lease = Get-OwnedProcess $record
    if (-not $lease) {
        $recordedProcess = Get-RecordedProcess $record
        if ($recordedProcess) {
            $recordedProcess.Dispose()
            throw "The recorded PID belongs to a different process; refusing lifecycle changes."
        }
        return [pscustomobject]@{ running = $false; host = $null; port = $null }
    }
    try {
        return [pscustomobject]@{ running = $true; host = [string]$record.host; port = [int]$record.port }
    } finally {
        Close-ProcessLease -Lease $lease
    }
}

function New-ProcessLease {
    param($Process)
    $safeHandle = $null
    $referenceAdded = $false
    try {
        $safeHandle = $Process.SafeHandle
        $safeHandle.DangerousAddRef([ref]$referenceAdded)
        if (-not $referenceAdded) { throw "The process handle could not be retained." }
        return [pscustomobject]@{ Process = $Process; SafeHandle = $safeHandle; ReferenceAdded = $true }
    } catch {
        if ($referenceAdded -and $safeHandle) { $safeHandle.DangerousRelease() }
        throw
    }
}

function Close-ProcessLease {
    param($Lease)
    if (-not $Lease) { return }
    try {
        if ($Lease.ReferenceAdded) {
            $Lease.SafeHandle.DangerousRelease()
            $Lease.ReferenceAdded = $false
        }
    } finally {
        $Lease.Process.Dispose()
    }
}

function Test-ProcessIdentity {
    param($Process, $Record)
    try {
        $Process.Refresh()
        if ($Process.HasExited) { return $false }
        $ticks = $Process.StartTime.ToUniversalTime().Ticks
        $path = $Process.Path
    } catch { return $false }
    return $ticks -eq [long]$Record.process_start_time_utc_ticks -and [string]::Equals($path, [string]$Record.process_executable_path, [StringComparison]::OrdinalIgnoreCase)
}

function Test-ProcessExited {
    param($Process)
    try {
        $Process.Refresh()
        return $Process.HasExited
    } catch [InvalidOperationException] {
        return $true
    } catch {
        return $false
    }
}

function Stop-VerifiedProcess {
    param($Lease)
    if (Test-ProcessExited -Process $Lease.Process) { return $true }
    try { $Lease.Process.Kill() }
    catch {
        if (Test-ProcessExited -Process $Lease.Process) { return $true }
        return $false
    }
    try { $Lease.Process.WaitForExit(10000) | Out-Null } catch {}
    return Test-ProcessExited -Process $Lease.Process
}

function Wait-ForExactProcessExit {
    param($Lease)
    while (-not (Test-ProcessExited -Process $Lease.Process)) {
        try { $Lease.Process.WaitForExit(1000) | Out-Null }
        catch { Start-Sleep -Milliseconds 100 }
    }
}

function Test-AppHealth {
    param([string]$HostName, [int]$Port, [string]$ExpectedVersion)
    try {
        $healthUri = (Get-AppUrl -HostName $HostName -Port $Port) + "api/health"
        $health = Invoke-RestMethod -Uri $healthUri -TimeoutSec 2
        return $health.ok -eq $true -and [string]$health.version -eq $ExpectedVersion
    } catch {
        return $false
    }
}

function Test-PortInUse {
    param([string]$HostName, [int]$Port)
    $probeHost = Get-ProbeHost -HostName $HostName
    $client = New-Object Net.Sockets.TcpClient
    try {
        $result = $client.BeginConnect($probeHost, $Port, $null, $null)
        if (-not $result.AsyncWaitHandle.WaitOne(500)) { return $false }
        $client.EndConnect($result)
        return $client.Connected
    } catch { return $false }
    finally { $client.Close() }
}

function Get-ServerRuntimeData {
    param($Context)
    try { $record = Read-ServerRecord $Context }
    catch { return [pscustomobject]@{ State = "stale runtime record"; Record = $null } }
    if (-not $record) { return [pscustomobject]@{ State = "stopped"; Record = $null } }

    $lease = Get-OwnedProcess $record
    if (-not $lease) { return [pscustomobject]@{ State = "stale runtime record"; Record = $record } }
    try {
        if (Test-AppHealth -HostName $record.host -Port $record.port -ExpectedVersion $record.version) {
            return [pscustomobject]@{ State = "running"; Record = $record }
        }
        return [pscustomobject]@{ State = "unhealthy"; Record = $record }
    } finally {
        Close-ProcessLease -Lease $lease
    }
}

function Get-AppStatusData {
    param($Context, $Environment, $Version)
    $runtime = Get-ServerRuntimeData $Context
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
        return [pscustomobject]@{ Items = $null; Database = "unavailable"; Generation = "unavailable"; Runtime = $runtime.State; Record = $runtime.Record }
    }
    $output = & $Version.Python @("-c", $statusScript, $Environment.LibraryPath) 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $output) {
        return [pscustomobject]@{ Items = $null; Database = "unavailable"; Generation = "unavailable"; Runtime = $runtime.State; Record = $runtime.Record }
    }
    try {
        $payload = $output | ConvertFrom-Json
        return [pscustomobject]@{ Items = $payload.items; Database = $payload.database; Generation = $payload.generation; Runtime = $runtime.State; Record = $runtime.Record }
    } catch {
        return [pscustomobject]@{ Items = $null; Database = "unavailable"; Generation = "unavailable"; Runtime = $runtime.State; Record = $runtime.Record }
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
    $url = if ($status.Runtime -in @("running", "unhealthy") -and $status.Record) {
        Get-AppUrl -HostName $status.Record.host -Port $status.Record.port
    } else {
        Get-AppUrl -HostName $environment.Host -Port $environment.Port
    }
    Write-Output ("URL: " + $url)
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
    param($Context, [string[]]$Arguments, $VersionOverride = $null)
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
    if (-not (Test-BindHost -HostName $hostName)) { throw "Host must be a single valid DNS name or IP address." }

    $lifecycleLock = Enter-LifecycleLock -Context $Context
    try {
        $version = if ($VersionOverride) { $VersionOverride } else { Get-CurrentVersion $Context }
        try { $record = Read-ServerRecord $Context }
        catch { throw "Cannot start with a malformed runtime record. Run image-prompt-library doctor." }
        if ($record) {
            $ownedLease = Get-OwnedProcess $record
            if ($ownedLease) {
                try {
                    if (Test-AppHealth -HostName $record.host -Port $record.port -ExpectedVersion $record.version) {
                        $existingUrl = Get-AppUrl -HostName $record.host -Port $record.port
                        Write-Output ("Image Prompt Library is already running at " + $existingUrl)
                        if (-not $noBrowser) {
                            try { Start-Process $existingUrl }
                            catch { Write-Warning "The app is running, but its URL could not be opened automatically." }
                        }
                        return
                    }
                    throw "The managed app process is unhealthy; it was not replaced. Run image-prompt-library stop before starting again."
                } finally {
                    Close-ProcessLease -Lease $ownedLease
                }
            }
            $recordedProcess = Get-RecordedProcess $record
            if ($recordedProcess) {
                $recordedProcess.Dispose()
                throw "The runtime record conflicts with a live process. Run image-prompt-library doctor."
            }
            if (-not (Remove-ServerRecordIfMatches -Context $Context -ExpectedRecord $record)) {
                throw "The runtime record changed while start was inspecting it; it was retained."
            }
        }
        if (Test-PortInUse -HostName $hostName -Port $port) {
            throw "Port $port is already in use by a process not managed by this install. Try image-prompt-library start --port <next-port>."
        }

        $env:IMAGE_PROMPT_LIBRARY_PATH = [IO.Path]::GetFullPath($settings.LibraryPath)
        $env:BACKEND_HOST = $hostName
        $env:BACKEND_PORT = [string]$port
        New-Item -ItemType Directory -Force -Path $Context.LogDir | Out-Null
        $outLog = Join-Path $Context.LogDir "app.out.log"
        $errLog = Join-Path $Context.LogDir "app.err.log"
        $previousOut = Join-Path $Context.LogDir "app.previous.out.log"
        $previousErr = Join-Path $Context.LogDir "app.previous.err.log"
        if (Test-Path -LiteralPath $outLog) { Move-Item -LiteralPath $outLog -Destination $previousOut -Force }
        if (Test-Path -LiteralPath $errLog) { Move-Item -LiteralPath $errLog -Destination $previousErr -Force }

        $arguments = @("-m", "uvicorn", "backend.main:app", "--host", $hostName, "--port", [string]$port)
        $process = $null
        $processLease = $null
        $record = $null
        try {
            $process = Start-Process -FilePath $version.Python -ArgumentList $arguments -WorkingDirectory $version.Root -WindowStyle Hidden -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru
            $processLease = New-ProcessLease -Process $process
            $processLease.Process.Refresh()
            try {
                $startTime = $processLease.Process.StartTime.ToUniversalTime()
                $actualExecutablePath = $processLease.Process.Path
            } catch {
                throw "The app process identity could not be read. See logs in $($Context.LogDir)."
            }
            $executablePath = [IO.Path]::GetFullPath($version.Python)
            if (-not [string]::Equals($actualExecutablePath, $executablePath, [StringComparison]::OrdinalIgnoreCase)) {
                throw "The launched app executable did not match the selected version."
            }
            $record = [pscustomobject][ordered]@{
                pid = $processLease.Process.Id
                process_start_time_utc = $startTime.ToString("o")
                process_start_time_utc_ticks = $startTime.Ticks
                process_executable_path = $actualExecutablePath
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
                    if (-not (Test-ProcessIdentity -Process $processLease.Process -Record $record)) {
                        throw "The launched app process identity changed before publication."
                    }
                    Write-ServerRecordAtomically -Context $Context -Record $record
                    $url = Get-AppUrl -HostName $hostName -Port $port
                    Write-Output ("Image Prompt Library is running at " + $url)
                    if (-not $noBrowser) {
                        try { Start-Process $url }
                        catch { Write-Warning "The app is running, but its URL could not be opened automatically." }
                    }
                    return
                }
                if (Test-ProcessExited -Process $processLease.Process) { break }
                Start-Sleep -Milliseconds 250
            }
            throw "The app did not become healthy. See logs in $($Context.LogDir)."
        } catch {
            $failure = $_.Exception.Message
            if ($processLease -and -not (Test-ProcessExited -Process $processLease.Process)) {
                $stopped = Stop-VerifiedProcess -Lease $processLease
                if (-not $stopped) {
                    if (-not $record) {
                        Wait-ForExactProcessExit -Lease $processLease
                        throw "$failure Cleanup retained the exact process handle until exit; no partial ownership record was written."
                    }
                    try {
                        $primaryRecordPath = Join-Path $Context.RunDir "server.json"
                        if ([IO.File]::Exists($primaryRecordPath)) {
                            $recoveryPath = Write-RecoveryServerRecord -Context $Context -Record $record
                        } else {
                            try {
                                Write-ServerRecordAtomically -Context $Context -Record $record
                                $recoveryPath = $primaryRecordPath
                            } catch {
                                $recoveryPath = Write-RecoveryServerRecord -Context $Context -Record $record
                            }
                        }
                    } catch {
                        Wait-ForExactProcessExit -Lease $processLease
                        throw "$failure Cleanup evidence could not be published; the exact process handle was retained until exit."
                    }
                    throw "$failure Cleanup could not confirm exit; ownership evidence was retained at $recoveryPath."
                }
            }
            throw $failure
        } finally {
            if ($processLease) { Close-ProcessLease -Lease $processLease }
            elseif ($process) { $process.Dispose() }
        }
    } finally {
        $lifecycleLock.Dispose()
    }
}

function Stop-App {
    param($Context)
    $lifecycleLock = Enter-LifecycleLock -Context $Context
    try {
        $record = Read-ServerRecord $Context
        if (-not $record) {
            Write-Output "Image Prompt Library is already stopped."
            return
        }
        $lease = Get-OwnedProcess $record
        if (-not $lease) {
            $recordedProcess = Get-RecordedProcess $record
            if ($recordedProcess) {
                $recordedProcess.Dispose()
                throw "The runtime record conflicts with a live process; it was not stopped."
            }
            if (-not (Remove-ServerRecordIfMatches -Context $Context -ExpectedRecord $record)) {
                throw "The runtime record changed while stop was inspecting it; it was retained."
            }
            Write-Output "Image Prompt Library is stopped."
            return
        }
        try {
            if (-not (Stop-VerifiedProcess -Lease $lease)) { throw "The app process did not stop; the runtime record was retained." }
            if (-not (Remove-ServerRecordIfMatches -Context $Context -ExpectedRecord $record)) {
                throw "The app stopped, but its runtime record changed and was retained."
            }
        } finally {
            Close-ProcessLease -Lease $lease
        }
        Write-Output "Image Prompt Library is stopped."
    } finally {
        $lifecycleLock.Dispose()
    }
}

function Write-VersionPointerAtomic {
    param([string]$Path, [AllowEmptyString()][string]$Value)
    if (-not $Value) {
        if (Test-Path -LiteralPath $Path) {
            if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Cannot remove non-file version pointer: $Path" }
            [IO.File]::Delete($Path)
        }
        return
    }
    $directory = [IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($Path))
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
    $temporary = Join-Path $directory ('.' + [IO.Path]::GetFileName($Path) + '.' + [Guid]::NewGuid().ToString('N') + '.tmp')
    $backup = $temporary + '.bak'
    try {
        [IO.File]::WriteAllBytes($temporary, [Text.Encoding]::ASCII.GetBytes($Value + [Environment]::NewLine))
        if (Test-Path -LiteralPath $Path) {
            if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Cannot atomically replace non-file $Path." }
            [IO.File]::Replace($temporary, $Path, $backup)
        } else {
            [IO.File]::Move($temporary, $Path)
        }
    } finally {
        if ([IO.File]::Exists($temporary)) { [IO.File]::Delete($temporary) }
        if ([IO.File]::Exists($backup)) { [IO.File]::Delete($backup) }
    }
}

function Get-VersionPointerState {
    param($Context)
    $currentPath = Join-Path $Context.AppDir "current-version"
    $previousPath = Join-Path $Context.AppDir "previous-version"
    return [pscustomobject]@{
        Current = if (Test-Path -LiteralPath $currentPath -PathType Leaf) { (Get-Content -LiteralPath $currentPath -Raw).Trim() } else { "" }
        Previous = if (Test-Path -LiteralPath $previousPath -PathType Leaf) { (Get-Content -LiteralPath $previousPath -Raw).Trim() } else { "" }
    }
}

function Restore-VersionPointerState {
    param($Context, $State)
    $errors = New-Object Collections.Generic.List[string]
    try {
        Write-VersionPointerAtomic -Path (Join-Path $Context.AppDir "current-version") -Value $State.Current
    } catch {
        $errors.Add("current-version: $($_.Exception.Message)")
    }
    try {
        Write-VersionPointerAtomic -Path (Join-Path $Context.AppDir "previous-version") -Value $State.Previous
    } catch {
        $errors.Add("previous-version: $($_.Exception.Message)")
    }
    if ($errors.Count) { throw "Pointer restoration failed: $($errors -join '; ')" }
}

function Restore-VersionSwitch {
    param($Context, $PointerState, $Runtime, $OldVersion, [string[]]$RestartArguments)
    $errors = New-Object Collections.Generic.List[string]
    $output = New-Object Collections.Generic.List[object]
    try {
        Restore-VersionPointerState -Context $Context -State $PointerState
    } catch {
        $errors.Add($_.Exception.Message)
    }
    if ($Runtime.running) {
        try {
            foreach ($line in @(Start-App -Context $Context -Arguments $RestartArguments -VersionOverride $OldVersion 2>&1)) { $output.Add($line) }
        } catch {
            $errors.Add("old-version restart: $($_.Exception.Message)")
        }
    }
    return [pscustomobject]@{ Errors = [string[]]$errors; Output = [object[]]$output }
}

function Switch-VersionTransactional {
    param($Context, [string]$TargetVersion)
    $current = Get-CurrentVersion $Context
    $pointerState = Get-VersionPointerState -Context $Context
    if (-not $TargetVersion -or $TargetVersion -in @('.', '..') -or $TargetVersion -match '[\\/]') {
        throw "The previous version pointer is invalid."
    }
    $versionsRoot = [IO.Path]::GetFullPath((Join-Path $Context.AppDir "versions"))
    $targetRoot = [IO.Path]::GetFullPath((Join-Path $versionsRoot $TargetVersion))
    if (-not $targetRoot.StartsWith($versionsRoot + "\", [StringComparison]::OrdinalIgnoreCase)) {
        throw "The previous version pointer is invalid."
    }
    if (-not (Test-Path -LiteralPath $targetRoot -PathType Container)) { throw "Previous version directory is missing: $targetRoot" }
    $runtime = Get-OwnedRuntimeState -Context $Context
    $restartArgs = @("--host", $runtime.host, "--port", [string]$runtime.port, "--no-browser")
    if ($runtime.running) { Stop-App -Context $Context }
    try {
        Write-VersionPointerAtomic -Path (Join-Path $Context.AppDir "current-version") -Value $TargetVersion
        Write-VersionPointerAtomic -Path (Join-Path $Context.AppDir "previous-version") -Value $current.Version
    } catch {
        $pointerFailure = $_.Exception.Message
        $recovery = Restore-VersionSwitch -Context $Context -PointerState $pointerState -Runtime $runtime -OldVersion $current -RestartArguments $restartArgs
        foreach ($line in $recovery.Output) { Write-Output $line }
        if ($recovery.Errors.Count) {
            throw "Version pointer switch failed: $pointerFailure Recovery failed: $($recovery.Errors -join '; ')"
        }
        throw "Version pointer switch failed: $pointerFailure Restored $($current.Version)."
    }
    if ($runtime.running) {
        try {
            Start-App -Context $Context -Arguments $restartArgs
        } catch {
            $recovery = Restore-VersionSwitch -Context $Context -PointerState $pointerState -Runtime $runtime -OldVersion $current -RestartArguments $restartArgs
            foreach ($line in $recovery.Output) { Write-Output $line }
            if ($recovery.Errors.Count) {
                throw "Rollback target failed health checks. Recovery failed: $($recovery.Errors -join '; ')"
            }
            throw "Rollback target failed health checks; restored $($current.Version)."
        }
    }
}

function Rollback-App {
    param($Context)
    $pointer = Join-Path $Context.AppDir "previous-version"
    if (-not (Test-Path -LiteralPath $pointer -PathType Leaf)) { throw "No previous version is available for rollback." }
    $previous = (Get-Content -LiteralPath $pointer -Raw).Trim()
    if (-not $previous) { throw "No previous version is available for rollback." }
    Switch-VersionTransactional -Context $Context -TargetVersion $previous
}

function Update-App {
    param($Context, [string[]]$Arguments)
    $version = "latest"
    if (@($Arguments).Count) {
        if (@($Arguments).Count -ne 2 -or $Arguments[0] -ne "--version" -or -not $Arguments[1]) {
            throw "Update accepts only optional --version <tag>."
        }
        $version = $Arguments[1]
    }
    $current = Get-CurrentVersion $Context
    $installer = Join-Path $current.Root "scripts\install.ps1"
    if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) { throw "The current Image Prompt Library version is incomplete." }
    $environment = Read-AppEnvironment -Context $Context
    $installArgs = @("-Version", $version, "-Prefix", $Context.Prefix, "-LibraryPath", $environment.LibraryPath)
    if ($env:IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL) {
        $installArgs += @("-ReleaseBaseUrl", $env:IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL)
    }
    & $installer @installArgs
    if ($LASTEXITCODE -ne 0) { throw "Update failed." }
}

function Install-SampleData {
    param($Context, [string[]]$Arguments)
    if (@($Arguments).Count -lt 1 -or @($Arguments).Count -gt 2 -or -not $Arguments[0]) {
        throw "Sample-data requires <en|zh_hans|zh_hant> and accepts optional [gpt-image-2-skill|awesome-gpt-image-2]."
    }
    $language = $Arguments[0]
    $package = if (@($Arguments).Count -eq 2) { $Arguments[1] } else { "gpt-image-2-skill" }
    if ($language -notin @("en", "zh_hans", "zh_hant")) { throw "Unsupported sample language: $language" }
    if ($package -notin @("gpt-image-2-skill", "awesome-gpt-image-2")) { throw "Unsupported sample package: $package" }
    if ($package -eq "awesome-gpt-image-2" -and $language -ne "zh_hant") {
        throw "awesome-gpt-image-2 sample package currently ships zh_hant manifests only"
    }
    $current = Get-CurrentVersion $Context
    $installer = Join-Path $current.Root "scripts\install-sample-data.ps1"
    if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) { throw "The current Image Prompt Library version is incomplete." }
    $environment = Read-AppEnvironment -Context $Context
    & $installer -Language $language -Package $package -AppRoot $current.Root -LibraryPath $environment.LibraryPath
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

function Get-NormalizedUninstallPath {
    param([AllowEmptyString()][string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { throw "Uninstall target paths must not be empty." }
    try {
        $full = [IO.Path]::GetFullPath($Path)
        $root = [IO.Path]::GetPathRoot($full)
    } catch {
        throw "Uninstall target path is invalid: $Path"
    }
    if (-not $root) { throw "Uninstall target path is invalid: $Path" }
    if ($full.Length -gt $root.Length) { $full = $full.TrimEnd('\') }
    return $full
}

function Test-UninstallPathWithinOrEqual {
    param([string]$Path, [string]$Parent)
    $target = Get-NormalizedUninstallPath -Path $Path
    $container = Get-NormalizedUninstallPath -Path $Parent
    if ($target.Equals($container, [StringComparison]::OrdinalIgnoreCase)) { return $true }
    $containerPrefix = if ($container.EndsWith('\')) { $container } else { $container + '\' }
    return $target.StartsWith($containerPrefix, [StringComparison]::OrdinalIgnoreCase)
}

function Assert-UninstallTargets {
    param($Context, $Environment)
    $prefix = Get-NormalizedUninstallPath -Path $Context.Prefix
    $library = Get-NormalizedUninstallPath -Path $Environment.LibraryPath
    foreach ($target in @($prefix, $library)) {
        if ($target.Equals([IO.Path]::GetPathRoot($target), [StringComparison]::OrdinalIgnoreCase)) {
            throw "Uninstall target paths must not be filesystem roots."
        }
    }
    $userProfile = Get-NormalizedUninstallPath -Path $env:USERPROFILE
    foreach ($target in @($prefix, $library)) {
        if (Test-UninstallPathWithinOrEqual -Path $userProfile -Parent $target) {
            throw "Uninstall target paths must not contain the user profile."
        }
    }
    if ((Test-UninstallPathWithinOrEqual -Path $prefix -Parent $library) -or
        (Test-UninstallPathWithinOrEqual -Path $library -Parent $prefix)) {
        throw "The app prefix and private library must not contain each other."
    }
    return [pscustomobject]@{ Prefix = $prefix; Library = $library; BinDir = Join-Path $prefix "bin" }
}

function Assert-UninstallTargetNotReparse {
    param([string]$Path, [string]$Name)
    $normalized = Get-NormalizedUninstallPath -Path $Path
    if (-not (Test-Path -LiteralPath $normalized)) { return $normalized }
    $item = Get-Item -LiteralPath $normalized -Force
    if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "$Name uninstall target must not be a reparse point."
    }
    return $normalized
}

function Test-UninstallPathEntryMatch {
    param([AllowEmptyString()][string]$Entry, [string]$NormalizedPath)
    if ([string]::IsNullOrWhiteSpace($Entry)) { return $false }
    $candidate = $Entry.Trim()
    if ($candidate.Length -ge 2 -and $candidate[0] -eq '"' -and $candidate[$candidate.Length - 1] -eq '"') {
        $candidate = $candidate.Substring(1, $candidate.Length - 2)
    }
    try {
        return (Get-NormalizedUninstallPath -Path $candidate).Equals($NormalizedPath, [StringComparison]::OrdinalIgnoreCase)
    } catch {
        return $false
    }
}

function Remove-UserPathEntry {
    param([string]$BinDir)
    $normalized = Get-NormalizedUninstallPath -Path $BinDir
    $userPath = [Environment]::GetEnvironmentVariable("Path", [EnvironmentVariableTarget]::User)
    if ($null -eq $userPath) { return }
    $kept = New-Object Collections.Generic.List[string]
    $removed = $false
    foreach ($entry in @($userPath -split ';')) {
        if (Test-UninstallPathEntryMatch -Entry $entry -NormalizedPath $normalized) {
            $removed = $true
        } else {
            $kept.Add($entry)
        }
    }
    if ($removed) {
        [Environment]::SetEnvironmentVariable("Path", ($kept -join ';'), [EnvironmentVariableTarget]::User)
    }
}

function Remove-UninstallTree {
    param([string]$Target, [string]$Root)
    $validated = Get-NormalizedUninstallPath -Path $Target
    if (-not (Test-UninstallPathWithinOrEqual -Path $validated -Parent $Root)) {
        throw "Uninstall cleanup path is outside the configured target."
    }
    if (-not (Test-Path -LiteralPath $validated)) { return }
    $item = Get-Item -LiteralPath $validated -Force
    if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        if ($item.PSIsContainer) {
            [IO.Directory]::Delete($validated, $false)
        } else {
            [IO.File]::Delete($validated)
        }
        return
    }
    if ($item.PSIsContainer) {
        foreach ($child in @(Get-ChildItem -LiteralPath $validated -Force)) {
            Remove-UninstallTree -Target $child.FullName -Root $Root
        }
        [IO.Directory]::Delete($validated, $false)
    } else {
        [IO.File]::Delete($validated)
    }
}

function Remove-ExactUninstallTree {
    param([string]$Target, [string]$ExpectedTarget)
    $validated = Get-NormalizedUninstallPath -Path $Target
    $expected = Get-NormalizedUninstallPath -Path $ExpectedTarget
    if (-not $validated.Equals($expected, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Uninstall cleanup target did not match the validated target."
    }
    Remove-UninstallTree -Target $validated -Root $expected
}

function Get-UninstallOptions {
    param([string[]]$Arguments)
    $deleteLibrary = $false
    $yes = $false
    foreach ($argument in @($Arguments)) {
        switch -CaseSensitive ($argument) {
            "--delete-library" {
                if ($deleteLibrary) { throw "Uninstall option was specified more than once: --delete-library" }
                $deleteLibrary = $true
            }
            "--yes" {
                if ($yes) { throw "Uninstall option was specified more than once: --yes" }
                $yes = $true
            }
            default { throw "Uninstall accepts only --delete-library and --yes." }
        }
    }
    return [pscustomobject]@{ DeleteLibrary = $deleteLibrary; Yes = $yes }
}

function Get-UninstallWorkingDirectory {
    param($Targets)
    $systemRoot = [IO.Path]::GetPathRoot([IO.Path]::GetFullPath($env:SystemRoot))
    if (-not $systemRoot -or -not (Test-Path -LiteralPath $systemRoot -PathType Container)) {
        throw "A safe working directory could not be determined for uninstall."
    }
    foreach ($target in @($Targets.Prefix, $Targets.Library)) {
        if (Test-UninstallPathWithinOrEqual -Path $systemRoot -Parent $target) {
            throw "A safe working directory could not be determined for uninstall."
        }
    }
    return $systemRoot
}

function Invoke-Uninstall {
    param($Context, [string[]]$Arguments)
    $options = Get-UninstallOptions -Arguments $Arguments
    Assert-UninstallTargetNotReparse -Path $Context.Prefix -Name "App prefix" | Out-Null
    $environment = Read-AppEnvironment -Context $Context
    $targets = Assert-UninstallTargets -Context $Context -Environment $environment
    Assert-UninstallTargetNotReparse -Path $targets.Library -Name "Private library" | Out-Null
    $workingDirectory = Get-UninstallWorkingDirectory -Targets $targets
    if ($options.DeleteLibrary -and -not $options.Yes) {
        $confirmation = Read-Host "Type DELETE to remove the private library"
        if ($confirmation -cne "DELETE") {
            Write-Output "Uninstall cancelled."
            return
        }
    }
    Set-Location -LiteralPath $workingDirectory
    [Environment]::CurrentDirectory = $workingDirectory
    Stop-App -Context $Context
    Remove-UserPathEntry -BinDir $targets.BinDir
    if (-not $options.DeleteLibrary) {
        Write-Output "Private library preserved at $($targets.Library)"
    }
    Remove-ExactUninstallTree -Target $targets.Prefix -ExpectedTarget $targets.Prefix
    if ($options.DeleteLibrary) {
        try {
            Remove-ExactUninstallTree -Target $targets.Library -ExpectedTarget $targets.Library
        } catch {
            Write-Output "Application removed at $($targets.Prefix)."
            throw "Application removal succeeded, but private library removal failed: $($_.Exception.Message)"
        }
        Write-Output "Image Prompt Library and private library uninstalled."
    } else {
        Write-Output "Image Prompt Library uninstalled."
    }
}

function Show-Usage {
    Write-Output "Usage: image-prompt-library <version|status|doctor|start|stop|update|rollback|sample-data|uninstall>"
}

try {
    $argumentCount = @($CommandArgs).Count
    $command = if ($argumentCount) { $CommandArgs[0].ToLowerInvariant() } else { "help" }
    $rest = @()
    if ($argumentCount -gt 1) { $rest = @($CommandArgs[1..($argumentCount - 1)]) }
    $context = Get-InstallContext
    switch ($command) {
        "version" { (Get-CurrentVersion $context).Version }
        "status" { Show-Status -Context $context }
        "doctor" { Show-Doctor -Context $context }
        "start" { Start-App -Context $context -Arguments $rest }
        "stop" {
            if (@($rest).Count) { throw "Stop does not accept arguments." }
            Stop-App -Context $context
        }
        "update" { Update-App -Context $context -Arguments $rest }
        "sample-data" { Install-SampleData -Context $context -Arguments $rest }
        "uninstall" { Invoke-Uninstall -Context $context -Arguments $rest }
        "rollback" {
            if (@($rest).Count) { throw "Rollback does not accept arguments." }
            Rollback-App -Context $context
        }
        "internal-owned-runtime" { Get-OwnedRuntimeState -Context $context | ConvertTo-Json -Compress }
        "help" { Show-Usage }
        default { [Console]::Error.WriteLine("Unknown command: $command"); Show-Usage; exit 2 }
    }
} catch {
    [Console]::Error.WriteLine("ERROR: " + $_.Exception.Message)
    exit 1
}
