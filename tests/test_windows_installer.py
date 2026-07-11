from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def powershell_executable() -> str:
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if not powershell:
        pytest.skip("Windows PowerShell is unavailable")
    return powershell


def run_appctl(prefix: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["IMAGE_PROMPT_LIBRARY_PREFIX"] = str(prefix)
    return subprocess.run(
        [powershell_executable(), "-NoProfile", "-File", str(ROOT / "scripts" / "appctl.ps1"), *arguments],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def powershell_literal(value: Path | str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def run_powershell(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [powershell_executable(), "-NoProfile", "-Command", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def test_windows_runtime_setup_is_local_and_never_installs_python():
    path = ROOT / "scripts" / "setup-runtime.ps1"
    assert path.is_file()
    script = path.read_text(encoding="utf-8")
    assert "Set-StrictMode -Version Latest" in script
    assert "sys.version_info >= (3, 10)" in script
    assert 'Join-Path $AppRoot ".venv\\Scripts\\python.exe"' in script
    assert 'Test-PythonCandidate -Exe $venvPython -PrefixArgs @()' in script
    assert 'Existing .venv Python is unsupported; remove .venv and rerun setup.' in script
    assert '@("-m", "venv", (Join-Path $AppRoot ".venv"))' in script
    assert '-Args @("-m", "pip", "install", $AppRoot)' in script
    assert "import backend.main, uvicorn" in script
    assert "image-prompt-library-runtime-probe-" in script
    assert "IMAGE_PROMPT_LIBRARY_PATH" in script
    assert "https://www.python.org/downloads/windows/" in script
    assert not re.search(r"(?i)winget\s+install", script)
    assert "npm" not in script.lower()
    assert "node" not in script.lower()
    assert "Start-Process" not in script


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


def test_windows_appctl_version_rejects_dot_segments(tmp_path: Path):
    prefix = tmp_path / "prefix with spaces"
    versions = prefix / "app" / "versions"
    version = "2026.07.11"
    (versions / version).mkdir(parents=True)
    pointer = prefix / "app" / "current-version"
    environment = os.environ.copy()
    environment["IMAGE_PROMPT_LIBRARY_PREFIX"] = str(prefix)

    for invalid_version in (".", ".."):
        pointer.write_text(f"{invalid_version}\n", encoding="utf-8")
        result = subprocess.run(
            [powershell_executable(), "-NoProfile", "-File", str(ROOT / "scripts" / "appctl.ps1"), "version"],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 1
        assert "current version pointer is invalid" in result.stderr.lower()

    pointer.write_text(f"{version}\n", encoding="utf-8")
    result = subprocess.run(
        [powershell_executable(), "-NoProfile", "-File", str(ROOT / "scripts" / "appctl.ps1"), "version"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == version


def test_windows_appctl_doctor_uses_user_path_and_status_database_data():
    script = read("scripts/appctl.ps1")
    runtime_section = script.split('Write-Output "Updates / Runtime"', 1)[1].split('Write-Output "Next steps"', 1)[0]
    database_section = script.split('Write-Output "Database"', 1)[1].split('Write-Output "Generation"', 1)[0]

    assert '[Environment]::GetEnvironmentVariable("Path", [EnvironmentVariableTarget]::User)' in runtime_section
    assert "$env:Path" not in runtime_section
    assert "OrdinalIgnoreCase" in runtime_section
    assert "Get-AppStatusData" in database_section
    assert "$status.Items" in database_section
    assert "Test-Path" not in database_section


def test_windows_appctl_records_exact_process_identity_before_stop():
    script = read("scripts/appctl.ps1")
    for name in ("Read-ServerRecord", "Get-OwnedProcess", "Test-AppHealth", "Test-PortInUse", "Start-App", "Stop-App"):
        assert f"function {name}" in script
    assert "process_start_time_utc_ticks" in script
    assert "process_executable_path" in script
    assert "app.previous.out.log" in script
    assert "app.previous.err.log" in script
    assert '"api/health"' in script
    assert "Start-Process" in script
    assert "-WindowStyle Hidden" in script
    assert "-RedirectStandardOutput" in script
    assert "-RedirectStandardError" in script
    assert '"start"' in script
    assert '"stop"' in script
    assert "Stop-Process -Id" not in script
    assert "$Lease.Process.Kill()" in script
    assert ".SafeHandle" in script
    assert "DangerousAddRef" in script
    assert "DangerousRelease" in script


def test_windows_appctl_stop_uses_retained_handle_for_disposable_child(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    appctl = powershell_literal(ROOT / "scripts" / "appctl.ps1")
    run_dir_literal = powershell_literal(run_dir)
    script = f"""
. {appctl} help
$child = $null
try {{
    $child = Start-Process -FilePath (Join-Path $PSHOME "powershell.exe") -ArgumentList @("-NoProfile", "-Command", "Start-Sleep -Seconds 120") -WindowStyle Hidden -PassThru
    $child.Refresh()
    $safeHandle = $child.SafeHandle
    $startTime = $child.StartTime.ToUniversalTime()
    $record = [pscustomobject][ordered]@{{
        pid = $child.Id
        process_start_time_utc = $startTime.ToString("o")
        process_start_time_utc_ticks = $startTime.Ticks
        process_executable_path = $child.Path
        version = "test"
        app_root = {powershell_literal(tmp_path)}
        host = "127.0.0.1"
        port = 65534
        stdout_log = {powershell_literal(tmp_path / "out.log")}
        stderr_log = {powershell_literal(tmp_path / "err.log")}
        created_at = [DateTime]::UtcNow.ToString("o")
    }}
    [IO.File]::WriteAllText((Join-Path {run_dir_literal} "server.json"), ($record | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
    Stop-App -Context ([pscustomobject]@{{ RunDir = {run_dir_literal} }})
    $child.Refresh()
    [pscustomobject]@{{ exited = $child.HasExited; record_exists = [IO.File]::Exists((Join-Path {run_dir_literal} "server.json")) }} | ConvertTo-Json -Compress
}} finally {{
    if ($child) {{
        $child.Refresh()
        if (-not $child.HasExited) {{ $child.Kill(); $child.WaitForExit(5000) | Out-Null }}
        $child.Dispose()
    }}
}}
"""

    result = run_powershell(script)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload == {"exited": True, "record_exists": False}


def test_windows_appctl_stop_retains_conflicting_live_process_record(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    appctl = powershell_literal(ROOT / "scripts" / "appctl.ps1")
    run_dir_literal = powershell_literal(run_dir)
    script = f"""
. {appctl} help
$child = $null
try {{
    $child = Start-Process -FilePath (Join-Path $PSHOME "powershell.exe") -ArgumentList @("-NoProfile", "-Command", "Start-Sleep -Seconds 120") -WindowStyle Hidden -PassThru
    $child.Refresh()
    $safeHandle = $child.SafeHandle
    $wrongStartTime = $child.StartTime.ToUniversalTime().AddTicks(1)
    $record = [pscustomobject][ordered]@{{
        pid = $child.Id
        process_start_time_utc = $wrongStartTime.ToString("o")
        process_start_time_utc_ticks = $wrongStartTime.Ticks
        process_executable_path = $child.Path
        version = "test"
        app_root = {powershell_literal(tmp_path)}
        host = "127.0.0.1"
        port = 65534
        stdout_log = {powershell_literal(tmp_path / "out.log")}
        stderr_log = {powershell_literal(tmp_path / "err.log")}
        created_at = [DateTime]::UtcNow.ToString("o")
    }}
    $recordPath = Join-Path {run_dir_literal} "server.json"
    [IO.File]::WriteAllText($recordPath, ($record | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
    $conflict = $false
    try {{ Stop-App -Context ([pscustomobject]@{{ RunDir = {run_dir_literal} }}) }}
    catch {{ $conflict = $_.Exception.Message -like "*conflicts with a live process*" }}
    $child.Refresh()
    [pscustomobject]@{{ conflict = $conflict; child_alive = -not $child.HasExited; record_exists = [IO.File]::Exists($recordPath) }} | ConvertTo-Json -Compress
}} finally {{
    if ($child) {{
        $child.Refresh()
        if (-not $child.HasExited) {{ $child.Kill(); $child.WaitForExit(5000) | Out-Null }}
        $child.Dispose()
    }}
}}
"""

    result = run_powershell(script)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload == {"conflict": True, "child_alive": True, "record_exists": True}


@pytest.mark.parametrize(
    "invalid_fields",
    [
        {"pid": "123"},
        {"pid": 0},
        {"process_start_time_utc_ticks": "639193248000000000"},
        {"process_start_time_utc_ticks": 639193248000000001},
        {"process_executable_path": ""},
        {"version": ""},
        {"app_root": ""},
        {"host": "bad host"},
        {"port": "8000"},
        {"port": 65536},
        {"stdout_log": ""},
        {"stderr_log": ""},
        {"created_at": "not-a-timestamp"},
    ],
)
def test_windows_appctl_retains_malformed_record_when_stop_fails(tmp_path: Path, invalid_fields: dict[str, object]):
    record_path = tmp_path / "run" / "server.json"
    record_path.parent.mkdir(parents=True)
    record = {
        "pid": 2147483647,
        "process_start_time_utc": "2026-07-11T00:00:00.0000000Z",
        "process_start_time_utc_ticks": 639193248000000000,
        "process_executable_path": r"C:\safe\python.exe",
        "version": "2026.07.11",
        "app_root": r"C:\safe\app",
        "host": "127.0.0.1",
        "port": 8000,
        "stdout_log": r"C:\safe\app.out.log",
        "stderr_log": r"C:\safe\app.err.log",
        "created_at": "2026-07-11T00:00:00.0000000Z",
    }
    record.update(invalid_fields)
    malformed = json.dumps(record)
    record_path.write_text(malformed, encoding="utf-8")

    result = run_appctl(tmp_path, "stop")

    assert result.returncode == 1
    assert "runtime record is malformed" in result.stderr.lower()
    assert record_path.read_text(encoding="utf-8") == malformed


@pytest.mark.parametrize("host", ["bad host", "127.0.0.1 --port 9", "-EncodedCommand", "[::1]"])
def test_windows_appctl_rejects_invalid_bind_host_before_launch(tmp_path: Path, host: str):
    result = run_appctl(tmp_path, "start", "--host", host, "--no-browser")

    assert result.returncode == 1
    assert "host must be a single valid dns name or ip address" in result.stderr.lower()
    assert not (tmp_path / "run" / "server.json").exists()


def test_windows_appctl_rejects_stop_arguments(tmp_path: Path):
    result = run_appctl(tmp_path, "stop", "--force")

    assert result.returncode == 1
    assert "stop does not accept arguments" in result.stderr.lower()


def test_windows_appctl_stop_waits_for_lifecycle_lock(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    lock_path = run_dir / "start.lock"
    ready_path = tmp_path / "lock-ready"
    holder_script = f"""
$lock = [IO.File]::Open({powershell_literal(lock_path)}, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
try {{
    [IO.File]::WriteAllText({powershell_literal(ready_path)}, "ready")
    Start-Sleep -Milliseconds 1500
}} finally {{
    $lock.Dispose()
}}
"""
    holder = subprocess.Popen(
        [powershell_executable(), "-NoProfile", "-Command", holder_script],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 5
        while not ready_path.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert ready_path.exists(), holder.communicate(timeout=1)[1]

        started = time.monotonic()
        result = run_appctl(tmp_path, "stop")
        elapsed = time.monotonic() - started

        assert result.returncode == 0, result.stderr
        assert elapsed >= 1.0
    finally:
        if holder.poll() is None:
            holder.terminate()
        holder.communicate(timeout=5)


def test_windows_appctl_atomic_publication_preserves_existing_destination(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    record_path = run_dir / "server.json"
    record_path.write_text("conflicting record", encoding="utf-8")
    script = f"""
. {powershell_literal(ROOT / "scripts" / "appctl.ps1")} help
$context = [pscustomobject]@{{ RunDir = {powershell_literal(run_dir)} }}
$collided = $false
try {{ Write-ServerRecordAtomically -Context $context -Record ([pscustomobject]@{{ pid = 1 }}) }}
catch {{ $collided = $true }}
[pscustomobject]@{{ collided = $collided; contents = [IO.File]::ReadAllText({powershell_literal(record_path)}); temp_count = @(Get-ChildItem -LiteralPath {powershell_literal(run_dir)} -Filter "*.tmp").Count }} | ConvertTo-Json -Compress
"""

    result = run_powershell(script)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload == {"collided": True, "contents": "conflicting record", "temp_count": 0}


def test_windows_appctl_recovery_record_does_not_overwrite_primary(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    record_path = run_dir / "server.json"
    record_path.write_text("conflicting record", encoding="utf-8")
    script = f"""
. {powershell_literal(ROOT / "scripts" / "appctl.ps1")} help
$context = [pscustomobject]@{{ RunDir = {powershell_literal(run_dir)} }}
$record = [pscustomobject][ordered]@{{
    pid = 123
    process_start_time_utc = "2026-07-11T00:00:00.0000000Z"
    process_start_time_utc_ticks = 639193248000000000
    process_executable_path = "C:\\safe\\python.exe"
    version = "test"
    app_root = "C:\\safe\\app"
    host = "127.0.0.1"
    port = 8000
    stdout_log = "C:\\safe\\out.log"
    stderr_log = "C:\\safe\\err.log"
    created_at = "2026-07-11T00:00:00.0000000Z"
}}
$recoveryPath = Write-RecoveryServerRecord -Context $context -Record $record
[pscustomobject]@{{ primary = [IO.File]::ReadAllText({powershell_literal(record_path)}); recovery = [IO.File]::ReadAllText($recoveryPath); name = [IO.Path]::GetFileName($recoveryPath) }} | ConvertTo-Json -Compress
"""

    result = run_powershell(script)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["primary"] == "conflicting record"
    assert json.loads(payload["recovery"])["pid"] == 123
    assert re.fullmatch(r"server\.recovery\.[0-9a-f]{32}\.json", payload["name"])


def test_windows_appctl_serializes_lifecycle_and_publishes_records_atomically():
    script = read("scripts/appctl.ps1")
    start_section = script.split("function Start-App", 1)[1].split("function Stop-App", 1)[0]
    stop_section = script.split("function Stop-App", 1)[1].split("function Show-Usage", 1)[0]

    assert "FileMode]::OpenOrCreate" in script
    assert "FileAccess]::ReadWrite" in script
    assert "FileShare]::None" in script
    assert "Enter-LifecycleLock -Context $Context" in start_section
    assert "Enter-LifecycleLock -Context $Context" in stop_section
    assert "$lifecycleLock.Dispose()" in start_section
    assert "$lifecycleLock.Dispose()" in stop_section
    assert "Write-ServerRecordAtomically" in start_section
    assert "Write-RecoveryServerRecord" in start_section
    assert "Remove-ServerRecordIfMatches" in stop_section
    assert "Set-Content" not in script.split("function Write-ServerRecordAtomically", 1)[1].split("function ", 1)[0]
    assert "[IO.File]::Move" in script
    assert start_section.index("Read-ServerRecord") < start_section.index("Test-PortInUse")
    assert start_section.index("Test-PortInUse") < start_section.index("Start-Process -FilePath")
    assert start_section.index("Start-Process -FilePath") < start_section.index("Write-ServerRecordAtomically")
    assert stop_section.index("Enter-LifecycleLock") < stop_section.index("Read-ServerRecord")
    assert "Cleanup could not confirm exit, and the launched process identity could not be retained" not in start_section


def test_windows_appctl_retains_safe_handle_through_identity_and_termination():
    script = read("scripts/appctl.ps1")
    lease_section = script.split("function New-ProcessLease", 1)[1].split("function Close-ProcessLease", 1)[0]
    owned_section = script.split("function Get-OwnedProcess", 1)[1].split("function Test-ProcessIdentity", 1)[0]
    start_section = script.split("function Start-App", 1)[1].split("function Stop-App", 1)[0]
    stop_section = script.split("function Stop-App", 1)[1].split("function Show-Usage", 1)[0]

    assert "$Process.SafeHandle" in lease_section
    assert "DangerousAddRef" in lease_section
    assert "DangerousRelease" in script.split("function Close-ProcessLease", 1)[1].split("function ", 1)[0]
    assert owned_section.index("New-ProcessLease") < owned_section.index("Test-ProcessIdentity")
    assert "$Lease.Process.Kill()" in script
    assert start_section.index("New-ProcessLease -Process $process") < start_section.index("$processLease.Process.StartTime")
    assert start_section.index("Stop-VerifiedProcess -Lease $processLease") < start_section.rindex("Close-ProcessLease -Lease $processLease")
    assert stop_section.index("Stop-VerifiedProcess") < stop_section.index("Close-ProcessLease")
    assert "Get-Process" not in script.split("function Stop-VerifiedProcess", 1)[1].split("function ", 1)[0]


def test_windows_appctl_uses_runtime_endpoint_and_safe_argument_boundaries():
    script = read("scripts/appctl.ps1")
    status_section = script.split("function Show-Status", 1)[1].split("function Show-Doctor", 1)[0]
    start_section = script.split("function Start-App", 1)[1].split("function Stop-App", 1)[0]

    assert "Get-AppUrl" in status_section
    assert "$status.Record.host" in status_section
    assert "$status.Record.port" in status_section
    assert "Test-BindHost -HostName $hostName" in start_section
    assert '$arguments = @("-m", "uvicorn", "backend.main:app", "--host", $hostName, "--port", [string]$port)' in start_section
    assert start_section.index("Test-BindHost -HostName $hostName") < start_section.index("$arguments = @(")
    assert 'if ($HostName.Contains(":")) { "[" + $HostName.Replace("%", "%25") + "]" }' in script
    assert '$HostName -in @("0.0.0.0", "::")' in script


def test_windows_appctl_formats_wildcard_and_ipv6_urls_behaviorally():
    script = f"""
. {powershell_literal(ROOT / "scripts" / "appctl.ps1")} help
@(
    (Get-AppUrl -HostName "0.0.0.0" -Port 8000),
    (Get-AppUrl -HostName "::" -Port 8001),
    (Get-AppUrl -HostName "::1" -Port 8002),
    (Get-AppUrl -HostName "fe80::1%12" -Port 8003)
) | ConvertTo-Json -Compress
"""

    result = run_powershell(script)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.strip().splitlines()[-1]) == [
        "http://127.0.0.1:8000/",
        "http://127.0.0.1:8001/",
        "http://[::1]:8002/",
        "http://[fe80::1%2512]:8003/",
    ]


@pytest.mark.parametrize("runtime", ["running", "unhealthy"])
def test_windows_appctl_status_uses_valid_owned_runtime_endpoint(runtime: str):
    script = f"""
. {powershell_literal(ROOT / "scripts" / "appctl.ps1")} help
function Read-AppEnvironment {{ [pscustomobject]@{{ LibraryPath = "C:\\configured"; Host = "127.0.0.1"; Port = 9000 }} }}
function Get-CurrentVersion {{ [pscustomobject]@{{ Version = "test"; Python = "missing" }} }}
function Get-AppStatusData {{
    [pscustomobject]@{{
        Items = 0
        Database = "ok"
        Generation = "not connected"
        Runtime = {powershell_literal(runtime)}
        Record = [pscustomobject]@{{ host = "::1"; port = 8123 }}
    }}
}}
Show-Status -Context ([pscustomobject]@{{}})
"""

    result = run_powershell(script)

    assert result.returncode == 0, result.stderr
    assert "URL: http://[::1]:8123/" in result.stdout
    assert "URL: http://127.0.0.1:9000/" not in result.stdout


def test_windows_appctl_status_uses_configured_endpoint_without_owned_runtime():
    script = f"""
. {powershell_literal(ROOT / "scripts" / "appctl.ps1")} help
function Read-AppEnvironment {{ [pscustomobject]@{{ LibraryPath = "C:\\configured"; Host = "127.0.0.1"; Port = 9000 }} }}
function Get-CurrentVersion {{ [pscustomobject]@{{ Version = "test"; Python = "missing" }} }}
function Get-AppStatusData {{
    [pscustomobject]@{{
        Items = 0
        Database = "ok"
        Generation = "not connected"
        Runtime = "stale runtime record"
        Record = [pscustomobject]@{{ host = "::1"; port = 8123 }}
    }}
}}
Show-Status -Context ([pscustomobject]@{{}})
"""

    result = run_powershell(script)

    assert result.returncode == 0, result.stderr
    assert "URL: http://127.0.0.1:9000/" in result.stdout
    assert "URL: http://[::1]:8123/" not in result.stdout
