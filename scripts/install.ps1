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

$RunningFromFile = [bool]$MyInvocation.MyCommand.Path
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Repo = "EddieTYP/image-prompt-library"
$Capability = "windows-powershell-v1"

function Fail-Friendly {
    param([string]$Message)
    [Console]::Error.WriteLine("ERROR: $Message")
    $global:LASTEXITCODE = 1
    if ($RunningFromFile) { exit 1 }
}

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

function Assert-DisjointPaths {
    param([string]$AppPrefix, [string]$PrivateLibrary)
    $app = Get-NormalizedPath -Path $AppPrefix
    $library = Get-NormalizedPath -Path $PrivateLibrary
    if ((Test-PathWithinOrEqual -Path $app -Parent $library) -or
        (Test-PathWithinOrEqual -Path $library -Parent $app)) {
        throw "The app prefix and private library must not contain each other."
    }
}

function Get-NormalizedPath {
    param([string]$Path)
    $full = [IO.Path]::GetFullPath($Path)
    $root = [IO.Path]::GetPathRoot($full)
    if ($full.Length -gt $root.Length) { $full = $full.TrimEnd('\') }
    return $full
}

function Test-PathWithinOrEqual {
    param([string]$Path, [string]$Parent)
    $target = Get-NormalizedPath -Path $Path
    $container = Get-NormalizedPath -Path $Parent
    $comparison = [StringComparison]::OrdinalIgnoreCase
    if ($target.Equals($container, $comparison)) { return $true }
    $containerPrefix = if ($container.EndsWith('\')) { $container } else { $container + '\' }
    return $target.StartsWith($containerPrefix, $comparison)
}

function Assert-ManagedPath {
    param([string]$Path, [string]$AppPrefix)
    $target = Get-NormalizedPath -Path $Path
    $prefix = Get-NormalizedPath -Path $AppPrefix
    if ($target.Equals($prefix, [StringComparison]::OrdinalIgnoreCase) -or
        -not (Test-PathWithinOrEqual -Path $target -Parent $prefix)) {
        throw "Installer cleanup path is outside the configured prefix."
    }
    return $target
}

function Test-WindowsPathComponent {
    param([string]$Value)
    if (-not $Value -or $Value.EndsWith('.') -or $Value.EndsWith(' ') -or $Value.Contains(':')) { return $false }
    $base = $Value.Split('.')[0]
    return $base -notmatch '^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$'
}

function Test-VersionToken {
    param([string]$Value)
    return $Value -match '^[A-Za-z0-9][A-Za-z0-9._-]*$' -and
        $Value -notmatch '(?i)\.backup$' -and
        (Test-WindowsPathComponent -Value $Value)
}

function Enter-InstallLock {
    param([string]$AppPrefix)
    $bytes = [Text.Encoding]::UTF8.GetBytes((Get-NormalizedPath -Path $AppPrefix).ToUpperInvariant())
    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        $name = "ImagePromptLibrary.Install." + (($sha256.ComputeHash($bytes) | ForEach-Object { $_.ToString('x2') }) -join '')
    } finally {
        $sha256.Dispose()
    }
    $mutex = New-Object Threading.Mutex($false, $name)
    try {
        if (-not $mutex.WaitOne([TimeSpan]::FromMinutes(2))) {
            throw "Another Image Prompt Library installer is already running for this prefix."
        }
    } catch [Threading.AbandonedMutexException] {
    } catch {
        $mutex.Dispose()
        throw
    }
    return $mutex
}

function Exit-InstallLock {
    param([Threading.Mutex]$Mutex)
    if ($Mutex) {
        try { $Mutex.ReleaseMutex() } finally { $Mutex.Dispose() }
    }
}

function Remove-ValidatedTree {
    param([string]$Target, [string]$AppPrefix)
    $validated = Assert-ManagedPath -Path $Target -AppPrefix $AppPrefix
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
            Remove-ValidatedTree -Target $child.FullName -AppPrefix $AppPrefix
        }
    }
    Remove-Item -LiteralPath $validated -Force
}

function Publish-AtomicBytes {
    param([string]$Path, [byte[]]$Bytes)
    $directory = [IO.Path]::GetDirectoryName((Get-NormalizedPath -Path $Path))
    if (-not (Test-Path -LiteralPath $directory -PathType Container)) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }
    $temporary = Join-Path $directory ('.' + [IO.Path]::GetFileName($Path) + '.' + [Guid]::NewGuid().ToString('N') + '.tmp')
    $replacementBackup = $temporary + '.bak'
    try {
        [IO.File]::WriteAllBytes($temporary, $Bytes)
        if (Test-Path -LiteralPath $Path) {
            if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Cannot atomically replace non-file $Path." }
            [IO.File]::Replace($temporary, $Path, $replacementBackup)
        } else {
            [IO.File]::Move($temporary, $Path)
        }
    } finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
        if (Test-Path -LiteralPath $replacementBackup) { Remove-Item -LiteralPath $replacementBackup -Force }
    }
}

function Publish-AtomicText {
    param([string]$Path, [AllowEmptyString()][string]$Value)
    Publish-AtomicBytes -Path $Path -Bytes ([Text.Encoding]::ASCII.GetBytes($Value + [Environment]::NewLine))
}

function Get-FileState {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return [pscustomobject]@{ Exists = $false; Bytes = $null } }
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Expected a file at $Path." }
    return [pscustomobject]@{ Exists = $true; Bytes = [IO.File]::ReadAllBytes($Path) }
}

function Restore-FileState {
    param([string]$Path, [object]$State, [string]$AppPrefix)
    if ($State.Exists) {
        Publish-AtomicBytes -Path $Path -Bytes $State.Bytes
    } elseif (Test-Path -LiteralPath $Path) {
        Remove-ValidatedTree -Target $Path -AppPrefix $AppPrefix
    }
}

function Invoke-Download {
    param([string]$Uri, [string]$Destination)
    $parent = [IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($Destination))
    if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    if (Test-Path -LiteralPath $Uri -PathType Leaf) {
        Copy-Item -LiteralPath $Uri -Destination $Destination -Force
        return
    }
    $parsed = $null
    if ([Uri]::TryCreate($Uri, [UriKind]::Absolute, [ref]$parsed) -and $parsed.IsFile) {
        Copy-Item -LiteralPath $parsed.LocalPath -Destination $Destination -Force
        return
    }
    if (-not $parsed -or $parsed.Scheme -notin @("http", "https")) {
        throw "Release asset location is not a local file or HTTP(S) URL: $Uri"
    }
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try {
            Invoke-WebRequest -Uri $Uri -UseBasicParsing -OutFile $Destination
            return
        } catch {
            if ($attempt -eq 3) { throw }
            Start-Sleep -Seconds $attempt
        }
    }
}

function Get-ApiJson {
    param([string]$Uri)
    $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -Headers @{ "User-Agent" = "image-prompt-library-installer" }
    return $response.Content | ConvertFrom-Json
}

function Assert-GitHubAssetUri {
    param([string]$Uri)
    $parsed = $null
    $expectedPath = "/$Repo/releases/download/"
    if (-not [Uri]::TryCreate($Uri, [UriKind]::Absolute, [ref]$parsed) -or
        $parsed.Scheme -ne 'https' -or
        -not $parsed.IsDefaultPort -or
        -not $parsed.Host.Equals('github.com', [StringComparison]::OrdinalIgnoreCase) -or
        -not $parsed.AbsolutePath.StartsWith($expectedPath, [StringComparison]::OrdinalIgnoreCase)) {
        throw "GitHub release assets must use the configured repository HTTPS release download origin."
    }
}

function New-ReleaseSpec {
    param([string]$Tag, [string]$BaseUrl, [object[]]$Assets = @())
    if (-not (Test-VersionToken -Value $Tag)) { throw "Release version is invalid: $Tag" }
    $artifact = "image-prompt-library-$Tag.tar.gz"
    $checksum = "$artifact.sha256"
    $manifest = "image-prompt-library-$Tag.manifest.json"
    if ($Assets.Count -gt 0) {
        $locations = @{}
        foreach ($asset in $Assets) { $locations[[string]$asset.name] = [string]$asset.browser_download_url }
        foreach ($name in @($artifact, $checksum, $manifest)) {
            if (-not $locations.ContainsKey($name) -or -not $locations[$name]) {
                throw "Release $Tag does not contain all native Windows assets."
            }
        }
        $artifactUri = $locations[$artifact]
        $checksumUri = $locations[$checksum]
        $manifestUri = $locations[$manifest]
        foreach ($uri in @($artifactUri, $checksumUri, $manifestUri)) { Assert-GitHubAssetUri -Uri $uri }
    } elseif (Test-Path -LiteralPath $BaseUrl -PathType Container) {
        $artifactUri = Join-Path $BaseUrl $artifact
        $checksumUri = Join-Path $BaseUrl $checksum
        $manifestUri = Join-Path $BaseUrl $manifest
    } else {
        $base = $BaseUrl.TrimEnd('/') + "/"
        $artifactUri = ([Uri]::new([Uri]$base, $artifact)).AbsoluteUri
        $checksumUri = ([Uri]::new([Uri]$base, $checksum)).AbsoluteUri
        $manifestUri = ([Uri]::new([Uri]$base, $manifest)).AbsoluteUri
    }
    return [pscustomobject]@{
        Version = $Tag
        BaseUrl = $BaseUrl
        Artifact = $artifact
        Checksum = $checksum
        Manifest = $manifest
        ArtifactUri = $artifactUri
        ChecksumUri = $checksumUri
        ManifestUri = $manifestUri
    }
}

function Test-ApiReleaseCompatibility {
    param([object]$Release)
    $temporary = Join-Path ([IO.Path]::GetTempPath()) ("image-prompt-library-manifest-" + [Guid]::NewGuid().ToString("N") + ".json")
    try {
        Invoke-Download -Uri $Release.ManifestUri -Destination $temporary
        Read-CompatibleManifest -Release $Release -ManifestPath $temporary | Out-Null
        return $true
    } catch {
        return $false
    } finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
    }
}

function Resolve-Release {
    if ($ReleaseBaseUrl) {
        if ($Version -eq "latest") { throw "-ReleaseBaseUrl requires an explicit -Version tag." }
        $base = if (Test-Path -LiteralPath $ReleaseBaseUrl -PathType Container) {
            [IO.Path]::GetFullPath($ReleaseBaseUrl)
        } else {
            $ReleaseBaseUrl
        }
        return New-ReleaseSpec -Tag $Version -BaseUrl $base
    }
    $apiBase = "https://api.github.com/repos/$Repo/releases"
    if ($Version -ne "latest") {
        $encoded = [Uri]::EscapeDataString($Version)
        $apiRelease = Get-ApiJson -Uri "$apiBase/tags/$encoded"
        $release = New-ReleaseSpec -Tag ([string]$apiRelease.tag_name) -BaseUrl ([string]$apiRelease.html_url) -Assets @($apiRelease.assets)
        if (-not (Test-ApiReleaseCompatibility -Release $release)) {
            throw "Release $Version does not advertise required capability $Capability."
        }
        return $release
    }
    foreach ($candidate in @(Get-ApiJson -Uri "$apiBase`?per_page=20")) {
        if ($candidate.draft -or $candidate.prerelease) { continue }
        try {
            $release = New-ReleaseSpec -Tag ([string]$candidate.tag_name) -BaseUrl ([string]$candidate.html_url) -Assets @($candidate.assets)
            if (Test-ApiReleaseCompatibility -Release $release) { return $release }
        } catch {
            continue
        }
    }
    throw "No published stable release currently supports native Windows PowerShell installation."
}

function Read-CompatibleManifest {
    param([object]$Release, [string]$ManifestPath)
    try {
        $manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
    } catch {
        throw "Release manifest is not valid JSON."
    }
    $names = @($manifest.PSObject.Properties.Name)
    foreach ($required in @("name", "version", "artifact", "capabilities", "sha256")) {
        if ($names -notcontains $required) { throw "Release manifest is missing $required." }
    }
    if ($manifest.name -ne "image-prompt-library" -or
        $manifest.version -ne $Release.Version -or
        $manifest.artifact -ne $Release.Artifact) {
        throw "Release manifest identity does not match the selected release."
    }
    if (@($manifest.capabilities) -notcontains $Capability) {
        throw "Release manifest does not advertise required capability $Capability."
    }
    if ([string]$manifest.sha256 -notmatch '^[0-9a-fA-F]{64}$') {
        throw "Release manifest SHA256 is invalid."
    }
    return $manifest
}

function Confirm-ArtifactChecksum {
    param([string]$ChecksumPath, [object]$Manifest)
    $lines = @(Get-Content -LiteralPath $ChecksumPath | Where-Object { $_.Trim() })
    if ($lines.Count -ne 1 -or $lines[0] -notmatch '^([0-9a-fA-F]{64})(?:\s+.*)?$') {
        throw "Checksum file must contain exactly one leading SHA256 value."
    }
    $checksumSha = $Matches[1]
    $manifestSha = [string]$Manifest.sha256
    if (-not $checksumSha.Equals($manifestSha, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Checksum file SHA256 does not match the release manifest."
    }
}

function Expand-SafeTar {
    param([string]$ArtifactPath, [string]$Destination, [object]$Python, [string]$ExpectedSha)
    $extractor = Join-Path ([IO.Path]::GetTempPath()) ("image-prompt-library-extractor-" + [Guid]::NewGuid().ToString("N") + ".py")
    $source = @'
from pathlib import Path
import hashlib
import re
import sys
import tarfile

archive_path = Path(sys.argv[1])
destination = Path(sys.argv[2]).resolve()
expected_sha = sys.argv[3].lower()
destination.mkdir(parents=True, exist_ok=True)
reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{number}" for number in range(1, 10)), *(f"LPT{number}" for number in range(1, 10))}
expected_files = {
    "version",
    "pyproject.toml",
    "backend/main.py",
    "frontend/dist/index.html",
    "scripts/appctl.ps1",
    "scripts/install.ps1",
    "scripts/install-sample-data.ps1",
    "scripts/setup-runtime.ps1",
}
expected_roots = {entry.split("/", 1)[0] for entry in expected_files} | {
    "license",
    "notice",
    "readme.md",
    "sample-data",
    "security.md",
}

with open(archive_path, "rb") as artifact_file:
    digest = hashlib.sha256()
    for chunk in iter(lambda: artifact_file.read(1024 * 1024), b""):
        digest.update(chunk)
    if digest.hexdigest().lower() != expected_sha:
        raise SystemExit("Calculated artifact checksum does not match the verified release metadata.")
    artifact_file.seek(0)
    with tarfile.open(fileobj=artifact_file, mode="r:gz") as archive:
        members = archive.getmembers()
        destinations = {}
        file_destinations = set()
        for member in members:
            raw_name = member.name.replace("\\", "/")
            if not raw_name or raw_name.startswith("/") or raw_name.startswith("//") or re.match(r"^[A-Za-z]:", raw_name):
                raise SystemExit(f"Refusing unsafe archive member: {member.name}")
            parts = raw_name.split("/")
            if any(not part or part in {".", ".."} or ":" in part or part.endswith((".", " ")) for part in parts):
                raise SystemExit(f"Refusing unsafe archive member: {member.name}")
            if any(part.split(".", 1)[0].upper() in reserved for part in parts):
                raise SystemExit(f"Refusing unsafe archive member: {member.name}")
            canonical_parts = tuple(part.casefold() for part in parts)
            if any(part == ".venv" for part in canonical_parts):
                raise SystemExit(f"Refusing staged Python environment: {member.name}")
            if member.issym() or member.islnk() or member.isdev():
                raise SystemExit(f"Refusing unsupported archive member: {member.name}")
            if not (member.isfile() or member.isdir()):
                raise SystemExit(f"Refusing unsupported archive member: {member.name}")
            if canonical_parts[0] not in expected_roots:
                raise SystemExit(f"Refusing ambiguous payload root: {member.name}")
            kind = "file" if member.isfile() else "directory"
            if canonical_parts in destinations or any(parent in file_destinations for parent in (canonical_parts[:index] for index in range(1, len(canonical_parts)))):
                raise SystemExit(f"Refusing ambiguous archive member: {member.name}")
            if kind == "file" and any(existing[:len(canonical_parts)] == canonical_parts for existing in destinations):
                raise SystemExit(f"Refusing file-directory conflict: {member.name}")
            destinations[canonical_parts] = kind
            if kind == "file":
                file_destinations.add(canonical_parts)
        if not expected_files.issubset({"/".join(path) for path, kind in destinations.items() if kind == "file"}):
            raise SystemExit("Refusing payload without the required application files.")
        archive.extractall(destination, members=members)
'@
    try {
        [IO.File]::WriteAllText($extractor, $source, (New-Object Text.UTF8Encoding($false)))
        $arguments = @($Python.PrefixArgs) + @($extractor, $ArtifactPath, $Destination, $ExpectedSha)
        & $Python.Exe @arguments
        if ($LASTEXITCODE -ne 0) { throw "Safe archive extraction failed." }
    } finally {
        if (Test-Path -LiteralPath $extractor) { Remove-Item -LiteralPath $extractor -Force }
    }
}

function Assert-VersionPayload {
    param([string]$Root, [string]$ExpectedVersion)
    foreach ($relative in @(
        "VERSION",
        "pyproject.toml",
        "backend\main.py",
        "frontend\dist\index.html",
        "scripts\appctl.ps1",
        "scripts\install.ps1",
        "scripts\install-sample-data.ps1",
        "scripts\setup-runtime.ps1"
    )) {
        if (-not (Test-Path -LiteralPath (Join-Path $Root $relative) -PathType Leaf)) {
            throw "Release payload is missing required file $relative."
        }
    }
    if ((Get-Content -LiteralPath (Join-Path $Root "VERSION") -Raw).Trim() -ne $ExpectedVersion) {
        throw "Release payload VERSION does not match the selected release."
    }
}

function Write-VersionPointer {
    param([string]$Path, [AllowEmptyString()][string]$Value, [string]$AppPrefix)
    if (-not $Value) {
        if (Test-Path -LiteralPath $Path) { Remove-ValidatedTree -Target $Path -AppPrefix $AppPrefix }
        return
    }
    Publish-AtomicText -Path $Path -Value $Value
}

function Get-CurrentPointerState {
    param([string]$AppDir)
    $currentPath = Join-Path $AppDir "current-version"
    $previousPath = Join-Path $AppDir "previous-version"
    $current = if (Test-Path -LiteralPath $currentPath -PathType Leaf) { (Get-Content -LiteralPath $currentPath -Raw).Trim() } else { "" }
    $previous = if (Test-Path -LiteralPath $previousPath -PathType Leaf) { (Get-Content -LiteralPath $previousPath -Raw).Trim() } else { "" }
    foreach ($value in @($current, $previous)) {
        if ($value -and -not (Test-VersionToken -Value $value)) { throw "A version pointer is invalid." }
    }
    return [pscustomobject]@{ Current = $current; Previous = $previous }
}

function Restore-PointerState {
    param([string]$AppDir, $State, [string]$AppPrefix)
    $errors = New-Object Collections.Generic.List[string]
    try {
        Write-VersionPointer -Path (Join-Path $AppDir "current-version") -Value $State.Current -AppPrefix $AppPrefix
    } catch {
        $errors.Add("current-version: $($_.Exception.Message)")
    }
    try {
        Write-VersionPointer -Path (Join-Path $AppDir "previous-version") -Value $State.Previous -AppPrefix $AppPrefix
    } catch {
        $errors.Add("previous-version: $($_.Exception.Message)")
    }
    if ($errors.Count) { throw "Pointer restoration failed: $($errors -join '; ')" }
}

function Invoke-Controller {
    param([string]$VersionRoot, [string[]]$Arguments)
    $controller = Join-Path $VersionRoot "scripts\appctl.ps1"
    if (-not (Test-Path -LiteralPath $controller -PathType Leaf)) { throw "The current Image Prompt Library version is incomplete." }
    $processArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $controller) + $Arguments
    $oldErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        if (@($Arguments).Count -gt 0 -and $Arguments[0] -eq "start") {
            $quotedArgs = @($processArgs | ForEach-Object { '"' + $_.Replace('"', '\"') + '"' })
            $prefix = [IO.Path]::GetDirectoryName([IO.Path]::GetDirectoryName([IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($VersionRoot))))
            $logDir = Join-Path $prefix "logs"
            New-Item -ItemType Directory -Path $logDir -Force | Out-Null
            $stdoutPath = Join-Path $logDir "controller.out.log"
            $stderrPath = Join-Path $logDir "controller.err.log"
            $command = '""powershell.exe" ' + ($quotedArgs -join " ") + ' 1>"' + $stdoutPath + '" 2>"' + $stderrPath + '""'
            $startInfo = New-Object Diagnostics.ProcessStartInfo
            $startInfo.FileName = $env:ComSpec
            $startInfo.Arguments = "/d /s /c $command"
            $startInfo.WorkingDirectory = $VersionRoot
            $startInfo.UseShellExecute = $false
            $startInfo.CreateNoWindow = $true
            $process = New-Object Diagnostics.Process
            $process.StartInfo = $startInfo
            try {
                if (-not $process.Start()) { throw "Could not start the version controller." }
                $process.WaitForExit()
                $exitCode = $process.ExitCode
            } finally {
                $process.Dispose()
            }
            $output = @()
            foreach ($path in @($stdoutPath, $stderrPath)) {
                if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { continue }
                $stream = [IO.File]::Open($path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
                $reader = New-Object IO.StreamReader($stream, [Text.Encoding]::UTF8, $true)
                try {
                    $text = $reader.ReadToEnd().TrimEnd()
                    if ($text) { $output += $text }
                } finally {
                    $reader.Dispose()
                    $stream.Dispose()
                }
            }
        } else {
            $output = & powershell.exe @processArgs 2>&1
            $exitCode = $LASTEXITCODE
        }
    } finally {
        $ErrorActionPreference = $oldErrorActionPreference
    }
    return [pscustomobject]@{ ExitCode = $exitCode; Output = @($output) }
}

function Invoke-UpdateRecovery {
    param(
        [string]$AppDir,
        $PointerState,
        [string]$AppPrefix,
        [string]$OldVersionRoot,
        $Runtime,
        [string]$TargetVersionRoot = "",
        [switch]$StopTarget
    )
    $errors = New-Object Collections.Generic.List[string]
    $output = New-Object Collections.Generic.List[object]
    if ($StopTarget) {
        try {
            $stopResult = Invoke-Controller -VersionRoot $TargetVersionRoot -Arguments @("stop")
            if ($stopResult.ExitCode -ne 0) {
                $errors.Add("target stop: $($stopResult.Output -join [Environment]::NewLine)")
            } else {
                foreach ($line in $stopResult.Output) { $output.Add($line) }
            }
        } catch {
            $errors.Add("target stop: $($_.Exception.Message)")
        }
    }
    try {
        Restore-PointerState -AppDir $AppDir -State $PointerState -AppPrefix $AppPrefix
    } catch {
        $errors.Add($_.Exception.Message)
    }
    if ($Runtime.running) {
        $restartArguments = @("start", "--host", [string]$Runtime.host, "--port", [string]$Runtime.port, "--no-browser")
        try {
            $restartResult = Invoke-Controller -VersionRoot $OldVersionRoot -Arguments $restartArguments
            if ($restartResult.ExitCode -ne 0) {
                $errors.Add("old-version restart: $($restartResult.Output -join [Environment]::NewLine)")
            } else {
                foreach ($line in $restartResult.Output) { $output.Add($line) }
            }
        } catch {
            $errors.Add("old-version restart: $($_.Exception.Message)")
        }
    }
    return [pscustomobject]@{ Errors = [string[]]$errors; Output = [object[]]$output }
}

function Write-CommandShim {
    param([string]$BinPath)
    if (-not (Test-Path -LiteralPath $BinPath -PathType Container)) {
        New-Item -ItemType Directory -Path $BinPath -Force | Out-Null
    }
    $powerShellShim = @'
[CmdletBinding()]
param([Parameter(ValueFromRemainingArguments=$true)][string[]]$CommandArgs)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$prefix = Split-Path -Parent $PSScriptRoot
$pointer = Join-Path $prefix "app\current-version"
if (-not (Test-Path -LiteralPath $pointer -PathType Leaf)) { throw "Image Prompt Library is not installed." }
$version = (Get-Content -LiteralPath $pointer -Raw).TrimEnd("`r", "`n")
if ($version -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]*$' -or $version.EndsWith('.') -or $version.EndsWith(' ') -or $version -match '(?i)\.backup$' -or $version.Split('.')[0] -match '^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$') { throw "The current version pointer is invalid." }
$versionsRoot = [IO.Path]::GetFullPath((Join-Path $prefix "app\versions"))
$controller = [IO.Path]::GetFullPath((Join-Path $versionsRoot "$version\scripts\appctl.ps1"))
$versionsPrefix = if ($versionsRoot.EndsWith('\')) { $versionsRoot } else { $versionsRoot + '\' }
if (-not $controller.StartsWith($versionsPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw "The current version pointer is invalid." }
if (-not (Test-Path -LiteralPath $controller -PathType Leaf)) { throw "The current Image Prompt Library version is incomplete." }
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $controller @CommandArgs
exit $LASTEXITCODE
'@
    $cmdShim = @'
@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0image-prompt-library.ps1" %*
exit /b %ERRORLEVEL%
'@
    Publish-AtomicText -Path (Join-Path $BinPath "image-prompt-library.ps1") -Value $powerShellShim
    Publish-AtomicText -Path (Join-Path $BinPath "image-prompt-library.cmd") -Value $cmdShim
}

function Add-UserPathEntry {
    param([string]$BinPath)
    $normalized = Get-NormalizedPath -Path $BinPath
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $parts = if ($null -eq $userPath) { @() } else { @($userPath -split ';') }
    $present = @($parts | Where-Object { Test-PathEntryMatch -Entry $_ -NormalizedPath $normalized }).Count -gt 0
    if (-not $present) {
        $newUserPath = if ([string]::IsNullOrEmpty($userPath)) { $normalized } else { $userPath + ';' + $normalized }
        [Environment]::SetEnvironmentVariable("Path", $newUserPath, "User")
    }
    $currentPath = $env:Path
    $currentParts = if ($null -eq $currentPath) { @() } else { @($currentPath -split ';') }
    $currentPresent = @($currentParts | Where-Object { Test-PathEntryMatch -Entry $_ -NormalizedPath $normalized }).Count -gt 0
    if (-not $currentPresent) { $env:Path = if ([string]::IsNullOrEmpty($currentPath)) { $normalized } else { $currentPath + ';' + $normalized } }
}

function Test-PathEntryMatch {
    param([AllowEmptyString()][string]$Entry, [string]$NormalizedPath)
    if ([string]::IsNullOrWhiteSpace($Entry)) { return $false }
    $candidate = $Entry.Trim()
    if ($candidate.Length -ge 2 -and $candidate[0] -eq '"' -and $candidate[$candidate.Length - 1] -eq '"') {
        $candidate = $candidate.Substring(1, $candidate.Length - 2)
    }
    try {
        return (Get-NormalizedPath -Path $candidate).Equals($NormalizedPath, [StringComparison]::OrdinalIgnoreCase)
    } catch {
        return $false
    }
}

function Write-AppEnvironment {
    param([string]$Path, [string]$PrivateLibrary, [string]$AppPrefix)
    if (Test-Path -LiteralPath $Path) { return }
    $hostName = if ($env:BACKEND_HOST) { $env:BACKEND_HOST } else { "127.0.0.1" }
    $port = if ($env:BACKEND_PORT) { $env:BACKEND_PORT } else { "8000" }
    $lines = @(
        "IMAGE_PROMPT_LIBRARY_PATH=$PrivateLibrary",
        "BACKEND_HOST=$hostName",
        "BACKEND_PORT=$port",
        "BACKUP_DIR=$(Join-Path $AppPrefix 'backups')"
    )
    Publish-AtomicText -Path $Path -Value ($lines -join [Environment]::NewLine)
}

function Start-InstalledVersion {
    param([string]$VersionRoot)
    if ($NoStart) { return }
    $controller = Join-Path $VersionRoot "scripts\appctl.ps1"
    $arguments = @("start")
    if ($NoBrowser) { $arguments += "--no-browser" }
    & $controller @arguments
    if ($LASTEXITCODE -ne 0) { throw "The application could not be started. Run image-prompt-library doctor for details." }
}

function Invoke-Install {
    $normalizedPrefix = Get-NormalizedPath -Path $Prefix
    $normalizedLibrary = Get-NormalizedPath -Path $LibraryPath
    if ($Version -ne 'latest' -and -not (Test-VersionToken -Value $Version)) { throw "Release version is invalid: $Version" }
    Assert-DisjointPaths -AppPrefix $normalizedPrefix -PrivateLibrary $normalizedLibrary
    $python = Find-SupportedPython
    $installLock = Enter-InstallLock -AppPrefix $normalizedPrefix
    $staging = $null
    $backupTarget = $null
    $finalTarget = $null
    $backupCreated = $false
    $targetPublished = $false
    $installCommitted = $false
    $stateCaptured = $false
    $oldPointerState = $null
    $oldUserPath = $null
    $oldProcessPath = $env:Path
    try {
        $release = Resolve-Release
        $appPath = Join-Path $normalizedPrefix 'app'
        $versionsPath = Join-Path $appPath 'versions'
        $downloadsPath = Join-Path (Join-Path $appPath 'downloads') $release.Version
        $currentPointer = Join-Path $appPath 'current-version'
        $previousPointer = Join-Path $appPath 'previous-version'
        $finalTarget = Join-Path $versionsPath $release.Version
        $backupTarget = Join-Path $versionsPath ($release.Version + '.backup')
        $binPath = Join-Path $normalizedPrefix 'bin'
        $environmentPath = Join-Path $normalizedPrefix '.env'
        $backupPath = Join-Path $normalizedPrefix 'backups'
        foreach ($path in @($appPath, $versionsPath, $downloadsPath, $currentPointer, $previousPointer, $finalTarget, $backupTarget, $binPath, $environmentPath, $backupPath)) {
            Assert-ManagedPath -Path $path -AppPrefix $normalizedPrefix | Out-Null
        }
        $currentVersion = ''
        if (Test-Path -LiteralPath $currentPointer -PathType Leaf) {
            $currentVersion = (Get-Content -LiteralPath $currentPointer -Raw).Trim()
            if ($currentVersion -and -not (Test-VersionToken -Value $currentVersion)) { throw 'The current version pointer is invalid.' }
        }

        $publishedState = [pscustomobject]@{
            Environment = Get-FileState -Path $environmentPath
            PowerShellShim = Get-FileState -Path (Join-Path $binPath 'image-prompt-library.ps1')
            CmdShim = Get-FileState -Path (Join-Path $binPath 'image-prompt-library.cmd')
            CurrentPointer = Get-FileState -Path $currentPointer
            PreviousPointer = Get-FileState -Path $previousPointer
        }
        $oldUserPath = [Environment]::GetEnvironmentVariable('Path', 'User')
        $stateCaptured = $true

        if ($currentVersion -ne $release.Version -or -not (Test-Path -LiteralPath $finalTarget -PathType Container)) {
            New-Item -ItemType Directory -Path $downloadsPath -Force | Out-Null
            $manifestPath = Join-Path $downloadsPath $release.Manifest
            $artifactPath = Join-Path $downloadsPath $release.Artifact
            $checksumPath = Join-Path $downloadsPath $release.Checksum
            Invoke-Download -Uri $release.ManifestUri -Destination $manifestPath
            $manifest = Read-CompatibleManifest -Release $release -ManifestPath $manifestPath
            Invoke-Download -Uri $release.ArtifactUri -Destination $artifactPath
            Invoke-Download -Uri $release.ChecksumUri -Destination $checksumPath
            Confirm-ArtifactChecksum -ChecksumPath $checksumPath -Manifest $manifest

            New-Item -ItemType Directory -Path $versionsPath -Force | Out-Null
            $staging = Join-Path $versionsPath ('.staging-' + [Guid]::NewGuid().ToString('N'))
            Assert-ManagedPath -Path $staging -AppPrefix $normalizedPrefix | Out-Null
            Expand-SafeTar -ArtifactPath $artifactPath -Destination $staging -Python $python -ExpectedSha ([string]$manifest.sha256)
            Assert-VersionPayload -Root $staging -ExpectedVersion $release.Version
            if (Test-Path -LiteralPath $finalTarget) {
                if (Test-Path -LiteralPath $backupTarget) { throw "A previous backup exists at $backupTarget." }
                Move-Item -LiteralPath $finalTarget -Destination $backupTarget
                $backupCreated = $true
            }
            Move-Item -LiteralPath $staging -Destination $finalTarget
            $staging = $null
            $targetPublished = $true
            $setup = Join-Path $finalTarget 'scripts\setup-runtime.ps1'
            & $setup -AppRoot $finalTarget -PythonExe $python.Exe -PythonPrefixArgs $python.PrefixArgs
            if (-not $?) { throw 'Runtime setup failed.' }
        }

        if (-not (Test-Path -LiteralPath $normalizedLibrary -PathType Container)) {
            New-Item -ItemType Directory -Path $normalizedLibrary -Force | Out-Null
        }
        if (-not (Test-Path -LiteralPath $backupPath -PathType Container)) {
            New-Item -ItemType Directory -Path $backupPath -Force | Out-Null
        }
        Write-AppEnvironment -Path $environmentPath -PrivateLibrary $normalizedLibrary -AppPrefix $normalizedPrefix
        Write-CommandShim -BinPath $binPath
        if (-not $SkipPath) { Add-UserPathEntry -BinPath $binPath }
        if ($targetPublished -and $currentVersion -ne $release.Version) {
            $oldPointerState = Get-CurrentPointerState -AppDir $appPath
            $oldRuntime = [pscustomobject]@{ running = $false; host = $null; port = $null }
            $oldVersionRoot = $null
            if ($oldPointerState.Current) {
                $oldVersionRoot = Join-Path $versionsPath $oldPointerState.Current
                $runtimeResult = Invoke-Controller -VersionRoot $oldVersionRoot -Arguments @("internal-owned-runtime")
                if ($runtimeResult.ExitCode -ne 0) {
                    throw "Could not determine whether the current version is running: $($runtimeResult.Output -join [Environment]::NewLine)"
                }
                try {
                    $oldRuntime = ($runtimeResult.Output -join [Environment]::NewLine) | ConvertFrom-Json
                    if ($null -eq $oldRuntime.running -or ($oldRuntime.running -and ($null -eq $oldRuntime.host -or $null -eq $oldRuntime.port))) {
                        throw "invalid runtime state"
                    }
                } catch {
                    throw "The current version returned an invalid runtime state."
                }
                if ($oldRuntime.running) {
                    $stopResult = Invoke-Controller -VersionRoot $oldVersionRoot -Arguments @("stop")
                    if ($stopResult.ExitCode -ne 0) {
                        throw "Could not stop the current version before updating: $($stopResult.Output -join [Environment]::NewLine)"
                    }
                    Write-Output $stopResult.Output
                }
            }
            try {
                Write-VersionPointer -Path $previousPointer -Value $oldPointerState.Current -AppPrefix $normalizedPrefix
                Write-VersionPointer -Path $currentPointer -Value $release.Version -AppPrefix $normalizedPrefix
            } catch {
                $pointerFailure = $_.Exception.Message
                $recovery = Invoke-UpdateRecovery -AppDir $appPath -PointerState $oldPointerState -AppPrefix $normalizedPrefix -OldVersionRoot $oldVersionRoot -Runtime $oldRuntime
                foreach ($line in $recovery.Output) { Write-Output $line }
                if ($recovery.Errors.Count) {
                    throw "Version pointer switch failed: $pointerFailure Recovery failed: $($recovery.Errors -join '; ')"
                }
                if ($oldRuntime.running) { Write-Output "Automatic recovery restored $($oldPointerState.Current)." }
                throw "Version pointer switch failed: $pointerFailure"
            }
            if ($oldPointerState.Current -and $oldRuntime.running) {
                $restartArguments = @("start", "--host", [string]$oldRuntime.host, "--port", [string]$oldRuntime.port, "--no-browser")
                $targetStartResult = Invoke-Controller -VersionRoot $finalTarget -Arguments $restartArguments
                if ($targetStartResult.ExitCode -eq 0) {
                    Write-Output $targetStartResult.Output
                } else {
                    $recovery = Invoke-UpdateRecovery -AppDir $appPath -PointerState $oldPointerState -AppPrefix $normalizedPrefix -OldVersionRoot $oldVersionRoot -Runtime $oldRuntime -TargetVersionRoot $finalTarget -StopTarget
                    foreach ($line in $recovery.Output) { Write-Output $line }
                    $currentLogs = Join-Path $normalizedPrefix "logs\app.out.log"
                    $previousLogs = Join-Path $normalizedPrefix "logs\app.previous.out.log"
                    if (-not $recovery.Errors.Count) {
                        Write-Output "Automatic recovery restored $($oldPointerState.Current)."
                        throw "Update failed after target start failure. Target controller output: $($targetStartResult.Output -join [Environment]::NewLine) Current logs: $currentLogs. Previous logs: $previousLogs."
                    }
                    throw "Update failed; automatic recovery was incomplete and manual recovery is required. Target controller output: $($targetStartResult.Output -join [Environment]::NewLine) Recovery errors: $($recovery.Errors -join '; ') Current logs: $currentLogs. Previous logs: $previousLogs."
                }
            }
        }
        if (-not ($targetPublished -and $currentVersion -ne $release.Version -and $oldPointerState -and $oldPointerState.Current)) {
            Start-InstalledVersion -VersionRoot $finalTarget
        }
        $installCommitted = $true
        if ($backupCreated -and (Test-Path -LiteralPath $backupTarget)) {
            try {
                Remove-ValidatedTree -Target $backupTarget -AppPrefix $normalizedPrefix
            } catch {
                Write-Warning "Installed successfully, but the previous target backup could not be removed: $($_.Exception.Message)"
            }
        }
        if ($targetPublished) {
            Write-Output "Installed Image Prompt Library $($release.Version)."
        } else {
            Write-Output "Image Prompt Library $($release.Version) is already installed."
        }
    } catch {
        $installFailure = $_
        if ($installCommitted) { throw $installFailure }
        $rollbackErrors = New-Object Collections.Generic.List[string]
        $rollbackSteps = @()
        if ($stateCaptured) {
            $rollbackSteps += @(
                [pscustomobject]@{ Name = 'environment'; Action = { Restore-FileState -Path $environmentPath -State $publishedState.Environment -AppPrefix $normalizedPrefix } },
                [pscustomobject]@{ Name = 'PowerShell shim'; Action = { Restore-FileState -Path (Join-Path $binPath 'image-prompt-library.ps1') -State $publishedState.PowerShellShim -AppPrefix $normalizedPrefix } },
                [pscustomobject]@{ Name = 'cmd shim'; Action = { Restore-FileState -Path (Join-Path $binPath 'image-prompt-library.cmd') -State $publishedState.CmdShim -AppPrefix $normalizedPrefix } },
                [pscustomobject]@{ Name = 'current pointer'; Action = { Restore-FileState -Path $currentPointer -State $publishedState.CurrentPointer -AppPrefix $normalizedPrefix } },
                [pscustomobject]@{ Name = 'previous pointer'; Action = { Restore-FileState -Path $previousPointer -State $publishedState.PreviousPointer -AppPrefix $normalizedPrefix } }
            )
            if (-not $SkipPath) {
                $rollbackSteps += @(
                    [pscustomobject]@{ Name = 'user PATH'; Action = { [Environment]::SetEnvironmentVariable('Path', $oldUserPath, 'User') } },
                    [pscustomobject]@{ Name = 'process PATH'; Action = { $env:Path = $oldProcessPath } }
                )
            }
        }
        if ($targetPublished -and (Test-Path -LiteralPath $finalTarget)) {
            $rollbackSteps += [pscustomobject]@{ Name = 'failed target'; Action = { Remove-ValidatedTree -Target $finalTarget -AppPrefix $normalizedPrefix } }
        }
        if ($backupCreated -and (Test-Path -LiteralPath $backupTarget)) {
            $rollbackSteps += [pscustomobject]@{ Name = 'target backup'; Action = { Move-Item -LiteralPath $backupTarget -Destination $finalTarget } }
        }
        foreach ($step in $rollbackSteps) {
            try {
                & $step.Action
            } catch {
                $rollbackErrors.Add("$($step.Name): $($_.Exception.Message)")
            }
        }
        if ($rollbackErrors.Count -gt 0) {
            throw "Install failed: $($installFailure.Exception.Message) Rollback failed: $($rollbackErrors -join '; ')"
        }
        throw $installFailure
    } finally {
        if ($staging -and (Test-Path -LiteralPath $staging)) {
            Remove-ValidatedTree -Target $staging -AppPrefix $normalizedPrefix
        }
        Exit-InstallLock -Mutex $installLock
    }
}

try {
    Invoke-Install
} catch {
    Fail-Friendly $_.Exception.Message
    return
}
