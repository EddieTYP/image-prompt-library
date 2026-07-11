[CmdletBinding()]
param([switch]$KeepWorkRoot)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')
$workName = "image-prompt-library-smoke-" + [Guid]::NewGuid().ToString("N")
$workRoot = Join-Path $tempRoot $workName
$prefix = Join-Path $workRoot "App Prefix"
$library = Join-Path $workRoot "Private Library"
$releaseBase = Join-Path $workRoot "Local Release Base"
$packagerSource = Join-Path $workRoot "Packager Source"
$sampleRoot = Join-Path $workRoot "Sample Fixture"
$port = 18765
$versionA = "v0.8.0-test-a"
$versionB = "v0.8.0-test-b"
$versionBroken = "v0.8.0-test-broken"
$originalUserPath = [Environment]::GetEnvironmentVariable("Path", "User")
$originalProcessPath = $env:Path
$originalReleaseBase = [Environment]::GetEnvironmentVariable("IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL", "Process")
$sleeper = $null
$passed = $false

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw "ASSERTION FAILED: $Message" }
}

function Assert-Equal {
    param($Expected, $Actual, [string]$Message)
    if ($Expected -ne $Actual) { throw "ASSERTION FAILED: $Message Expected '$Expected', got '$Actual'." }
}

function Assert-Contains {
    param([string]$Text, [string]$Expected, [string]$Message)
    if (-not $Text.Contains($Expected)) { throw "ASSERTION FAILED: $Message Missing '$Expected'. Output: $Text" }
}

function Initialize-ImmediateProcessRunner {
    if ("ImagePromptLibraryImmediateProcessRunner" -as [type]) { return }
    Add-Type -TypeDefinition @'
using System;
using System.Diagnostics;
using System.Text;
using System.Threading;

public sealed class ImagePromptLibraryImmediateProcessResult
{
    public int ExitCode { get; set; }
    public string Stdout { get; set; }
    public string Stderr { get; set; }
}

public static class ImagePromptLibraryImmediateProcessRunner
{
    public static ImagePromptLibraryImmediateProcessResult Run(string fileName, string arguments, string workingDirectory)
    {
        var stdout = new StringBuilder();
        var stderr = new StringBuilder();
        var stdoutLock = new object();
        var stderrLock = new object();
        using (var process = new Process())
        {
            process.StartInfo = new ProcessStartInfo
            {
                FileName = fileName,
                Arguments = arguments,
                WorkingDirectory = workingDirectory,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true
            };
            process.OutputDataReceived += delegate(object sender, DataReceivedEventArgs eventArgs)
            {
                if (eventArgs.Data != null) lock (stdoutLock) stdout.AppendLine(eventArgs.Data);
            };
            process.ErrorDataReceived += delegate(object sender, DataReceivedEventArgs eventArgs)
            {
                if (eventArgs.Data != null) lock (stderrLock) stderr.AppendLine(eventArgs.Data);
            };
            if (!process.Start()) throw new InvalidOperationException("Could not start the child process.");
            process.BeginOutputReadLine();
            process.BeginErrorReadLine();
            if (!process.WaitForExit(Int32.MaxValue)) throw new TimeoutException("The child process did not exit.");
            var exitCode = process.ExitCode;
            Thread.Sleep(50);
            try { process.CancelOutputRead(); } catch (InvalidOperationException) { }
            try { process.CancelErrorRead(); } catch (InvalidOperationException) { }
            string output;
            string error;
            lock (stdoutLock) output = stdout.ToString().TrimEnd();
            lock (stderrLock) error = stderr.ToString().TrimEnd();
            return new ImagePromptLibraryImmediateProcessResult { ExitCode = exitCode, Stdout = output, Stderr = error };
        }
    }
}
'@
}

function Invoke-IsolatedPowerShell {
    param([string]$ScriptPath, [string[]]$Arguments = @())
    Initialize-ImmediateProcessRunner
    $captureRoot = Join-Path $workRoot ("Capture-" + [Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $captureRoot | Out-Null
    $wrapperPath = Join-Path $captureRoot "invoke.ps1"
    $argumentsPath = Join-Path $captureRoot "arguments.json"
    $wrapper = @'
[CmdletBinding()]
param([string]$Target, [string]$ArgumentsPath)
$childArguments = @((Get-Content -LiteralPath $ArgumentsPath -Raw | ConvertFrom-Json))
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Target @childArguments
exit $LASTEXITCODE
'@
    [IO.File]::WriteAllText($wrapperPath, $wrapper, (New-Object Text.UTF8Encoding($false)))
    $argumentJson = ConvertTo-Json -InputObject ([object[]]@($Arguments)) -Compress
    [IO.File]::WriteAllText($argumentsPath, $argumentJson, (New-Object Text.UTF8Encoding($false)))
    $parts = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $wrapperPath, "-Target", $ScriptPath, "-ArgumentsPath", $argumentsPath)
    $quoted = @($parts | ForEach-Object { '"' + $_.Replace('"', '\"') + '"' })
    $result = [ImagePromptLibraryImmediateProcessRunner]::Run("powershell.exe", ($quoted -join " "), $repoRoot)
    $output = @($result.Stdout, $result.Stderr) | Where-Object { $_ }
    return [pscustomobject]@{ ExitCode = $result.ExitCode; Output = ($output -join [Environment]::NewLine) }
}

function Assert-Succeeded {
    param($Result, [string]$Action)
    if ($Result.ExitCode -ne 0) { throw "$Action failed with exit code $($Result.ExitCode): $($Result.Output)" }
}

function Assert-Failed {
    param($Result, [string]$Action)
    if ($Result.ExitCode -eq 0) { throw "$Action unexpectedly succeeded: $($Result.Output)" }
}

function Invoke-App {
    param([string[]]$Arguments)
    return Invoke-IsolatedPowerShell -ScriptPath (Join-Path $prefix "bin\image-prompt-library.ps1") -Arguments $Arguments
}

function Get-Pointer {
    param([string]$Name)
    return (Get-Content -LiteralPath (Join-Path $prefix "app\$Name") -Raw).Trim()
}

function Test-PathMembership {
    param([AllowEmptyString()][string]$PathValue, [string]$ExpectedPath)
    $expected = [IO.Path]::GetFullPath($ExpectedPath).TrimEnd('\')
    foreach ($entry in @($PathValue -split ';')) {
        $candidate = $entry.Trim().Trim('"')
        if (-not $candidate) { continue }
        try {
            if ([IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($candidate)).TrimEnd('\').Equals($expected, [StringComparison]::OrdinalIgnoreCase)) {
                return $true
            }
        } catch {}
    }
    return $false
}

function ConvertTo-BashPath {
    param([string]$Path)
    $value = [IO.Path]::GetFullPath($Path).Replace('\', '/')
    if ($value -match '^([A-Za-z]):(.*)$') { return "/" + $Matches[1].ToLowerInvariant() + $Matches[2] }
    return $value
}

function Quote-Bash {
    param([string]$Value)
    return "'" + $Value.Replace("'", "'\''") + "'"
}

function Copy-PackagerSource {
    New-Item -ItemType Directory -Path $packagerSource | Out-Null
    foreach ($relative in @("backend", "scripts", "sample-data\manifests", "frontend\dist")) {
        $source = Join-Path $repoRoot $relative
        $destination = Join-Path $packagerSource $relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
        Copy-Item -LiteralPath $source -Destination $destination -Recurse
    }
    foreach ($relative in @("pyproject.toml", "README.md", "LICENSE", "NOTICE", "SECURITY.md")) {
        Copy-Item -LiteralPath (Join-Path $repoRoot $relative) -Destination (Join-Path $packagerSource $relative)
    }
}

function Find-Python {
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) {
        $candidate = (& $launcher.Source -3.11 -c "import sys; print(sys.executable)" 2>$null | Select-Object -Last 1)
        if ($LASTEXITCODE -eq 0 -and $candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) { return [IO.Path]::GetFullPath($candidate) }
    }
    foreach ($name in @("python.exe", "python")) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) {
            & $command.Source -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) { return $command.Source }
        }
    }
    throw "Python 3.10 or newer is required for the smoke."
}

function Find-GitBash {
    foreach ($candidate in @("C:\Program Files\Git\bin\bash.exe", "C:\Program Files\Git\usr\bin\bash.exe")) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    }
    $command = Get-Command bash.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    throw "Git Bash is required for the existing release packager."
}

function Build-Release {
    param([string]$Version, [string]$Bash, [string]$Python)
    $command = "python3() { " + (Quote-Bash (ConvertTo-BashPath $Python)) + " `"`$@`"; }; export -f python3; cd " + (Quote-Bash (ConvertTo-BashPath $packagerSource)) + "; scripts/package-release.sh " + (Quote-Bash $Version) + " --skip-build"
    $output = @(& $Bash -lc $command 2>&1 | ForEach-Object { $_.ToString() })
    if ($LASTEXITCODE -ne 0) { throw "Packaging $Version failed: $($output -join [Environment]::NewLine)" }
    foreach ($suffix in @(".tar.gz", ".tar.gz.sha256", ".manifest.json")) {
        $name = "image-prompt-library-$Version$suffix"
        Copy-Item -LiteralPath (Join-Path $packagerSource "dist-release\$name") -Destination (Join-Path $releaseBase $name)
    }
}

function Publish-DerivedRelease {
    param([string]$Python, [string]$SourceTag, [string]$TargetTag, [ValidateSet("unsafe", "broken")][string]$Mode, [string]$Destination)
    $builder = Join-Path $workRoot "derive-release.py"
    $sourceArtifact = Join-Path $releaseBase "image-prompt-library-$SourceTag.tar.gz"
    $script = @'
import hashlib
import io
import json
import pathlib
import sys
import tarfile

source = pathlib.Path(sys.argv[1])
destination = pathlib.Path(sys.argv[2])
source_tag = sys.argv[3]
target_tag = sys.argv[4]
mode = sys.argv[5]
destination.mkdir(parents=True, exist_ok=True)
artifact_name = f"image-prompt-library-{target_tag}.tar.gz"
artifact = destination / artifact_name
with tarfile.open(source, "r:gz") as incoming, tarfile.open(artifact, "w:gz") as outgoing:
    changed_health = False
    for member in incoming.getmembers():
        data = incoming.extractfile(member).read() if member.isfile() else None
        if mode == "broken" and member.name.lstrip("./") == "VERSION":
            data = (target_tag + "\n").encode("ascii")
            member.size = len(data)
        if mode == "broken" and member.name.lstrip("./") == "backend/main.py":
            old = b'def health(): return {"ok": True, "version": APP_VERSION}'
            new = b'def health(): return {"ok": False, "version": APP_VERSION}'
            if data is None or data.count(old) != 1:
                raise SystemExit("exact health response was not found once")
            data = data.replace(old, new)
            member.size = len(data)
            changed_health = True
        outgoing.addfile(member, io.BytesIO(data) if data is not None else None)
    if mode == "unsafe":
        payload = b"escape"
        member = tarfile.TarInfo("../escape.txt")
        member.size = len(payload)
        outgoing.addfile(member, io.BytesIO(payload))
    if mode == "broken" and not changed_health:
        raise SystemExit("health response was not changed")
digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
(destination / f"{artifact_name}.sha256").write_text(f"{digest}  {artifact_name}\n", encoding="ascii")
manifest = {
    "name": "image-prompt-library",
    "version": target_tag,
    "schema_version": 1,
    "capabilities": ["windows-powershell-v1"],
    "artifact": artifact_name,
    "sha256": digest,
    "python": ">=3.10",
    "node_required_for_runtime": False,
    "built_frontend": True,
}
(destination / f"image-prompt-library-{target_tag}.manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="ascii")
'@
    [IO.File]::WriteAllText($builder, $script, (New-Object Text.UTF8Encoding($false)))
    & $Python $builder $sourceArtifact $Destination $SourceTag $TargetTag $Mode
    if ($LASTEXITCODE -ne 0) { throw "Could not create $Mode release $TargetTag." }
}

function Get-Health {
    return Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/health" -TimeoutSec 5
}

function Assert-HealthVersion {
    param([string]$ExpectedVersion)
    $health = Get-Health
    Assert-True ($health.ok -eq $true) "Health must report ok."
    Assert-Equal $ExpectedVersion ([string]$health.version) "Health version mismatch."
}

function Remove-ValidatedWorkRoot {
    $full = [IO.Path]::GetFullPath($workRoot)
    $parent = [IO.Path]::GetDirectoryName($full)
    $leaf = [IO.Path]::GetFileName($full)
    if (-not $parent.Equals($tempRoot, [StringComparison]::OrdinalIgnoreCase) -or $leaf -notmatch '^image-prompt-library-smoke-[0-9a-f]{32}$') {
        throw "Refusing to remove unexpected smoke work root: $full"
    }
    if ([IO.Directory]::Exists($full)) { [IO.Directory]::Delete($full, $true) }
}

function Test-ExactString {
    param([AllowNull()][string]$Actual, [AllowNull()][string]$Expected)
    if ($null -eq $Expected) { return $null -eq $Actual }
    return [string]::Equals($Actual, $Expected, [StringComparison]::Ordinal)
}

function Invoke-CleanupStep {
    param([Collections.Generic.List[string]]$Errors, [string]$Name, [scriptblock]$Action)
    try { & $Action | Out-Null }
    catch { $Errors.Add("$Name`: $($_.Exception.Message)") }
}

function Invoke-SmokeCleanup {
    [CmdletBinding()]
    param([switch]$KeepWorkRoot)
    $errors = New-Object Collections.Generic.List[string]
    $ownedState = [pscustomobject]@{ Pid = $null; Running = $false }
    $shim = Join-Path $prefix "bin\image-prompt-library.ps1"
    $workRootExisted = Test-Path -LiteralPath $workRoot

    Invoke-CleanupStep -Errors $errors -Name "owned app record inspection" -Action {
        if (-not (Test-Path -LiteralPath $shim -PathType Leaf)) { return }
        $recordPath = Join-Path $prefix "run\server.json"
        if (Test-Path -LiteralPath $recordPath -PathType Leaf) {
            $record = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
            $ownedState.Pid = [int]$record.pid
        }
    }
    Invoke-CleanupStep -Errors $errors -Name "owned app state inspection" -Action {
        if (-not (Test-Path -LiteralPath $shim -PathType Leaf)) { return }
        $owned = Invoke-App -Arguments @("internal-owned-runtime")
        if ($owned.ExitCode -ne 0) { throw "internal-owned-runtime exited $($owned.ExitCode): $($owned.Output)" }
        $runtime = $owned.Output | ConvertFrom-Json
        $ownedState.Running = $runtime.running -eq $true
        if ($ownedState.Running -and $null -eq $ownedState.Pid) { throw "owned runtime record is missing" }
    }
    Invoke-CleanupStep -Errors $errors -Name "owned app stop" -Action {
        if (-not (Test-Path -LiteralPath $shim -PathType Leaf)) { return }
        $stopResult = Invoke-App -Arguments @("stop")
        if ($stopResult.ExitCode -ne 0) { throw "stop exited $($stopResult.ExitCode): $($stopResult.Output)" }
    }
    Invoke-CleanupStep -Errors $errors -Name "owned app termination" -Action {
        if ($null -eq $ownedState.Pid) { return }
        $deadline = [DateTime]::UtcNow.AddSeconds(10)
        do {
            $remaining = Get-Process -Id $ownedState.Pid -ErrorAction SilentlyContinue
            if (-not $remaining) { return }
            Start-Sleep -Milliseconds 100
        } while ([DateTime]::UtcNow -lt $deadline)
        throw "owned PID $($ownedState.Pid) remained alive"
    }
    Invoke-CleanupStep -Errors $errors -Name "owned app post-stop state" -Action {
        if (-not (Test-Path -LiteralPath $shim -PathType Leaf)) { return }
        $owned = Invoke-App -Arguments @("internal-owned-runtime")
        if ($owned.ExitCode -ne 0) { throw "internal-owned-runtime exited $($owned.ExitCode): $($owned.Output)" }
        $runtime = $owned.Output | ConvertFrom-Json
        if ($runtime.running -eq $true) { throw "owned runtime still reports running" }
    }
    Invoke-CleanupStep -Errors $errors -Name "User PATH restoration" -Action {
        [Environment]::SetEnvironmentVariable("Path", $originalUserPath, "User")
        $actual = [Environment]::GetEnvironmentVariable("Path", "User")
        if (-not (Test-ExactString -Actual $actual -Expected $originalUserPath)) { throw "exact User PATH was not restored" }
    }
    Invoke-CleanupStep -Errors $errors -Name "process PATH restoration" -Action {
        $env:Path = $originalProcessPath
        if (-not (Test-ExactString -Actual $env:Path -Expected $originalProcessPath)) { throw "exact process PATH was not restored" }
    }
    foreach ($name in @("SAMPLE_DATA_MANIFEST", "SAMPLE_DATA_IMAGE_ZIP", "SAMPLE_DATA_IMAGE_ZIP_SHA256", "SAMPLE_DATA_WORK_DIR", "SAMPLE_DATA_IMAGE_DIR", "SAMPLE_DATA_RELEASE_BASE_URL", "SAMPLE_DATA_RELEASE_ASSET_NAME")) {
        Invoke-CleanupStep -Errors $errors -Name "$name cleanup" -Action {
            [Environment]::SetEnvironmentVariable($name, $null, "Process")
            if ($null -ne [Environment]::GetEnvironmentVariable($name, "Process")) { throw "$name was not cleared" }
        }
    }
    Invoke-CleanupStep -Errors $errors -Name "release override restoration" -Action {
        [Environment]::SetEnvironmentVariable("IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL", $originalReleaseBase, "Process")
        $actual = [Environment]::GetEnvironmentVariable("IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL", "Process")
        if (-not (Test-ExactString -Actual $actual -Expected $originalReleaseBase)) { throw "release override was not restored" }
    }
    Invoke-CleanupStep -Errors $errors -Name "sleeper termination" -Action {
        if (-not $sleeper) { return }
        $sleeper.Refresh()
        if (-not $sleeper.HasExited) {
            $sleeper.Kill()
            if (-not $sleeper.WaitForExit(10000)) { throw "sleeper did not exit within 10 seconds" }
        }
    }
    Invoke-CleanupStep -Errors $errors -Name "sleeper exit verification" -Action {
        if (-not $sleeper) { return }
        $sleeper.Refresh()
        if (-not $sleeper.HasExited) { throw "sleeper remains alive" }
    }
    Invoke-CleanupStep -Errors $errors -Name "sleeper disposal" -Action {
        if ($sleeper) { $sleeper.Dispose() }
    }
    Invoke-CleanupStep -Errors $errors -Name "work-root cleanup" -Action {
        if (-not $KeepWorkRoot) { Remove-ValidatedWorkRoot }
    }
    Invoke-CleanupStep -Errors $errors -Name "work-root residue" -Action {
        $exists = Test-Path -LiteralPath $workRoot
        if ($KeepWorkRoot) {
            if ($workRootExisted -and -not $exists) { throw "-KeepWorkRoot did not retain the work root" }
        } elseif ($exists) {
            throw "smoke work root remains"
        }
    }
    Invoke-CleanupStep -Errors $errors -Name "owned process residue" -Action {
        foreach ($process in @(Get-Process -ErrorAction SilentlyContinue)) {
            try {
                if ($process.Path -and $process.Path.StartsWith($workRoot + "\", [StringComparison]::OrdinalIgnoreCase)) {
                    throw "PID $($process.Id) remains under the smoke work root"
                }
            } catch [Management.Automation.RuntimeException] { throw }
            catch {}
        }
    }
    return [string[]]$errors
}

$runFailure = $null
$cleanupErrors = @()
try {
    Assert-True (Test-Path -LiteralPath (Join-Path $repoRoot "frontend\dist\index.html") -PathType Leaf) "frontend/dist/index.html must exist before packaging."
    New-Item -ItemType Directory -Path $workRoot, $releaseBase, $sampleRoot | Out-Null
    $python = Find-Python
    $bash = Find-GitBash
    $installer = Join-Path $repoRoot "scripts\install.ps1"

    $missingPrefix = Join-Path $workRoot "Missing Python Prefix"
    $missing = Invoke-IsolatedPowerShell -ScriptPath $installer -Arguments @("-Version", $versionA, "-Prefix", $missingPrefix, "-LibraryPath", $library, "-ReleaseBaseUrl", $releaseBase, "-PythonExe", "missing-python.exe", "-NoStart")
    Assert-Failed $missing "Missing-Python install"
    Assert-Contains $missing.Output "requires Python 3.10 or newer" "Missing-Python failure must be actionable."
    Assert-True (-not (Test-Path -LiteralPath $missingPrefix)) "Missing-Python install must not create its prefix."

    Copy-PackagerSource
    Build-Release -Version $versionA -Bash $bash -Python $python
    Build-Release -Version $versionB -Bash $bash -Python $python

    $badChecksumRelease = Join-Path $workRoot "Bad Checksum Release"
    New-Item -ItemType Directory -Path $badChecksumRelease | Out-Null
    foreach ($suffix in @(".tar.gz", ".tar.gz.sha256", ".manifest.json")) {
        $name = "image-prompt-library-$versionA$suffix"
        Copy-Item -LiteralPath (Join-Path $releaseBase $name) -Destination (Join-Path $badChecksumRelease $name)
    }
    $badArtifact = Join-Path $badChecksumRelease "image-prompt-library-$versionA.tar.gz"
    $bytes = [IO.File]::ReadAllBytes($badArtifact)
    $bytes[[Math]::Floor($bytes.Length / 2)] = $bytes[[Math]::Floor($bytes.Length / 2)] -bxor 1
    [IO.File]::WriteAllBytes($badArtifact, $bytes)
    $checksumPrefix = Join-Path $workRoot "Checksum Probe Prefix"
    $checksumProbe = Invoke-IsolatedPowerShell -ScriptPath $installer -Arguments @("-Version", $versionA, "-Prefix", $checksumPrefix, "-LibraryPath", $library, "-ReleaseBaseUrl", $badChecksumRelease, "-PythonExe", $python, "-NoStart", "-SkipPath")
    Assert-Failed $checksumProbe "Checksum probe"
    Assert-Contains $checksumProbe.Output "checksum" "Checksum probe must report checksum failure."
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $checksumPrefix "app\current-version"))) "Checksum probe must not publish a pointer."
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $checksumPrefix "app\versions\$versionA"))) "Checksum probe must not publish a version."

    $unsafeRelease = Join-Path $workRoot "Unsafe Tar Release"
    Publish-DerivedRelease -Python $python -SourceTag $versionA -TargetTag $versionA -Mode unsafe -Destination $unsafeRelease
    $unsafePrefix = Join-Path $workRoot "Unsafe Tar Prefix"
    $unsafeProbe = Invoke-IsolatedPowerShell -ScriptPath $installer -Arguments @("-Version", $versionA, "-Prefix", $unsafePrefix, "-LibraryPath", $library, "-ReleaseBaseUrl", $unsafeRelease, "-PythonExe", $python, "-NoStart", "-SkipPath")
    Assert-Failed $unsafeProbe "Unsafe tar probe"
    Assert-Contains $unsafeProbe.Output "Refusing unsafe archive member" "Unsafe tar probe must reject traversal."
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $unsafePrefix "app\current-version"))) "Unsafe tar probe must not publish a pointer."
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $unsafePrefix "app\versions\$versionA"))) "Unsafe tar probe must not publish a version."
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $unsafePrefix "app\versions\escape.txt"))) "Unsafe tar probe must not escape staging."

    $install = Invoke-IsolatedPowerShell -ScriptPath $installer -Arguments @("-Version", $versionA, "-Prefix", $prefix, "-LibraryPath", $library, "-ReleaseBaseUrl", $releaseBase, "-PythonExe", $python, "-NoStart")
    Assert-Succeeded $install "Fresh install"
    Assert-Equal $versionA (Get-Pointer "current-version") "Fresh install current pointer mismatch."
    $versionRoot = Join-Path $prefix "app\versions\$versionA"
    Assert-True (Test-Path -LiteralPath (Join-Path $versionRoot ".venv\Scripts\python.exe") -PathType Leaf) "Version-local Python is missing."
    foreach ($name in @("appctl.ps1", "install.ps1", "install-sample-data.ps1", "setup-runtime.ps1")) {
        Assert-True (Test-Path -LiteralPath (Join-Path $versionRoot "scripts\$name") -PathType Leaf) "Packaged PowerShell script is missing: $name"
    }
    Assert-True (Test-Path -LiteralPath (Join-Path $prefix "bin\image-prompt-library.ps1") -PathType Leaf) "PowerShell shim is missing."
    Assert-True (Test-Path -LiteralPath (Join-Path $prefix "bin\image-prompt-library.cmd") -PathType Leaf) "CMD shim is missing."
    Assert-True (Test-PathMembership -PathValue ([Environment]::GetEnvironmentVariable("Path", "User")) -ExpectedPath (Join-Path $prefix "bin")) "User PATH does not contain the install bin directory."
    $versionResult = Invoke-App -Arguments @("version")
    Assert-Succeeded $versionResult "Version command"
    Assert-Equal $versionA $versionResult.Output.Trim() "Version command output mismatch."

    $start = Invoke-App -Arguments @("start", "--host", "127.0.0.1", "--port", [string]$port, "--no-browser")
    Assert-Succeeded $start "Start command"
    Assert-HealthVersion $versionA
    $status = Invoke-App -Arguments @("status")
    Assert-Succeeded $status "Status command"
    Assert-Contains $status.Output "Version: $versionA" "Status version mismatch."
    Assert-Contains $status.Output "URL: http://127.0.0.1:$port/" "Status URL mismatch."
    Assert-Contains $status.Output "App: running" "Status must report running."
    $doctor = Invoke-App -Arguments @("doctor")
    Assert-Succeeded $doctor "Doctor command"
    foreach ($section in @("App", "Library", "Database", "Generation", "Updates / Runtime")) { Assert-Contains $doctor.Output $section "Doctor section missing." }
    $record = Get-Content -LiteralPath (Join-Path $prefix "run\server.json") -Raw | ConvertFrom-Json
    $ownedPid = [int]$record.pid
    $stop = Invoke-App -Arguments @("stop")
    Assert-Succeeded $stop "Stop command"
    Start-Sleep -Milliseconds 250
    Assert-True ($null -eq (Get-Process -Id $ownedPid -ErrorAction SilentlyContinue)) "Recorded app PID survived stop."

    $sleeper = Start-Process -FilePath powershell.exe -ArgumentList @("-NoProfile", "-Command", "Start-Sleep -Seconds 600") -WindowStyle Hidden -PassThru
    $sleeper.Refresh()
    $fakeStart = $sleeper.StartTime.ToUniversalTime().AddTicks(1)
    $fakeRecord = [ordered]@{
        pid = $sleeper.Id
        process_start_time_utc = $fakeStart.ToString("o")
        process_start_time_utc_ticks = $fakeStart.Ticks
        process_executable_path = $sleeper.Path
        version = $versionA
        app_root = $versionRoot
        host = "127.0.0.1"
        port = $port
        stdout_log = (Join-Path $prefix "logs\fake.out.log")
        stderr_log = (Join-Path $prefix "logs\fake.err.log")
        created_at = [DateTime]::UtcNow.ToString("o")
    }
    New-Item -ItemType Directory -Path (Join-Path $prefix "run") -Force | Out-Null
    [IO.File]::WriteAllText((Join-Path $prefix "run\server.json"), ($fakeRecord | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
    $mismatchStop = Invoke-App -Arguments @("stop")
    Assert-Failed $mismatchStop "Mismatched-process stop"
    Assert-Contains $mismatchStop.Output "conflicts with a live process" "Mismatched-process stop must report the conflict."
    $sleeper.Refresh()
    Assert-True (-not $sleeper.HasExited) "Stop terminated an unowned sleeper."
    [IO.File]::Delete((Join-Path $prefix "run\server.json"))

    $imageDir = Join-Path $sampleRoot "images"
    New-Item -ItemType Directory -Path $imageDir | Out-Null
    $png = [Convert]::FromBase64String("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC")
    [IO.File]::WriteAllBytes((Join-Path $imageDir "one.png"), $png)
    $manifestPath = Join-Path $sampleRoot "manifest.json"
    $manifest = [ordered]@{
        schema_version = 2
        id = "windows-smoke-sample"
        language = "en"
        source = [ordered]@{ name = "smoke fixture"; license = "CC0" }
        collections = @([ordered]@{ id = "smoke"; name = "Smoke"; names = [ordered]@{ en = "Smoke" } })
        items = @([ordered]@{
            id = "windows-smoke-001"; title = "Windows smoke image"; slug = "windows-smoke-image"; collection_id = "smoke"; image = "one.png"
            source_name = "smoke fixture"; source_url = "https://example.test/windows-smoke"; author = "smoke"; license = "CC0"; tags = @("smoke")
            prompts = @([ordered]@{ language = "en"; text = "A one pixel smoke fixture."; is_primary = $true; is_original = $true; provenance = [ordered]@{ kind = "source"; source_language = "en"; derived_from = $null; method = $null } })
        })
    }
    [IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json -Depth 12), (New-Object Text.UTF8Encoding($false)))
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $sampleZip = Join-Path $sampleRoot "sample images.zip"
    [IO.Compression.ZipFile]::CreateFromDirectory($imageDir, $sampleZip)
    $env:SAMPLE_DATA_MANIFEST = $manifestPath
    $env:SAMPLE_DATA_IMAGE_ZIP = $sampleZip
    $env:SAMPLE_DATA_IMAGE_ZIP_SHA256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $sampleZip).Hash.ToLowerInvariant()
    $env:SAMPLE_DATA_WORK_DIR = Join-Path $sampleRoot "Installer Work"
    $firstImport = Invoke-App -Arguments @("sample-data", "en")
    Assert-Succeeded $firstImport "First sample import"
    Assert-Contains $firstImport.Output "Imported 1 items and 1 images" "First sample import counts mismatch."
    $secondImport = Invoke-App -Arguments @("sample-data", "en")
    Assert-Succeeded $secondImport "Second sample import"
    Assert-Contains $secondImport.Output "Imported 0 items and 0 images" "Second sample import must be idempotent."
    $sampleStatus = Invoke-App -Arguments @("status")
    Assert-Contains $sampleStatus.Output "Items: 1" "Status must report one imported item."

    $unsafeSampleZip = Join-Path $sampleRoot "unsafe sample.zip"
    $stream = [IO.File]::Open($unsafeSampleZip, [IO.FileMode]::CreateNew)
    try {
        $archive = New-Object IO.Compression.ZipArchive($stream, [IO.Compression.ZipArchiveMode]::Create, $false)
        try {
            $entry = $archive.CreateEntry("../sample-escape.png")
            $entryStream = $entry.Open()
            try { $entryStream.Write($png, 0, $png.Length) } finally { $entryStream.Dispose() }
        } finally { $archive.Dispose() }
    } finally { $stream.Dispose() }
    $env:SAMPLE_DATA_IMAGE_ZIP = $unsafeSampleZip
    $env:SAMPLE_DATA_IMAGE_ZIP_SHA256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $unsafeSampleZip).Hash.ToLowerInvariant()
    $unsafeSample = Invoke-App -Arguments @("sample-data", "en")
    Assert-Failed $unsafeSample "Unsafe sample ZIP import"
    Assert-Contains $unsafeSample.Output "Refusing unsafe ZIP member" "Unsafe sample ZIP must be rejected."
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $env:SAMPLE_DATA_WORK_DIR "sample-escape.png"))) "Unsafe sample ZIP escaped staging."
    $sampleStatus = Invoke-App -Arguments @("status")
    Assert-Contains $sampleStatus.Output "Items: 1" "Rejected sample ZIP changed item count."

    $env:IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL = $releaseBase
    $restartA = Invoke-App -Arguments @("start", "--host", "127.0.0.1", "--port", [string]$port, "--no-browser")
    Assert-Succeeded $restartA "Restart before update"
    $update = Invoke-App -Arguments @("update", "--version", $versionB)
    Assert-Succeeded $update "Update to test-b"
    Assert-Equal $versionB (Get-Pointer "current-version") "Update current pointer mismatch."
    Assert-Equal $versionA (Get-Pointer "previous-version") "Update previous pointer mismatch."
    Assert-HealthVersion $versionB
    $rollback = Invoke-App -Arguments @("rollback")
    Assert-Succeeded $rollback "Rollback to test-a"
    Assert-Equal $versionA (Get-Pointer "current-version") "Rollback current pointer mismatch."
    Assert-Equal $versionB (Get-Pointer "previous-version") "Rollback previous pointer mismatch."
    Assert-HealthVersion $versionA

    $previousErrorLog = Join-Path $prefix "logs\app.previous.err.log"
    $previousErrorLogExisted = Test-Path -LiteralPath $previousErrorLog -PathType Leaf
    $previousErrorLogHash = $null
    $previousErrorLogMtime = $null
    if ($previousErrorLogExisted) {
        $previousErrorLogHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $previousErrorLog).Hash
        $previousErrorLogMtime = (Get-Item -LiteralPath $previousErrorLog).LastWriteTimeUtc.Ticks
    }
    Publish-DerivedRelease -Python $python -SourceTag $versionB -TargetTag $versionBroken -Mode broken -Destination $releaseBase
    $brokenUpdate = Invoke-App -Arguments @("update", "--version", $versionBroken)
    Assert-Failed $brokenUpdate "Broken update"
    Assert-Contains $brokenUpdate.Output "Automatic recovery restored $versionA." "Broken update must report automatic recovery."
    Assert-Equal $versionA (Get-Pointer "current-version") "Recovery current pointer mismatch."
    Assert-Equal $versionB (Get-Pointer "previous-version") "Recovery previous pointer mismatch."
    Assert-HealthVersion $versionA
    Assert-True (Test-Path -LiteralPath $previousErrorLog -PathType Leaf) "Failed-launch previous error log was not retained."
    $freshErrorLog = Get-Item -LiteralPath $previousErrorLog
    Assert-True ($freshErrorLog.Length -gt 0) "Failed-launch previous error log was empty."
    if ($previousErrorLogExisted) {
        $freshErrorLogHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $previousErrorLog).Hash
        Assert-True ($freshErrorLog.LastWriteTimeUtc.Ticks -gt $previousErrorLogMtime -and $freshErrorLogHash -ne $previousErrorLogHash) "Failed-launch previous error log was not fresh."
    }

    $sentinel = Join-Path $library "private-sentinel.txt"
    [IO.File]::WriteAllText($sentinel, "preserve", [Text.Encoding]::ASCII)
    $stop = Invoke-App -Arguments @("stop")
    Assert-Succeeded $stop "Stop before preserving uninstall"
    $uninstall = Invoke-App -Arguments @("uninstall", "--yes")
    Assert-Succeeded $uninstall "Preserving uninstall"
    Assert-Contains $uninstall.Output "Private library preserved at $library" "Private library preserved at message mismatch."
    Assert-True (-not (Test-Path -LiteralPath $prefix)) "Preserving uninstall left the prefix."
    Assert-True (Test-Path -LiteralPath $sentinel -PathType Leaf) "Preserving uninstall removed private data."
    Assert-True (-not (Test-PathMembership -PathValue ([Environment]::GetEnvironmentVariable("Path", "User")) -ExpectedPath (Join-Path $prefix "bin"))) "Preserving uninstall left User PATH residue."

    $reinstall = Invoke-IsolatedPowerShell -ScriptPath $installer -Arguments @("-Version", $versionA, "-Prefix", $prefix, "-LibraryPath", $library, "-ReleaseBaseUrl", $releaseBase, "-PythonExe", $python, "-NoStart")
    Assert-Succeeded $reinstall "Reinstall before delete-library uninstall"
    $deleteUninstall = Invoke-App -Arguments @("uninstall", "--delete-library", "--yes")
    Assert-Succeeded $deleteUninstall "Delete-library uninstall"
    Assert-True (-not (Test-Path -LiteralPath $prefix)) "Delete-library uninstall left the prefix."
    Assert-True (-not (Test-Path -LiteralPath $library)) "Delete-library uninstall left the private library."
    Assert-True (-not (Test-PathMembership -PathValue ([Environment]::GetEnvironmentVariable("Path", "User")) -ExpectedPath (Join-Path $prefix "bin"))) "Delete-library uninstall left User PATH residue."
    $passed = $true
} catch {
    $runFailure = $_
} finally {
    try { $cleanupErrors = @(Invoke-SmokeCleanup -KeepWorkRoot:$KeepWorkRoot) }
    catch { $cleanupErrors = @("cleanup coordinator: $($_.Exception.Message)") }
}

if ($runFailure) {
    if ($cleanupErrors.Count) { throw "$($runFailure.Exception.Message) Cleanup errors: $($cleanupErrors -join '; ')" }
    throw $runFailure
}
if ($cleanupErrors.Count) { throw "Smoke cleanup failed: $($cleanupErrors -join '; ')" }
if (-not $passed) { throw "Smoke did not complete." }
Write-Output "Native Windows installer smoke passed."
