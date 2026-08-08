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
    return (Get-PythonCandidateInfo -Exe $Exe -PrefixArgs $PrefixArgs).Supported
}

function Get-PythonCandidateInfo {
    param([string]$Exe, [string[]]$PrefixArgs)
    try {
        $output = @(& $Exe @PrefixArgs -c "import sys; print('.'.join(map(str, sys.version_info[:3]))); raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" 2>$null)
        $version = if ($output.Count) { [string]$output[$output.Count - 1] } else { "unknown" }
        return [pscustomobject]@{ Supported = $LASTEXITCODE -eq 0; Version = $version.Trim() }
    } catch {
        return [pscustomobject]@{ Supported = $false; Version = "unavailable" }
    }
}

function New-PythonRequirementMessage {
    param([string[]]$Detected = @())
    $message = "Image Prompt Library requires Python 3.10 or newer."
    if ($Detected.Count) { $message += " Detected unsupported Python: $($Detected -join ',')." }
    return $message + " Install Python from https://www.python.org/downloads/windows/, make sure the Python launcher is available and 'py -3' works, then rerun the installer."
}

function Find-SupportedPython {
    if ($PythonExe) {
        $info = Get-PythonCandidateInfo -Exe $PythonExe -PrefixArgs $PythonPrefixArgs
        if (-not $info.Supported) {
            throw (New-PythonRequirementMessage -Detected @("$PythonExe $($info.Version)"))
        }
        return [pscustomobject]@{ Exe = $PythonExe; PrefixArgs = @($PythonPrefixArgs) }
    }
    $detected = New-Object Collections.Generic.List[string]
    foreach ($candidate in @(
        [pscustomobject]@{ Name = "py"; PrefixArgs = @("-3") },
        [pscustomobject]@{ Name = "python"; PrefixArgs = @() }
    )) {
        $command = Get-Command $candidate.Name -ErrorAction SilentlyContinue
        if ($command) {
            $info = Get-PythonCandidateInfo -Exe $command.Source -PrefixArgs $candidate.PrefixArgs
            if ($info.Supported) {
                return [pscustomobject]@{ Exe = $command.Source; PrefixArgs = @($candidate.PrefixArgs) }
            }
            $detected.Add("$($candidate.Name) $($info.Version)")
        }
    }
    throw (New-PythonRequirementMessage -Detected ([string[]]$detected))
}

function Assert-DisjointPaths {
    param([string]$AppPrefix, [string]$PrivateLibrary)
    $lexicalApp = Get-NormalizedPath -Path $AppPrefix
    $lexicalLibrary = Get-NormalizedPath -Path $PrivateLibrary
    if ((Test-PathWithinOrEqual -Path $lexicalApp -Parent $lexicalLibrary) -or
        (Test-PathWithinOrEqual -Path $lexicalLibrary -Parent $lexicalApp)) {
        throw "The app prefix and private library must not contain each other."
    }
    $app = Get-PhysicalPathIdentity -Path $AppPrefix
    $library = Get-PhysicalPathIdentity -Path $PrivateLibrary
    if ((Test-PathWithinOrEqual -Path $app -Parent $library) -or
        (Test-PathWithinOrEqual -Path $library -Parent $app)) {
        throw "The app prefix and private library must not contain each other."
    }
}

function Get-NormalizedPath {
    param([string]$Path)
    $full = [IO.Path]::GetFullPath($Path)
    if ($full.StartsWith('\\?\UNC\', [StringComparison]::OrdinalIgnoreCase)) {
        $full = '\\' + $full.Substring(8)
    } elseif ($full.StartsWith('\\?\', [StringComparison]::OrdinalIgnoreCase)) {
        $full = $full.Substring(4)
    }
    $full = [IO.Path]::GetFullPath($full)
    $root = [IO.Path]::GetPathRoot($full)
    if ($full.Length -gt $root.Length) { $full = $full.TrimEnd('\') }
    return $full
}

if (-not ('ImagePromptLibrary.NativePaths' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;

namespace ImagePromptLibrary {
    public static class NativePaths {
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern SafeFileHandle CreateFile(string name, uint access, uint share, IntPtr security, uint creation, uint flags, IntPtr template);
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern uint GetFinalPathNameByHandle(SafeFileHandle handle, StringBuilder path, uint length, uint flags);

        public static string GetFinalPath(string path) {
            using (SafeFileHandle handle = CreateFile(path, 0, 7, IntPtr.Zero, 3, 0x02000000, IntPtr.Zero)) {
                if (handle.IsInvalid) throw new Win32Exception(Marshal.GetLastWin32Error());
                StringBuilder buffer = new StringBuilder(32768);
                uint length = GetFinalPathNameByHandle(handle, buffer, (uint)buffer.Capacity, 0);
                if (length == 0 || length >= buffer.Capacity) throw new Win32Exception(Marshal.GetLastWin32Error());
                return buffer.ToString();
            }
        }
    }
}
'@
}

function Get-PhysicalPathIdentity {
    param([string]$Path)
    $normalized = Get-NormalizedPath -Path $Path
    $suffix = New-Object Collections.Generic.List[string]
    $cursor = $normalized
    while (-not [IO.Directory]::Exists($cursor) -and -not [IO.File]::Exists($cursor)) {
        $leaf = [IO.Path]::GetFileName($cursor)
        if (-not $leaf) { throw "No existing ancestor could be resolved for path: $Path" }
        $suffix.Insert(0, $leaf)
        $cursor = [IO.Path]::GetDirectoryName($cursor)
    }
    $physical = Get-NormalizedPath -Path ([ImagePromptLibrary.NativePaths]::GetFinalPath($cursor))
    foreach ($component in $suffix) { $physical = Join-Path $physical $component }
    return (Get-NormalizedPath -Path $physical)
}

function Get-UserProfilePhysicalIdentity {
    $profile = Get-NormalizedPath -Path $env:USERPROFILE
    $parent = Get-PhysicalPathIdentity -Path ([IO.Path]::GetDirectoryName($profile))
    return (Get-NormalizedPath -Path (Join-Path $parent ([IO.Path]::GetFileName($profile))))
}

function Assert-SafeInstallTarget {
    param([string]$Path, [string]$Name)
    $normalized = Get-NormalizedPath -Path $Path
    $lexicalRoot = [IO.Path]::GetPathRoot($normalized)
    $lexicalProfile = Get-NormalizedPath -Path $env:USERPROFILE
    if ($normalized.Equals($lexicalRoot, [StringComparison]::OrdinalIgnoreCase) -or
        (Test-PathWithinOrEqual -Path $lexicalProfile -Parent $normalized)) {
        throw "$Name must not be an unsafe root path."
    }
    $identity = Get-PhysicalPathIdentity -Path $Path
    $profileIdentity = Get-UserProfilePhysicalIdentity
    if ($identity.Equals([IO.Path]::GetPathRoot($identity), [StringComparison]::OrdinalIgnoreCase) -or
        (Test-PathWithinOrEqual -Path $profileIdentity -Parent $identity)) {
        throw "$Name must not be an unsafe root path."
    }
    return $identity
}

function Assert-NoReparseAncestors {
    param([string]$Path, [string]$Name, [switch]$ExcludeLeaf)
    $normalized = Get-NormalizedPath -Path $Path
    $root = [IO.Path]::GetPathRoot($normalized)
    $parts = @($normalized.Substring($root.Length).Split(@('\'), [StringSplitOptions]::RemoveEmptyEntries))
    $limit = if ($ExcludeLeaf -and $parts.Count) { $parts.Count - 1 } else { $parts.Count }
    $cursor = $root
    for ($index = 0; $index -lt $limit; $index++) {
        $cursor = Join-Path $cursor $parts[$index]
        try {
            $attributes = [IO.File]::GetAttributes($cursor)
        } catch {
            $cause = if ($_.Exception.InnerException) { $_.Exception.InnerException } else { $_.Exception }
            if ($cause -is [IO.FileNotFoundException] -or $cause -is [IO.DirectoryNotFoundException]) { return $normalized }
            throw
        }
        if (($attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "$Name must not use an existing reparse-point ancestor: $cursor"
        }
    }
    return $normalized
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
    if (-not $Value -or -not (Test-WindowsPathComponent -Value $Value)) { return $false }
    $match = [regex]::Match(
        $Value,
        '^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?\z'
    )
    if (-not $match.Success) { return $false }
    foreach ($identifier in @($match.Groups[4].Value -split '\.')) {
        if ($identifier -match '^[0-9]+\z' -and $identifier.Length -gt 1 -and $identifier.StartsWith('0')) {
            return $false
        }
    }
    return $true
}

function Test-InstalledVersionToken {
    param([string]$Value)
    return $Value -match '^[A-Za-z0-9][A-Za-z0-9._-]*$' -and
        $Value -notmatch '(?i)\.backup$' -and
        (Test-WindowsPathComponent -Value $Value)
}

function Enter-InstallLock {
    param([string]$AppPrefix)
    $bytes = [Text.Encoding]::UTF8.GetBytes((Get-PhysicalPathIdentity -Path $AppPrefix).ToUpperInvariant())
    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        $name = "ImagePromptLibrary.Transaction." + (($sha256.ComputeHash($bytes) | ForEach-Object { $_.ToString('x2') }) -join '')
    } finally {
        $sha256.Dispose()
    }
    $mutex = New-Object Threading.Mutex($false, $name)
    try {
        if (-not $mutex.WaitOne([TimeSpan]::FromMinutes(2))) {
            throw "Another Image Prompt Library transaction is already running for this prefix."
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
    Assert-NoReparseAncestors -Path $validated -Name "Installer cleanup path" -ExcludeLeaf | Out-Null
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
    Assert-NoReparseAncestors -Path $validated -Name "Installer cleanup path" -ExcludeLeaf | Out-Null
    Remove-Item -LiteralPath $validated -Force
}

function Remove-InstallerStagingRemnants {
    param([string]$VersionsPath, [string]$AppPrefix)
    if (-not (Test-Path -LiteralPath $VersionsPath -PathType Container)) { return }
    $versionsIdentity = Get-PhysicalPathIdentity -Path $VersionsPath
    foreach ($item in @(Get-ChildItem -LiteralPath $VersionsPath -Force)) {
        if ($item.Name -notmatch '^\.staging-[0-9a-fA-F]{32}$') { continue }
        if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Refusing ambiguous installer staging remnant: $($item.FullName)"
        }
        $itemParent = [IO.Path]::GetDirectoryName($item.FullName)
        if (-not [string]::Equals((Get-PhysicalPathIdentity -Path $itemParent), $versionsIdentity, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing installer staging remnant outside the managed versions directory."
        }
        Remove-ValidatedTree -Target $item.FullName -AppPrefix $AppPrefix
    }
}

function Get-LiteralPathEntry {
    param([string]$Path)
    $parent = [IO.Path]::GetDirectoryName((Get-NormalizedPath -Path $Path))
    $leaf = [IO.Path]::GetFileName($Path)
    if (-not [IO.Directory]::Exists($parent)) { return $null }
    foreach ($item in @(Get-ChildItem -LiteralPath $parent -Force)) {
        if ([string]::Equals($item.Name, $leaf, [StringComparison]::OrdinalIgnoreCase)) {
            return $item
        }
    }
    return $null
}

function Repair-InterruptedVersionPublication {
    param(
        [string]$FinalTarget,
        [string]$BackupTarget,
        [string]$CurrentVersion,
        [string]$ReleaseVersion,
        [string]$AppPrefix
    )
    $backupItem = Get-LiteralPathEntry -Path $BackupTarget
    if ($null -eq $backupItem) { return }
    if (-not $backupItem.PSIsContainer -or ($backupItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Refusing ambiguous installer backup remnant: $BackupTarget"
    }
    Assert-VersionPayload -Root $BackupTarget -ExpectedVersion $ReleaseVersion
    if (-not (Test-Path -LiteralPath (Join-Path $BackupTarget '.venv\Scripts\python.exe') -PathType Leaf)) {
        throw "Installer backup remnant is missing its version-local Python runtime: $BackupTarget"
    }
    $targetItem = Get-LiteralPathEntry -Path $FinalTarget
    if ($null -eq $targetItem) {
        Move-Item -LiteralPath $BackupTarget -Destination $FinalTarget
        return
    }
    if (-not $targetItem.PSIsContainer -or ($targetItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Refusing ambiguous version target beside installer backup: $FinalTarget"
    }
    if ($CurrentVersion -eq $ReleaseVersion) {
        Assert-VersionPayload -Root $FinalTarget -ExpectedVersion $ReleaseVersion
        if (-not (Test-Path -LiteralPath (Join-Path $FinalTarget '.venv\Scripts\python.exe') -PathType Leaf)) {
            throw "Selected version target is missing its version-local Python runtime: $FinalTarget"
        }
        Remove-ValidatedTree -Target $BackupTarget -AppPrefix $AppPrefix
        return
    }
    Remove-ValidatedTree -Target $FinalTarget -AppPrefix $AppPrefix
    Move-Item -LiteralPath $BackupTarget -Destination $FinalTarget
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
    Publish-AtomicBytes -Path $Path -Bytes ([Text.Encoding]::UTF8.GetBytes($Value + [Environment]::NewLine))
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

function Get-ValidatedRedirectUri {
    param([Uri]$Current, [string]$Location)
    if (-not $Location) { throw "Release download redirect did not provide a location." }
    $next = [Uri]::new($Current, $Location)
    return (Assert-ReleaseSource -Source $next.AbsoluteUri)
}

function Invoke-Download {
    param([string]$Uri, [string]$Destination)
    $parent = [IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($Destination))
    if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    $parsed = Assert-ReleaseSource -Source $Uri
    if ($parsed.IsFile) {
        Copy-Item -LiteralPath $parsed.LocalPath -Destination $Destination -Force
        return
    }
    $temporary = $Destination + ".download-" + [Guid]::NewGuid().ToString("N")
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try {
            $current = $parsed
            for ($redirect = 0; $redirect -le 10; $redirect++) {
                $request = [Net.HttpWebRequest]::Create($current)
                $request.AllowAutoRedirect = $false
                $request.UserAgent = "image-prompt-library-installer"
                $response = $null
                try {
                    $response = $request.GetResponse()
                    $status = [int]$response.StatusCode
                    if ($status -in @(301, 302, 303, 307, 308)) {
                        if ($redirect -eq 10) { throw "Release download exceeded 10 redirects." }
                        $current = Get-ValidatedRedirectUri -Current $current -Location ([string]$response.Headers["Location"])
                        continue
                    }
                    if ($status -lt 200 -or $status -ge 300) { throw "Release download returned HTTP $status." }
                    $inputStream = $response.GetResponseStream()
                    $outputStream = [IO.File]::Open($temporary, [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::None)
                    try { $inputStream.CopyTo($outputStream) }
                    finally {
                        $outputStream.Dispose()
                        $inputStream.Dispose()
                    }
                    Move-Item -LiteralPath $temporary -Destination $Destination -Force
                    return
                } finally {
                    if ($response) { $response.Dispose() }
                }
            }
        } catch {
            if ([IO.File]::Exists($temporary)) { [IO.File]::Delete($temporary) }
            if ($attempt -eq 3 -or $_.Exception.Message -match 'must use HTTPS|Remote file') { throw }
            Start-Sleep -Seconds $attempt
        }
    }
}

function Assert-ReleaseSource {
    param([string]$Source)
    $isUncLiteral = $Source.StartsWith('\\?\UNC\', [StringComparison]::OrdinalIgnoreCase) -or
        ($Source.StartsWith('\\', [StringComparison]::Ordinal) -and
            -not $Source.StartsWith('\\?\', [StringComparison]::OrdinalIgnoreCase))
    if ($isUncLiteral) { throw "Remote file release assets are not allowed." }
    if (Test-Path -LiteralPath $Source -PathType Leaf) { return [Uri]::new([IO.Path]::GetFullPath($Source)) }
    $parsed = $null
    if (-not [Uri]::TryCreate($Source, [UriKind]::Absolute, [ref]$parsed)) {
        throw "Release asset location is not a local file or valid URL: $Source"
    }
    if ($parsed.IsFile) {
        if ($parsed.IsUnc -or $parsed.Host) { throw "Remote file release assets are not allowed." }
        return $parsed
    }
    if ($parsed.Scheme -eq "https") { return $parsed }
    if ($parsed.Scheme -eq "http") {
        $address = $null
        $loopback = $parsed.Host.TrimEnd('.').Equals("localhost", [StringComparison]::OrdinalIgnoreCase) -or
            ([Net.IPAddress]::TryParse($parsed.Host, [ref]$address) -and [Net.IPAddress]::IsLoopback($address))
        if ($loopback) { return $parsed }
    }
    throw "Remote release assets must use HTTPS; plain HTTP is allowed only for loopback test servers."
}

function Get-ApiJson {
    param([string]$Uri)
    $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -Headers @{ "User-Agent" = "image-prompt-library-installer" }
    return $response.Content | ConvertFrom-Json
}

function Resolve-LatestReleaseTag {
    $request = [Net.HttpWebRequest]::Create("https://github.com/$Repo/releases/latest")
    $request.AllowAutoRedirect = $true
    $request.MaximumAutomaticRedirections = 10
    $request.UserAgent = "image-prompt-library-installer"
    $response = $null
    try {
        $response = $request.GetResponse()
        $final = $response.ResponseUri
    } finally {
        if ($response) { $response.Dispose() }
    }
    $prefix = "/$Repo/releases/tag/"
    if (-not $final.Scheme.Equals("https", [StringComparison]::OrdinalIgnoreCase) -or
        -not $final.IsDefaultPort -or
        -not $final.Host.Equals("github.com", [StringComparison]::OrdinalIgnoreCase) -or
        -not $final.AbsolutePath.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Latest release pointer is invalid."
    }
    $tag = [Uri]::UnescapeDataString($final.AbsolutePath.Substring($prefix.Length)).TrimEnd('/')
    if (-not (Test-VersionToken -Value $tag) -or $tag.Contains('-')) {
        throw "Latest release pointer is invalid."
    }
    return $tag
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
        $base = "https://github.com/$Repo/releases/download/$Version"
        $release = New-ReleaseSpec -Tag $Version -BaseUrl $base
        if (-not (Test-ApiReleaseCompatibility -Release $release)) {
            throw "Release $Version does not advertise required capability $Capability."
        }
        return $release
    }
    try {
        $latestTag = Resolve-LatestReleaseTag
        $latestBase = "https://github.com/$Repo/releases/download/$latestTag"
        $latest = New-ReleaseSpec -Tag $latestTag -BaseUrl $latestBase
        if (Test-ApiReleaseCompatibility -Release $latest) { return $latest }
    } catch {
        # Fall back to the release list so an older compatible stable release remains installable.
    }
    $page = 1
    while ($true) {
        $candidates = @(Get-ApiJson -Uri "$apiBase`?per_page=100&page=$page")
        foreach ($candidate in $candidates) {
            if ($candidate.draft -or $candidate.prerelease) { continue }
            try {
                $release = New-ReleaseSpec -Tag ([string]$candidate.tag_name) -BaseUrl ([string]$candidate.html_url) -Assets @($candidate.assets)
                if (Test-ApiReleaseCompatibility -Release $release) { return $release }
            } catch {
                continue
            }
        }
        if ($candidates.Count -lt 100) { break }
        $page += 1
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
    if (-not ($manifest.capabilities -is [Array]) -or
        @($manifest.capabilities | Where-Object { $_ -isnot [string] }).Count -gt 0) {
        throw "Release manifest capabilities are invalid."
    }
    if (@($manifest.capabilities) -notcontains $Capability) {
        throw "Release manifest does not advertise required capability $Capability."
    }
    if ([string]$manifest.sha256 -notmatch '^[0-9a-fA-F]{64}$') {
        throw "Release manifest SHA256 is invalid."
    }
    $schemaVersion = 1
    if ($names -contains "schema_version") {
        if (-not ($manifest.schema_version -is [int] -or $manifest.schema_version -is [long]) -or
            [int64]$manifest.schema_version -notin @(1, 2)) {
            throw "Release manifest schema_version is unsupported."
        }
        $schemaVersion = [int64]$manifest.schema_version
    }
    if ($schemaVersion -ge 2 -and $names -notcontains "source_sha") {
        throw "Release manifest is missing source_sha."
    }
    if ($names -contains "source_sha" -and [string]$manifest.source_sha -notmatch '^[0-9a-fA-F]{40}$') {
        throw "Release manifest source_sha is invalid."
    }
    return $manifest
}

function Confirm-ArtifactChecksum {
    param([string]$ChecksumPath, [object]$Manifest, [string]$ExpectedArtifact)
    $lines = @(Get-Content -LiteralPath $ChecksumPath | Where-Object { $_.Trim() })
    if ($lines.Count -ne 1 -or $lines[0] -notmatch '^([0-9a-fA-F]{64})\s+\*?([^\s]+)$') {
        throw "Checksum file must contain exactly one SHA256 and artifact filename."
    }
    $checksumSha = $Matches[1]
    $checksumArtifact = $Matches[2]
    if (-not $checksumArtifact.Equals($ExpectedArtifact, [StringComparison]::Ordinal)) {
        throw "Checksum file artifact name does not match the selected release."
    }
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
            if raw_name.endswith("/"):
                raw_name = raw_name.rstrip("/")
            parts = raw_name.split("/")
            if any(not part or part in {".", ".."} or ":" in part or part.endswith((".", " ")) for part in parts):
                raise SystemExit(f"Refusing unsafe archive member: {member.name}")
            if any(part.split(".", 1)[0].upper() in reserved for part in parts):
                raise SystemExit(f"Refusing unsafe archive member: {member.name}")
            canonical_parts = tuple(part.casefold() for part in parts)
            private_components = {
                ".agents", ".codebase-memory", ".git", ".local-work", ".superpowers", ".venv",
                "backups", "library", "logs", "node_modules", "reports", "__pycache__",
            }
            private = any(
                part in private_components
                or part == ".env"
                or part.startswith(".env.")
                or part.startswith(".codex")
                or part.startswith(".qa-")
                for part in canonical_parts
            )
            private_docs = len(canonical_parts) >= 2 and canonical_parts[0] == "docs" and canonical_parts[1] in {"plans", "qa"}
            if private or private_docs or raw_name.casefold().endswith(".pyc"):
                raise SystemExit(f"Refusing private or runtime archive member: {member.name}")
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
    param([string]$Root, [string]$ExpectedVersion, [switch]$RequirePortableBackup)
    $required = @(
        "VERSION",
        "pyproject.toml",
        "backend\main.py",
        "frontend\dist\index.html",
        "scripts\appctl.ps1",
        "scripts\install.ps1",
        "scripts\install-sample-data.ps1",
        "scripts\setup-runtime.ps1"
    )
    if ($RequirePortableBackup) { $required += "scripts\library-archive.py" }
    foreach ($relative in $required) {
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
        if ($value -and -not (Test-InstalledVersionToken -Value $value)) { throw "A version pointer is invalid." }
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

function Invoke-Controller {
    param([string]$VersionRoot, [string[]]$Arguments)
    $controller = Join-Path $VersionRoot "scripts\appctl.ps1"
    if (-not (Test-Path -LiteralPath $controller -PathType Leaf)) { throw "The current Image Prompt Library version is incomplete." }
    $processArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $controller) + $Arguments
    $oldErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        if (@($Arguments).Count -gt 0 -and $Arguments[0] -in @("start", "internal-start")) {
            Initialize-ImmediateProcessRunner
            $quotedArgs = @($processArgs | ForEach-Object { '"' + $_.Replace('"', '\"') + '"' })
            $result = [ImagePromptLibraryImmediateProcessRunner]::Run("powershell.exe", ($quotedArgs -join " "), $VersionRoot)
            $exitCode = $result.ExitCode
            $output = @($result.Stdout, $result.Stderr) | Where-Object { $_ }
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
            $stopResult = Invoke-Controller -VersionRoot $TargetVersionRoot -Arguments @("internal-stop")
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
        $restartArguments = @("internal-start", "--host", [string]$Runtime.host, "--port", [string]$Runtime.port, "--no-browser")
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
if ($env:IMAGE_PROMPT_LIBRARY_CMD_SHIM -eq "1") {
    $delegate = Get-Process -Id $PID -ErrorAction Stop
    try {
        $env:IMAGE_PROMPT_LIBRARY_CMD_DELEGATE_PID = [string]$PID
        $env:IMAGE_PROMPT_LIBRARY_CMD_DELEGATE_START_TICKS = [string]$delegate.StartTime.ToUniversalTime().Ticks
    } finally {
        $delegate.Dispose()
    }
}
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
@setlocal EnableExtensions EnableDelayedExpansion
@set "IMAGE_PROMPT_LIBRARY_CMD_SHIM=1" & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0image-prompt-library-delegate.ps1" %* & exit /b !errorlevel!
'@
    Publish-AtomicText -Path (Join-Path $BinPath "image-prompt-library-delegate.ps1") -Value $powerShellShim
    Publish-AtomicText -Path (Join-Path $BinPath "image-prompt-library.cmd") -Value $cmdShim
    $legacyShim = Join-Path $BinPath "image-prompt-library.ps1"
    if (Test-Path -LiteralPath $legacyShim) { Remove-ValidatedTree -Target $legacyShim -AppPrefix (Split-Path -Parent $BinPath) }
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
    return [pscustomobject]@{ AddedUser = -not $present; AddedProcess = -not $currentPresent }
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

function Remove-OnePathEntry {
    param([AllowEmptyString()][string]$PathValue, [string]$NormalizedPath)
    if ($null -eq $PathValue) { return $null }
    $parts = @($PathValue -split ';')
    $kept = New-Object Collections.Generic.List[string]
    $removed = $false
    foreach ($entry in $parts) {
        if (-not $removed -and (Test-PathEntryMatch -Entry $entry -NormalizedPath $NormalizedPath)) {
            $removed = $true
        } else {
            $kept.Add($entry)
        }
    }
    return ($kept -join ';')
}

function Undo-AddedPathEntry {
    param([string]$BinPath, $Change)
    $normalized = Get-NormalizedPath -Path $BinPath
    if ($Change.AddedUser) {
        $currentUserPath = [Environment]::GetEnvironmentVariable('Path', 'User')
        [Environment]::SetEnvironmentVariable('Path', (Remove-OnePathEntry -PathValue $currentUserPath -NormalizedPath $normalized), 'User')
    }
    if ($Change.AddedProcess) {
        $env:Path = Remove-OnePathEntry -PathValue $env:Path -NormalizedPath $normalized
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
    $arguments = @("internal-start")
    if ($NoBrowser) { $arguments += "--no-browser" }
    $result = Invoke-Controller -VersionRoot $VersionRoot -Arguments $arguments
    Write-Output $result.Output
    if ($result.ExitCode -ne 0) { throw "The application could not be started. Run image-prompt-library doctor for details." }
}

function Invoke-Install {
    $normalizedPrefix = Get-NormalizedPath -Path $Prefix
    $normalizedLibrary = Get-NormalizedPath -Path $LibraryPath
    if ($Version -ne 'latest' -and -not (Test-VersionToken -Value $Version)) { throw "Release version is invalid: $Version" }
    Assert-SafeInstallTarget -Path $normalizedPrefix -Name "App prefix" | Out-Null
    Assert-SafeInstallTarget -Path $normalizedLibrary -Name "Private library" | Out-Null
    Assert-NoReparseAncestors -Path $normalizedPrefix -Name "App prefix" | Out-Null
    Assert-NoReparseAncestors -Path $normalizedLibrary -Name "Private library" | Out-Null
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
    $pathChange = [pscustomobject]@{ AddedUser = $false; AddedProcess = $false }
    try {
        Assert-NoReparseAncestors -Path $normalizedPrefix -Name "App prefix" | Out-Null
        Assert-NoReparseAncestors -Path $normalizedLibrary -Name "Private library" | Out-Null
        $retiredMarker = Join-Path $normalizedPrefix 'bin\.retired-generation'
        if ([IO.File]::Exists($retiredMarker)) { [IO.File]::Delete($retiredMarker) }
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
            Assert-NoReparseAncestors -Path $path -Name "Managed install path" | Out-Null
        }
        $currentVersion = ''
        if (Test-Path -LiteralPath $currentPointer -PathType Leaf) {
            $currentVersion = (Get-Content -LiteralPath $currentPointer -Raw).Trim()
            if ($currentVersion -and -not (Test-InstalledVersionToken -Value $currentVersion)) { throw 'The current version pointer is invalid.' }
        }
        Remove-InstallerStagingRemnants -VersionsPath $versionsPath -AppPrefix $normalizedPrefix
        Repair-InterruptedVersionPublication -FinalTarget $finalTarget -BackupTarget $backupTarget -CurrentVersion $currentVersion -ReleaseVersion $release.Version -AppPrefix $normalizedPrefix

        $publishedState = [pscustomobject]@{
            Environment = Get-FileState -Path $environmentPath
            LegacyPowerShellShim = Get-FileState -Path (Join-Path $binPath 'image-prompt-library.ps1')
            PowerShellDelegate = Get-FileState -Path (Join-Path $binPath 'image-prompt-library-delegate.ps1')
            CmdShim = Get-FileState -Path (Join-Path $binPath 'image-prompt-library.cmd')
            CurrentPointer = Get-FileState -Path $currentPointer
            PreviousPointer = Get-FileState -Path $previousPointer
        }
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
            Confirm-ArtifactChecksum -ChecksumPath $checksumPath -Manifest $manifest -ExpectedArtifact $release.Artifact

            New-Item -ItemType Directory -Path $versionsPath -Force | Out-Null
            $staging = Join-Path $versionsPath ('.staging-' + [Guid]::NewGuid().ToString('N'))
            Assert-ManagedPath -Path $staging -AppPrefix $normalizedPrefix | Out-Null
            Expand-SafeTar -ArtifactPath $artifactPath -Destination $staging -Python $python -ExpectedSha ([string]$manifest.sha256)
            $requiresPortableBackup = @($manifest.capabilities) -contains "portable-backup-v1"
            Assert-VersionPayload -Root $staging -ExpectedVersion $release.Version -RequirePortableBackup:$requiresPortableBackup
            if (Test-Path -LiteralPath $finalTarget) {
                if ($null -ne (Get-LiteralPathEntry -Path $backupTarget)) { throw "A previous backup exists at $backupTarget." }
                Move-Item -LiteralPath $finalTarget -Destination $backupTarget
                $backupCreated = $true
            }
            Move-Item -LiteralPath $staging -Destination $finalTarget
            $staging = $null
            $targetPublished = $true
            $setup = Join-Path $finalTarget 'scripts\setup-runtime.ps1'
            $setupArguments = @("-AppRoot", $finalTarget, "-PythonExe", $python.Exe)
            if (@($python.PrefixArgs).Count) { $setupArguments += @("-PythonPrefixArgs") + @($python.PrefixArgs) }
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $setup @setupArguments
            if ($LASTEXITCODE -ne 0) { throw 'Runtime setup failed.' }
        }

        if (-not (Test-Path -LiteralPath $normalizedLibrary -PathType Container)) {
            New-Item -ItemType Directory -Path $normalizedLibrary -Force | Out-Null
        }
        if (-not (Test-Path -LiteralPath $backupPath -PathType Container)) {
            New-Item -ItemType Directory -Path $backupPath -Force | Out-Null
        }
        Write-AppEnvironment -Path $environmentPath -PrivateLibrary $normalizedLibrary -AppPrefix $normalizedPrefix
        Write-CommandShim -BinPath $binPath
        if (-not $SkipPath) { $pathChange = Add-UserPathEntry -BinPath $binPath }
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
                    $stopResult = Invoke-Controller -VersionRoot $oldVersionRoot -Arguments @("internal-stop")
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
                $restartArguments = @("internal-start", "--host", [string]$oldRuntime.host, "--port", [string]$oldRuntime.port, "--no-browser")
                $targetStartResult = Invoke-Controller -VersionRoot $finalTarget -Arguments $restartArguments
                if ($targetStartResult.ExitCode -eq 0) {
                    Write-Output $targetStartResult.Output
                } else {
                    $recovery = Invoke-UpdateRecovery -AppDir $appPath -PointerState $oldPointerState -AppPrefix $normalizedPrefix -OldVersionRoot $oldVersionRoot -Runtime $oldRuntime -TargetVersionRoot $finalTarget -StopTarget
                    foreach ($line in $recovery.Output) { Write-Output $line }
                    $currentLogs = "stdout=$(Join-Path $normalizedPrefix 'logs\app.out.log'); stderr=$(Join-Path $normalizedPrefix 'logs\app.err.log')"
                    $previousLogs = "previous stdout=$(Join-Path $normalizedPrefix 'logs\app.previous.out.log'); previous stderr=$(Join-Path $normalizedPrefix 'logs\app.previous.err.log')"
                    if (-not $recovery.Errors.Count) {
                        Write-Output "Automatic recovery restored $($oldPointerState.Current)."
                        throw "Update failed after target start failure. Target controller output: $($targetStartResult.Output -join [Environment]::NewLine) Current logs: $currentLogs. Previous logs: $previousLogs."
                    }
                    throw "Update failed; automatic recovery was incomplete and manual recovery is required. Target controller output: $($targetStartResult.Output -join [Environment]::NewLine) Recovery errors: $($recovery.Errors -join '; ') Current logs: $currentLogs. Previous logs: $previousLogs."
                }
            }
        }
        if ($targetPublished -and -not ($currentVersion -ne $release.Version -and $oldPointerState -and $oldPointerState.Current)) {
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
                [pscustomobject]@{ Name = 'legacy PowerShell shim'; Action = { Restore-FileState -Path (Join-Path $binPath 'image-prompt-library.ps1') -State $publishedState.LegacyPowerShellShim -AppPrefix $normalizedPrefix } },
                [pscustomobject]@{ Name = 'PowerShell delegate'; Action = { Restore-FileState -Path (Join-Path $binPath 'image-prompt-library-delegate.ps1') -State $publishedState.PowerShellDelegate -AppPrefix $normalizedPrefix } },
                [pscustomobject]@{ Name = 'cmd shim'; Action = { Restore-FileState -Path (Join-Path $binPath 'image-prompt-library.cmd') -State $publishedState.CmdShim -AppPrefix $normalizedPrefix } },
                [pscustomobject]@{ Name = 'current pointer'; Action = { Restore-FileState -Path $currentPointer -State $publishedState.CurrentPointer -AppPrefix $normalizedPrefix } },
                [pscustomobject]@{ Name = 'previous pointer'; Action = { Restore-FileState -Path $previousPointer -State $publishedState.PreviousPointer -AppPrefix $normalizedPrefix } }
            )
            if (-not $SkipPath) {
                $rollbackSteps += [pscustomobject]@{ Name = 'PATH addition'; Action = { Undo-AddedPathEntry -BinPath $binPath -Change $pathChange } }
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
        try {
            if ($staging -and (Test-Path -LiteralPath $staging)) {
                Remove-ValidatedTree -Target $staging -AppPrefix $normalizedPrefix
            }
        } catch {
            Write-Warning "Installer staging cleanup failed and will be retried on the next install: $($_.Exception.Message)"
        } finally {
            Exit-InstallLock -Mutex $installLock
        }
    }
}

try {
    Invoke-Install
} catch {
    Fail-Friendly $_.Exception.Message
    return
}
