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
    if (-not $version -or $version -match '[\\/]') { throw "The current version pointer is invalid." }
    $root = Join-Path $Context.AppDir ("versions\" + $version)
    if (-not (Test-Path -LiteralPath $root -PathType Container)) { throw "The current version directory is missing: $root" }
    [pscustomobject]@{ Version = $version; Root = $root; Python = Join-Path $root ".venv\Scripts\python.exe" }
}

function Get-AppStatusData {
    param($Context, $Environment, $Version)
    $statusScript = @'
import json, sqlite3, sys
from pathlib import Path

library = Path(sys.argv[1])
payload = {"items": None, "generation": "unavailable"}
try:
    db = library / "db.sqlite"
    if db.exists():
        with sqlite3.connect(db) as conn:
            payload["items"] = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
except Exception:
    pass
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
        return [pscustomobject]@{ Items = $null; Generation = "unavailable" }
    }
    $output = & $Version.Python @("-c", $statusScript, $Environment.LibraryPath) 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $output) {
        return [pscustomobject]@{ Items = $null; Generation = "unavailable" }
    }
    try {
        $payload = $output | ConvertFrom-Json
        return [pscustomobject]@{ Items = $payload.items; Generation = $payload.generation }
    } catch {
        return [pscustomobject]@{ Items = $null; Generation = "unavailable" }
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
        $database = Join-Path (Read-AppEnvironment $Context).LibraryPath "db.sqlite"
        if (Test-Path -LiteralPath $database -PathType Leaf) { Write-Output "  Database: OK" }
        else { Write-Output ("  Database: MISSING - " + $database) }
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
        $pathEntries = @($env:Path -split [IO.Path]::PathSeparator)
        if ($pathEntries -contains $Context.BinDir) { Write-Output "  User PATH: OK" }
        else { Write-Output ("  User PATH: MISSING - " + $Context.BinDir) }
    } catch { Write-Output ("  User PATH: ERROR - " + $_.Exception.Message) }
    try {
        if (Test-Path -LiteralPath $Context.LogDir -PathType Container) { Write-Output ("  Logs: OK - " + $Context.LogDir) }
        else { Write-Output ("  Logs: MISSING - " + $Context.LogDir) }
    } catch { Write-Output ("  Logs: ERROR - " + $_.Exception.Message) }

    Write-Output "Next steps"
    Write-Output "  Run image-prompt-library status for a concise summary."
}

function Show-Usage {
    Write-Output "Usage: image-prompt-library <version|status|doctor>"
}

try {
    $command = if ($CommandArgs.Count) { $CommandArgs[0].ToLowerInvariant() } else { "help" }
    $rest = if ($CommandArgs.Count -gt 1) { @($CommandArgs[1..($CommandArgs.Count - 1)]) } else { @() }
    $context = Get-InstallContext
    switch ($command) {
        "version" { (Get-CurrentVersion $context).Version }
        "status" { Show-Status -Context $context }
        "doctor" { Show-Doctor -Context $context }
        "help" { Show-Usage }
        default { [Console]::Error.WriteLine("Unknown command: $command"); Show-Usage; exit 2 }
    }
} catch {
    [Console]::Error.WriteLine("ERROR: " + $_.Exception.Message)
    exit 1
}
