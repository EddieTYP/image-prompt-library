[CmdletBinding()]
param(
    [string]$Language,
    [string]$Package = "gpt-image-2-skill",
    [string]$AppRoot,
    [string]$LibraryPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$script:ScriptRoot = $PSScriptRoot

function Throw-SampleDataUsageError {
    param([string]$Message)
    $exception = New-Object ArgumentException $Message
    $exception.Data["SampleDataExitCode"] = 2
    throw $exception
}

function Remove-SampleTree {
    param([string]$Target)
    if (-not (Test-Path -LiteralPath $Target)) { return }
    $item = Get-Item -LiteralPath $Target -Force
    if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        if ($item.PSIsContainer) { [IO.Directory]::Delete($Target, $false) } else { [IO.File]::Delete($Target) }
        return
    }
    if ($item.PSIsContainer) {
        foreach ($child in @(Get-ChildItem -LiteralPath $Target -Force)) {
            Remove-SampleTree -Target $child.FullName
        }
    }
    Remove-Item -LiteralPath $Target -Force
}

function Remove-ExactStaging {
    param([string]$Staging, [string]$WorkRoot)
    $root = [IO.Path]::GetFullPath($WorkRoot).TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
    $target = [IO.Path]::GetFullPath($Staging)
    $prefix = $root + [IO.Path]::DirectorySeparatorChar
    if (-not $target.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase) -or -not [IO.Path]::GetFileName($target).StartsWith(".staging-", [StringComparison]::Ordinal)) {
        throw "Refusing to clean an unexpected sample-data staging directory: $target"
    }
    Remove-SampleTree -Target $target
}

function Invoke-DownloadWithRetry {
    param([string]$Uri, [string]$Destination)
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try {
            Invoke-WebRequest -UseBasicParsing -Uri $Uri -OutFile $Destination
            return
        } catch {
            if ($attempt -eq 3) { throw "Sample image download failed after 3 attempts: $($_.Exception.Message)" }
            Start-Sleep -Seconds $attempt
        }
    }
}

function Invoke-SafeZipExtraction {
    param([string]$PythonExe, [string]$ArchivePath, [string]$Destination, [string]$ExpectedSha)
    $extractor = @'
from pathlib import Path
import hashlib
import re
import shutil
import stat
import sys
import zipfile

archive_path = Path(sys.argv[1])
destination = Path(sys.argv[2]).resolve()
expected_sha = sys.argv[3].lower()
reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{number}" for number in range(1, 10)), *(f"LPT{number}" for number in range(1, 10))}

with open(archive_path, "rb") as archive_file:
    digest = hashlib.sha256()
    for chunk in iter(lambda: archive_file.read(1024 * 1024), b""):
        digest.update(chunk)
    if digest.hexdigest().lower() != expected_sha:
        raise SystemExit("Sample image ZIP checksum mismatch.")
    archive_file.seek(0)
    with zipfile.ZipFile(archive_file) as archive:
        members = []
        destinations = {}
        file_destinations = set()
        for member in archive.infolist():
            raw_name = member.filename.replace("\\", "/")
            is_directory = member.is_dir()
            normalized_name = raw_name.rstrip("/") if is_directory else raw_name
            if not normalized_name or normalized_name.startswith("/") or normalized_name.startswith("//") or re.match(r"^[A-Za-z]:", normalized_name):
                raise SystemExit(f"Refusing unsafe ZIP member: {member.filename}")
            parts = normalized_name.split("/")
            if any(not part or part in {".", ".."} or ":" in part or part.endswith((".", " ")) for part in parts):
                raise SystemExit(f"Refusing unsafe ZIP member: {member.filename}")
            if any(part.split(".", 1)[0].upper() in reserved for part in parts):
                raise SystemExit(f"Refusing unsafe ZIP member: {member.filename}")
            mode = member.external_attr >> 16
            file_type = mode & 0o170000
            if (member.external_attr & 0x400) or stat.S_ISLNK(mode) or (file_type and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode))):
                raise SystemExit(f"Refusing unsafe ZIP member: {member.filename}")
            is_directory = is_directory or stat.S_ISDIR(mode)
            canonical_parts = tuple(part.casefold() for part in parts)
            if canonical_parts in destinations or any(parent in file_destinations for parent in (canonical_parts[:index] for index in range(1, len(canonical_parts)))):
                raise SystemExit(f"Refusing unsafe ZIP member: {member.filename}")
            if not is_directory and any(existing[:len(canonical_parts)] == canonical_parts for existing in destinations):
                raise SystemExit(f"Refusing unsafe ZIP member: {member.filename}")
            member_path = Path(*parts)
            target = (destination / member_path).resolve()
            try:
                target.relative_to(destination)
            except ValueError as exc:
                raise SystemExit(f"Refusing unsafe ZIP member: {member.filename}") from exc
            destinations[canonical_parts] = is_directory
            if not is_directory:
                file_destinations.add(canonical_parts)
            members.append((member, target, is_directory))

        destination.mkdir(parents=True, exist_ok=True)
        for member, target, is_directory in members:
            if is_directory:
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, open(target, "xb") as output:
                    shutil.copyfileobj(source, output)
'@
    $extractorPath = Join-Path ([IO.Path]::GetTempPath()) ("image-prompt-library-sample-data-" + [Guid]::NewGuid().ToString("N") + ".py")
    try {
        [IO.File]::WriteAllText($extractorPath, $extractor, (New-Object Text.UTF8Encoding($false)))
        & $PythonExe $extractorPath $ArchivePath $Destination $ExpectedSha
        if ($LASTEXITCODE -ne 0) { throw "Safe ZIP extraction failed." }
    } finally {
        if ([IO.File]::Exists($extractorPath)) { [IO.File]::Delete($extractorPath) }
    }
}

function Invoke-SampleDataInstall {
    if (-not $Language) { Throw-SampleDataUsageError -Message "Usage: install-sample-data.ps1 <en|zh_hans|zh_hant> [gpt-image-2-skill|awesome-gpt-image-2]" }
    if ($Language -notin @("en", "zh_hans", "zh_hant")) { Throw-SampleDataUsageError -Message "Unsupported sample language: $Language" }
    if ($Package -notin @("gpt-image-2-skill", "awesome-gpt-image-2")) { Throw-SampleDataUsageError -Message "Unsupported sample package: $Package" }
    if ($Package -eq "awesome-gpt-image-2" -and $Language -ne "zh_hant") {
        Throw-SampleDataUsageError -Message "awesome-gpt-image-2 sample package currently ships zh_hant manifests only"
    }

    if (-not $AppRoot) {
        if (-not $script:ScriptRoot) { throw "Cannot determine the Image Prompt Library application root." }
        $AppRoot = Split-Path -Parent $script:ScriptRoot
    }
    $normalizedAppRoot = [IO.Path]::GetFullPath($AppRoot)
    if (-not $LibraryPath) {
        $LibraryPath = if ($env:IMAGE_PROMPT_LIBRARY_PATH) { $env:IMAGE_PROMPT_LIBRARY_PATH } else { Join-Path $normalizedAppRoot "library" }
    }
    $venvPython = Join-Path $normalizedAppRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) { throw "The current Image Prompt Library version is missing its local Python runtime." }

    $manifestPath = if ($env:SAMPLE_DATA_MANIFEST) {
        $env:SAMPLE_DATA_MANIFEST
    } elseif ($Package -eq "awesome-gpt-image-2") {
        Join-Path $normalizedAppRoot "sample-data\manifests\awesome-gpt-image-2\$Language.json"
    } else {
        Join-Path $normalizedAppRoot "sample-data\manifests\$Language.json"
    }
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw "Sample manifest not found: $manifestPath" }

    if ($Package -eq "awesome-gpt-image-2") {
        $releaseTag = "sample-data-awesome-gpt-image-2-v1"
        $defaultAsset = "image-prompt-library-awesome-gpt-image-2-sample-images-v1.zip"
        $defaultSha = "153714b7611524d7b98b4b0452baa86c8d05053477bb670b731953e8d26a8c9c"
    } else {
        $releaseTag = "sample-data-v1"
        $defaultAsset = "image-prompt-library-sample-images-v1.zip"
        $defaultSha = "8a458f6c8c96079f40fbc46c689e7de0bd2eb464ee7f800f94f3ca60131d5035"
    }
    $releaseBaseUrl = if ($env:SAMPLE_DATA_RELEASE_BASE_URL) { $env:SAMPLE_DATA_RELEASE_BASE_URL } else { "https://github.com/EddieTYP/image-prompt-library/releases/download/$releaseTag" }
    $releaseAsset = if ($env:SAMPLE_DATA_RELEASE_ASSET_NAME) { $env:SAMPLE_DATA_RELEASE_ASSET_NAME } else { $defaultAsset }
    $expectedSha = if ($env:SAMPLE_DATA_IMAGE_ZIP_SHA256) { $env:SAMPLE_DATA_IMAGE_ZIP_SHA256 } else { $defaultSha }
    if ($expectedSha -notmatch '^[0-9a-fA-F]{64}$') { throw "Sample image ZIP SHA256 is invalid." }

    $workRoot = [IO.Path]::GetFullPath($(if ($env:SAMPLE_DATA_WORK_DIR) { $env:SAMPLE_DATA_WORK_DIR } else { Join-Path $normalizedAppRoot ".local-work\sample-data-installer\$Package" }))
    $assetDir = $env:SAMPLE_DATA_IMAGE_DIR
    $staging = $null
    try {
        if (-not $assetDir) {
            New-Item -ItemType Directory -Force -Path $workRoot | Out-Null
            $imageZip = if ($env:SAMPLE_DATA_IMAGE_ZIP) { $env:SAMPLE_DATA_IMAGE_ZIP } else { Join-Path $workRoot $releaseAsset }
            if ($env:SAMPLE_DATA_IMAGE_ZIP) {
                if (-not (Test-Path -LiteralPath $imageZip -PathType Leaf)) { throw "Sample image ZIP not found: $imageZip" }
            } else {
                Write-Output "Downloading sample images from $releaseBaseUrl/$releaseAsset"
                Invoke-DownloadWithRetry -Uri "$releaseBaseUrl/$releaseAsset" -Destination $imageZip
            }
            $staging = Join-Path $workRoot (".staging-" + [Guid]::NewGuid().ToString("N"))
            Invoke-SafeZipExtraction -PythonExe $venvPython -ArchivePath $imageZip -Destination $staging -ExpectedSha $expectedSha
            $assetDir = $staging
        }

        Push-Location -LiteralPath $normalizedAppRoot
        try {
            $resultText = (& $venvPython -m backend.services.import_sample_bundle --manifest $manifestPath --assets $assetDir --library $LibraryPath | Out-String)
            if ($LASTEXITCODE -ne 0) { throw "Sample data import failed." }
        } finally {
            Pop-Location
        }
        $result = $resultText | ConvertFrom-Json
        Write-Output "Imported $($result.item_count) items and $($result.image_count) images into $LibraryPath"
        if ($result.log -and $result.log.Trim()) { Write-Output $result.log }
    } finally {
        if ($staging) { Remove-ExactStaging -Staging $staging -WorkRoot $workRoot }
    }
}

try {
    Invoke-SampleDataInstall
} catch {
    [Console]::Error.WriteLine("ERROR: " + $_.Exception.Message)
    $exitCode = if ($_.Exception.Data["SampleDataExitCode"]) { [int]$_.Exception.Data["SampleDataExitCode"] } else { 1 }
    exit $exitCode
}
