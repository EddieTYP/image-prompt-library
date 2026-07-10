# Native Windows Quick Start Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a verified, user-level native Windows PowerShell install and lifecycle path that takes a Python 3.10+ user from one command to a healthy background Image Prompt Library in the browser.

**Architecture:** Keep the existing Bash release path unchanged. Add four PowerShell 5.1-compatible scripts that reuse the current tar.gz release artifact, use text files instead of privileged Windows symlinks, manage one owned background Uvicorn process through exact runtime metadata, and switch versions transactionally. Advertise native Windows support only through an additive release-manifest capability and verify the complete flow in a dependency-free PowerShell smoke script on `windows-latest`.

**Tech Stack:** Windows PowerShell 5.1, Python 3.10+ standard library, existing FastAPI/Uvicorn runtime, Bash release packager, pytest contract tests, GitHub Actions Windows runner.

## Global Constraints

- Work on `codex/native-windows-quick-start`; preserve unrelated `.superpowers/sdd/*` edits and ignored QA logs.
- Do not install Python, PowerShell, `winget`, Git, WSL, Node.js, or another system dependency.
- Require Windows 10/11, PowerShell 5.1+, and Python 3.10+ through `py -3` or `python`.
- Do not require administrator access or modify the machine-wide PATH.
- Do not add an EXE/MSI/MSIX, Windows service, Scheduled Task, login startup, Docker path, or runtime dependency.
- Keep PowerShell source and normal console output ASCII; support paths containing spaces.
- Keep the default bind address `127.0.0.1`.
- Never execute `.env` as PowerShell and never log OAuth tokens, environment secrets, or private prompt content.
- Verify manifest, checksum file, and calculated SHA256 before extraction.
- Never kill a process unless PID, exact start-time ticks, and executable path match its runtime record.
- Never delete a wildcard or discovered target; validate exact literal prefix/library targets first.
- Keep `%USERPROFILE%\ImagePromptLibrary` outside `%LOCALAPPDATA%\ImagePromptLibrary` and preserve it on default uninstall.
- Keep existing Linux/macOS/WSL Bash behavior unchanged.
- Use no Pester dependency; Windows behavior tests run through a plain PowerShell smoke script.
- Keep current public release wording on `v0.7.10` until the real compatible release exists; expected first compatible stable release is `v0.8.0`.
- Run focused checks per task. Reserve the full Ubuntu suite/build and complete Windows smoke for the final implementation gate.

## File Structure

### Create

- `scripts/setup-runtime.ps1` - validate/use Python and create the version-local runtime.
- `scripts/appctl.ps1` - configuration, process lifecycle, diagnostics, update/rollback, sample-data dispatch, and uninstall.
- `scripts/install.ps1` - release selection, download, verification, safe extraction, install, pointers, shim, and transactional update orchestration.
- `scripts/install-sample-data.ps1` - sample ZIP verification, safe extraction, and importer invocation.
- `tests/test_windows_installer.py` - cross-platform source/package/docs/workflow contracts.
- `tests/windows-installer-smoke.ps1` - real native Windows end-to-end flow without Pester.
- `docs/releases/v0.8.0.md` - stable minor-release notes prepared before tagging.
- `docs/qa/2026-07-10-native-windows-quick-start-qa.md` - local and CI evidence, completed during final QA.

### Modify

- `scripts/package-release.sh` - include PowerShell scripts and emit `windows-powershell-v1`.
- `.github/workflows/ci.yml` - add focused `windows-installer` job.
- `README.md` - capability-aware Windows quick start and current-release-safe wording.
- `README_zh-TW.md` - Traditional Chinese Windows guidance.
- `README_zh-CN.md` - Simplified Chinese Windows guidance.
- `docs/INSTALLATION.md` - native Windows install/lifecycle reference and inspect-first path.
- `docs/TROUBLESHOOTING.md` - Python, PATH, port, runtime record, health, and logs guidance.
- `ROADMAP.md` - remove completed/stale work and retain real follow-ups.
- `tests/test_installer_release.py` - release artifact and Bash compatibility assertions.
- `tests/test_public_mvp.py` - multilingual public-doc status assertions.

---

### Task 1: Windows Runtime Setup

**Files:**
- Create: `scripts/setup-runtime.ps1`
- Create: `tests/test_windows_installer.py`

**Interfaces:**
- Consumes: an extracted app root containing `pyproject.toml` and `backend/`.
- Produces: `scripts/setup-runtime.ps1 -AppRoot <path> [-PythonExe <path>] [-PythonPrefixArgs <args>]`; a ready `<app-root>\.venv\Scripts\python.exe` or a nonzero exit.

- [ ] **Step 1: Write the failing source-contract tests**

Create `tests/test_windows_installer.py` with:

```python
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_windows_runtime_setup_is_local_and_never_installs_python():
    path = ROOT / "scripts" / "setup-runtime.ps1"
    assert path.is_file()
    script = path.read_text(encoding="utf-8")
    assert "Set-StrictMode -Version Latest" in script
    assert "sys.version_info >= (3, 10)" in script
    assert 'Join-Path $AppRoot ".venv\\Scripts\\python.exe"' in script
    assert "-m venv" in script
    assert "-m pip install" in script
    assert "import backend.main, uvicorn" in script
    assert "image-prompt-library-runtime-probe-" in script
    assert "IMAGE_PROMPT_LIBRARY_PATH" in script
    assert "https://www.python.org/downloads/windows/" in script
    assert not re.search(r"(?i)winget\s+install", script)
    assert "npm" not in script.lower()
    assert "node" not in script.lower()
    assert "Start-Process" not in script
```

- [ ] **Step 2: Run the test and confirm it fails because the script is absent**

Run:

```powershell
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m pytest tests/test_windows_installer.py::test_windows_runtime_setup_is_local_and_never_installs_python -q
```

Expected: FAIL at `assert path.is_file()`.

- [ ] **Step 3: Implement the runtime setup script**

Create `scripts/setup-runtime.ps1` with this structure and exact command flow:

```powershell
[CmdletBinding()]
param(
    [string]$AppRoot = (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)),
    [string]$PythonExe = "",
    [string[]]$PythonPrefixArgs = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Test-PythonCandidate {
    param([string]$Exe, [string[]]$PrefixArgs)
    try {
        & $Exe @PrefixArgs -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" 2>$null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Find-SupportedPython {
    if ($PythonExe) {
        if (-not (Test-PythonCandidate -Exe $PythonExe -PrefixArgs $PythonPrefixArgs)) {
            throw "Image Prompt Library requires Python 3.10 or newer. Download it from https://www.python.org/downloads/windows/ and rerun the installer."
        }
        return [pscustomobject]@{ Exe = $PythonExe; PrefixArgs = @($PythonPrefixArgs) }
    }
    foreach ($candidate in @(
        [pscustomobject]@{ Name = "py"; PrefixArgs = @("-3") },
        [pscustomobject]@{ Name = "python"; PrefixArgs = @() }
    )) {
        $command = Get-Command $candidate.Name -ErrorAction SilentlyContinue
        if ($command -and (Test-PythonCandidate -Exe $command.Source -PrefixArgs $candidate.PrefixArgs)) {
            return [pscustomobject]@{ Exe = $command.Source; PrefixArgs = @($candidate.PrefixArgs) }
        }
    }
    throw "Image Prompt Library requires Python 3.10 or newer. Download it from https://www.python.org/downloads/windows/ and rerun the installer."
}

function Invoke-PythonChecked {
    param([string]$Exe, [string[]]$Args, [string]$FailureMessage)
    & $Exe @Args
    if ($LASTEXITCODE -ne 0) { throw $FailureMessage }
}

$AppRoot = [IO.Path]::GetFullPath($AppRoot)
if (-not (Test-Path -LiteralPath (Join-Path $AppRoot "pyproject.toml") -PathType Leaf)) {
    throw "Runtime setup requires pyproject.toml under $AppRoot"
}

$python = Find-SupportedPython
$venvPython = Join-Path $AppRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    $venvArgs = @($python.PrefixArgs) + @("-m", "venv", (Join-Path $AppRoot ".venv"))
    Invoke-PythonChecked -Exe $python.Exe -Args $venvArgs -FailureMessage "Could not create the version-local Python environment."
}

Invoke-PythonChecked -Exe $venvPython -Args @("-m", "pip", "install", "--upgrade", "pip") -FailureMessage "Could not prepare pip in the version-local environment."
Invoke-PythonChecked -Exe $venvPython -Args @("-m", "pip", "install", $AppRoot) -FailureMessage "Could not install Image Prompt Library into the version-local environment."
$probeLibrary = Join-Path ([IO.Path]::GetTempPath()) ("image-prompt-library-runtime-probe-" + [Guid]::NewGuid().ToString("N"))
$incomingLibrary = $env:IMAGE_PROMPT_LIBRARY_PATH
try {
    $env:IMAGE_PROMPT_LIBRARY_PATH = $probeLibrary
    Invoke-PythonChecked -Exe $venvPython -Args @("-c", "import backend.main, uvicorn") -FailureMessage "The installed runtime could not import Image Prompt Library."
} finally {
    if ($null -eq $incomingLibrary) { Remove-Item Env:IMAGE_PROMPT_LIBRARY_PATH -ErrorAction SilentlyContinue }
    else { $env:IMAGE_PROMPT_LIBRARY_PATH = $incomingLibrary }
    if (Test-Path -LiteralPath $probeLibrary) { Remove-Item -LiteralPath $probeLibrary -Recurse -Force }
}
Write-Output "Runtime setup complete."
```

Keep all strings ASCII. Do not catch and flatten the final actionable error into a PowerShell stack dump; the caller will print the message.

- [ ] **Step 4: Parse the script and run the focused test**

Run:

```powershell
$tokens=$null; $errors=$null
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path scripts/setup-runtime.ps1), [ref]$tokens, [ref]$errors) | Out-Null
if ($errors.Count) { $errors | Format-List; exit 1 }
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m pytest tests/test_windows_installer.py::test_windows_runtime_setup_is_local_and_never_installs_python -q
```

Expected: PowerShell parser exits 0; pytest reports `1 passed`.

- [ ] **Step 5: Commit the runtime setup slice**

```powershell
git add scripts/setup-runtime.ps1 tests/test_windows_installer.py
git commit -m "feat: add Windows runtime setup"
```

### Task 2: Controller Context, Version, Status, and Doctor

**Files:**
- Create: `scripts/appctl.ps1`
- Modify: `tests/test_windows_installer.py`

**Interfaces:**
- Consumes: a version root under `<prefix>\app\versions\<version>`, pointer files under `<prefix>\app`, and known keys from `<prefix>\.env`.
- Produces: `Get-InstallContext`, `Read-AppEnvironment`, `Get-CurrentVersion`, `Get-AppStatusData`, `Show-Status`, `Show-Doctor`, and command dispatch for `version`, `status`, and `doctor`.

- [ ] **Step 1: Add the failing controller contract test**

Append:

```python
def test_windows_appctl_loads_known_config_and_exposes_diagnostics():
    path = ROOT / "scripts" / "appctl.ps1"
    assert path.is_file()
    script = path.read_text(encoding="utf-8")
    for name in (
        "Get-InstallContext",
        "Read-AppEnvironment",
        "Get-CurrentVersion",
        "Get-AppStatusData",
        "Show-Status",
        "Show-Doctor",
    ):
        assert f"function {name}" in script
    assert "IMAGE_PROMPT_LIBRARY_PATH" in script
    assert "BACKEND_HOST" in script
    assert "BACKEND_PORT" in script
    assert "App" in script
    assert "Library" in script
    assert '"version"' in script
    assert '"status"' in script
    assert '"doctor"' in script
    assert ". $EnvFile" not in script
    assert "Invoke-Expression" not in script
```

- [ ] **Step 2: Run the test and confirm the file is absent**

Run:

```powershell
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m pytest tests/test_windows_installer.py::test_windows_appctl_loads_known_config_and_exposes_diagnostics -q
```

Expected: FAIL at `assert path.is_file()`.

- [ ] **Step 3: Implement context and safe `.env` parsing**

Create `scripts/appctl.ps1` with a manual `$args` dispatcher and these exact boundaries:

```powershell
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
```

Do not dot-source `.env`. Normalize only paths that are used as paths; do not mutate a user-provided host.

- [ ] **Step 4: Implement version/status/doctor through the version-local Python**

Add `Get-AppStatusData` by invoking `<version>\.venv\Scripts\python.exe -c <script>` with positional arguments. The embedded Python must:

```python
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
```

`Show-Status` prints version, library, URL, item count/unavailable, generation state, and `Run image-prompt-library doctor for detailed diagnostics.` `Show-Doctor` prints headings `App`, `Library`, `Database`, `Generation`, `Updates / Runtime`, and `Next steps`; it checks pointer validity, venv existence, shim existence, user PATH membership, and log paths. Catch each diagnostic category independently.

Wrap dispatch in a friendly top-level catch and use exactly:

```powershell
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
```

`Show-Usage` may list only implemented commands at this task. Later tasks extend the same dispatcher.

- [ ] **Step 5: Parse and run the focused tests**

```powershell
$tokens=$null; $errors=$null
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path scripts/appctl.ps1), [ref]$tokens, [ref]$errors) | Out-Null
if ($errors.Count) { $errors | Format-List; exit 1 }
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m pytest tests/test_windows_installer.py -q
```

Expected: parser exits 0; both tests pass.

- [ ] **Step 6: Commit diagnostics**

```powershell
git add scripts/appctl.ps1 tests/test_windows_installer.py
git commit -m "feat: add Windows app diagnostics"
```

### Task 3: Owned Background Start and Safe Stop

**Files:**
- Modify: `scripts/appctl.ps1`
- Modify: `tests/test_windows_installer.py`

**Interfaces:**
- Consumes: context/version/environment from Task 2 and `/api/health` returning `{"ok": true, "version": <version>}`.
- Produces: `Read-ServerRecord`, `Get-OwnedProcess`, `Test-AppHealth`, `Start-App`, `Stop-App`; `start [--host H] [--port P] [--no-browser]` and `stop` commands.

- [ ] **Step 1: Add failing process-safety contracts**

Append:

```python
def test_windows_appctl_records_exact_process_identity_before_stop():
    script = read("scripts/appctl.ps1")
    for name in ("Read-ServerRecord", "Get-OwnedProcess", "Test-AppHealth", "Test-PortInUse", "Start-App", "Stop-App"):
        assert f"function {name}" in script
    assert "process_start_time_utc_ticks" in script
    assert "process_executable_path" in script
    assert "app.previous.out.log" in script
    assert "app.previous.err.log" in script
    assert '"/api/health"' in script
    assert "Start-Process" in script
    assert "-WindowStyle Hidden" in script
    assert "-RedirectStandardOutput" in script
    assert "-RedirectStandardError" in script
    assert '"start"' in script
    assert '"stop"' in script
    assert "Stop-Process -Id" in script
```

- [ ] **Step 2: Run the new test and confirm the lifecycle functions are absent**

```powershell
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m pytest tests/test_windows_installer.py::test_windows_appctl_records_exact_process_identity_before_stop -q
```

Expected: FAIL on `function Read-ServerRecord`.

- [ ] **Step 3: Implement runtime-record validation**

Add:

```powershell
function Read-ServerRecord {
    param($Context)
    $path = Join-Path $Context.RunDir "server.json"
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { return $null }
    try { return Get-Content -LiteralPath $path -Raw | ConvertFrom-Json }
    catch { throw "The runtime record is malformed: $path" }
}

function Get-OwnedProcess {
    param($Record)
    if (-not $Record) { return $null }
    $process = Get-Process -Id ([int]$Record.pid) -ErrorAction SilentlyContinue
    if (-not $process) { return $null }
    try {
        $ticks = $process.StartTime.ToUniversalTime().Ticks
        $path = $process.Path
    } catch {
        return $null
    }
    if ($ticks -ne [int64]$Record.process_start_time_utc_ticks) { return $null }
    if (-not [string]::Equals($path, [string]$Record.process_executable_path, [StringComparison]::OrdinalIgnoreCase)) { return $null }
    return $process
}

function Test-AppHealth {
    param([string]$HostName, [int]$Port, [string]$ExpectedVersion)
    try {
        $health = Invoke-RestMethod -Uri ("http://{0}:{1}/api/health" -f $HostName, $Port) -TimeoutSec 2
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
```

A malformed record must be reported as stale by status/doctor. Remove the record only when no process exists at the recorded PID; retain it when a PID exists but identity differs so the user can inspect the conflict.

- [ ] **Step 4: Implement background start and log rotation**

`Start-App` must parse only `--host`, `--port`, and `--no-browser`. Validate port as integer 1-65535. Then:

```powershell
$settings = Read-AppEnvironment -Context $Context
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
$record = [ordered]@{
    pid = $process.Id
    process_start_time_utc = $process.StartTime.ToUniversalTime().ToString("o")
    process_start_time_utc_ticks = $process.StartTime.ToUniversalTime().Ticks
    process_executable_path = $process.Path
    version = $version.Version
    app_root = $version.Root
    host = $hostName
    port = $port
    stdout_log = $outLog
    stderr_log = $errLog
    created_at = [DateTime]::UtcNow.ToString("o")
}
$record | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Context.RunDir "server.json") -Encoding UTF8
```

Poll every 250ms for up to 30 seconds. If health succeeds, print the URL and open it with `Start-Process $url` unless no-browser. If the process exits or timeout occurs, terminate only through `Get-OwnedProcess`, retain logs, and exit nonzero.

Before launching, if an owned healthy process already exists, report/open it. Use `Test-PortInUse` before launch; when the port is occupied without a matching owned healthy record, fail with `Port <port> is already in use by a process not managed by this install. Try image-prompt-library start --port <next-port>.` Never kill it. For health polling, probe `127.0.0.1` when bind host is `0.0.0.0` or `::`.

- [ ] **Step 5: Implement safe stop and expose process state**

`Stop-App` obtains the record and calls `Get-OwnedProcess`. When owned, call `Stop-Process -Id $process.Id`, wait up to 10 seconds, and remove `server.json` only after exit. When the PID is absent, remove the stale record and report stopped. When PID exists but identity differs, exit nonzero without calling `Stop-Process`.

Update `Get-AppStatusData`, `Show-Status`, and `Show-Doctor` to expose `running`, `stopped`, `unhealthy`, or `stale runtime record` using the same identity and health functions.

Extend dispatch/usage:

```powershell
"start" { Start-App -Context $context -Arguments $rest }
"stop" { Stop-App -Context $context }
```

- [ ] **Step 6: Parse and run focused tests**

```powershell
$tokens=$null; $errors=$null
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path scripts/appctl.ps1), [ref]$tokens, [ref]$errors) | Out-Null
if ($errors.Count) { $errors | Format-List; exit 1 }
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m pytest tests/test_windows_installer.py -q
```

Expected: parser exits 0; all Windows contract tests pass.

- [ ] **Step 7: Commit lifecycle controls**

```powershell
git add scripts/appctl.ps1 tests/test_windows_installer.py
git commit -m "feat: manage Windows app process safely"
```

### Task 4: Native Release Installer, Verification, Pointers, and Shim

**Files:**
- Create: `scripts/install.ps1`
- Modify: `tests/test_windows_installer.py`

**Interfaces:**
- Consumes: GitHub Releases or an explicit local/HTTP `-ReleaseBaseUrl`; release manifest/checksum/tar.gz; `scripts/setup-runtime.ps1`; `scripts/appctl.ps1`.
- Produces: `install.ps1 [-Version <tag>] [-Prefix <path>] [-LibraryPath <path>] [-ReleaseBaseUrl <url-or-path>] [-NoStart] [-SkipPath] [-NoBrowser]`; verified version directory, atomic pointer files, `.env`, stable shim, optional initial launch.

- [ ] **Step 1: Add failing installer and safety contracts**

Append:

```python
def test_windows_installer_requires_python_and_a_capable_verified_release():
    path = ROOT / "scripts" / "install.ps1"
    assert path.is_file()
    script = path.read_text(encoding="utf-8")
    for name in (
        "Find-SupportedPython",
        "Invoke-Download",
        "Resolve-Release",
        "Read-CompatibleManifest",
        "Confirm-ArtifactChecksum",
        "Expand-SafeTar",
        "Write-VersionPointer",
        "Write-CommandShim",
        "Add-UserPathEntry",
    ):
        assert f"function {name}" in script
    assert "windows-powershell-v1" in script
    assert "Get-FileHash" in script
    assert "process_start_time_utc_ticks" not in script
    assert "tarfile" in script
    assert "member.issym()" in script
    assert "member.islnk()" in script
    assert "https://www.python.org/downloads/windows/" in script
    assert "current-version" in script
    assert "previous-version" in script
    assert "image-prompt-library.cmd" in script
    assert "image-prompt-library.ps1" in script
    assert not re.search(r"(?i)winget\s+install", script)
    assert "New-ScheduledTask" not in script
    assert "Start-Service" not in script
    assert "Set-ExecutionPolicy" not in script
    assert "-Verb RunAs" not in script
    assert '"Machine"' not in script
    assert '"User"' in script


def test_windows_installer_rejects_overlapping_app_and_library_paths():
    script = read("scripts/install.ps1")
    assert "Assert-DisjointPaths" in script
    assert "The app prefix and private library must not contain each other." in script
```

The negative `process_start_time_utc_ticks` assertion keeps process ownership in `appctl.ps1`; remove it only if the installer later has a demonstrated need to inspect runtime records directly. Transactional orchestration in Task 5 should call the controller instead.

- [ ] **Step 2: Run the tests and confirm the installer is absent**

```powershell
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m pytest tests/test_windows_installer.py::test_windows_installer_requires_python_and_a_capable_verified_release tests/test_windows_installer.py::test_windows_installer_rejects_overlapping_app_and_library_paths -q
```

Expected: both tests fail at `assert path.is_file()` or missing functions.

- [ ] **Step 3: Add parameters, top-level error handling, and Python discovery**

Create `scripts/install.ps1`:

```powershell
[CmdletBinding()]
param(
    [string]$Version = "latest",
    [string]$Prefix = (Join-Path $env:LOCALAPPDATA "ImagePromptLibrary"),
    [string]$LibraryPath = (Join-Path $env:USERPROFILE "ImagePromptLibrary"),
    [string]$ReleaseBaseUrl = "",
    [string]$PythonExe = "",
    [string[]]$PythonPrefixArgs = @(),
    [switch]$NoStart,
    [switch]$SkipPath,
    [switch]$NoBrowser
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Repo = "EddieTYP/image-prompt-library"
$Capability = "windows-powershell-v1"
$RunningFromFile = [bool]$MyInvocation.MyCommand.Path

function Fail-Friendly {
    param([string]$Message)
    [Console]::Error.WriteLine("ERROR: $Message")
    $global:LASTEXITCODE = 1
    if ($RunningFromFile) { exit 1 }
}
```

Implement `Find-SupportedPython` with the same candidate order and version probe as Task 1. When explicit `-PythonExe` was supplied, validate only that candidate and fail instead of falling back. Return `{ Exe, PrefixArgs }`. Do not call another installer or package manager. The explicit override exists for deterministic advanced/CI use and does not appear in the normal quick start.

Add:

```powershell
function Assert-DisjointPaths {
    param([string]$AppPrefix, [string]$PrivateLibrary)
    $app = [IO.Path]::GetFullPath($AppPrefix).TrimEnd('\')
    $library = [IO.Path]::GetFullPath($PrivateLibrary).TrimEnd('\')
    $comparison = [StringComparison]::OrdinalIgnoreCase
    if ($app.Equals($library, $comparison) -or
        $app.StartsWith($library + "\", $comparison) -or
        $library.StartsWith($app + "\", $comparison)) {
        throw "The app prefix and private library must not contain each other."
    }
}
```

- [ ] **Step 4: Implement bounded downloads and release resolution**

`Invoke-Download -Uri <uri-or-path> -Destination <path>` creates the destination parent. For an existing literal local path, use `Copy-Item -LiteralPath`; for a `file:` URI, copy its decoded local path. For HTTP(S), attempt `Invoke-WebRequest -UseBasicParsing -OutFile` up to three times, sleep 1 then 2 seconds, and rethrow the third failure.

`Resolve-Release` returns:

```powershell
[pscustomobject]@{
    Version = $tag
    BaseUrl = $baseUrl
    Artifact = "image-prompt-library-$tag.tar.gz"
    Checksum = "image-prompt-library-$tag.tar.gz.sha256"
    Manifest = "image-prompt-library-$tag.manifest.json"
}
```

For explicit `-ReleaseBaseUrl`, require an explicit non-`latest` version and form local literal paths for a directory or URLs for HTTP/file URI. For GitHub explicit version, read `/repos/$Repo/releases/tags/<escaped-tag>`. For default latest, read `/repos/$Repo/releases?per_page=20`, skip draft/prerelease entries, require all three asset names, download/parse each candidate manifest, and select the first whose capabilities contain `windows-powershell-v1`.

Use asset `browser_download_url` values returned by the API rather than reconstructing URLs during API-backed resolution. If no candidate qualifies, throw `No published stable release currently supports native Windows PowerShell installation.`

- [ ] **Step 5: Implement manifest/checksum validation and safe tar extraction**

`Read-CompatibleManifest` must require:

```powershell
$manifest.name -eq "image-prompt-library"
$manifest.version -eq $Release.Version
$manifest.artifact -eq $Release.Artifact
@($manifest.capabilities) -contains $Capability
$manifest.sha256 -match '^[0-9a-fA-F]{64}$'
```

`Confirm-ArtifactChecksum` parses exactly one leading 64-hex checksum from the separate file, compares it case-insensitively with manifest SHA, then compares both with:

```powershell
(Get-FileHash -LiteralPath $ArtifactPath -Algorithm SHA256).Hash
```

`Expand-SafeTar` invokes the discovered Python with a UTF-8 temporary extractor script containing:

```python
from pathlib import Path
import sys, tarfile

archive_path = Path(sys.argv[1])
destination = Path(sys.argv[2]).resolve()
destination.mkdir(parents=True, exist_ok=True)
with tarfile.open(archive_path, "r:gz") as archive:
    members = archive.getmembers()
    for member in members:
        member_path = Path(member.name)
        if member_path.is_absolute() or ".." in member_path.parts:
            raise SystemExit(f"Refusing unsafe archive member: {member.name}")
        if member.issym() or member.islnk() or member.isdev():
            raise SystemExit(f"Refusing unsupported archive member: {member.name}")
        target = (destination / member_path).resolve()
        try:
            target.relative_to(destination)
        except ValueError as exc:
            raise SystemExit(f"Refusing unsafe archive member: {member.name}") from exc
    archive.extractall(destination, members=members)
```

Delete that one temporary extractor file in `finally`. After extraction require literal files: `VERSION`, `pyproject.toml`, `backend/main.py`, `frontend/dist/index.html`, and all four PowerShell scripts.

- [ ] **Step 6: Implement version preparation and atomic pointers**

Use:

```powershell
function Write-VersionPointer {
    param([string]$Path, [AllowEmptyString()][string]$Value)
    if (-not $Value) {
        if (Test-Path -LiteralPath $Path) { Remove-Item -LiteralPath $Path -Force }
        return
    }
    $temporary = "$Path.tmp"
    Set-Content -LiteralPath $temporary -Value $Value -Encoding ASCII
    Move-Item -LiteralPath $temporary -Destination $Path -Force
}
```

Implement `Invoke-Install` with this preparation order:

1. normalize/disjoint-check prefix and library;
2. find Python before creating prefix/download directories;
3. resolve release;
4. download manifest/artifact/checksum under `app\downloads\<version>`;
5. verify checksums;
6. extract application code under one generated temporary directory beneath `app\versions` and validate required members;
7. if the final non-current target exists, move it to the exact sibling `<version>.backup` after first removing only a stale literal backup target;
8. move extracted application code to the final `app\versions\<version>` path;
9. invoke final-path `setup-runtime.ps1 -AppRoot <final-target> -PythonExe <exe> -PythonPrefixArgs <args>` so the venv is created only at its permanent path;
10. on setup success, remove the exact backup target; on setup failure, remove the exact failed final target, restore the backup when present, and leave pointers/running app unchanged.

When the selected version is already current, do not delete or reinstall it; refresh shim/PATH and start/open it if requested. Never move a populated `.venv` directory.

- [ ] **Step 7: Create `.env`, stable shim, and user PATH entry**

Create `.env` only when absent using actual normalized values, not `%VARIABLE%` tokens. Use incoming `BACKEND_HOST` and `BACKEND_PORT` when set; otherwise write `127.0.0.1` and `8000`. Write ASCII lines for library, host, port, and backup path.

`Write-CommandShim` creates `bin\image-prompt-library.ps1` that derives its prefix from its own location, reads `app\current-version`, validates the version token, and invokes `app\versions\<version>\scripts\appctl.ps1 @CommandArgs`, preserving `$LASTEXITCODE`. Create `image-prompt-library.cmd` as:

```bat
@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0image-prompt-library.ps1" %*
exit /b %ERRORLEVEL%
```

`Add-UserPathEntry` splits the user PATH on `;`, trims trailing separators for comparison, adds only an absent case-insensitive exact bin path, persists with `[Environment]::SetEnvironmentVariable(..., "User")`, and adds it to the current `$env:PATH` only when absent.

For a fresh install, write `previous-version` empty and switch `current-version` only after runtime setup and shim creation. If `-NoStart` is absent, call the target `appctl.ps1 start`, passing `--no-browser` only when `-NoBrowser` is set.

After every helper and `Invoke-Install` definition, make this the final executable block in `install.ps1` (PowerShell 5.1 does not hoist later function definitions):

```powershell
try {
    Invoke-Install
} catch {
    Fail-Friendly $_.Exception.Message
    return
}
```

- [ ] **Step 8: Parse and run focused contract tests**

```powershell
$tokens=$null; $errors=$null
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path scripts/install.ps1), [ref]$tokens, [ref]$errors) | Out-Null
if ($errors.Count) { $errors | Format-List; exit 1 }
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m pytest tests/test_windows_installer.py -q
```

Expected: parser exits 0; all contract tests pass.

- [ ] **Step 9: Commit the fresh-install slice**

```powershell
git add scripts/install.ps1 tests/test_windows_installer.py
git commit -m "feat: add native Windows release installer"
```

### Task 5: Transactional Update, Failed-Start Recovery, and Rollback

**Files:**
- Modify: `scripts/install.ps1`
- Modify: `scripts/appctl.ps1`
- Modify: `tests/test_windows_installer.py`

**Interfaces:**
- Consumes: verified prepared version from Task 4 and owned process functions from Task 3.
- Produces: `update [--version V]`, transactional pointer switch/restart/automatic recovery in installer, and `rollback` in controller.

- [ ] **Step 1: Add failing transaction contracts**

Append:

```python
def test_windows_update_and_rollback_are_transactional():
    installer = read("scripts/install.ps1")
    appctl = read("scripts/appctl.ps1")
    assert "Get-CurrentPointerState" in installer
    assert "Restore-PointerState" in installer
    assert "Invoke-Controller" in installer
    assert "Automatic recovery restored" in installer
    assert "--no-browser" in installer
    assert "function Get-OwnedRuntimeState" in appctl
    assert '"internal-owned-runtime"' in appctl
    assert "function Switch-VersionTransactional" in appctl
    assert '"update"' in appctl
    assert '"rollback"' in appctl
    assert "No previous version is available for rollback." in appctl
```

- [ ] **Step 2: Run the test and confirm transaction helpers are absent**

```powershell
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m pytest tests/test_windows_installer.py::test_windows_update_and_rollback_are_transactional -q
```

Expected: FAIL on `Get-CurrentPointerState`.

- [ ] **Step 3: Make installer switching transactional**

Add:

```powershell
function Get-CurrentPointerState {
    param([string]$AppDir)
    $currentPath = Join-Path $AppDir "current-version"
    $previousPath = Join-Path $AppDir "previous-version"
    [pscustomobject]@{
        Current = if (Test-Path -LiteralPath $currentPath) { (Get-Content -LiteralPath $currentPath -Raw).Trim() } else { "" }
        Previous = if (Test-Path -LiteralPath $previousPath) { (Get-Content -LiteralPath $previousPath -Raw).Trim() } else { "" }
    }
}

function Restore-PointerState {
    param([string]$AppDir, $State)
    Write-VersionPointer -Path (Join-Path $AppDir "current-version") -Value $State.Current
    Write-VersionPointer -Path (Join-Path $AppDir "previous-version") -Value $State.Previous
}

function Invoke-Controller {
    param([string]$VersionRoot, [string[]]$Arguments)
    $controller = Join-Path $VersionRoot "scripts\appctl.ps1"
    $processArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $controller) + $Arguments
    $output = & powershell.exe @processArgs 2>&1
    return [pscustomobject]@{ ExitCode = $LASTEXITCODE; Output = @($output) }
}
```

After target preparation, read old pointer state. If old current exists, invoke its private `internal-owned-runtime` command through `Invoke-Controller` and require `ExitCode -eq 0`. That command is omitted from usage and prints one compact JSON object: `{"running": true|false, "host": <recorded-host-or-null>, "port": <recorded-port-or-null>}` from `Get-OwnedRuntimeState`; parse the joined `Output` with `ConvertFrom-Json` and do not infer running state only from the port.

If running, stop through the old controller and require a zero exit before changing pointers. Write old current to previous and target to current. If old was running, run target `start --host <recorded-host> --port <recorded-port> --no-browser`. Write successful controller output back to the user. On a nonzero target-start result:

1. call target `stop` (safe when no owned process remains);
2. restore both pointer values;
3. call old `start --host <recorded-host> --port <recorded-port> --no-browser` and capture its result;
4. print `Automatic recovery restored <old-version>.`;
5. if old restart succeeds, throw an update-failed message naming current and previous log paths; if old restart also fails, throw a combined message that pointers were restored but manual recovery is required and include both controller outputs/log paths.

If the old app was stopped, switch pointers without starting. A fresh install with no old current keeps previous empty and follows Task 4 initial-start behavior.

- [ ] **Step 4: Add controller update dispatch**

`Update-App` manually parses only optional `--version <tag>`, defaults to `latest`, and invokes the current version's `scripts\install.ps1` with the current prefix and library. Forward `IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL` as `-ReleaseBaseUrl` when set so local smoke tests use the same path.

Dispatch:

```powershell
"update" { Update-App -Context $context -Arguments $rest }
```

Add this private runtime-state function and dispatcher case; do not include the case in public usage:

```powershell
function Get-OwnedRuntimeState {
    param($Context)
    $record = Read-ServerRecord -Context $Context
    if (-not $record) {
        return [pscustomobject]@{ running = $false; host = $null; port = $null }
    }
    $process = Get-OwnedProcess -Record $record
    if (-not $process) {
        if (Get-Process -Id ([int]$record.pid) -ErrorAction SilentlyContinue) {
            throw "The recorded PID belongs to a different process; refusing lifecycle changes."
        }
        return [pscustomobject]@{ running = $false; host = $null; port = $null }
    }
    [pscustomobject]@{ running = $true; host = [string]$record.host; port = [int]$record.port }
}

"internal-owned-runtime" { Get-OwnedRuntimeState -Context $context | ConvertTo-Json -Compress }
```

- [ ] **Step 5: Implement explicit rollback with the same restart rule**

Add `Write-VersionPointerAtomic` to `appctl.ps1` with the same exact behavior as installer `Write-VersionPointer` and:

```powershell
function Switch-VersionTransactional {
    param($Context, [string]$TargetVersion)
    $current = Get-CurrentVersion $Context
    $targetRoot = Join-Path $Context.AppDir ("versions\" + $TargetVersion)
    if (-not (Test-Path -LiteralPath $targetRoot -PathType Container)) { throw "Previous version directory is missing: $targetRoot" }
    $runtime = Get-OwnedRuntimeState -Context $Context
    if ($runtime.running) { Stop-App -Context $Context }
    Write-VersionPointerAtomic -Path (Join-Path $Context.AppDir "current-version") -Value $TargetVersion
    Write-VersionPointerAtomic -Path (Join-Path $Context.AppDir "previous-version") -Value $current.Version
    if ($runtime.running) {
        $restartArgs = @("--host", $runtime.host, "--port", [string]$runtime.port, "--no-browser")
        try { Start-App -Context $Context -Arguments $restartArgs }
        catch {
            Write-VersionPointerAtomic -Path (Join-Path $Context.AppDir "current-version") -Value $current.Version
            Write-VersionPointerAtomic -Path (Join-Path $Context.AppDir "previous-version") -Value $TargetVersion
            Start-App -Context $Context -Arguments $restartArgs
            throw "Rollback target failed health checks; restored $($current.Version)."
        }
    }
}
```

`Rollback-App` reads/validates `previous-version`, then calls this helper. If missing/empty, throw `No previous version is available for rollback.`

Dispatch:

```powershell
"rollback" { Rollback-App -Context $context }
```

- [ ] **Step 6: Parse scripts and run focused contracts**

```powershell
foreach($path in 'scripts/install.ps1','scripts/appctl.ps1') {
  $tokens=$null; $errors=$null
  [System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $path), [ref]$tokens, [ref]$errors) | Out-Null
  if ($errors.Count) { $errors | Format-List; exit 1 }
}
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m pytest tests/test_windows_installer.py -q
```

Expected: parsers exit 0; all contracts pass.

- [ ] **Step 7: Commit version switching**

```powershell
git add scripts/install.ps1 scripts/appctl.ps1 tests/test_windows_installer.py
git commit -m "feat: make Windows updates recoverable"
```

### Task 6: Native Sample-Data Installation

**Files:**
- Create: `scripts/install-sample-data.ps1`
- Modify: `scripts/appctl.ps1`
- Modify: `tests/test_windows_installer.py`

**Interfaces:**
- Consumes: language/package arguments, version-local Python, packaged manifests, published sample ZIPs, configured private library.
- Produces: verified safe staging extraction and `backend.services.import_sample_bundle` invocation; `sample-data` controller command.

- [ ] **Step 1: Add failing sample-data contract**

Append:

```python
def test_windows_sample_data_uses_pinned_hash_and_safe_zip_extraction():
    path = ROOT / "scripts" / "install-sample-data.ps1"
    assert path.is_file()
    script = path.read_text(encoding="utf-8")
    assert "gpt-image-2-skill" in script
    assert "awesome-gpt-image-2" in script
    assert "8a458f6c8c96079f40fbc46c689e7de0bd2eb464ee7f800f94f3ca60131d5035" in script
    assert "153714b7611524d7b98b4b0452baa86c8d05053477bb670b731953e8d26a8c9c" in script
    assert "Get-FileHash" in script
    assert "zipfile.ZipFile" in script
    assert '".." in member_path.parts' in script
    assert "backend.services.import_sample_bundle" in script
    assert '"sample-data"' in read("scripts/appctl.ps1")
```

- [ ] **Step 2: Run the test and confirm the native sample script is absent**

```powershell
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m pytest tests/test_windows_installer.py::test_windows_sample_data_uses_pinned_hash_and_safe_zip_extraction -q
```

Expected: FAIL at `assert path.is_file()`.

- [ ] **Step 3: Implement package/language validation and checksum selection**

Create `scripts/install-sample-data.ps1` with parameters `Language`, `Package = "gpt-image-2-skill"`, `AppRoot`, `LibraryPath`, and optional environment-backed local overrides matching existing Bash names. Accept only `en`, `zh_hans`, `zh_hant`; accept only both known packages; require `zh_hant` for `awesome-gpt-image-2`.

Use the exact release tags, asset names, and SHA256 values from `install-sample-data.sh`. Download to `<app-root>\.local-work\sample-data-installer\<package>` with bounded three-attempt retry. Verify with `Get-FileHash` before extraction.

- [ ] **Step 4: Implement safe ZIP extraction and import**

Invoke version-local Python with this extraction guard:

```python
from pathlib import Path
import sys, zipfile

archive_path = Path(sys.argv[1])
destination = Path(sys.argv[2]).resolve()
destination.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(archive_path) as archive:
    for member in archive.infolist():
        member_path = Path(member.filename)
        if member_path.is_absolute() or ".." in member_path.parts:
            raise SystemExit(f"Refusing unsafe ZIP member: {member.filename}")
        target = (destination / member_path).resolve()
        try:
            target.relative_to(destination)
        except ValueError as exc:
            raise SystemExit(f"Refusing unsafe ZIP member: {member.filename}") from exc
    archive.extractall(destination)
```

Then run:

```powershell
& $venvPython -m backend.services.import_sample_bundle --manifest $manifestPath --assets $assetDir --library $LibraryPath
```

Parse returned JSON with `ConvertFrom-Json` and print imported item/image counts plus nonempty log text.

- [ ] **Step 5: Wire controller dispatch**

`Install-SampleData` requires language, accepts optional package, rejects extra args, and invokes the current version's `scripts\install-sample-data.ps1` with current app root and configured library path. Preserve nonzero exit code.

Dispatch:

```powershell
"sample-data" { Install-SampleData -Context $context -Arguments $rest }
```

- [ ] **Step 6: Parse and run focused contracts**

```powershell
foreach($path in 'scripts/install-sample-data.ps1','scripts/appctl.ps1') {
  $tokens=$null; $errors=$null
  [System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $path), [ref]$tokens, [ref]$errors) | Out-Null
  if ($errors.Count) { $errors | Format-List; exit 1 }
}
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m pytest tests/test_windows_installer.py -q
```

Expected: parsers exit 0; all contracts pass.

- [ ] **Step 7: Commit sample-data parity**

```powershell
git add scripts/install-sample-data.ps1 scripts/appctl.ps1 tests/test_windows_installer.py
git commit -m "feat: add Windows sample data import"
```

### Task 7: Safe Native Uninstall

**Files:**
- Modify: `scripts/appctl.ps1`
- Modify: `tests/test_windows_installer.py`

**Interfaces:**
- Consumes: configured exact prefix/library, process ownership record, user PATH.
- Produces: `uninstall [--delete-library] [--yes]`; owned-process stop, exact PATH removal, exact validated prefix removal, optional confirmed private-data removal.

- [ ] **Step 1: Add failing uninstall safety contract**

Append:

```python
def test_windows_uninstall_preserves_library_and_guards_exact_paths():
    script = read("scripts/appctl.ps1")
    assert "Assert-SafeDeleteTarget" in script
    assert "Remove-UserPathEntry" in script
    assert "Private library preserved at" in script
    assert '"--delete-library"' in script
    assert '"--yes"' in script
    assert '"uninstall"' in script
    assert "GetPathRoot" in script
    assert "Remove-Item -LiteralPath" in script
    assert "Remove-Item -Path" not in script
    assert "-Filter" not in script
```

- [ ] **Step 2: Run the test and confirm uninstall helpers are absent**

```powershell
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m pytest tests/test_windows_installer.py::test_windows_uninstall_preserves_library_and_guards_exact_paths -q
```

Expected: FAIL on `Assert-SafeDeleteTarget`.

- [ ] **Step 3: Implement exact target guards**

Add:

```powershell
function Assert-SafeDeleteTarget {
    param([string]$Target, [string]$Kind, [string]$OtherProtectedPath)
    $full = [IO.Path]::GetFullPath($Target).TrimEnd('\')
    $root = [IO.Path]::GetPathRoot($full).TrimEnd('\')
    $home = [IO.Path]::GetFullPath($env:USERPROFILE).TrimEnd('\')
    $other = [IO.Path]::GetFullPath($OtherProtectedPath).TrimEnd('\')
    if (-not $full -or $full.Equals($root, [StringComparison]::OrdinalIgnoreCase)) { throw "Refusing to delete a drive root as $Kind." }
    if ($full.Equals($home, [StringComparison]::OrdinalIgnoreCase)) { throw "Refusing to delete the user profile as $Kind." }
    if ($full.Equals($other, [StringComparison]::OrdinalIgnoreCase)) { throw "Refusing overlapping app and library delete targets." }
    return $full
}
```

Also reject the app prefix when it is the parent of the library and reject the library when it is the parent of the prefix, using the same case-insensitive boundary-aware `StartsWith($path + "\")` rule as Task 4.

- [ ] **Step 4: Remove only the exact user PATH entry**

`Remove-UserPathEntry` reads user PATH, removes only entries whose normalized full path equals `Context.BinDir` case-insensitively, preserves order/other entries, writes the joined PATH back at User scope, and updates current `$env:PATH` similarly.

- [ ] **Step 5: Implement uninstall flow**

Parse only `--delete-library` and `--yes`. Stop through `Stop-App`; fail if a conflicting live PID prevents ownership proof. Validate prefix and library before any deletion.

When deleting private data without `--yes`, require exact response `DELETE` from `Read-Host`. Print the preserved library path before removing the app prefix. Set current location to `$env:TEMP`, remove only:

```powershell
Remove-Item -LiteralPath $validatedPrefix -Recurse -Force
```

If explicit library deletion was confirmed, remove only the separately validated library literal target. Never enumerate parent directories or use wildcards.

Dispatch:

```powershell
"uninstall" { Uninstall-App -Context $context -Arguments $rest }
```

- [ ] **Step 6: Parse and run all Windows contracts**

```powershell
$tokens=$null; $errors=$null
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path scripts/appctl.ps1), [ref]$tokens, [ref]$errors) | Out-Null
if ($errors.Count) { $errors | Format-List; exit 1 }
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m pytest tests/test_windows_installer.py -q
```

Expected: parser exits 0; all tests pass.

- [ ] **Step 7: Commit uninstall safety**

```powershell
git add scripts/appctl.ps1 tests/test_windows_installer.py
git commit -m "feat: add safe Windows uninstall"
```

### Task 8: Release Package Capability

**Files:**
- Modify: `scripts/package-release.sh`
- Modify: `tests/test_installer_release.py`
- Modify: `tests/test_windows_installer.py`

**Interfaces:**
- Consumes: all four completed PowerShell scripts.
- Produces: release tar.gz containing the scripts and schema-v1 manifest with `capabilities: ["windows-powershell-v1"]`; existing Bash assets remain unchanged.

- [ ] **Step 1: Add failing package-source contract**

Append to `tests/test_windows_installer.py`:

```python
def test_release_packager_includes_windows_scripts_and_capability():
    script = read("scripts/package-release.sh")
    for path in (
        "scripts/appctl.ps1",
        "scripts/install.ps1",
        "scripts/install-sample-data.ps1",
        "scripts/setup-runtime.ps1",
    ):
        assert path in script
    assert '"capabilities": ["windows-powershell-v1"]' in script


def test_windows_powershell_sources_are_ascii():
    for path in (
        "scripts/appctl.ps1",
        "scripts/install.ps1",
        "scripts/install-sample-data.ps1",
        "scripts/setup-runtime.ps1",
    ):
        (ROOT / path).read_bytes().decode("ascii")
```

Extend `test_package_release_creates_manifest_and_excludes_private_runtime_data` in `tests/test_installer_release.py` after loading its manifest/listing:

```python
assert manifest["capabilities"] == ["windows-powershell-v1"]
for member in (
    "scripts/appctl.ps1",
    "scripts/install.ps1",
    "scripts/install-sample-data.ps1",
    "scripts/setup-runtime.ps1",
):
    assert member in listing
```

- [ ] **Step 2: Run the source contract and confirm the package script lacks the paths/capability**

```powershell
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m pytest tests/test_windows_installer.py::test_release_packager_includes_windows_scripts_and_capability -q
```

Expected: FAIL on the first PowerShell script path.

- [ ] **Step 3: Include the completed PowerShell scripts**

Add these paths next to their Bash counterparts in `scripts/package-release.sh`:

```bash
  scripts/appctl.ps1 \
  scripts/install.ps1 \
  scripts/install-sample-data.ps1 \
  scripts/setup-runtime.ps1 \
```

Leave PowerShell files at normal 0644 artifact permissions; only `.sh` scripts need executable mode.

- [ ] **Step 4: Emit the additive manifest capability**

Add to the embedded Python manifest literal without changing `schema_version`:

```python
    "capabilities": ["windows-powershell-v1"],
```

Do not change artifact names or remove existing fields consumed by Bash installs.

- [ ] **Step 5: Run focused source and real-package tests**

```powershell
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m pytest tests/test_windows_installer.py::test_release_packager_includes_windows_scripts_and_capability tests/test_installer_release.py::test_package_release_creates_manifest_and_excludes_private_runtime_data tests/test_installer_release.py::test_installer_and_runtime_scripts_define_versioned_install_contract -q
```

Expected: all selected tests pass and the real tar listing includes all four scripts.

- [ ] **Step 6: Commit the release contract**

```powershell
git add scripts/package-release.sh tests/test_installer_release.py tests/test_windows_installer.py
git commit -m "build: package native Windows support"
```

### Task 9: Native Windows End-to-End Smoke and CI

**Files:**
- Create: `tests/windows-installer-smoke.ps1`
- Modify: `.github/workflows/ci.yml`
- Modify: `tests/test_windows_installer.py`

**Interfaces:**
- Consumes: local release package contract, all native scripts, built frontend, Git Bash only for release packaging.
- Produces: one dependency-free PowerShell smoke command and a focused `windows-installer` Actions job.

- [ ] **Step 1: Add failing workflow/smoke contracts**

Append:

```python
def test_ci_runs_native_windows_installer_smoke():
    smoke_path = ROOT / "tests" / "windows-installer-smoke.ps1"
    assert smoke_path.is_file()
    smoke = smoke_path.read_text(encoding="utf-8")
    workflow = read(".github/workflows/ci.yml")
    assert "v0.8.0-test-a" in smoke
    assert "v0.8.0-test-b" in smoke
    assert "v0.8.0-test-broken" in smoke
    assert "missing-python.exe" in smoke
    assert "Automatic recovery restored" in smoke
    assert "process_start_time_utc_ticks" in smoke
    assert "Private library preserved at" in smoke
    assert "windows-installer:" in workflow
    assert "runs-on: windows-latest" in workflow
    assert "tests/windows-installer-smoke.ps1" in workflow
```

- [ ] **Step 2: Run the contract and confirm smoke/workflow are absent**

```powershell
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m pytest tests/test_windows_installer.py::test_ci_runs_native_windows_installer_smoke -q
```

Expected: FAIL at `assert smoke_path.is_file()`.

- [ ] **Step 3: Create a plain PowerShell assertion harness**

Start `tests/windows-installer-smoke.ps1` with:

```powershell
[CmdletBinding()]
param([switch]$KeepWorkRoot)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$workRoot = Join-Path ([IO.Path]::GetTempPath()) ("image-prompt-library-windows-smoke-" + [Guid]::NewGuid().ToString("N"))
$prefix = Join-Path $workRoot "app prefix"
$library = Join-Path $workRoot "private library"
$releaseBase = Join-Path $workRoot "releases"
$port = 18765
$originalUserPath = [Environment]::GetEnvironmentVariable("Path", "User")
$originalProcessPath = $env:PATH

function Assert-True { param([bool]$Condition, [string]$Message); if (-not $Condition) { throw $Message } }
function Assert-Equal { param($Expected, $Actual, [string]$Message); if ($Expected -ne $Actual) { throw "$Message Expected=$Expected Actual=$Actual" } }
function Invoke-Checked {
    param([string]$File, [string[]]$Arguments)
    & $File @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$File failed with exit code $LASTEXITCODE" }
}
function Invoke-IsolatedPowerShell {
    param([string]$Script, [string[]]$Arguments)
    $all = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $Script) + $Arguments
    $output = & powershell.exe @all 2>&1
    return [pscustomobject]@{ ExitCode = $LASTEXITCODE; Output = (@($output) -join [Environment]::NewLine) }
}
```

Always restore both PATH values in `finally`. Stop a proven owned app through the shim when available. Remove only the generated `$workRoot` literal target after asserting it begins with the OS temp root plus a separator. `-KeepWorkRoot` skips only the final work-root removal, not PATH restoration or process stop.

- [ ] **Step 4: Prove missing Python changes nothing**

Invoke source `scripts/install.ps1` in isolated PowerShell with `-PythonExe (Join-Path $workRoot "missing-python.exe")`, a dedicated absent prefix, and an explicit test version/release base. Require nonzero exit, output containing `requires Python 3.10 or newer`, and require the dedicated prefix was never created. This runs before valid release packaging/install.

- [ ] **Step 5: Build two valid local releases and test fresh install/lifecycle**

From `$repo`, run the Bash packager twice with `v0.8.0-test-a` and `v0.8.0-test-b`, copying each version's three assets from `dist-release` into `$releaseBase`.

Before the valid install, copy test-a's three assets to a separate generated release directory, flip the last artifact byte without changing manifest/checksum, and invoke installer with a dedicated prefix. Require nonzero exit containing `checksum`, no `current-version`, and no extracted version directory.

Also create `v0.8.0-test-unsafe.tar.gz` with Python `tarfile` containing one regular member named `../escape.txt`, then write a matching SHA/checksum and capability-bearing manifest. Invoke installer with another dedicated prefix. Require nonzero exit containing `Refusing unsafe archive member`, no current pointer, and no `escape.txt` outside the extraction target.

The unsafe archive helper uses:

```python
import hashlib, io, json, sys, tarfile
from pathlib import Path

base = Path(sys.argv[1])
tag = "v0.8.0-test-unsafe"
artifact = base / f"image-prompt-library-{tag}.tar.gz"
payload = b"must not escape"
with tarfile.open(artifact, "w:gz") as archive:
    member = tarfile.TarInfo("../escape.txt")
    member.size = len(payload)
    archive.addfile(member, io.BytesIO(payload))
sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
(base / f"{artifact.name}.sha256").write_text(f"{sha}  {artifact.name}\n", encoding="ascii")
(base / f"image-prompt-library-{tag}.manifest.json").write_text(json.dumps({
    "name": "image-prompt-library",
    "version": tag,
    "schema_version": 1,
    "artifact": artifact.name,
    "sha256": sha,
    "python": ">=3.10",
    "node_required_for_runtime": False,
    "built_frontend": True,
    "capabilities": ["windows-powershell-v1"],
}), encoding="utf-8")
```

After both negative probes, invoke source `scripts/install.ps1` for test-a with the valid release base, prefix, library, and `-NoStart`.

Assert exact paths for current pointer, version venv Python, all four packaged PowerShell scripts, both shim files, and user PATH membership. Assert `version` is test-a.

Run the shim with `start --host 127.0.0.1 --port 18765 --no-browser`, then assert:

```powershell
$health = Invoke-RestMethod -Uri "http://127.0.0.1:18765/api/health" -TimeoutSec 5
Assert-True ($health.ok -eq $true) "Health did not report ok."
Assert-Equal "v0.8.0-test-a" $health.version "Health version mismatch."
```

Capture `status` and `doctor` output and require `running`, the URL, version, `App`, `Library`, `Database`, `Generation`, and `Updates / Runtime`. Stop and prove the recorded PID no longer exists.

- [ ] **Step 6: Prove stop refuses a reused/conflicting PID**

Start a separate hidden PowerShell sleeper. Write `run\server.json` using its real PID/path but `process_start_time_utc_ticks` plus one. Invoke `stop` through `Invoke-IsolatedPowerShell`; require `ExitCode` is nonzero and require the sleeper remains alive. Stop only the sleeper created by the smoke harness in `finally`, then remove the fake record.

- [ ] **Step 7: Prove native sample-data import and idempotency**

While the app is stopped, create a local fixture exactly as follows, then ZIP the `images` directory with `Compress-Archive`:

```powershell
$fixture = Join-Path $workRoot "sample fixture"
$images = Join-Path $fixture "images"
New-Item -ItemType Directory -Force -Path $images | Out-Null
[IO.File]::WriteAllBytes((Join-Path $images "one.png"), [Convert]::FromBase64String("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="))
$manifest = Join-Path $fixture "manifest.json"
@'
{
  "schema_version": 2,
  "id": "windows-smoke-sample",
  "language": "en",
  "source": {"name": "Windows smoke fixture", "license": "CC0"},
  "collections": [{"id": "visual", "name": "Visual", "names": {"en": "Visual"}}],
  "items": [{
    "id": "windows-smoke-001",
    "title": "Windows smoke image",
    "slug": "windows-smoke-image",
    "collection_id": "visual",
    "image": "images/one.png",
    "source_name": "Windows smoke fixture",
    "source_url": "https://example.test/windows-smoke",
    "license": "CC0",
    "tags": ["smoke"],
    "prompts": [{
      "language": "en",
      "text": "A single red pixel",
      "is_primary": true,
      "is_original": true,
      "provenance": {"kind": "source", "source_language": "en", "derived_from": null, "method": null}
    }]
  }]
}
'@ | Set-Content -LiteralPath $manifest -Encoding ASCII
$zip = Join-Path $fixture "images.zip"
Compress-Archive -LiteralPath (Join-Path $fixture "images") -DestinationPath $zip
$env:SAMPLE_DATA_MANIFEST = $manifest
$env:SAMPLE_DATA_IMAGE_ZIP = $zip
$env:SAMPLE_DATA_IMAGE_ZIP_SHA256 = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
```

Invoke `sample-data en` twice. Require first output reports one item/image, second reports zero new items/images, and `status` reports `Items: 1`. Clear `SAMPLE_DATA_MANIFEST`, `SAMPLE_DATA_IMAGE_ZIP`, and `SAMPLE_DATA_IMAGE_ZIP_SHA256` in `finally`.

Then create a second ZIP with the version-local Python:

```python
import sys, zipfile
with zipfile.ZipFile(sys.argv[1], "w") as archive:
    archive.writestr("../sample-escape.png", b"must not escape")
```

Update the ZIP/checksum overrides, invoke `sample-data en` in isolated PowerShell, require nonzero exit containing `Refusing unsafe ZIP member`, require no escaped file exists, and confirm `status` still reports one item.

- [ ] **Step 8: Prove update/rollback preserve the active host/port**

Start test-a again on port 18765. Set `IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL` to `$releaseBase` and run `update --version v0.8.0-test-b`. Assert current is test-b, previous is test-a, health remains on port 18765, and health version is test-b.

Run `rollback`; assert current test-a, previous test-b, and health remains on port 18765 with version test-a.

- [ ] **Step 9: Create and exercise a health-failing release**

Create `v0.8.0-test-broken` from the test-b artifact in a generated staging directory using Python `tarfile`:

1. safely extract test-b;
2. replace the `VERSION` content with `v0.8.0-test-broken`;
3. replace the exact health code `return {"ok": True, "version": APP_VERSION}` with `return {"ok": False, "version": APP_VERSION}` and require exactly one replacement;
4. create a new tar.gz;
5. calculate SHA256;
6. write a checksum file and schema-v1 manifest with `windows-powershell-v1`.

With test-a running on port 18765, invoke `update --version v0.8.0-test-broken` in isolated PowerShell. Require `ExitCode` is nonzero and `Output` contains `Automatic recovery restored v0.8.0-test-a.` Assert current remains test-a, previous remains test-b, health is restored on port 18765, and `app.previous.err.log` exists for the failed launch.

- [ ] **Step 10: Prove default preservation and explicit private-data deletion**

Create `$library\sentinel.txt`, stop the app, and run `uninstall --yes`. Require output contains `Private library preserved at`, prefix no longer exists, sentinel still exists, and user PATH no longer contains the normalized bin path.

Reinstall valid test-a with `-NoStart`, then run `uninstall --delete-library --yes`. Require both exact prefix and exact private library are gone. Restore original PATH values in `finally` even when any earlier assertion fails.

- [ ] **Step 11: Run the native smoke locally**

Ensure `frontend/dist/index.html` is a local app build, then run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tests/windows-installer-smoke.ps1
```

Expected final line: `Native Windows installer smoke passed.` No app process, temp prefix, or PATH entry remains.

- [ ] **Step 12: Add focused Windows CI job**

Append to `.github/workflows/ci.yml`:

```yaml
  windows-installer:
    runs-on: windows-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v5
      - name: Setup Python
        uses: actions/setup-python@v6
        with:
          python-version: '3.11'
          cache: pip
      - name: Setup Node
        uses: actions/setup-node@v5
        with:
          node-version: 24
          cache: npm
      - name: Install test dependencies
        run: python -m pip install -e '.[dev]'
      - name: Install frontend dependencies
        run: npm install
      - name: Build local app
        run: npm run build
      - name: Run Windows installer contracts
        run: python -m pytest tests/test_windows_installer.py -q
      - name: Run native Windows installer smoke
        shell: powershell
        run: powershell.exe -NoProfile -ExecutionPolicy Bypass -File tests/windows-installer-smoke.ps1
```

Do not run the known-platform-sensitive full pytest suite in this job; the existing Ubuntu job remains the full application gate.

- [ ] **Step 13: Run focused checks and commit CI coverage**

```powershell
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m pytest tests/test_windows_installer.py -q
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tests/windows-installer-smoke.ps1
git diff --check
git add tests/windows-installer-smoke.ps1 tests/test_windows_installer.py .github/workflows/ci.yml
git commit -m "ci: verify native Windows install flow"
```

Expected: contracts and smoke pass; diff check is clean.

### Task 10: Capability-Aware Public Documentation and Roadmap Truth

**Files:**
- Create: `docs/releases/v0.8.0.md`
- Modify: `README.md`
- Modify: `README_zh-TW.md`
- Modify: `README_zh-CN.md`
- Modify: `docs/INSTALLATION.md`
- Modify: `docs/TROUBLESHOOTING.md`
- Modify: `ROADMAP.md`
- Modify: `tests/test_windows_installer.py`
- Modify: `tests/test_public_mvp.py`

**Interfaces:**
- Consumes: final native command behavior and `windows-powershell-v1` release requirement.
- Produces: public instructions that describe Windows support beginning with v0.8.0 without falsely changing the current stable release before it exists.

- [ ] **Step 1: Add failing public-doc contracts**

Append to `tests/test_windows_installer.py`:

```python
def test_public_docs_explain_native_windows_without_installing_python():
    readmes = [read("README.md"), read("README_zh-TW.md"), read("README_zh-CN.md")]
    installation = read("docs/INSTALLATION.md")
    troubleshooting = read("docs/TROUBLESHOOTING.md")
    roadmap = read("ROADMAP.md")
    release = read("docs/releases/v0.8.0.md")
    for document in readmes:
        assert "scripts/install.ps1" in document
        assert "Python 3.10+" in document
        assert "v0.8.0" in document
    assert "The installer does not install Python" in installation
    assert "image-prompt-library stop" in installation
    assert "app.previous.err.log" in troubleshooting
    assert "Native Windows PowerShell scripts or a Docker Compose" not in roadmap
    assert "Add search/sort polish before larger batch workflows" not in roadmap
    assert "Add stronger token refresh locking" not in roadmap
    assert "Generic URL plus X/Threads import" in roadmap
    assert "Native Windows Quick Start" in release
    assert "v0.7.10" in read("README.md")


def test_public_docs_do_not_claim_legacy_release_is_windows_native():
    installation = read("docs/INSTALLATION.md")
    assert "Native Windows support begins with v0.8.0" in installation
    assert "v0.7.10 supports native Windows" not in installation
```

Extend `test_public_install_helper_files_exist_and_document_local_data` in `tests/test_public_mvp.py` to require all four PowerShell scripts exist and installation docs mention `install.ps1`, while retaining every Bash helper assertion.

- [ ] **Step 2: Run the tests and confirm Windows docs/release note are absent**

```powershell
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m pytest tests/test_windows_installer.py::test_public_docs_explain_native_windows_without_installing_python tests/test_windows_installer.py::test_public_docs_do_not_claim_legacy_release_is_windows_native tests/test_public_mvp.py::test_public_install_helper_files_exist_and_document_local_data -q
```

Expected: FAIL on missing `scripts/install.ps1` references or missing release note.

- [ ] **Step 3: Add separate Windows and Unix quick starts**

In all three READMEs:

- keep the current stable release link at `v0.7.10` until Task 12;
- add `Windows (v0.8.0+)` before the existing macOS/Linux/WSL command;
- state Python 3.10+ is required and not installed by the app;
- show `irm https://raw.githubusercontent.com/EddieTYP/image-prompt-library/main/scripts/install.ps1 | iex`;
- explain that successful install starts in the background and opens the browser;
- mention `image-prompt-library stop` and link detailed installation docs;
- retain WSL as an alternative, not the only Windows path.

Use natural Traditional/Simplified Chinese phrasing in localized files while preserving commands and product names exactly.

- [ ] **Step 4: Rewrite native Windows installation reference**

In `docs/INSTALLATION.md`, replace the unsupported-native-Windows paragraph with sections covering:

1. prerequisites and no automatic Python install;
2. short install command;
3. inspect-first download/notepad/execute commands;
4. native layout and private-library separation;
5. background start, stop, status, doctor, and log paths;
6. selected-version install through downloaded script `-Version`;
7. update, rollback, sample-data, and uninstall;
8. WSL alternative;
9. statement `Native Windows support begins with v0.8.0`.

Do not say current `v0.7.10` supports the native path.

- [ ] **Step 5: Add focused troubleshooting**

In `docs/TROUBLESHOOTING.md`, add actionable Windows headings for:

- Python missing/too old and official download URL;
- command not found/new terminal and user PATH;
- port occupied and `start --port`;
- `stale runtime record` and `doctor`;
- startup/health failure with `app.err.log`, `app.out.log`, `app.previous.err.log`, and `app.previous.out.log`;
- update automatic recovery and checking current version/status;
- uninstall preserving private library.

Do not recommend deleting PID files while a matching process exists or killing all Python processes.

- [ ] **Step 6: Make Roadmap current**

Remove completed/stale future claims for search/sort polish, generic cleanup preview/apply, install/onboarding polish, and OAuth refresh locking. Mark native Windows quick start as the v0.8.0 release focus while the branch is unreleased. Keep these genuine follow-ups visible:

- service/update resilience beyond the Windows background controller;
- batch image editing;
- richer generation retry and saved-reference/input-image UX;
- mobile Explore gestures/layout;
- Generic URL plus X/Threads import, then Instagram later;
- optional export/import backup archive UI.

Do not change the local-first/non-SaaS direction or account-management section beyond stale release-status wording.

- [ ] **Step 7: Prepare v0.8.0 release notes**

Create `docs/releases/v0.8.0.md` in English with:

- title `Image Prompt Library v0.8.0 - Native Windows Quick Start`;
- requirements and one-line install command;
- background lifecycle commands;
- verified release/checksum/capability behavior;
- transactional update/recovery and rollback;
- sample-data and safe uninstall;
- statement that Python is never installed automatically;
- macOS/Linux/WSL behavior remains supported;
- local-first data/privacy note;
- verification summary naming Ubuntu full CI, Windows native smoke, and post-release asset QA as release gates.

Do not claim post-release QA has passed before Task 12; describe it as a gate.

- [ ] **Step 8: Run focused docs/contracts and commit**

```powershell
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m pytest tests/test_windows_installer.py tests/test_public_mvp.py::test_public_install_helper_files_exist_and_document_local_data tests/test_public_mvp.py::test_public_docs_explain_first_run_status_and_doctor tests/test_installer_release.py::test_readme_prefers_installer_for_users_and_keeps_source_setup_for_developers -q
git diff --check
git add README.md README_zh-TW.md README_zh-CN.md docs/INSTALLATION.md docs/TROUBLESHOOTING.md ROADMAP.md docs/releases/v0.8.0.md tests/test_windows_installer.py tests/test_public_mvp.py
git commit -m "docs: prepare native Windows quick start"
```

Expected: selected tests pass; current-release line remains v0.7.10; docs identify v0.8.0 as first compatible native Windows release.

### Task 11: Pre-Release Verification, Independent Review, and PR

**Files:**
- Create: `docs/qa/2026-07-10-native-windows-quick-start-qa.md`
- Modify only when review finds a concrete defect: files already listed in Tasks 1-10.

**Interfaces:**
- Consumes: complete implementation branch.
- Produces: fresh local evidence, independent correctness/spec review, pushed branch, ready PR, and green Ubuntu plus Windows CI. No release tag is created in this task.

- [ ] **Step 1: Run PowerShell parser checks for every native script**

```powershell
foreach($path in 'scripts/setup-runtime.ps1','scripts/appctl.ps1','scripts/install.ps1','scripts/install-sample-data.ps1','tests/windows-installer-smoke.ps1') {
  $tokens=$null; $errors=$null
  [System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $path), [ref]$tokens, [ref]$errors) | Out-Null
  if ($errors.Count) { Write-Host $path; $errors | Format-List; exit 1 }
}
```

Expected: no parser errors under Windows PowerShell 5.1.

- [ ] **Step 2: Run focused automated checks once**

```powershell
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m pytest tests/test_windows_installer.py tests/test_installer_release.py tests/test_public_mvp.py -q -p no:cacheprovider
npm run build
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tests/windows-installer-smoke.ps1
git diff --check
```

Expected: selected Python tests pass, one local frontend build passes, native smoke passes, diff check is clean. Do not repeat the full local pytest suite; known unrelated Windows/platform failures remain outside this milestone, and GitHub Ubuntu CI is the authoritative full-suite gate.

- [ ] **Step 3: Perform native browser QA from a temporary local release**

Run the installer against a locally packaged test release with a fresh temporary prefix/library. Set incoming `BACKEND_HOST=127.0.0.1` and a free nondefault `BACKEND_PORT` before invoking the installer. Do not pass `-NoBrowser`; verify the default browser opens only after `/api/health` returns the expected version. Confirm the existing first-run empty-library panel is visible and usable at desktop viewport. No mobile layout QA is required because this milestone changes no frontend code.

Then run status, doctor, stop, and uninstall; confirm no process, temp app prefix, or PATH entry remains and a private-library sentinel remains.

- [ ] **Step 4: Write the QA evidence note**

Create `docs/qa/2026-07-10-native-windows-quick-start-qa.md` using the actual observed commands/results from Steps 1-3. Include:

- Windows and PowerShell versions;
- Python version selected;
- parser result;
- focused pytest count/warnings;
- frontend build result;
- native smoke result including valid update, rollback, failed-update recovery, PID mismatch refusal, and uninstall sentinel;
- browser URL/health version and first-run observation;
- exact statement that Python was not installed or modified;
- known residual risk: unsigned PowerShell bootstrap/SmartScreen policy and external GitHub/PyPI availability;
- statement that post-release real-asset QA remains pending until Task 12.

Redact the user profile name and temporary absolute paths. Do not include OAuth status payloads or private library content.

- [ ] **Step 5: Request independent spec and correctness review**

Invoke `superpowers:requesting-code-review` against the diff from `4a55e2e` (the branch base) through HEAD. The reviewer must check:

- every acceptance criterion in the approved design;
- PowerShell 5.1 compatibility;
- no automatic Python/system dependency install;
- archive traversal/link rejection;
- checksum triple agreement;
- PID reuse protection;
- port conflict behavior;
- host/port-preserving update, failed-start recovery, and rollback;
- PATH and delete-target safety;
- Bash compatibility and accurate public docs;
- Windows smoke assertions actually exercise behavior rather than only string matching.

Address only technically valid findings with the narrowest relevant tests. Re-run only the affected focused check plus the native smoke when runtime behavior changed.

- [ ] **Step 6: Commit QA/review corrections**

```powershell
git add docs/qa/2026-07-10-native-windows-quick-start-qa.md
git add -- scripts/setup-runtime.ps1 scripts/appctl.ps1 scripts/install.ps1 scripts/install-sample-data.ps1 scripts/package-release.sh tests/test_windows_installer.py tests/windows-installer-smoke.ps1 tests/test_installer_release.py tests/test_public_mvp.py .github/workflows/ci.yml README.md README_zh-TW.md README_zh-CN.md docs/INSTALLATION.md docs/TROUBLESHOOTING.md ROADMAP.md docs/releases/v0.8.0.md
git diff --cached --check
git commit -m "test: record native Windows install QA"
```

If review required no code/doc corrections, the commit contains only the QA note. Never stage the unrelated SDD reports or QA server logs.

- [ ] **Step 7: Push and open a ready PR**

```powershell
git push -u origin codex/native-windows-quick-start
gh pr create --base main --head codex/native-windows-quick-start --title "feat: add native Windows quick start" --body-file docs/qa/2026-07-10-native-windows-quick-start-qa.md
```

In the PR description, supplement the QA note with a short summary, public-doc rollout caveat, and statement that release/tagging is not part of the PR.

- [ ] **Step 8: Wait for both required CI jobs**

```powershell
gh pr checks --watch --interval 10
```

Expected: existing Ubuntu `test` and new `windows-installer` both pass. If either fails, use `github:gh-fix-ci`, identify the root cause from logs, obtain approval for any new fix outside the approved plan, push the focused fix, and recheck.

- [ ] **Step 9: Merge and synchronize main after approval**

Use `superpowers:finishing-a-development-branch`. Merge only after the user approves the green reviewed PR. Then:

```powershell
git switch main
git pull --ff-only origin main
```

Preserve unrelated local dirt during branch switch and pull.

### Task 12: Publish v0.8.0, Verify Real Assets, and Sync Stable Docs

**Files:**
- Modify after successful real-asset QA: `README.md`
- Modify after successful real-asset QA: `README_zh-TW.md`
- Modify after successful real-asset QA: `README_zh-CN.md`
- Modify after successful real-asset QA: `ROADMAP.md`
- Modify after successful real-asset QA: `docs/qa/2026-07-10-native-windows-quick-start-qa.md`
- Modify tests only for current stable wording: `tests/test_windows_installer.py`, `tests/test_public_mvp.py`

**Interfaces:**
- Consumes: merged green main and explicit user approval to publish `v0.8.0`.
- Produces: prerelease-gated real-asset evidence, promoted stable GitHub release/assets, and merged public current-release sync.

- [ ] **Step 1: Present the release gate and obtain explicit publish approval**

Report the merge commit, independent review result, local native smoke, browser QA, Ubuntu CI, Windows CI, and remaining unsigned-script/network risks. Ask exactly whether to publish stable tag `v0.8.0`. Do not create or push the tag before approval.

- [ ] **Step 2: Create the final tag as a prerelease on the reviewed merge commit**

After approval:

```powershell
git status --short --branch
$mergeCommit = git rev-parse HEAD
if ($mergeCommit -ne (git rev-parse origin/main)) { throw "Local main is not synchronized with origin/main." }
gh release create v0.8.0 --target $mergeCommit --prerelease --title "v0.8.0 - Native Windows Quick Start" --notes-file docs/releases/v0.8.0.md
```

Creating the prerelease creates the final lightweight tag and triggers the tag release-assets workflow. Unrelated unstaged files are allowed; no tracked implementation change may be uncommitted.

- [ ] **Step 3: Wait for release assets and apply release notes**

```powershell
$runId = ""
for ($attempt = 0; $attempt -lt 6 -and -not $runId; $attempt++) {
    $runId = gh run list --workflow release-assets.yml --branch v0.8.0 --limit 1 --json databaseId --jq '.[0].databaseId'
    if (-not $runId) { Start-Sleep -Seconds 5 }
}
if (-not $runId) {
    gh workflow run release-assets.yml --ref v0.8.0 -f version=v0.8.0
    for ($attempt = 0; $attempt -lt 12 -and -not $runId; $attempt++) {
        $runId = gh run list --workflow release-assets.yml --branch v0.8.0 --limit 1 --json databaseId --jq '.[0].databaseId'
        if (-not $runId) { Start-Sleep -Seconds 5 }
    }
}
if (-not $runId) { throw "Release-assets workflow did not start for v0.8.0." }
gh run watch $runId --exit-status
gh release view v0.8.0 --json tagName,name,isDraft,isPrerelease,url,assets
```

Expected at this stage: non-draft prerelease with tar.gz, `.sha256`, and manifest assets. Download/inspect the manifest and require `windows-powershell-v1` before public install QA.

- [ ] **Step 4: Run public raw-URL install against real GitHub assets**

Download `scripts/install.ps1` from raw `main` to an OS-temp file so test-only prefix/library parameters can be supplied. Use `-Version v0.8.0` because default discovery intentionally skips prereleases. Use fresh OS-temp prefix/library, a nondefault loopback port through the incoming environment, and the public GitHub release path (no local release base). Exercise:

1. explicit prerelease resolution selects `v0.8.0`;
2. artifact/checksum/manifest verification succeeds;
3. background start and `/api/health` report v0.8.0;
4. browser loads the first-run app;
5. version, status, and doctor report expected state;
6. rollback reports no previous version without changing current;
7. stop succeeds;
8. uninstall preserves a sentinel private library and removes PATH entry.

Clean only exact generated temporary targets and restore incoming environment/PATH values in `finally`. If any check fails, leave the GitHub release marked prerelease, record the failure, and stop the rollout.

- [ ] **Step 5: Promote stable and verify default discovery with another fresh install**

After the explicit-version real-asset path passes:

```powershell
gh release edit v0.8.0 --prerelease=false --latest
gh release view v0.8.0 --json isDraft,isPrerelease,url
```

Require non-draft and non-prerelease. With a second fresh prefix/library and no `-Version`, run the raw-main installer again. Require default discovery selects v0.8.0, health passes, then stop/uninstall while preserving a second sentinel. Do not promote when the explicit-version path failed.

- [ ] **Step 6: Update QA note with real-asset evidence**

Replace the pending post-release statement with actual release URL, workflow result, manifest capability, selected version, health result, browser observation, command results, and cleanup result. Keep machine/user paths redacted.

- [ ] **Step 7: Create a small post-release docs-sync branch**

```powershell
git switch -c codex/v0.8.0-stable-docs-sync
```

Update release badge links/current stable paragraphs in all three READMEs and current stable direction in `ROADMAP.md` from v0.7.10 to v0.8.0. Update the two doc contract tests to require v0.8.0. Do not change implementation or rerun frontend build.

- [ ] **Step 8: Run proportional docs verification and commit**

```powershell
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m pytest tests/test_windows_installer.py::test_public_docs_explain_native_windows_without_installing_python tests/test_windows_installer.py::test_public_docs_do_not_claim_legacy_release_is_windows_native tests/test_public_mvp.py::test_public_docs_explain_first_run_status_and_doctor -q -p no:cacheprovider
git diff --check
git add README.md README_zh-TW.md README_zh-CN.md ROADMAP.md docs/qa/2026-07-10-native-windows-quick-start-qa.md tests/test_windows_installer.py tests/test_public_mvp.py
git commit -m "docs: publish v0.8.0 stable status"
git push -u origin codex/v0.8.0-stable-docs-sync
```

Expected: only direct docs tests run locally; GitHub CI remains the full gate.

- [ ] **Step 9: Open, gate, and merge the docs-sync PR**

```powershell
gh pr create --base main --head codex/v0.8.0-stable-docs-sync --title "docs: publish v0.8.0 stable status" --body "Sync public current-release wording after successful native Windows real-asset QA."
gh pr checks --watch --interval 10
```

Merge after green CI, then fast-forward local main. Confirm release badge, README Windows command, release URL, and Roadmap all agree on v0.8.0.

## Final Completion Evidence

Do not call the milestone complete until all evidence exists:

- implementation PR merge commit on `main`;
- independent review with no unresolved correctness/spec findings;
- Ubuntu full CI pass;
- Windows installer CI pass;
- local native Windows PowerShell 5.1 smoke pass;
- local browser first-run QA pass;
- stable v0.8.0 release with all three expected assets and manifest capability;
- public raw-URL install/health/lifecycle/uninstall pass against real assets;
- post-release docs-sync PR merged and public version links consistent;
- unrelated local SDD reports and QA logs preserved.
