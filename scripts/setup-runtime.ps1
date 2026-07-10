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
} elseif (-not (Test-PythonCandidate -Exe $venvPython -PrefixArgs @())) {
    throw "Existing .venv Python is unsupported; remove .venv and rerun setup."
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
