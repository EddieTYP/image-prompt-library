from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
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
    assert "$Process.Kill()" in script


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


def test_windows_appctl_serializes_start_and_publishes_records_atomically():
    script = read("scripts/appctl.ps1")
    start_section = script.split("function Start-App", 1)[1].split("function Stop-App", 1)[0]

    assert "FileMode]::OpenOrCreate" in script
    assert "FileAccess]::ReadWrite" in script
    assert "FileShare]::None" in script
    assert "$startLock.Dispose()" in start_section
    assert "Write-ServerRecordAtomically" in start_section
    assert "Set-Content" not in script.split("function Write-ServerRecordAtomically", 1)[1].split("function ", 1)[0]
    assert "[IO.File]::Move" in script
    assert start_section.index("Read-ServerRecord") < start_section.index("Test-PortInUse")
    assert start_section.index("Test-PortInUse") < start_section.index("Start-Process -FilePath")
    assert start_section.index("Start-Process -FilePath") < start_section.index("Write-ServerRecordAtomically")


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
