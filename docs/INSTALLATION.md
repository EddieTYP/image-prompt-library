# Installation and Runtime Guide

This guide keeps operational details out of the main README.

## Native Windows PowerShell (v0.8.0+)

Native Windows support begins with v0.8.0. The current stable release is v0.7.10 and does not provide this native PowerShell quick-start path.

### Prerequisites

- Windows 10 or 11
- Windows PowerShell 5.1 or newer
- Python 3.10+ available through `py -3` or `python`

The installer does not install Python. If Python is missing or too old, install a current version from <https://www.python.org/downloads/windows/> and run the installer again. No administrator access, Git, Node.js, WSL, or machine-wide PATH changes are required.

### Install

In PowerShell, run:

```powershell
irm https://raw.githubusercontent.com/EddieTYP/image-prompt-library/main/scripts/install.ps1 | iex
```

The installer downloads a release only when its manifest advertises the `windows-powershell-v1` capability, verifies the release checksum before extraction, creates a version-local Python runtime, starts the app in the background, and opens the browser.

The public bare command resolves to `%LOCALAPPDATA%\ImagePromptLibrary\bin\image-prompt-library.cmd`. The CMD shim launches its differently named internal PowerShell delegate with `-NoProfile -ExecutionPolicy Bypass -File`, so normal commands continue to work when the caller's Windows PowerShell execution policy is `Restricted`.

To inspect the script before running it:

```powershell
$installer = Join-Path $env:TEMP "image-prompt-library-install.ps1"
Invoke-WebRequest https://raw.githubusercontent.com/EddieTYP/image-prompt-library/main/scripts/install.ps1 -OutFile $installer
notepad $installer
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installer
```

To choose a released version, use the downloaded script:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installer -Version v0.8.0
```

Development and CI release overrides accept literal local directories, `file:` URLs, and loopback HTTP servers. Non-loopback remote release sources must use HTTPS.

### Layout and private data

Replaceable app code, shims, logs, and runtime metadata live under:

```text
%LOCALAPPDATA%\ImagePromptLibrary
```

Your private library defaults to:

```text
%USERPROFILE%\ImagePromptLibrary
```

The private library is separate from versioned app code, so updates and rollbacks do not replace its SQLite database or images.

### Lifecycle, diagnostics, and logs

```powershell
image-prompt-library status
image-prompt-library doctor
image-prompt-library stop
image-prompt-library start
```

`start` runs in the background and opens the browser. `status` reports the selected version, library, URL, app state, item count, and generation state. `doctor` checks the version pointer, runtime, user PATH, logs, database, and provider state.

The current logs are `%LOCALAPPDATA%\ImagePromptLibrary\logs\app.out.log` and `app.err.log`. The previous startup logs are `app.previous.out.log` and `app.previous.err.log` in the same directory.

### Update, rollback, sample data, and uninstall

```powershell
image-prompt-library update
image-prompt-library update --version v0.8.0
image-prompt-library rollback
image-prompt-library sample-data en
image-prompt-library sample-data zh_hans
image-prompt-library sample-data zh_hant awesome-gpt-image-2
image-prompt-library uninstall
```

Update, rollback, start, stop, and uninstall operations share one per-prefix transaction lock. An update switches version pointers transactionally and restores the prior version and runtime after a handled setup, switch, or health failure. This is not durable power-loss recovery: an OS or power interruption can still require `image-prompt-library doctor` followed by a manual retry or rollback. `rollback` validates the previous payload and version-local Python before changing either pointer. Default uninstall removes only the app state and preserves `%USERPROFILE%\ImagePromptLibrary`; use `image-prompt-library uninstall --delete-library` only to remove the private library too, and add `--yes` for non-interactive use.

## Unix and WSL 2

macOS and Linux use the Bash installer below. Windows users who prefer Linux tooling can use the same path through **WSL 2**.

If the server starts in WSL but the Windows browser cannot open `http://127.0.0.1:8000/`, stop the server with Ctrl-C and run:

```bash
image-prompt-library start --host 0.0.0.0
```

Then open <http://localhost:8000/>. Binding to `0.0.0.0` can expose the app outside WSL, so use it only on a trusted machine/network.

## Requirements

For normal Unix/WSL release installs:

- Python 3.10+
- `curl` or a browser to download the installer

For source/development installs:

- Python 3.10+
- Node.js 20+ recommended
- npm

Normal release installs do not require Node.js because tagged release assets include the built frontend.

## Install the latest release

```bash
curl -fsSL https://raw.githubusercontent.com/EddieTYP/image-prompt-library/main/scripts/install.sh | bash
image-prompt-library start
```

`image-prompt-library start` runs the local server in the current terminal. Keep it open, then visit <http://127.0.0.1:8000/> in your browser. Press `Ctrl-C` in that terminal to stop the server.

## First run

A fresh local library starts empty. Click `+ Add` in the app to create your first prompt card, or import the optional starter sample library:

```bash
image-prompt-library sample-data en
```

Check the short runtime summary and detailed diagnostics with:

```bash
image-prompt-library status
image-prompt-library doctor
```

## Install a specific release

```bash
curl -fsSL https://raw.githubusercontent.com/EddieTYP/image-prompt-library/main/scripts/install.sh | bash -s -- --version <version>
image-prompt-library start
```

The selected release must have matching GitHub Release assets:

- `image-prompt-library-<version>.tar.gz`
- `image-prompt-library-<version>.tar.gz.sha256`
- `image-prompt-library-<version>.manifest.json`

The installer verifies SHA256 before switching `app/current` to the new version.

## Data locations

The installer keeps replaceable app code under:

```text
~/.image-prompt-library/app/versions/<version>
```

Your private prompt library defaults to:

```text
~/ImagePromptLibrary
```

That data directory is separate from app code, so updates or rollbacks should not overwrite your private SQLite database or images.

## Sample data

Sample data is optional. Install a starter sample library only if you want demo references in a fresh local library:

```bash
image-prompt-library sample-data en
```

Other languages:

```bash
image-prompt-library sample-data zh_hans
image-prompt-library sample-data zh_hant
```

Larger Traditional Chinese sample package:

```bash
image-prompt-library sample-data zh_hant awesome-gpt-image-2
```

## Health check

```bash
image-prompt-library status
image-prompt-library doctor
```

`image-prompt-library status` prints a short local summary. `image-prompt-library doctor` prints deeper diagnostics for the installed app, library path, database, and generation provider state.

## Update and rollback

Update to the latest release:

```bash
image-prompt-library update
```

Install or switch to a specific version:

```bash
image-prompt-library update --version <version>
```

Rollback to the previous installed version:

```bash
image-prompt-library rollback
```

## macOS launchd service

Install/manage a user launchd service for a long-running local instance:

```bash
image-prompt-library service install --host 127.0.0.1 --port 8000
image-prompt-library service status
image-prompt-library service restart
image-prompt-library service stop
image-prompt-library service start
image-prompt-library service uninstall
```

Service install refuses to overwrite an existing plist for the same label unless you pass `--replace`, so a managed service is not silently replaced during reinstall.

Use `--host 0.0.0.0` only when you intentionally want LAN access and understand the firewall exposure.

## PATH fallback

If the `image-prompt-library` command is not found, add `~/.local/bin` to your shell `PATH`, or use the fallback command printed by the installer:

```bash
~/.image-prompt-library/app/current/scripts/appctl.sh start
```

## Uninstall

Keep your private library and uninstall only the app:

```bash
image-prompt-library uninstall
```

This removes the app files but keeps your prompts and images in `~/ImagePromptLibrary`, so you can reinstall later.

Delete everything, including your private library, only when you are sure:

```bash
image-prompt-library uninstall --delete-library
```

If you run that from a script or non-interactive shell, add `--yes`:

```bash
image-prompt-library uninstall --delete-library --yes
```
