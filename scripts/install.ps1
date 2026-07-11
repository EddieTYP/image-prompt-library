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
    $app = [IO.Path]::GetFullPath($AppPrefix).TrimEnd('\')
    $library = [IO.Path]::GetFullPath($PrivateLibrary).TrimEnd('\')
    $comparison = [StringComparison]::OrdinalIgnoreCase
    if ($app.Equals($library, $comparison) -or
        $app.StartsWith($library + "\", $comparison) -or
        $library.StartsWith($app + "\", $comparison)) {
        throw "The app prefix and private library must not contain each other."
    }
}

function Test-VersionToken {
    param([string]$Value)
    return $Value -notin @(".", "..") -and $Value -match '^[A-Za-z0-9][A-Za-z0-9._-]*$'
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
    param([string]$ArtifactPath, [string]$ChecksumPath, [object]$Manifest)
    $lines = @(Get-Content -LiteralPath $ChecksumPath | Where-Object { $_.Trim() })
    if ($lines.Count -ne 1 -or $lines[0] -notmatch '^([0-9a-fA-F]{64})(?:\s+.*)?$') {
        throw "Checksum file must contain exactly one leading SHA256 value."
    }
    $checksumSha = $Matches[1]
    $manifestSha = [string]$Manifest.sha256
    if (-not $checksumSha.Equals($manifestSha, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Checksum file SHA256 does not match the release manifest."
    }
    $calculatedSha = (Get-FileHash -LiteralPath $ArtifactPath -Algorithm SHA256).Hash
    if (-not $calculatedSha.Equals($manifestSha, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Calculated artifact checksum does not match the verified release metadata."
    }
}

function Expand-SafeTar {
    param([string]$ArtifactPath, [string]$Destination, [object]$Python)
    $extractor = Join-Path ([IO.Path]::GetTempPath()) ("image-prompt-library-extractor-" + [Guid]::NewGuid().ToString("N") + ".py")
    $source = @'
from pathlib import Path
import sys, tarfile

archive_path = Path(sys.argv[1])
destination = Path(sys.argv[2]).resolve()
destination.mkdir(parents=True, exist_ok=True)
with tarfile.open(archive_path, "r:gz") as archive:
    members = archive.getmembers()
    for member in members:
        member_path = Path(member.name)
        if member_path.is_absolute() or member_path.drive or ".." in member_path.parts:
            raise SystemExit(f"Refusing unsafe archive member: {member.name}")
        if any(part.lower() == ".venv" for part in member_path.parts):
            raise SystemExit(f"Refusing staged Python environment: {member.name}")
        if member.issym() or member.islnk() or member.isdev():
            raise SystemExit(f"Refusing unsupported archive member: {member.name}")
        if not (member.isfile() or member.isdir()):
            raise SystemExit(f"Refusing unsupported archive member: {member.name}")
        target = (destination / member_path).resolve()
        try:
            target.relative_to(destination)
        except ValueError as exc:
            raise SystemExit(f"Refusing unsafe archive member: {member.name}") from exc
    archive.extractall(destination, members=members)
'@
    try {
        [IO.File]::WriteAllText($extractor, $source, (New-Object Text.UTF8Encoding($false)))
        $arguments = @($Python.PrefixArgs) + @($extractor, $ArtifactPath, $Destination)
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
    param([string]$Path, [AllowEmptyString()][string]$Value)
    if (-not $Value) {
        if (Test-Path -LiteralPath $Path) { Remove-Item -LiteralPath $Path -Force }
        return
    }
    $temporary = "$Path.tmp"
    Set-Content -LiteralPath $temporary -Value $Value -Encoding ASCII
    Move-Item -LiteralPath $temporary -Destination $Path -Force
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
$version = (Get-Content -LiteralPath $pointer -Raw).Trim()
if ($version -in @(".", "..") -or $version -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]*$') { throw "The current version pointer is invalid." }
$controller = Join-Path $prefix "app\versions\$version\scripts\appctl.ps1"
if (-not (Test-Path -LiteralPath $controller -PathType Leaf)) { throw "The current Image Prompt Library version is incomplete." }
& $controller @CommandArgs
$code = $LASTEXITCODE
if ($null -eq $code) { $code = 0 }
exit $code
'@
    $cmdShim = @'
@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0image-prompt-library.ps1" %*
exit /b %ERRORLEVEL%
'@
    Set-Content -LiteralPath (Join-Path $BinPath "image-prompt-library.ps1") -Value $powerShellShim -Encoding ASCII
    Set-Content -LiteralPath (Join-Path $BinPath "image-prompt-library.cmd") -Value $cmdShim -Encoding ASCII
}

function Add-UserPathEntry {
    param([string]$BinPath)
    $normalized = [IO.Path]::GetFullPath($BinPath).TrimEnd('\')
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $parts = @($userPath -split ";" | Where-Object { $_ })
    $present = @($parts | Where-Object { $_.Trim().TrimEnd('\').Equals($normalized, [StringComparison]::OrdinalIgnoreCase) }).Count -gt 0
    if (-not $present) {
        $newUserPath = (@($parts) + @($normalized)) -join ";"
        [Environment]::SetEnvironmentVariable("Path", $newUserPath, "User")
    }
    $currentParts = @($env:Path -split ";" | Where-Object { $_ })
    $currentPresent = @($currentParts | Where-Object { $_.Trim().TrimEnd('\').Equals($normalized, [StringComparison]::OrdinalIgnoreCase) }).Count -gt 0
    if (-not $currentPresent) { $env:Path = (@($currentParts) + @($normalized)) -join ";" }
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
    Set-Content -LiteralPath $Path -Value $lines -Encoding ASCII
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
    $normalizedPrefix = [IO.Path]::GetFullPath($Prefix).TrimEnd('\')
    $normalizedLibrary = [IO.Path]::GetFullPath($LibraryPath).TrimEnd('\')
    Assert-DisjointPaths -AppPrefix $normalizedPrefix -PrivateLibrary $normalizedLibrary
    $python = Find-SupportedPython
    $release = Resolve-Release

    $appPath = Join-Path $normalizedPrefix "app"
    $versionsPath = Join-Path $appPath "versions"
    $downloadsPath = Join-Path (Join-Path $appPath "downloads") $release.Version
    $currentPointer = Join-Path $appPath "current-version"
    $previousPointer = Join-Path $appPath "previous-version"
    $finalTarget = Join-Path $versionsPath $release.Version
    $binPath = Join-Path $normalizedPrefix "bin"
    $currentVersion = ""
    if (Test-Path -LiteralPath $currentPointer -PathType Leaf) {
        $currentVersion = (Get-Content -LiteralPath $currentPointer -Raw).Trim()
    }

    if ($currentVersion -eq $release.Version -and (Test-Path -LiteralPath $finalTarget -PathType Container)) {
        Write-AppEnvironment -Path (Join-Path $normalizedPrefix ".env") -PrivateLibrary $normalizedLibrary -AppPrefix $normalizedPrefix
        Write-CommandShim -BinPath $binPath
        if (-not $SkipPath) { Add-UserPathEntry -BinPath $binPath }
        Start-InstalledVersion -VersionRoot $finalTarget
        Write-Output "Image Prompt Library $($release.Version) is already installed."
        return
    }

    New-Item -ItemType Directory -Path $downloadsPath -Force | Out-Null
    $manifestPath = Join-Path $downloadsPath $release.Manifest
    $artifactPath = Join-Path $downloadsPath $release.Artifact
    $checksumPath = Join-Path $downloadsPath $release.Checksum
    Invoke-Download -Uri $release.ManifestUri -Destination $manifestPath
    $manifest = Read-CompatibleManifest -Release $release -ManifestPath $manifestPath
    Invoke-Download -Uri $release.ArtifactUri -Destination $artifactPath
    Invoke-Download -Uri $release.ChecksumUri -Destination $checksumPath
    Confirm-ArtifactChecksum -ArtifactPath $artifactPath -ChecksumPath $checksumPath -Manifest $manifest

    New-Item -ItemType Directory -Path $versionsPath -Force | Out-Null
    $staging = Join-Path $versionsPath (".staging-" + [Guid]::NewGuid().ToString("N"))
    $backupTarget = Join-Path $versionsPath ($release.Version + ".backup")
    $backupCreated = $false
    try {
        Expand-SafeTar -ArtifactPath $artifactPath -Destination $staging -Python $python
        Assert-VersionPayload -Root $staging -ExpectedVersion $release.Version
        if (Test-Path -LiteralPath $finalTarget) {
            if (Test-Path -LiteralPath $backupTarget) { Remove-Item -LiteralPath $backupTarget -Recurse -Force }
            Move-Item -LiteralPath $finalTarget -Destination $backupTarget
            $backupCreated = $true
        }
        Move-Item -LiteralPath $staging -Destination $finalTarget
        try {
            $setup = Join-Path $finalTarget "scripts\setup-runtime.ps1"
            & $setup -AppRoot $finalTarget -PythonExe $python.Exe -PythonPrefixArgs $python.PrefixArgs
            if (-not $?) { throw "Runtime setup failed." }
        } catch {
            if (Test-Path -LiteralPath $finalTarget) { Remove-Item -LiteralPath $finalTarget -Recurse -Force }
            if ($backupCreated -and (Test-Path -LiteralPath $backupTarget)) {
                Move-Item -LiteralPath $backupTarget -Destination $finalTarget
            }
            throw
        }
        if ($backupCreated -and (Test-Path -LiteralPath $backupTarget)) {
            Remove-Item -LiteralPath $backupTarget -Recurse -Force
        }
    } finally {
        if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
    }

    if (-not (Test-Path -LiteralPath $normalizedLibrary -PathType Container)) {
        New-Item -ItemType Directory -Path $normalizedLibrary -Force | Out-Null
    }
    $backupPath = Join-Path $normalizedPrefix "backups"
    if (-not (Test-Path -LiteralPath $backupPath -PathType Container)) {
        New-Item -ItemType Directory -Path $backupPath -Force | Out-Null
    }
    Write-AppEnvironment -Path (Join-Path $normalizedPrefix ".env") -PrivateLibrary $normalizedLibrary -AppPrefix $normalizedPrefix
    Write-CommandShim -BinPath $binPath
    if (-not $SkipPath) { Add-UserPathEntry -BinPath $binPath }
    Write-VersionPointer -Path $previousPointer -Value $currentVersion
    Write-VersionPointer -Path $currentPointer -Value $release.Version
    Start-InstalledVersion -VersionRoot $finalTarget
    Write-Output "Installed Image Prompt Library $($release.Version)."
}

try {
    Invoke-Install
} catch {
    Fail-Friendly $_.Exception.Message
    return
}
