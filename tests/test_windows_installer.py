from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
import warnings
import zipfile
from pathlib import Path

import pytest
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_native_windows_smoke_and_ci_contract():
    smoke_path = ROOT / "tests" / "windows-installer-smoke.ps1"
    assert smoke_path.is_file()
    smoke = smoke_path.read_text(encoding="ascii")
    for required in (
        "v0.8.0-test-a",
        "v0.8.0-test-b",
        "v0.8.0-test-broken",
        "missing-python.exe",
        "Automatic recovery restored",
        "process_start_time_utc_ticks",
        "Private library preserved at",
    ):
        assert required in smoke

    workflow = read(".github/workflows/ci.yml")
    assert re.search(r"(?m)^  windows-installer:\s*$", workflow)
    windows_job = workflow.split("  windows-installer:", 1)[1]
    assert "runs-on: windows-latest" in windows_job
    assert "actions/checkout@v5" in windows_job
    assert "actions/setup-python@v6" in windows_job
    assert "python-version: '3.11'" in windows_job
    assert "cache: pip" in windows_job
    assert "actions/setup-node@v5" in windows_job
    assert "node-version: 24" in windows_job
    assert "cache: npm" in windows_job
    assert "python -m pip install -e '.[dev]'" in windows_job
    assert "npm install" in windows_job
    assert "npm run build" in windows_job
    assert "tests/test_windows_installer.py" in windows_job
    assert "tests/windows-installer-smoke.ps1" in windows_job


def test_native_windows_smoke_embeds_a_loadable_sample_png():
    smoke = (ROOT / "tests" / "windows-installer-smoke.ps1").read_text(encoding="ascii")
    encoded = re.search(r'FromBase64String\("([A-Za-z0-9+/=]+)"\)', smoke)
    assert encoded
    with Image.open(io.BytesIO(base64.b64decode(encoded.group(1)))) as image:
        image.load()


def test_native_windows_smoke_capture_does_not_wait_for_detached_descendants(
    tmp_path: Path,
):
    child = tmp_path / "start-detached.ps1"
    child.write_text(
        "$processPath = $env:Path\n"
        "[Environment]::SetEnvironmentVariable('PATH', $null, 'Process')\n"
        "[Environment]::SetEnvironmentVariable('Path', $processPath, 'Process')\n"
        "$outLog = Join-Path $PSScriptRoot 'child.out.log'\n"
        "$errLog = Join-Path $PSScriptRoot 'child.err.log'\n"
        "$sleeper = Start-Process powershell.exe -ArgumentList @('-NoProfile', '-Command', 'Start-Sleep -Seconds 5') -WindowStyle Hidden -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru\n"
        "[IO.File]::WriteAllText((Join-Path $PSScriptRoot 'sleeper.pid'), [string]$sleeper.Id)\n"
        "Write-Output 'done'\n",
        encoding="ascii",
    )
    result_path = tmp_path / "result.json"
    smoke = powershell_literal(ROOT / "tests" / "windows-installer-smoke.ps1")
    script = f"""
$source = [IO.File]::ReadAllText({smoke})
$functionStart = $source.IndexOf('function Invoke-IsolatedPowerShell')
$functionEnd = $source.IndexOf('function Assert-Succeeded')
if ($functionStart -lt 0 -or $functionEnd -lt 0) {{ throw 'Smoke process helper was not found.' }}
$repoRoot = {powershell_literal(ROOT)}
$workRoot = {powershell_literal(tmp_path / 'capture-root')}
New-Item -ItemType Directory -Path $workRoot | Out-Null
Invoke-Expression $source.Substring($functionStart, $functionEnd - $functionStart)
$stopwatch = [Diagnostics.Stopwatch]::StartNew()
$result = Invoke-IsolatedPowerShell -ScriptPath {powershell_literal(child)}
$stopwatch.Stop()
$sleeperId = [int][IO.File]::ReadAllText({powershell_literal(tmp_path / 'sleeper.pid')})
$sleeper = Get-Process -Id $sleeperId -ErrorAction SilentlyContinue
if ($sleeper) {{ Stop-Process -Id $sleeperId -Force; Wait-Process -Id $sleeperId -ErrorAction SilentlyContinue }}
[IO.File]::WriteAllText({powershell_literal(result_path)}, ([pscustomobject]@{{ ExitCode = $result.ExitCode; Output = $result.Output; ElapsedMilliseconds = $stopwatch.ElapsedMilliseconds }} | ConvertTo-Json -Compress))
"""

    result = run_powershell(script)

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result_path.read_text())
    assert payload["ExitCode"] == 0
    assert payload["Output"] == "done"
    assert payload["ElapsedMilliseconds"] < 3000


def test_native_windows_smoke_preserves_switch_like_argument_arrays(tmp_path: Path):
    child = tmp_path / "echo-arguments.ps1"
    child.write_text(
        "param([Parameter(ValueFromRemainingArguments=$true)][string[]]$CommandArgs)\n"
        "ConvertTo-Json -InputObject ([object[]]@($CommandArgs)) -Compress\n",
        encoding="ascii",
    )
    smoke = powershell_literal(ROOT / "tests" / "windows-installer-smoke.ps1")
    script = f"""
$source = [IO.File]::ReadAllText({smoke})
$functionStart = $source.IndexOf('function Invoke-IsolatedPowerShell')
$functionEnd = $source.IndexOf('function Assert-Succeeded')
if ($functionStart -lt 0 -or $functionEnd -lt 0) {{ throw 'Smoke process helper was not found.' }}
$repoRoot = {powershell_literal(ROOT)}
$workRoot = {powershell_literal(tmp_path / 'capture-root')}
New-Item -ItemType Directory -Path $workRoot | Out-Null
Invoke-Expression $source.Substring($functionStart, $functionEnd - $functionStart)
$result = Invoke-IsolatedPowerShell -ScriptPath {powershell_literal(child)} -Arguments @('update', '--version', 'v2.0.0', '-ReleaseBaseUrl', 'release with spaces')
$result | ConvertTo-Json -Compress
"""

    result = run_powershell(script)

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["ExitCode"] == 0
    assert json.loads(payload["Output"]) == [
        "update",
        "--version",
        "v2.0.0",
        "-ReleaseBaseUrl",
        "release with spaces",
    ]


def powershell_executable() -> str:
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if not powershell:
        pytest.skip("Windows PowerShell is unavailable")
    return powershell


def run_appctl(
    prefix: Path,
    *arguments: str,
    input_text: str | None = None,
    environment_overrides: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["IMAGE_PROMPT_LIBRARY_PREFIX"] = str(prefix)
    if environment_overrides:
        environment.update(environment_overrides)
    return subprocess.run(
        [powershell_executable(), "-NoProfile", "-File", str(ROOT / "scripts" / "appctl.ps1"), *arguments],
        cwd=cwd or ROOT,
        env=environment,
        input=input_text,
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


def run_installer_function(script: str) -> subprocess.CompletedProcess[str]:
    installer = powershell_literal(ROOT / "scripts" / "install.ps1")
    return run_powershell(
        f"""
$source = [IO.File]::ReadAllText({installer})
$entryPoint = $source.LastIndexOf('try {{')
if ($entryPoint -lt 0) {{ throw 'Installer entry point was not found.' }}
Invoke-Expression $source.Substring(0, $entryPoint)
{script}
"""
    )


def run_appctl_function(script: str) -> subprocess.CompletedProcess[str]:
    appctl = powershell_literal(ROOT / "scripts" / "appctl.ps1")
    script_root = powershell_literal(ROOT / "scripts")
    script_root_assignment = powershell_literal(f"$script:ScriptRoot = {script_root}")
    return run_powershell(
        f"""
$source = [IO.File]::ReadAllText({appctl})
$source = $source.Replace('$script:ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path', {script_root_assignment})
$entryPoint = $source.LastIndexOf('try {{')
if ($entryPoint -lt 0) {{ throw 'Controller entry point was not found.' }}
Invoke-Expression $source.Substring(0, $entryPoint)
{script}
"""
    )


def run_sample_data_installer(
    language: str,
    package: str,
    app_root: Path,
    library: Path,
    environment: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            powershell_executable(),
            "-NoProfile",
            "-File",
            str(ROOT / "scripts" / "install-sample-data.ps1"),
            "-Language",
            language,
            "-Package",
            package,
            "-AppRoot",
            str(app_root),
            "-LibraryPath",
            str(library),
        ],
        cwd=ROOT,
        env={**os.environ, **environment},
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def run_sample_data_command(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            powershell_executable(),
            "-NoProfile",
            "-File",
            str(ROOT / "scripts" / "install-sample-data.ps1"),
            *arguments,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def run_sample_data_installer_function(script: str) -> subprocess.CompletedProcess[str]:
    installer = powershell_literal(ROOT / "scripts" / "install-sample-data.ps1")
    probe = powershell_literal("\n" + script)
    return run_powershell(
        f"""
$source = [IO.File]::ReadAllText({installer})
$entryPoint = $source.LastIndexOf('try {{')
if ($entryPoint -lt 0) {{ throw 'Sample-data installer entry point was not found.' }}
Invoke-Expression ($source.Substring(0, $entryPoint) + {probe})
"""
    )


def write_sample_zip(path: Path, members: list[tuple[str, str]]) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(path, "w") as archive:
            for kind, name in members:
                info = zipfile.ZipInfo(name)
                if kind == "directory":
                    info.external_attr = 0o40755 << 16
                    archive.writestr(info, b"")
                elif kind == "symlink":
                    info.create_system = 3
                    info.external_attr = 0o120777 << 16
                    archive.writestr(info, "target")
                elif kind == "fifo":
                    info.create_system = 3
                    info.external_attr = 0o010644 << 16
                    archive.writestr(info, b"")
                elif kind == "reparse":
                    info.external_attr = 0x400
                    archive.writestr(info, b"target")
                else:
                    archive.writestr(info, b"sample")


def write_empty_sample_manifest(path: Path) -> None:
    path.write_text(
        json.dumps({"schema_version": 2, "language": "en", "collections": [], "items": []}),
        encoding="utf-8",
    )


def write_sample_data_appctl_install(prefix: Path, library: Path, child_script: str) -> Path:
    current = prefix / "app" / "versions" / "v1.0.0"
    scripts = current / "scripts"
    scripts.mkdir(parents=True)
    (prefix / "app" / "current-version").write_text("v1.0.0\n", encoding="ascii")
    prefix.mkdir(exist_ok=True)
    (prefix / ".env").write_text(f"IMAGE_PROMPT_LIBRARY_PATH={library}\n", encoding="ascii")
    (scripts / "install-sample-data.ps1").write_text(child_script, encoding="ascii")
    return current


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
    assert '-Arguments @("-m", "pip", "install", $AppRoot)' in script
    assert "import backend.main, uvicorn" in script
    assert "image-prompt-library-runtime-probe-" in script
    assert "IMAGE_PROMPT_LIBRARY_PATH" in script
    assert "https://www.python.org/downloads/windows/" in script
    assert not re.search(r"(?i)winget\s+install", script)
    assert "npm" not in script.lower()
    assert "node" not in script.lower()
    assert "Start-Process" not in script


def test_windows_runtime_setup_forwards_checked_argument_arrays():
    setup_runtime = powershell_literal(ROOT / "scripts" / "setup-runtime.ps1")
    python = powershell_literal(Path(sys.executable))
    result = run_powershell(
        f"""
$source = [IO.File]::ReadAllText({setup_runtime})
$functionStart = $source.IndexOf('function Invoke-PythonChecked')
$entryPoint = $source.IndexOf('$AppRoot = [IO.Path]::GetFullPath')
if ($functionStart -lt 0 -or $entryPoint -lt 0) {{ throw 'Runtime setup function was not found.' }}
Invoke-Expression $source.Substring($functionStart, $entryPoint - $functionStart)
Invoke-PythonChecked -Exe {python} -Arguments @('-c', 'import json,sys; print(json.dumps(sys.argv[1:]))', 'alpha', 'beta gamma') -FailureMessage 'forwarding failed'
"""
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout.strip()) == ["alpha", "beta gamma"]


def test_real_release_package_extracts_with_hardened_windows_installer(tmp_path: Path):
    version = "v9.9.11-test"
    git_bash = next(
        (
            candidate
            for candidate in (
                Path(r"C:\Program Files\Git\bin\bash.exe"),
                Path(r"C:\Program Files\Git\usr\bin\bash.exe"),
            )
            if candidate.is_file()
        ),
        None,
    )
    if git_bash is None:
        pytest.skip("Git Bash is required for the real release package regression")
    bash_root = f"/{ROOT.drive[0].lower()}{ROOT.as_posix()[2:]}"
    python_path = Path(sys.executable)
    bash_python = f"/{python_path.drive[0].lower()}{python_path.as_posix()[2:]}"
    packaged = subprocess.run(
        [
            git_bash,
            "-lc",
            f"python3() {{ '{bash_python}' \"$@\"; }}; export -f python3; cd '{bash_root}' && scripts/package-release.sh '{version}' --skip-build",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=120,
    )
    assert packaged.returncode == 0, packaged.stdout + packaged.stderr

    artifact = ROOT / "dist-release" / f"image-prompt-library-{version}.tar.gz"
    manifest = json.loads(
        (ROOT / "dist-release" / f"image-prompt-library-{version}.manifest.json").read_text()
    )
    with tarfile.open(artifact, "r:gz") as archive:
        names = [member.name for member in archive.getmembers()]
    assert "." not in names
    assert not any(name.startswith("./") for name in names)

    destination = tmp_path / "extracted"
    python = powershell_literal(Path(sys.executable))
    result = run_installer_function(
        f"""
$python = [pscustomobject]@{{ Exe = {python}; PrefixArgs = @() }}
Expand-SafeTar -ArtifactPath {powershell_literal(artifact)} -Destination {powershell_literal(destination)} -ExpectedSha '{manifest['sha256']}' -Python $python
"""
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert (destination / "VERSION").read_text(encoding="ascii").strip() == version
    assert (destination / "sample-data" / "manifests").is_dir()
    assert (destination / "LICENSE").is_file()


def test_windows_release_sources_are_ascii():
    for relative_path in (
        "scripts/appctl.ps1",
        "scripts/install.ps1",
        "scripts/install-sample-data.ps1",
        "scripts/setup-runtime.ps1",
    ):
        (ROOT / relative_path).read_bytes().decode("ascii")


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


def test_windows_appctl_status_python_script_runs_under_windows_powershell(
    tmp_path: Path,
):
    library = tmp_path / "library with spaces"
    library.mkdir()
    result = run_appctl_function(
        f"""
function Get-ServerRuntimeData {{
    param($Context)
    return [pscustomobject]@{{ State = 'stopped'; Record = $null }}
}}
$context = [pscustomobject]@{{}}
$environment = [pscustomobject]@{{ LibraryPath = {powershell_literal(library)} }}
$version = [pscustomobject]@{{ Python = {powershell_literal(Path(sys.executable))} }}
Get-AppStatusData -Context $context -Environment $environment -Version $version | ConvertTo-Json -Compress
"""
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["Database"] == "missing"
    assert payload["Items"] is None


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


def test_windows_appctl_waits_for_started_process_path_before_identity_check():
    expected = r"C:\App\venv\Scripts\python.exe"
    result = run_appctl_function(
        f"""
$script:pathReads = 0
$process = New-Object psobject
$process | Add-Member -MemberType ScriptMethod -Name Refresh -Value {{}}
$process | Add-Member -MemberType ScriptProperty -Name StartTime -Value {{ [DateTime]::UtcNow }}
$process | Add-Member -MemberType ScriptProperty -Name Path -Value {{
    $script:pathReads++
    if ($script:pathReads -eq 1) {{ return $null }}
    return {powershell_literal(expected)}
}}
$process | Add-Member -MemberType ScriptProperty -Name HasExited -Value {{ $false }}
$identity = Get-StartedProcessIdentity -Process $process -ExpectedPath {powershell_literal(expected)} -TimeoutMilliseconds 500
[pscustomobject]@{{ Path = $identity.Path; Reads = $script:pathReads }} | ConvertTo-Json -Compress
"""
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload == {"Path": expected, "Reads": 2}


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


def write_uninstall_layout(prefix: Path, library: Path) -> None:
    (prefix / "bin").mkdir(parents=True)
    (prefix / "bin" / "image-prompt-library.ps1").write_text("shim\n", encoding="ascii")
    (prefix / ".env").write_text(f"IMAGE_PROMPT_LIBRARY_PATH={library}\n", encoding="ascii")
    library.mkdir(parents=True, exist_ok=True)
    (library / "private.txt").write_text("keep\n", encoding="ascii")


def create_dangling_directory_link(link: Path, target: Path) -> None:
    target.mkdir()
    result = run_powershell(
        f"""
New-Item -ItemType Junction -Path {powershell_literal(link)} -Target {powershell_literal(target)} -ErrorAction Stop | Out-Null
[IO.Directory]::Delete({powershell_literal(target)}, $false)
$attributes = [IO.File]::GetAttributes({powershell_literal(link)})
if (($attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) {{ throw 'Dangling link entry was not retained.' }}
"""
    )
    if result.returncode != 0:
        pytest.skip(f"Windows dangling junction creation unavailable: {result.stderr.strip()}")


def assert_windows_reparse_entry(path: Path) -> None:
    result = run_powershell(
        f"$attributes = [IO.File]::GetAttributes({powershell_literal(path)}); if (($attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) {{ exit 1 }}"
    )
    assert result.returncode == 0, result.stderr


def test_windows_appctl_reparse_preflight_inspects_entry_without_test_path_gate():
    script = read("scripts/appctl.ps1")
    section = script.split("function Assert-UninstallTargetNotReparse", 1)[1].split("function ", 1)[0]

    assert "[IO.File]::GetAttributes" in section
    assert "Test-Path" not in section


def test_windows_appctl_uninstall_preserves_private_library_by_default_with_spaces(tmp_path: Path):
    prefix = tmp_path / "app prefix"
    library = tmp_path / "private library"
    write_uninstall_layout(prefix, library)

    result = run_appctl(prefix, "uninstall")

    assert result.returncode == 0, result.stderr
    assert not prefix.exists()
    assert (library / "private.txt").read_text(encoding="ascii") == "keep\n"
    assert f"Private library preserved at {library.resolve()}" in result.stdout
    assert result.stdout.index("Private library preserved at") < result.stdout.index("uninstalled")


def test_windows_appctl_uninstall_deletes_private_library_after_exact_confirmation(tmp_path: Path):
    prefix = tmp_path / "app prefix"
    library = tmp_path / "private library"
    write_uninstall_layout(prefix, library)

    result = run_appctl(prefix, "uninstall", "--delete-library", input_text="DELETE\n")

    assert result.returncode == 0, result.stderr
    assert not prefix.exists()
    assert not library.exists()


def test_windows_appctl_uninstall_deletes_private_library_with_yes(tmp_path: Path):
    prefix = tmp_path / "prefix"
    library = tmp_path / "library"
    write_uninstall_layout(prefix, library)

    result = run_appctl(prefix, "uninstall", "--delete-library", "--yes")

    assert result.returncode == 0, result.stderr
    assert not prefix.exists()
    assert not library.exists()


def test_windows_appctl_uninstall_preserves_normally_missing_private_library(tmp_path: Path):
    prefix = tmp_path / "prefix"
    (prefix / "bin").mkdir(parents=True)
    (prefix / "bin" / "image-prompt-library.ps1").write_text("shim\n", encoding="ascii")
    library = tmp_path / "missing-library"
    (prefix / ".env").write_text(f"IMAGE_PROMPT_LIBRARY_PATH={library}\n", encoding="ascii")

    result = run_appctl(prefix, "uninstall")

    assert result.returncode == 0, result.stderr
    assert not prefix.exists()
    assert not library.exists()
    assert f"Private library preserved at {library.resolve()}" in result.stdout


def test_windows_appctl_uninstall_refusal_leaves_app_and_library_unchanged(tmp_path: Path):
    prefix = tmp_path / "prefix"
    library = tmp_path / "library"
    write_uninstall_layout(prefix, library)

    result = run_appctl(prefix, "uninstall", "--delete-library", input_text="delete\n")

    assert result.returncode == 0, result.stderr
    assert "cancelled" in result.stdout.lower()
    assert (prefix / "bin" / "image-prompt-library.ps1").is_file()
    assert (library / "private.txt").is_file()


@pytest.mark.parametrize(
    "arguments",
    [
        ("--delete-library", "--delete-library"),
        ("--yes", "--yes"),
        ("--unknown",),
        ("--delete-library", "--unknown"),
    ],
)
def test_windows_appctl_uninstall_rejects_duplicate_and_unknown_options(tmp_path: Path, arguments: tuple[str, ...]):
    prefix = tmp_path / "prefix"
    library = tmp_path / "library"
    write_uninstall_layout(prefix, library)

    result = run_appctl(prefix, "uninstall", *arguments)

    assert result.returncode == 1
    assert (prefix / "bin" / "image-prompt-library.ps1").is_file()
    assert (library / "private.txt").is_file()


@pytest.mark.parametrize(
    "target_kind",
    ["root", "home", "equal", "prefix_contains_library", "library_contains_prefix"],
)
def test_windows_appctl_uninstall_rejects_unsafe_targets_before_mutation(tmp_path: Path, target_kind: str):
    library = tmp_path / "library"
    if target_kind == "root":
        prefix = Path(tmp_path.anchor)
    elif target_kind == "home":
        prefix = Path(os.environ["USERPROFILE"])
    elif target_kind == "equal":
        prefix = tmp_path / "target"
        library = prefix
        write_uninstall_layout(prefix, library)
    elif target_kind == "prefix_contains_library":
        prefix = tmp_path / "prefix"
        library = prefix / "library"
        write_uninstall_layout(prefix, library)
    else:
        library = tmp_path / "library"
        prefix = library / "prefix"
        write_uninstall_layout(prefix, library)

    if target_kind in {"root", "home"}:
        library.mkdir()
        (library / "private.txt").write_text("keep\n", encoding="ascii")

    result = run_appctl(
        prefix,
        "uninstall",
        environment_overrides={"IMAGE_PROMPT_LIBRARY_PATH": str(library)},
    )

    assert result.returncode == 1
    if target_kind not in {"root", "home"}:
        assert "must not contain each other" in result.stderr.lower()
    else:
        assert "uninstall" in result.stderr.lower()
    assert (library / "private.txt").read_text(encoding="ascii") == "keep\n"
    if target_kind not in {"root", "home"}:
        assert (prefix / "bin" / "image-prompt-library.ps1").is_file()
        assert not (prefix / "run").exists()


def test_windows_appctl_uninstall_rejects_prefix_junction_before_read_or_write(tmp_path: Path):
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_text("keep\n", encoding="ascii")
    prefix = tmp_path / "prefix-junction"
    created = run_powershell(
        f"New-Item -ItemType Junction -Path {powershell_literal(prefix)} -Target {powershell_literal(outside)} -ErrorAction Stop | Out-Null"
    )
    if created.returncode != 0:
        pytest.skip(f"Windows junction creation unavailable: {created.stderr.strip()}")
    library = tmp_path / "library"
    library.mkdir()
    (library / "private.txt").write_text("keep\n", encoding="ascii")

    result = run_appctl(
        prefix,
        "uninstall",
        environment_overrides={"IMAGE_PROMPT_LIBRARY_PATH": str(library)},
    )

    assert result.returncode == 1
    assert "reparse" in result.stderr.lower()
    assert prefix.exists()
    assert sentinel.read_text(encoding="ascii") == "keep\n"
    assert not (outside / "run").exists()
    assert (library / "private.txt").is_file()


def test_windows_appctl_uninstall_rejects_library_junction_before_mutation(tmp_path: Path):
    prefix = tmp_path / "prefix"
    (prefix / "bin").mkdir(parents=True)
    shim = prefix / "bin" / "image-prompt-library.ps1"
    shim.write_text("shim\n", encoding="ascii")
    outside = tmp_path / "outside-library"
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_text("keep\n", encoding="ascii")
    library = tmp_path / "library-junction"
    created = run_powershell(
        f"New-Item -ItemType Junction -Path {powershell_literal(library)} -Target {powershell_literal(outside)} -ErrorAction Stop | Out-Null"
    )
    if created.returncode != 0:
        pytest.skip(f"Windows junction creation unavailable: {created.stderr.strip()}")
    (prefix / ".env").write_text(f"IMAGE_PROMPT_LIBRARY_PATH={library}\n", encoding="ascii")

    result = run_appctl(prefix, "uninstall", "--delete-library", "--yes")

    assert result.returncode == 1
    assert "reparse" in result.stderr.lower()
    assert shim.read_text(encoding="ascii") == "shim\n"
    assert not (prefix / "run").exists()
    assert library.exists()
    assert sentinel.read_text(encoding="ascii") == "keep\n"


def test_windows_appctl_uninstall_rejects_dangling_prefix_reparse_without_mutation(tmp_path: Path):
    prefix = tmp_path / "dangling-prefix"
    outside = tmp_path / "missing-prefix-target"
    create_dangling_directory_link(prefix, outside)
    local_sentinel = tmp_path / "local-sentinel.txt"
    local_sentinel.write_text("keep\n", encoding="ascii")
    library = tmp_path / "library"
    library.mkdir()
    private = library / "private.txt"
    private.write_text("keep\n", encoding="ascii")

    result = run_appctl(
        prefix,
        "uninstall",
        environment_overrides={"IMAGE_PROMPT_LIBRARY_PATH": str(library)},
    )

    assert result.returncode == 1
    assert "reparse" in result.stderr.lower()
    assert_windows_reparse_entry(prefix)
    assert not outside.exists()
    assert local_sentinel.read_text(encoding="ascii") == "keep\n"
    assert private.read_text(encoding="ascii") == "keep\n"


def test_windows_appctl_uninstall_rejects_dangling_library_reparse_without_mutation(tmp_path: Path):
    prefix = tmp_path / "prefix"
    (prefix / "bin").mkdir(parents=True)
    shim = prefix / "bin" / "image-prompt-library.ps1"
    shim.write_text("shim\n", encoding="ascii")
    library = tmp_path / "dangling-library"
    outside = tmp_path / "missing-library-target"
    create_dangling_directory_link(library, outside)
    (prefix / ".env").write_text(f"IMAGE_PROMPT_LIBRARY_PATH={library}\n", encoding="ascii")
    local_sentinel = tmp_path / "local-sentinel.txt"
    local_sentinel.write_text("keep\n", encoding="ascii")

    result = run_appctl(prefix, "uninstall", "--delete-library", "--yes")

    assert result.returncode == 1
    assert "reparse" in result.stderr.lower()
    assert shim.read_text(encoding="ascii") == "shim\n"
    assert not (prefix / "run").exists()
    assert_windows_reparse_entry(library)
    assert not outside.exists()
    assert local_sentinel.read_text(encoding="ascii") == "keep\n"


def test_windows_appctl_uninstall_safe_working_directory_failure_is_nonmutating(tmp_path: Path):
    prefix = tmp_path / "prefix"
    library = tmp_path / "library"
    write_uninstall_layout(prefix, library)
    appctl = powershell_literal(ROOT / "scripts" / "appctl.ps1")
    original_text = f"Keep;{prefix / 'bin'};Tail"
    path_state = tmp_path / "path-state.txt"
    script = f"""
$original = [Environment]::GetEnvironmentVariable("Path", "User")
try {{
    [Environment]::SetEnvironmentVariable("Path", {powershell_literal(original_text)}, "User")
    $env:IMAGE_PROMPT_LIBRARY_PREFIX = {powershell_literal(prefix)}
    $env:IMAGE_PROMPT_LIBRARY_PATH = {powershell_literal(library)}
    $env:SystemRoot = "Z:\\missing-system-root"
    & {appctl} uninstall
}} finally {{
    $after = [Environment]::GetEnvironmentVariable("Path", "User")
    [IO.File]::WriteAllText({powershell_literal(path_state)}, $after, [Text.Encoding]::UTF8)
    [Environment]::SetEnvironmentVariable("Path", $original, "User")
}}
"""

    result = run_powershell(script)

    assert result.returncode == 1
    assert path_state.read_text(encoding="utf-8-sig") == original_text
    assert not (prefix / "run").exists()
    assert (prefix / "bin" / "image-prompt-library.ps1").is_file()
    assert (library / "private.txt").is_file()


def test_windows_appctl_uninstall_reports_partial_library_delete_failure(tmp_path: Path):
    prefix = tmp_path / "prefix"
    library = tmp_path / "library"
    write_uninstall_layout(prefix, library)
    appctl = powershell_literal(ROOT / "scripts" / "appctl.ps1")
    script = f"""
$env:IMAGE_PROMPT_LIBRARY_PREFIX = {powershell_literal(prefix)}
$env:IMAGE_PROMPT_LIBRARY_PATH = {powershell_literal(library)}
$lock = [IO.File]::Open({powershell_literal(library / "private.txt")}, [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
try {{
    & powershell.exe -NoProfile -File {appctl} uninstall --delete-library --yes
    $code = $LASTEXITCODE
    [pscustomobject]@{{ code = $code; app_exists = [IO.Directory]::Exists({powershell_literal(prefix)}); library_exists = [IO.Directory]::Exists({powershell_literal(library)}); private_exists = [IO.File]::Exists({powershell_literal(library / "private.txt")}) }} | ConvertTo-Json -Compress
}} finally {{
    $lock.Dispose()
}}
"""

    result = run_powershell(script)

    assert result.returncode == 0
    assert json.loads(result.stdout.strip().splitlines()[-1]) == {
        "code": 1,
        "app_exists": False,
        "library_exists": True,
        "private_exists": True,
    }
    assert f"Application removed at {prefix.resolve()}." in result.stdout
    assert "application removal succeeded, but private library removal failed" in result.stderr.lower()


def test_windows_appctl_uninstall_works_when_invoked_inside_prefix(tmp_path: Path):
    prefix = tmp_path / "prefix"
    library = tmp_path / "library"
    write_uninstall_layout(prefix, library)
    working_directory = prefix / "app" / "nested"
    working_directory.mkdir(parents=True)

    result = run_appctl(prefix, "uninstall", cwd=working_directory)

    assert result.returncode == 0, result.stderr
    assert not prefix.exists()
    assert (library / "private.txt").is_file()


def test_windows_appctl_uninstall_removes_only_matching_user_path_entry(tmp_path: Path):
    prefix = tmp_path / "prefix"
    library = tmp_path / "library"
    write_uninstall_layout(prefix, library)
    appctl = powershell_literal(ROOT / "scripts" / "appctl.ps1")
    unmatched = tmp_path / "other" / ".." / "other-bin"
    original_text = f'Alpha;;"{unmatched}";bad|entry;"{prefix / "bin"}";'
    script = f"""
$original = [Environment]::GetEnvironmentVariable("Path", "User")
try {{
    [Environment]::SetEnvironmentVariable("Path", {powershell_literal(original_text)}, "User")
    $env:IMAGE_PROMPT_LIBRARY_PREFIX = {powershell_literal(prefix)}
    $env:IMAGE_PROMPT_LIBRARY_PATH = {powershell_literal(library)}
    & powershell.exe -NoProfile -File {appctl} uninstall
    $code = $LASTEXITCODE
    $after = [Environment]::GetEnvironmentVariable("Path", "User")
    [pscustomobject]@{{ code = $code; path = $after }} | ConvertTo-Json -Compress
}} finally {{
    [Environment]::SetEnvironmentVariable("Path", $original, "User")
}}
"""

    result = run_powershell(script)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload == {"code": 0, "path": f'Alpha;;"{unmatched}";bad|entry;'}


def test_windows_appctl_uninstall_stops_an_owned_runtime_before_removing_app(tmp_path: Path):
    prefix = tmp_path / "prefix"
    library = tmp_path / "library"
    write_uninstall_layout(prefix, library)
    appctl = powershell_literal(ROOT / "scripts" / "appctl.ps1")
    script = f"""
$env:IMAGE_PROMPT_LIBRARY_PREFIX = {powershell_literal(prefix)}
$env:IMAGE_PROMPT_LIBRARY_PATH = {powershell_literal(library)}
$child = $null
try {{
    $child = Start-Process -FilePath (Join-Path $PSHOME "powershell.exe") -ArgumentList @("-NoProfile", "-Command", "Start-Sleep -Seconds 120") -WindowStyle Hidden -PassThru
    $child.Refresh()
    $startTime = $child.StartTime.ToUniversalTime()
    $record = [pscustomobject][ordered]@{{
        pid = $child.Id
        process_start_time_utc = $startTime.ToString("o")
        process_start_time_utc_ticks = $startTime.Ticks
        process_executable_path = $child.Path
        version = "test"
        app_root = {powershell_literal(prefix)}
        host = "127.0.0.1"
        port = 65534
        stdout_log = {powershell_literal(prefix / "out.log")}
        stderr_log = {powershell_literal(prefix / "err.log")}
        created_at = [DateTime]::UtcNow.ToString("o")
    }}
    New-Item -ItemType Directory -Path {powershell_literal(prefix / "run")} -Force | Out-Null
    [IO.File]::WriteAllText((Join-Path {powershell_literal(prefix / "run")} "server.json"), ($record | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
    & powershell.exe -NoProfile -File {appctl} uninstall
    $code = $LASTEXITCODE
    $child.Refresh()
    [pscustomobject]@{{ code = $code; exited = $child.HasExited; app_exists = [IO.Directory]::Exists({powershell_literal(prefix)}); library_exists = [IO.Directory]::Exists({powershell_literal(library)}) }} | ConvertTo-Json -Compress
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
    assert json.loads(result.stdout.strip().splitlines()[-1]) == {
        "code": 0,
        "exited": True,
        "app_exists": False,
        "library_exists": True,
    }


def test_windows_appctl_uninstall_retains_conflicting_runtime_and_targets(tmp_path: Path):
    prefix = tmp_path / "prefix"
    library = tmp_path / "library"
    write_uninstall_layout(prefix, library)
    appctl = powershell_literal(ROOT / "scripts" / "appctl.ps1")
    script = f"""
$env:IMAGE_PROMPT_LIBRARY_PREFIX = {powershell_literal(prefix)}
$env:IMAGE_PROMPT_LIBRARY_PATH = {powershell_literal(library)}
$child = $null
try {{
    $child = Start-Process -FilePath (Join-Path $PSHOME "powershell.exe") -ArgumentList @("-NoProfile", "-Command", "Start-Sleep -Seconds 120") -WindowStyle Hidden -PassThru
    $child.Refresh()
    $wrongStartTime = $child.StartTime.ToUniversalTime().AddTicks(1)
    $record = [pscustomobject][ordered]@{{
        pid = $child.Id
        process_start_time_utc = $wrongStartTime.ToString("o")
        process_start_time_utc_ticks = $wrongStartTime.Ticks
        process_executable_path = $child.Path
        version = "test"
        app_root = {powershell_literal(prefix)}
        host = "127.0.0.1"
        port = 65534
        stdout_log = {powershell_literal(prefix / "out.log")}
        stderr_log = {powershell_literal(prefix / "err.log")}
        created_at = [DateTime]::UtcNow.ToString("o")
    }}
    New-Item -ItemType Directory -Path {powershell_literal(prefix / "run")} -Force | Out-Null
    [IO.File]::WriteAllText((Join-Path {powershell_literal(prefix / "run")} "server.json"), ($record | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
    & powershell.exe -NoProfile -File {appctl} uninstall
    $code = $LASTEXITCODE
    $child.Refresh()
    [pscustomobject]@{{ code = $code; child_alive = -not $child.HasExited; app_exists = [IO.Directory]::Exists({powershell_literal(prefix)}); library_exists = [IO.Directory]::Exists({powershell_literal(library)}) }} | ConvertTo-Json -Compress
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
    assert json.loads(result.stdout.strip().splitlines()[-1]) == {
        "code": 1,
        "child_alive": True,
        "app_exists": True,
        "library_exists": True,
    }


def test_windows_appctl_uninstall_does_not_follow_junction(tmp_path: Path):
    prefix = tmp_path / "prefix"
    library = tmp_path / "library"
    write_uninstall_layout(prefix, library)
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_text("keep", encoding="ascii")
    junction = prefix / "junction"
    created = run_powershell(
        f"New-Item -ItemType Junction -Path {powershell_literal(junction)} -Target {powershell_literal(outside)} -ErrorAction Stop | Out-Null"
    )
    if created.returncode != 0:
        pytest.skip(f"Windows junction creation unavailable: {created.stderr.strip()}")

    result = run_appctl(prefix, "uninstall")

    assert result.returncode == 0, result.stderr
    assert not prefix.exists()
    assert sentinel.read_text(encoding="ascii") == "keep"


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
    assert start_section.index("New-ProcessLease -Process $process") < start_section.index(
        "Get-StartedProcessIdentity -Process $processLease.Process"
    )
    assert "$Process.StartTime.ToUniversalTime()" in script.split(
        "function Get-StartedProcessIdentity", 1
    )[1].split("function ", 1)[0]
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
    assert "hashlib.sha256" in script
    assert "fileobj=artifact_file" in script
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


def test_windows_installer_hardens_identity_and_cleanup_boundaries():
    script = read("scripts/install.ps1")

    assert "Get-FileHash" not in script
    assert "$Path.tmp" not in script
    assert "-Recurse" not in script


def test_windows_installer_rejects_github_release_assets_on_nondefault_port():
    asset_names = (
        "image-prompt-library-v1.2.3.tar.gz",
        "image-prompt-library-v1.2.3.tar.gz.sha256",
        "image-prompt-library-v1.2.3.manifest.json",
    )
    assets = ",".join(
        "[pscustomobject]@{ name = '"
        + name
        + "'; browser_download_url = 'https://github.com:444/EddieTYP/image-prompt-library/releases/download/v1.2.3/"
        + name
        + "' }"
        for name in asset_names
    )

    result = run_installer_function(
        f"New-ReleaseSpec -Tag 'v1.2.3' -BaseUrl '' -Assets @({assets})"
    )

    assert result.returncode == 1
    assert "release download origin" in result.stderr.lower()


@pytest.mark.parametrize(
    "pointer_value",
    ["v1.2.3.", "v1.2.3 ", "v1.2.3.backup.", "v1.2.3.backup "],
)
def test_windows_installer_generated_shim_rejects_windows_version_aliases(
    tmp_path: Path, pointer_value: str
):
    release_dir = tmp_path / "release"
    prefix = tmp_path / "prefix"
    write_test_release(release_dir)
    installed = run_installer(release_dir, prefix, tmp_path / "library")
    assert installed.returncode == 0, installed.stderr
    (prefix / "app" / "current-version").write_text(pointer_value + "\n", encoding="ascii")

    result = subprocess.run(
        [
            powershell_executable(),
            "-NoProfile",
            "-File",
            str(prefix / "bin" / "image-prompt-library.ps1"),
            "status",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 1
    assert "current version pointer is invalid" in result.stderr.lower()


def test_windows_installer_generated_shim_handles_power_shell_only_success(tmp_path: Path):
    prefix = tmp_path / "prefix"
    scripts = prefix / "app" / "versions" / "v1.0.0" / "scripts"
    scripts.mkdir(parents=True)
    (prefix / "app" / "current-version").write_text("v1.0.0\n", encoding="ascii")
    (scripts / "appctl.ps1").write_text(
        "param([Parameter(ValueFromRemainingArguments=$true)][string[]]$CommandArgs)\n"
        "Write-Output ($CommandArgs -join ',')\n",
        encoding="ascii",
    )
    generated = run_installer_function(
        f"Write-CommandShim -BinPath {powershell_literal(prefix / 'bin')}"
    )
    assert generated.returncode == 0, generated.stdout + generated.stderr

    result = subprocess.run(
        [
            powershell_executable(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(prefix / "bin" / "image-prompt-library.ps1"),
            "version",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "version"


def test_windows_installer_generated_shim_does_not_leak_handled_native_exit(
    tmp_path: Path,
):
    prefix = tmp_path / "prefix"
    scripts = prefix / "app" / "versions" / "v1.0.0" / "scripts"
    scripts.mkdir(parents=True)
    (prefix / "app" / "current-version").write_text("v1.0.0\n", encoding="ascii")
    (scripts / "appctl.ps1").write_text(
        "param([Parameter(ValueFromRemainingArguments=$true)][string[]]$CommandArgs)\n"
        "if ($CommandArgs -contains 'fail') { exit 2 }\n"
        "& $env:ComSpec /d /c exit 7\n"
        "Write-Output ($CommandArgs -join ',')\n",
        encoding="ascii",
    )
    generated = run_installer_function(
        f"Write-CommandShim -BinPath {powershell_literal(prefix / 'bin')}"
    )
    assert generated.returncode == 0, generated.stdout + generated.stderr

    result = subprocess.run(
        [
            powershell_executable(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(prefix / "bin" / "image-prompt-library.ps1"),
            "status",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "status"

    failed = subprocess.run(
        [
            powershell_executable(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(prefix / "bin" / "image-prompt-library.ps1"),
            "fail",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert failed.returncode == 2, failed.stdout + failed.stderr


def test_windows_installer_rejects_drive_root_containing_prefix(tmp_path: Path):
    drive_root = Path(tmp_path.anchor)

    result = run_installer(tmp_path / "missing", tmp_path / "prefix", drive_root)

    assert result.returncode == 1
    assert "must not contain each other" in result.stderr.lower()


def test_windows_installer_rejects_unc_root_containing_prefix():
    result = run_installer_function(
        "Assert-DisjointPaths -AppPrefix '\\\\server\\share\\prefix' -PrivateLibrary '\\\\server\\share\\'"
    )

    assert result.returncode == 1
    assert "must not contain each other" in result.stderr.lower()


@pytest.mark.parametrize(
    "unsafe_name",
    [
        "CON",
        "CON.txt",
        "folder:stream.txt",
        "trailing-dot.",
        "trailing-space ",
        "other-root/VERSION",
        "VERSION",
        "Version",
        "backend",
    ],
)
def test_windows_installer_rejects_ambiguous_windows_archive_names(
    tmp_path: Path, unsafe_name: str
):
    release_dir = tmp_path / "release"
    write_test_release(release_dir, extra_members=(("file", unsafe_name),))

    result = run_installer(release_dir, tmp_path / "prefix", tmp_path / "library")

    assert result.returncode == 1
    assert "refusing" in result.stderr.lower()
    assert not (tmp_path / "prefix" / "app" / "versions" / "v1.2.3").exists()


@pytest.mark.parametrize("version", ["CON", "con.txt", "v1.2.3.", "v1.2.3.backup"])
def test_windows_installer_rejects_canonical_version_aliases(tmp_path: Path, version: str):
    result = run_installer(
        tmp_path / "missing release", tmp_path / "prefix", tmp_path / "library", version=version
    )

    assert result.returncode == 1
    assert "release version is invalid" in result.stderr.lower()
    assert not (tmp_path / "prefix").exists()


def test_windows_installer_rolls_back_late_publication_and_start_failure(tmp_path: Path):
    release_dir = tmp_path / "release"
    write_test_release(release_dir, start_failure=True)
    prefix = tmp_path / "prefix"
    library = tmp_path / "library"
    old_target = prefix / "app" / "versions" / "v1.0.0"
    old_target.mkdir(parents=True)
    write_running_test_controller(old_target, host="127.0.0.5", port=4231)
    (old_target / "keep.txt").write_text("old runtime", encoding="ascii")
    app = prefix / "app"
    (app / "current-version").write_text("v1.0.0\n", encoding="ascii")
    (app / "previous-version").write_text("v0.9.0\n", encoding="ascii")
    prefix.mkdir(exist_ok=True)
    (prefix / ".env").write_text("old env\n", encoding="ascii")
    (prefix / "bin").mkdir()
    (prefix / "bin" / "image-prompt-library.ps1").write_text("old ps1\n", encoding="ascii")
    (prefix / "bin" / "image-prompt-library.cmd").write_text("old cmd\n", encoding="ascii")

    result = run_installer(
        release_dir, prefix, library, no_start=False
    )

    assert result.returncode == 1
    assert "intentional start failure" in result.stderr
    assert "Automatic recovery restored v1.0.0." in result.stdout
    commands = (old_target / "scripts" / "commands.log").read_text(encoding="ascii").splitlines()
    assert "start --host 127.0.0.5 --port 4231 --no-browser" in commands
    assert (old_target / "keep.txt").read_text(encoding="ascii") == "old runtime"
    assert (app / "current-version").read_text(encoding="ascii") == "v1.0.0\n"
    assert (app / "previous-version").read_text(encoding="ascii") == "v0.9.0\n"
    assert (prefix / ".env").read_text(encoding="ascii") == "old env\n"
    assert (prefix / "bin" / "image-prompt-library.ps1").read_text(encoding="ascii") == "old ps1\n"
    assert (prefix / "bin" / "image-prompt-library.cmd").read_text(encoding="ascii") == "old cmd\n"
    assert not (app / "versions" / "v1.2.3").exists()
    assert not (app / "versions" / "v1.2.3.backup").exists()


def test_windows_installer_restores_published_state_when_target_cleanup_fails(tmp_path: Path):
    release_dir = tmp_path / "release"
    write_test_release(release_dir, locked_start_failure=True, lock_backup_during_setup=True)
    prefix = tmp_path / "prefix"
    library = tmp_path / "library"
    app = prefix / "app"
    old_target = app / "versions" / "v1.0.0"
    old_target.mkdir(parents=True)
    write_running_test_controller(old_target)
    (old_target / "keep.txt").write_text("old runtime", encoding="ascii")
    (app / "current-version").write_text("v1.0.0\n", encoding="ascii")
    (app / "previous-version").write_text("v0.9.0\n", encoding="ascii")
    prefix.mkdir(exist_ok=True)
    (prefix / ".env").write_text("old env\n", encoding="ascii")
    (prefix / "bin").mkdir()
    (prefix / "bin" / "image-prompt-library.ps1").write_text("old ps1\n", encoding="ascii")
    (prefix / "bin" / "image-prompt-library.cmd").write_text("old cmd\n", encoding="ascii")
    replaced_target = app / "versions" / "v1.2.3"
    replaced_target.mkdir()
    (replaced_target / "locked.txt").write_text("locked old target", encoding="ascii")

    result = run_installer(release_dir, prefix, library, no_start=False)

    assert result.returncode == 1
    assert "intentional locked start failure" in result.stderr
    assert "Rollback failed" in result.stderr
    assert (app / "current-version").read_text(encoding="ascii") == "v1.0.0\n"
    assert (app / "previous-version").read_text(encoding="ascii") == "v0.9.0\n"
    assert (prefix / ".env").read_text(encoding="ascii") == "old env\n"
    assert (prefix / "bin" / "image-prompt-library.ps1").read_text(encoding="ascii") == "old ps1\n"
    assert (prefix / "bin" / "image-prompt-library.cmd").read_text(encoding="ascii") == "old cmd\n"


def test_windows_installer_does_not_rollback_after_backup_cleanup_failure(tmp_path: Path):
    release_dir = tmp_path / "release"
    write_test_release(release_dir, lock_backup_during_setup=True)
    prefix = tmp_path / "prefix"
    library = tmp_path / "library"
    app = prefix / "app"
    replaced_target = app / "versions" / "v1.2.3"
    replaced_target.mkdir(parents=True)
    locked_file = replaced_target / "locked.txt"
    locked_file.write_text("locked old target", encoding="ascii")
    old_target = app / "versions" / "v1.0.0"
    old_target.mkdir()
    write_stopped_test_controller(old_target)
    (app / "current-version").write_text("v1.0.0\n", encoding="ascii")
    result = run_installer(release_dir, prefix, library)

    assert result.returncode == 0, result.stderr
    assert (app / "current-version").read_text(encoding="ascii").strip() == "v1.2.3"
    assert (replaced_target / "setup-called.txt").is_file()
    assert (app / "versions" / "v1.2.3.backup" / "locked.txt").is_file()


def test_windows_installer_same_version_reinstall_preserves_previous_pointer(tmp_path: Path):
    release_dir = tmp_path / "release"
    prefix = tmp_path / "prefix"
    library = tmp_path / "library"
    write_test_release(release_dir)
    first = run_installer(release_dir, prefix, library)
    assert first.returncode == 0, first.stderr
    previous = prefix / "app" / "previous-version"
    previous.write_text("v1.0.0\n", encoding="ascii")

    second = run_installer(release_dir, prefix, library)

    assert second.returncode == 0, second.stderr
    assert previous.read_text(encoding="ascii") == "v1.0.0\n"


def test_windows_installer_preserves_user_path_text_when_appending(tmp_path: Path):
    release_dir = tmp_path / "release"
    prefix = tmp_path / "prefix"
    library = tmp_path / "library"
    write_test_release(release_dir)
    installer = powershell_literal(ROOT / "scripts" / "install.ps1")
    release = powershell_literal(release_dir)
    prefix_literal = powershell_literal(prefix)
    library_literal = powershell_literal(library)
    python_literal = powershell_literal(shutil.which("python.exe") or shutil.which("python") or "python")
    script = f"""
$original = [Environment]::GetEnvironmentVariable("Path", "User")
try {{
    [Environment]::SetEnvironmentVariable("Path", "Alpha;;Beta;", "User")
    & powershell.exe -NoProfile -File {installer} -Version v1.2.3 -Prefix {prefix_literal} -LibraryPath {library_literal} -ReleaseBaseUrl {release} -PythonExe {python_literal} -NoStart
    $code = $LASTEXITCODE
    $after = [Environment]::GetEnvironmentVariable("Path", "User")
    [pscustomobject]@{{ code = $code; path = $after }} | ConvertTo-Json -Compress
}} finally {{
    [Environment]::SetEnvironmentVariable("Path", $original, "User")
}}
"""

    result = run_powershell(script)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["code"] == 0
    assert payload["path"] == f"Alpha;;Beta;;{(prefix / 'bin').resolve()}"


def test_windows_installer_preserves_malformed_user_path_entries(tmp_path: Path):
    release_dir = tmp_path / "release"
    prefix = tmp_path / "prefix"
    library = tmp_path / "library"
    write_test_release(release_dir)
    installer = powershell_literal(ROOT / "scripts" / "install.ps1")
    release = powershell_literal(release_dir)
    prefix_literal = powershell_literal(prefix)
    library_literal = powershell_literal(library)
    python_literal = powershell_literal(shutil.which("python.exe") or shutil.which("python") or "python")
    quoted_noncanonical_target = prefix / "other" / ".." / "bin"
    original_text = f'Alpha;;"{quoted_noncanonical_target}";bad|entry;'
    script = f"""
$original = [Environment]::GetEnvironmentVariable("Path", "User")
try {{
    [Environment]::SetEnvironmentVariable("Path", {powershell_literal(original_text)}, "User")
    & powershell.exe -NoProfile -File {installer} -Version v1.2.3 -Prefix {prefix_literal} -LibraryPath {library_literal} -ReleaseBaseUrl {release} -PythonExe {python_literal} -NoStart
    $code = $LASTEXITCODE
    $after = [Environment]::GetEnvironmentVariable("Path", "User")
    [pscustomobject]@{{ code = $code; path = $after }} | ConvertTo-Json -Compress
}} finally {{
    [Environment]::SetEnvironmentVariable("Path", $original, "User")
}}
"""

    result = run_powershell(script)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["code"] == 0
    assert payload["path"] == original_text


def write_test_release(
    release_dir: Path,
    version: str = "v1.2.3",
    *,
    capabilities: tuple[str, ...] = ("windows-powershell-v1",),
    unsafe_member: tuple[str, bytes | str] | None = None,
    extra_members: tuple[tuple[str, str], ...] = (),
    manifest_sha: str | None = None,
    checksum_sha: str | None = None,
    start_failure: bool = False,
    locked_start_failure: bool = False,
    lock_backup_during_setup: bool = False,
    setup_delay_ms: int = 0,
) -> None:
    release_dir.mkdir(parents=True)
    artifact_name = f"image-prompt-library-{version}.tar.gz"
    artifact = release_dir / artifact_name
    files = {
        "VERSION": version,
        "pyproject.toml": "[project]\nname='image-prompt-library'\nversion='1.2.3'\n",
        "backend/main.py": "app = None\n",
        "frontend/dist/index.html": "<!doctype html>\n",
        "scripts/appctl.ps1": (
            "$global:testLock = [IO.File]::Open((Join-Path $PSScriptRoot 'locked.bin'), 'OpenOrCreate', 'ReadWrite', 'None')\n"
            "if ($args -contains 'start') { throw 'intentional locked start failure' }\n"
            if locked_start_failure
            else (
                "if ($args -contains 'start') { throw 'intentional start failure' }\n"
                if start_failure
                else "Write-Output ($args -join ' ')\n"
            )
        ),
        "scripts/install.ps1": "# packaged installer\n",
        "scripts/install-sample-data.ps1": "# packaged sample installer\n",
        "scripts/setup-runtime.ps1": (
            "param([string]$AppRoot,[string]$PythonExe,[string[]]$PythonPrefixArgs=@())\n"
            "Set-Content -LiteralPath (Join-Path $AppRoot 'setup-called.txt') -Value $AppRoot -Encoding ASCII\n"
            + (
                "$global:testBackupLock = [IO.File]::Open((Join-Path ($AppRoot + '.backup') 'locked.txt'), 'Open', 'Read', 'None')\n"
                if lock_backup_during_setup
                else ""
            )
            + (f"Start-Sleep -Milliseconds {setup_delay_ms}\n" if setup_delay_ms else "")
        ),
    }
    with tarfile.open(artifact, "w:gz") as archive:
        for name, content in files.items():
            source = release_dir / "payload" / Path(name)
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(content, encoding="ascii")
            archive.add(source, arcname=name)
        if unsafe_member:
            kind, name = unsafe_member
            member = tarfile.TarInfo(str(name))
            if kind in {"symlink", "hardlink"}:
                member.type = tarfile.SYMTYPE if kind == "symlink" else tarfile.LNKTYPE
                member.linkname = "VERSION"
                archive.addfile(member)
            elif kind == "fifo":
                member.type = tarfile.FIFOTYPE
                archive.addfile(member)
            else:
                data = b"unsafe"
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
        for kind, name in extra_members:
            member = tarfile.TarInfo(str(name))
            if kind == "directory":
                member.type = tarfile.DIRTYPE
                archive.addfile(member)
            else:
                data = b"extra"
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))

    calculated_sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
    manifest = {
        "name": "image-prompt-library",
        "version": version,
        "artifact": artifact_name,
        "capabilities": list(capabilities),
        "sha256": manifest_sha or calculated_sha,
    }
    (release_dir / f"image-prompt-library-{version}.manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    (release_dir / f"{artifact_name}.sha256").write_text(
        f"{checksum_sha or calculated_sha}  {artifact_name}\n", encoding="ascii"
    )


def write_stopped_test_controller(version_root: Path) -> None:
    controller = version_root / "scripts" / "appctl.ps1"
    controller.parent.mkdir(exist_ok=True)
    controller.write_text(
        "if ($args -contains 'internal-owned-runtime') { Write-Output '{\"running\":false,\"host\":null,\"port\":null}'; exit 0 }\n"
        "Write-Output ($args -join ' ')\n",
        encoding="ascii",
    )


def write_running_test_controller(
    version_root: Path, host: str = "127.0.0.1", port: int = 8000
) -> None:
    controller = version_root / "scripts" / "appctl.ps1"
    controller.parent.mkdir(exist_ok=True)
    controller.write_text(
        "$args -join ' ' | Add-Content -LiteralPath (Join-Path $PSScriptRoot 'commands.log')\n"
        f"if ($args -contains 'internal-owned-runtime') {{ Write-Output '{{\"running\":true,\"host\":\"{host}\",\"port\":{port}}}'; exit 0 }}\n"
        "Write-Output ($args -join ' ')\n",
        encoding="ascii",
    )


def run_installer(
    release_dir: Path,
    prefix: Path,
    library: Path,
    version: str = "v1.2.3",
    *,
    environment: dict[str, str] | None = None,
    no_start: bool = True,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if environment:
        env.update(environment)
    arguments = [
            powershell_executable(),
            "-NoProfile",
            "-File",
            str(ROOT / "scripts" / "install.ps1"),
            "-Version",
            version,
            "-Prefix",
            str(prefix),
            "-LibraryPath",
            str(library),
            "-ReleaseBaseUrl",
            str(release_dir),
            "-PythonExe",
            shutil.which("python.exe") or shutil.which("python") or "python",
        ]
    if no_start:
        arguments.append("-NoStart")
    arguments.append("-SkipPath")
    return subprocess.run(
        arguments,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def test_windows_installer_serializes_concurrent_publication(tmp_path: Path):
    release_dir = tmp_path / "release"
    prefix = tmp_path / "prefix"
    library = tmp_path / "library"
    write_test_release(release_dir, setup_delay_ms=750)
    arguments = [
        powershell_executable(),
        "-NoProfile",
        "-File",
        str(ROOT / "scripts" / "install.ps1"),
        "-Version",
        "v1.2.3",
        "-Prefix",
        str(prefix),
        "-LibraryPath",
        str(library),
        "-ReleaseBaseUrl",
        str(release_dir),
        "-PythonExe",
        shutil.which("python.exe") or shutil.which("python") or "python",
        "-NoStart",
        "-SkipPath",
    ]
    processes = [
        subprocess.Popen(arguments, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for _ in range(2)
    ]

    results = [process.communicate(timeout=30) + (process.returncode,) for process in processes]

    assert [result[2] for result in results] == [0, 0], results
    assert (prefix / "app" / "current-version").read_text(encoding="ascii").strip() == "v1.2.3"
    assert (prefix / "app" / "versions" / "v1.2.3" / "setup-called.txt").is_file()
    assert not any(path.name.endswith((".tmp", ".tmp.bak")) for path in prefix.rglob("*"))


def test_windows_installer_cleanup_does_not_follow_junction(tmp_path: Path):
    prefix = tmp_path / "prefix"
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_text("keep", encoding="ascii")
    junction = prefix / "cleanup-target"
    junction.parent.mkdir()
    created = run_powershell(
        f"New-Item -ItemType Junction -Path {powershell_literal(junction)} -Target {powershell_literal(outside)} -ErrorAction Stop | Out-Null"
    )
    if created.returncode != 0:
        pytest.skip(f"Windows junction creation unavailable: {created.stderr.strip()}")

    result = run_installer_function(
        f"Remove-ValidatedTree -Target {powershell_literal(junction)} -AppPrefix {powershell_literal(prefix)}"
    )

    assert result.returncode == 0, result.stderr
    assert not junction.exists()
    assert sentinel.read_text(encoding="ascii") == "keep"


def test_windows_installer_places_runtime_then_publishes_shim_and_pointers(tmp_path: Path):
    release_dir = tmp_path / "release files"
    prefix = tmp_path / "app prefix"
    library = tmp_path / "private library"
    write_test_release(release_dir)

    result = run_installer(
        release_dir,
        prefix,
        library,
        environment={"BACKEND_HOST": "localhost", "BACKEND_PORT": "8123"},
    )

    assert result.returncode == 0, result.stderr
    final = prefix / "app" / "versions" / "v1.2.3"
    assert (final / "setup-called.txt").read_text(encoding="ascii").strip() == str(final)
    assert (prefix / "app" / "current-version").read_text(encoding="ascii").strip() == "v1.2.3"
    assert not (prefix / "app" / "previous-version").exists()
    assert (prefix / "bin" / "image-prompt-library.ps1").is_file()
    assert (prefix / "bin" / "image-prompt-library.cmd").is_file()
    assert not any(path.name.startswith(".staging-") for path in final.parent.iterdir())
    assert (prefix / ".env").read_text(encoding="ascii").splitlines() == [
        f"IMAGE_PROMPT_LIBRARY_PATH={library.resolve()}",
        "BACKEND_HOST=localhost",
        "BACKEND_PORT=8123",
        f"BACKUP_DIR={(prefix / 'backups').resolve()}",
    ]


@pytest.mark.parametrize(
    ("manifest_sha", "checksum_sha"),
    [
        ("0" * 64, None),
        (None, "f" * 64),
        ("a" * 64, "a" * 64),
    ],
)
def test_windows_installer_requires_three_way_checksum_agreement(
    tmp_path: Path, manifest_sha: str | None, checksum_sha: str | None
):
    release_dir = tmp_path / "release"
    write_test_release(release_dir, manifest_sha=manifest_sha, checksum_sha=checksum_sha)

    result = run_installer(release_dir, tmp_path / "prefix", tmp_path / "library")

    assert result.returncode == 1
    assert "checksum" in result.stderr.lower()
    assert not (tmp_path / "prefix" / "app" / "versions" / "v1.2.3").exists()


def test_windows_installer_rejects_legacy_release_without_native_capability(tmp_path: Path):
    release_dir = tmp_path / "legacy release"
    write_test_release(release_dir, version="v0.7.10", capabilities=())

    result = run_installer(
        release_dir, tmp_path / "prefix", tmp_path / "library", version="v0.7.10"
    )

    assert result.returncode == 1
    assert "windows-powershell-v1" in result.stderr
    assert not (tmp_path / "prefix" / "app" / "versions" / "v0.7.10").exists()


@pytest.mark.parametrize(
    "unsafe_member",
    [
        ("file", "/absolute.txt"),
        ("file", "C:/drive-qualified.txt"),
        ("file", "//server/share/unc.txt"),
        ("file", "../escaped.txt"),
        ("symlink", "linked.txt"),
        ("hardlink", "hard-linked.txt"),
        ("fifo", "reparse-like"),
        ("file", ".venv/Scripts/python.exe"),
    ],
)
def test_windows_installer_rejects_unsafe_archive_members(
    tmp_path: Path, unsafe_member: tuple[str, str]
):
    release_dir = tmp_path / "release"
    write_test_release(release_dir, unsafe_member=unsafe_member)
    prefix = tmp_path / "prefix"

    result = run_installer(release_dir, prefix, tmp_path / "library")

    assert result.returncode == 1
    assert "refusing" in result.stderr.lower()
    assert not (tmp_path / "escaped.txt").exists()
    assert not (prefix / "app" / "versions" / "v1.2.3").exists()


def test_windows_installer_restores_existing_target_when_runtime_setup_fails(tmp_path: Path):
    release_dir = tmp_path / "release"
    write_test_release(release_dir)
    failing_setup = release_dir / "payload" / "scripts" / "setup-runtime.ps1"
    failing_setup.write_text("throw 'intentional setup failure'\n", encoding="ascii")
    artifact = release_dir / "image-prompt-library-v1.2.3.tar.gz"
    with tarfile.open(artifact, "w:gz") as archive:
        for source in (release_dir / "payload").rglob("*"):
            if source.is_file():
                archive.add(source, arcname=source.relative_to(release_dir / "payload").as_posix())
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    manifest_path = release_dir / "image-prompt-library-v1.2.3.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sha256"] = digest
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    (release_dir / "image-prompt-library-v1.2.3.tar.gz.sha256").write_text(
        f"{digest}  image-prompt-library-v1.2.3.tar.gz\n", encoding="ascii"
    )
    prefix = tmp_path / "prefix"
    stale_target = prefix / "app" / "versions" / "v1.2.3"
    stale_target.mkdir(parents=True)
    (stale_target / "keep.txt").write_text("original", encoding="ascii")
    pointer = prefix / "app" / "current-version"
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text("v1.0.0\n", encoding="ascii")

    result = run_installer(release_dir, prefix, tmp_path / "library")

    assert result.returncode == 1
    assert "intentional setup failure" in result.stderr
    assert (stale_target / "keep.txt").read_text(encoding="ascii") == "original"
    assert pointer.read_text(encoding="ascii").strip() == "v1.0.0"
    assert not (prefix / "app" / "versions" / "v1.2.3.backup").exists()


def test_windows_installer_direct_errors_nonzero_but_irm_iex_style_returns(tmp_path: Path):
    shared = tmp_path / "same root"
    direct = subprocess.run(
        [
            powershell_executable(),
            "-NoProfile",
            "-File",
            str(ROOT / "scripts" / "install.ps1"),
            "-Prefix",
            str(shared),
            "-LibraryPath",
            str(shared),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    piped_script = f"""
$env:LOCALAPPDATA = {powershell_literal(shared.parent)}
$env:USERPROFILE = {powershell_literal(shared.parent)}
Invoke-Expression ([IO.File]::ReadAllText({powershell_literal(ROOT / 'scripts' / 'install.ps1')}))
Write-Output 'INTERACTIVE-SHELL-RETAINED'
"""
    piped = run_powershell(piped_script)

    assert direct.returncode == 1
    assert "must not contain each other" in direct.stderr.lower()
    assert piped.returncode == 0
    assert "INTERACTIVE-SHELL-RETAINED" in piped.stdout
    assert "must not contain each other" in piped.stderr.lower()


def test_windows_installer_running_update_ignores_no_start_and_preserves_endpoint(tmp_path: Path):
    release_dir = tmp_path / "release"
    prefix = tmp_path / "prefix"
    library = tmp_path / "library"
    write_test_release(release_dir)
    old_target = prefix / "app" / "versions" / "v1.0.0"
    old_target.mkdir(parents=True)
    write_running_test_controller(old_target, host="127.0.0.9", port=4312)
    app = prefix / "app"
    (app / "current-version").write_text("v1.0.0\n", encoding="ascii")
    (app / "previous-version").write_text("v0.9.0\n", encoding="ascii")

    result = run_installer(release_dir, prefix, library, no_start=True)

    assert result.returncode == 0, result.stderr
    assert "start --host 127.0.0.9 --port 4312 --no-browser" in result.stdout
    assert (app / "current-version").read_text(encoding="ascii") == "v1.2.3\n"
    assert (app / "previous-version").read_text(encoding="ascii") == "v1.0.0\n"


def test_windows_installer_stopped_update_preserves_stopped_state(tmp_path: Path):
    release_dir = tmp_path / "release"
    prefix = tmp_path / "prefix"
    library = tmp_path / "library"
    write_test_release(release_dir)
    old_target = prefix / "app" / "versions" / "v1.0.0"
    old_target.mkdir(parents=True)
    write_stopped_test_controller(old_target)
    app = prefix / "app"
    (app / "current-version").write_text("v1.0.0\n", encoding="ascii")
    (app / "previous-version").write_text("v0.9.0\n", encoding="ascii")

    result = run_installer(release_dir, prefix, library, no_start=False)

    assert result.returncode == 0, result.stderr
    assert all(not line.startswith("start") for line in result.stdout.splitlines())
    assert (app / "current-version").read_text(encoding="ascii") == "v1.2.3\n"
    assert (app / "previous-version").read_text(encoding="ascii") == "v1.0.0\n"


def test_windows_appctl_update_invokes_installer_with_exact_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    prefix = tmp_path / "prefix with spaces"
    library = tmp_path / "library with spaces"
    release = tmp_path / "release with spaces"
    current = prefix / "app" / "versions" / "v1.0.0"
    scripts = current / "scripts"
    scripts.mkdir(parents=True)
    (prefix / "app" / "current-version").write_text("v1.0.0\n", encoding="ascii")
    prefix.mkdir(exist_ok=True)
    (prefix / ".env").write_text(f"IMAGE_PROMPT_LIBRARY_PATH={library}\n", encoding="ascii")
    (scripts / "install.ps1").write_text(
        "[CmdletBinding()]\n"
        "param([string]$Version,[string]$Prefix,[string]$LibraryPath,[string]$ReleaseBaseUrl,[string]$PythonExe='',[string[]]$PythonPrefixArgs=@(),[switch]$NoStart,[switch]$SkipPath,[switch]$NoBrowser)\n"
        "[ordered]@{ Version=$Version; Prefix=$Prefix; LibraryPath=$LibraryPath; ReleaseBaseUrl=$ReleaseBaseUrl } | ConvertTo-Json -Compress | Set-Content -LiteralPath (Join-Path $env:IMAGE_PROMPT_LIBRARY_PREFIX 'update-args.json') -Encoding UTF8\n"
        "$global:LASTEXITCODE = 0\n",
        encoding="ascii",
    )
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL", str(release))

    result = run_appctl(prefix, "update", "--version", "v2.0.0")

    assert result.returncode == 0, result.stderr
    assert json.loads((prefix / "update-args.json").read_text(encoding="utf-8-sig")) == {
        "Version": "v2.0.0",
        "Prefix": str(prefix),
        "LibraryPath": str(library),
        "ReleaseBaseUrl": str(release),
    }


def test_windows_installer_controller_start_does_not_wait_for_detached_app(
    tmp_path: Path,
):
    version_root = tmp_path / "version"
    scripts = version_root / "scripts"
    scripts.mkdir(parents=True)
    pid_path = tmp_path / "sleeper.pid"
    (scripts / "appctl.ps1").write_text(
        "$processPath = $env:Path\n"
        "[Environment]::SetEnvironmentVariable('PATH', $null, 'Process')\n"
        "[Environment]::SetEnvironmentVariable('Path', $processPath, 'Process')\n"
        "$outLog = Join-Path $PSScriptRoot 'child.out.log'\n"
        "$errLog = Join-Path $PSScriptRoot 'child.err.log'\n"
        "$sleeper = Start-Process powershell.exe -ArgumentList @('-NoProfile', '-Command', 'Start-Sleep -Seconds 5') -WindowStyle Hidden -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru\n"
        f"[IO.File]::WriteAllText({powershell_literal(pid_path)}, [string]$sleeper.Id)\n"
        "Write-Output 'started'\n",
        encoding="ascii",
    )
    result = run_installer_function(
        f"""
$stopwatch = [Diagnostics.Stopwatch]::StartNew()
$controllerResult = Invoke-Controller -VersionRoot {powershell_literal(version_root)} -Arguments @('start')
$stopwatch.Stop()
$sleeperId = [int][IO.File]::ReadAllText({powershell_literal(pid_path)})
$sleeper = Get-Process -Id $sleeperId -ErrorAction SilentlyContinue
if ($sleeper) {{ Stop-Process -Id $sleeperId -Force; Wait-Process -Id $sleeperId -ErrorAction SilentlyContinue }}
[pscustomobject]@{{ ExitCode = $controllerResult.ExitCode; ElapsedMilliseconds = $stopwatch.ElapsedMilliseconds }} | ConvertTo-Json -Compress
"""
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["ExitCode"] == 0
    assert payload["ElapsedMilliseconds"] < 3000


def test_windows_appctl_rollback_command_preserves_stopped_state(tmp_path: Path):
    prefix = tmp_path / "prefix"
    app = prefix / "app"
    (app / "versions" / "v1.0.0").mkdir(parents=True)
    (app / "versions" / "v0.9.0").mkdir()
    (app / "current-version").write_text("v1.0.0\n", encoding="ascii")
    (app / "previous-version").write_text("v0.9.0\n", encoding="ascii")

    result = run_appctl(prefix, "rollback")

    assert result.returncode == 0, result.stderr
    assert (app / "current-version").read_text(encoding="ascii") == "v0.9.0\n"
    assert (app / "previous-version").read_text(encoding="ascii") == "v1.0.0\n"
    assert not (prefix / "run" / "server.json").exists()


def test_windows_appctl_rollback_target_failure_restores_runtime_and_pointer_pair(tmp_path: Path):
    prefix = tmp_path / "prefix"
    app = prefix / "app"
    (app / "versions" / "v1.0.0").mkdir(parents=True)
    (app / "versions" / "v0.9.0").mkdir()
    (app / "current-version").write_text("v1.0.0\n", encoding="ascii")
    (app / "previous-version").write_text("v0.9.0\n", encoding="ascii")
    script = f"""
$env:IMAGE_PROMPT_LIBRARY_PREFIX = {powershell_literal(prefix)}
$context = Get-InstallContext
$script:startLines = New-Object Collections.Generic.List[string]
function Get-OwnedRuntimeState {{ [pscustomobject]@{{ running = $true; host = '127.0.0.7'; port = 4567 }} }}
function Stop-App {{ param($Context) }}
function Start-App {{
    param($Context, [string[]]$Arguments, $VersionOverride = $null)
    $resolvedVersion = if ($VersionOverride) {{ $VersionOverride.Version }} else {{ (Get-Content -LiteralPath (Join-Path $Context.AppDir 'current-version') -Raw).Trim() }}
    $script:startLines.Add($resolvedVersion + '|' + ($Arguments -join ' '))
    if ($resolvedVersion -eq 'v0.9.0') {{ throw 'forced target start failure' }}
}}
$failure = ''
try {{ Rollback-App -Context $context }} catch {{ $failure = $_.Exception.Message }}
[pscustomobject]@{{
    failure = $failure
    current = (Get-Content -LiteralPath (Join-Path $context.AppDir 'current-version') -Raw).Trim()
    previous = (Get-Content -LiteralPath (Join-Path $context.AppDir 'previous-version') -Raw).Trim()
    starts = @($script:startLines)
}} | ConvertTo-Json -Compress
"""

    result = run_appctl_function(script)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert "Rollback target failed health checks; restored v1.0.0." in payload["failure"]
    assert payload["current"] == "v1.0.0"
    assert payload["previous"] == "v0.9.0"
    assert payload["starts"] == [
        "v0.9.0|--host 127.0.0.7 --port 4567 --no-browser",
        "v1.0.0|--host 127.0.0.7 --port 4567 --no-browser",
    ]


def test_windows_appctl_pointer_failure_restores_both_and_restarts_old_runtime(tmp_path: Path):
    prefix = tmp_path / "prefix"
    app = prefix / "app"
    (app / "versions" / "v1.0.0").mkdir(parents=True)
    (app / "versions" / "v0.9.0").mkdir()
    (app / "current-version").write_text("v1.0.0\n", encoding="ascii")
    (app / "previous-version").write_text("v0.9.0\n", encoding="ascii")
    script = f"""
$env:IMAGE_PROMPT_LIBRARY_PREFIX = {powershell_literal(prefix)}
$context = Get-InstallContext
$script:realWriter = ${{function:Write-VersionPointerAtomic}}
$script:writeCalls = 0
$script:startLines = New-Object Collections.Generic.List[string]
function Get-OwnedRuntimeState {{ [pscustomobject]@{{ running = $true; host = '127.0.0.8'; port = 4678 }} }}
function Stop-App {{ param($Context) }}
function Start-App {{
    param($Context, [string[]]$Arguments, $VersionOverride = $null)
    $resolvedVersion = if ($VersionOverride) {{ $VersionOverride.Version }} else {{ (Get-Content -LiteralPath (Join-Path $Context.AppDir 'current-version') -Raw).Trim() }}
    $script:startLines.Add($resolvedVersion + '|' + ($Arguments -join ' '))
}}
function Write-VersionPointerAtomic {{
    param([string]$Path, [AllowEmptyString()][string]$Value)
    $script:writeCalls++
    if ($script:writeCalls -eq 2) {{ throw 'forced second pointer failure' }}
    if ($script:writeCalls -eq 3) {{ throw 'forced current restoration failure' }}
    if ($script:writeCalls -eq 4) {{ throw 'forced previous restoration failure' }}
    & $script:realWriter -Path $Path -Value $Value
}}
$failure = ''
try {{ Rollback-App -Context $context }} catch {{ $failure = $_.Exception.Message }}
[pscustomobject]@{{
    failure = $failure
    write_calls = $script:writeCalls
    previous = (Get-Content -LiteralPath (Join-Path $context.AppDir 'previous-version') -Raw).Trim()
    current = (Get-Content -LiteralPath (Join-Path $context.AppDir 'current-version') -Raw).Trim()
    starts = @($script:startLines)
}} | ConvertTo-Json -Compress
"""

    result = run_appctl_function(script)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert "forced second pointer failure" in payload["failure"]
    assert "forced current restoration failure" in payload["failure"]
    assert "forced previous restoration failure" in payload["failure"]
    assert payload["write_calls"] == 4
    assert payload["current"] == "v0.9.0"
    assert payload["previous"] == "v0.9.0"
    assert payload["starts"] == ["v1.0.0|--host 127.0.0.8 --port 4678 --no-browser"]


def test_windows_sample_data_uses_same_handle_pinned_hash_and_safe_zip_extraction():
    path = ROOT / "scripts" / "install-sample-data.ps1"
    assert path.is_file()
    script = path.read_text(encoding="utf-8")
    assert "gpt-image-2-skill" in script
    assert "awesome-gpt-image-2" in script
    assert "8a458f6c8c96079f40fbc46c689e7de0bd2eb464ee7f800f94f3ca60131d5035" in script
    assert "153714b7611524d7b98b4b0452baa86c8d05053477bb670b731953e8d26a8c9c" in script
    assert "hashlib.sha256" in script
    assert "zipfile.ZipFile" in script
    assert "archive.extractall" not in script
    assert "Get-FileHash" not in script
    assert "backend.services.import_sample_bundle" in script
    assert '"sample-data"' in read("scripts/appctl.ps1")


@pytest.mark.parametrize(
    "unsafe_member",
    [
        ("file", "/absolute.txt"),
        ("file", "C:/drive-qualified.txt"),
        ("file", "//server/share/unc.txt"),
        ("file", "../escaped.txt"),
        ("file", "folder\\..\\escaped.txt"),
        ("file", "folder:stream.txt"),
        ("file", "CON.txt"),
        ("file", "trailing-dot."),
        ("file", "trailing-space "),
        ("file", "duplicate.txt"),
        ("file", "DUPLICATE.TXT"),
        ("symlink", "linked.txt"),
        ("reparse", "reparse-like.txt"),
        ("fifo", "special-unix-entry"),
    ],
)
def test_windows_sample_data_rejects_hostile_zip_members_before_import(
    tmp_path: Path, unsafe_member: tuple[str, str]
):
    zip_path = tmp_path / "hostile.zip"
    manifest = tmp_path / "manifest.json"
    work_dir = tmp_path / "work"
    write_empty_sample_manifest(manifest)
    write_sample_zip(zip_path, [unsafe_member])
    if unsafe_member[1] in {"duplicate.txt", "DUPLICATE.TXT"}:
        write_sample_zip(zip_path, [("file", "duplicate.txt"), unsafe_member])
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()

    result = run_sample_data_installer(
        "en",
        "gpt-image-2-skill",
        ROOT,
        tmp_path / "library",
        {
            "SAMPLE_DATA_MANIFEST": str(manifest),
            "SAMPLE_DATA_IMAGE_ZIP": str(zip_path),
            "SAMPLE_DATA_IMAGE_ZIP_SHA256": digest,
            "SAMPLE_DATA_WORK_DIR": str(work_dir),
        },
    )

    assert result.returncode == 1, result.stderr
    assert "refusing unsafe zip member" in result.stderr.lower()
    assert not (tmp_path / "escaped.txt").exists()
    assert not list(work_dir.glob(".staging-*"))


@pytest.mark.parametrize(
    "members",
    [
        [("file", "parent"), ("file", "parent/child.txt")],
        [("file", "parent/child.txt"), ("file", "parent")],
    ],
)
def test_windows_sample_data_rejects_file_directory_collisions_in_both_orders(
    tmp_path: Path, members: list[tuple[str, str]]
):
    zip_path = tmp_path / "collision.zip"
    manifest = tmp_path / "manifest.json"
    work_dir = tmp_path / "work"
    write_empty_sample_manifest(manifest)
    write_sample_zip(zip_path, members)

    result = run_sample_data_installer(
        "en",
        "gpt-image-2-skill",
        ROOT,
        tmp_path / "library",
        {
            "SAMPLE_DATA_MANIFEST": str(manifest),
            "SAMPLE_DATA_IMAGE_ZIP": str(zip_path),
            "SAMPLE_DATA_IMAGE_ZIP_SHA256": hashlib.sha256(zip_path.read_bytes()).hexdigest(),
            "SAMPLE_DATA_WORK_DIR": str(work_dir),
        },
    )

    assert result.returncode == 1
    assert "refusing unsafe zip member" in result.stderr.lower()
    assert not list(work_dir.glob(".staging-*"))


def test_windows_sample_data_accepts_safe_backslash_member_paths(tmp_path: Path):
    zip_path = tmp_path / "backslash.zip"
    manifest = tmp_path / "manifest.json"
    work_dir = tmp_path / "work"
    write_empty_sample_manifest(manifest)
    write_sample_zip(zip_path, [("file", "images\\placeholder.txt")])

    result = run_sample_data_installer(
        "en",
        "gpt-image-2-skill",
        ROOT,
        tmp_path / "library",
        {
            "SAMPLE_DATA_MANIFEST": str(manifest),
            "SAMPLE_DATA_IMAGE_ZIP": str(zip_path),
            "SAMPLE_DATA_IMAGE_ZIP_SHA256": hashlib.sha256(zip_path.read_bytes()).hexdigest(),
            "SAMPLE_DATA_WORK_DIR": str(work_dir),
        },
    )

    assert result.returncode == 0, result.stderr
    assert not list(work_dir.glob(".staging-*"))


def test_windows_sample_data_download_stops_after_three_attempts(tmp_path: Path):
    destination = tmp_path / "sample.zip"
    result = run_sample_data_installer_function(
        f"""
$script:attempts = 0
function Invoke-WebRequest {{
    param([switch]$UseBasicParsing, [string]$Uri, [string]$OutFile)
    $script:attempts++
    throw 'forced download failure'
}}
function Start-Sleep {{ param([int]$Seconds) }}
$failure = ''
try {{ Invoke-DownloadWithRetry -Uri 'https://example.invalid/sample.zip' -Destination {powershell_literal(destination)} }} catch {{ $failure = $_.Exception.Message }}
[pscustomobject]@{{ attempts = $script:attempts; failure = $failure }} | ConvertTo-Json -Compress
"""
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["attempts"] == 3, payload
    assert "failed after 3 attempts" in payload["failure"].lower()


def test_windows_sample_data_imports_a_safe_zip_and_cleans_its_staging_directory(tmp_path: Path):
    zip_path = tmp_path / "safe.zip"
    manifest = tmp_path / "manifest.json"
    work_dir = tmp_path / "work"
    library = tmp_path / "library"
    write_empty_sample_manifest(manifest)
    write_sample_zip(zip_path, [("directory", "images/"), ("file", "images/placeholder.txt")])
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()

    result = run_sample_data_installer(
        "en",
        "gpt-image-2-skill",
        ROOT,
        library,
        {
            "SAMPLE_DATA_MANIFEST": str(manifest),
            "SAMPLE_DATA_IMAGE_ZIP": str(zip_path),
            "SAMPLE_DATA_IMAGE_ZIP_SHA256": digest,
            "SAMPLE_DATA_WORK_DIR": str(work_dir),
        },
    )

    assert result.returncode == 0, result.stderr
    assert "Imported 0 items and 0 images" in result.stdout
    assert not list(work_dir.glob(".staging-*"))


def test_windows_appctl_sample_data_invokes_current_installer_with_exact_context(tmp_path: Path):
    prefix = tmp_path / "prefix with spaces"
    library = tmp_path / "library with spaces"
    current = write_sample_data_appctl_install(
        prefix,
        library,
        "$args | ConvertTo-Json -Compress | Set-Content -LiteralPath (Join-Path $env:IMAGE_PROMPT_LIBRARY_PREFIX 'sample-data-args.json') -Encoding UTF8\n"
        "$global:LASTEXITCODE = 0\n",
    )

    result = run_appctl(prefix, "sample-data", "zh_hant", "awesome-gpt-image-2")

    assert result.returncode == 0, result.stderr
    assert json.loads((prefix / "sample-data-args.json").read_text(encoding="utf-8-sig")) == [
        "-Language",
        "zh_hant",
        "-Package",
        "awesome-gpt-image-2",
        "-AppRoot",
        str(current),
        "-LibraryPath",
        str(library),
    ]


@pytest.mark.parametrize(
    "arguments",
    [
        (),
        ("invalid",),
        ("en", "invalid"),
        ("en", "gpt-image-2-skill", "extra"),
    ],
)
def test_windows_appctl_sample_data_rejects_invalid_missing_and_extra_arguments(
    tmp_path: Path, arguments: tuple[str, ...]
):
    prefix = tmp_path / "prefix"
    marker = prefix / "child-called.txt"
    write_sample_data_appctl_install(
        prefix,
        tmp_path / "library",
        f"Set-Content -LiteralPath {powershell_literal(marker)} -Value called\n$global:LASTEXITCODE = 0\n",
    )

    result = run_appctl(prefix, "sample-data", *arguments)

    assert result.returncode == 1
    assert not marker.exists()


def test_windows_appctl_sample_data_preserves_child_exit_code(tmp_path: Path):
    prefix = tmp_path / "prefix"
    write_sample_data_appctl_install(
        prefix,
        tmp_path / "library",
        "[Console]::Error.WriteLine('forced child failure')\nexit 7\n",
    )

    result = run_appctl(prefix, "sample-data", "en")

    assert result.returncode == 7
    assert "forced child failure" in result.stderr


@pytest.mark.parametrize(
    "arguments",
    [
        (),
        ("-Language", "invalid"),
        ("-Language", "en", "-Package", "invalid"),
        ("-Language", "en", "-Package", "awesome-gpt-image-2"),
    ],
)
def test_windows_sample_data_direct_invalid_usage_exits_two(arguments: tuple[str, ...]):
    result = run_sample_data_command(*arguments)

    assert result.returncode == 2


def test_windows_installer_pointer_failure_restores_both_and_restarts_old_runtime(tmp_path: Path):
    release_dir = tmp_path / "release"
    prefix = tmp_path / "prefix"
    library = tmp_path / "library"
    write_test_release(release_dir)
    old_target = prefix / "app" / "versions" / "v1.0.0"
    old_target.mkdir(parents=True)
    write_running_test_controller(old_target, host="127.0.0.6", port=4789)
    app = prefix / "app"
    (app / "current-version").write_text("v1.0.0\n", encoding="ascii")
    (app / "previous-version").write_text("v0.9.0\n", encoding="ascii")
    script = f"""
$Version = 'v1.2.3'
$Prefix = {powershell_literal(prefix)}
$LibraryPath = {powershell_literal(library)}
$ReleaseBaseUrl = {powershell_literal(release_dir)}
$PythonExe = {powershell_literal(shutil.which('python.exe') or shutil.which('python') or 'python')}
$PythonPrefixArgs = @()
$NoStart = $true
$SkipPath = $true
$NoBrowser = $false
$script:realWriter = ${{function:Write-VersionPointer}}
$script:writeCalls = 0
function Write-VersionPointer {{
    param([string]$Path, [AllowEmptyString()][string]$Value, [string]$AppPrefix)
    $script:writeCalls++
    if ($script:writeCalls -eq 2) {{ throw 'forced second pointer failure' }}
    if ($script:writeCalls -eq 3) {{ throw 'forced current restoration failure' }}
    if ($script:writeCalls -eq 4) {{ throw 'forced previous restoration failure' }}
    & $script:realWriter -Path $Path -Value $Value -AppPrefix $AppPrefix
}}
$failure = ''
try {{ Invoke-Install }} catch {{ $failure = $_.Exception.Message }}
[pscustomobject]@{{ failure = $failure; write_calls = $script:writeCalls }} | ConvertTo-Json -Compress
"""

    result = run_installer_function(script)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert "forced second pointer failure" in payload["failure"]
    assert "forced current restoration failure" in payload["failure"]
    assert "forced previous restoration failure" in payload["failure"]
    assert payload["write_calls"] == 4
    assert (app / "current-version").read_text(encoding="ascii") == "v1.0.0\n"
    assert (app / "previous-version").read_text(encoding="ascii") == "v0.9.0\n"
    commands = (old_target / "scripts" / "commands.log").read_text(encoding="ascii").splitlines()
    assert "start --host 127.0.0.6 --port 4789 --no-browser" in commands
