# Installation and Runtime Guide

This guide keeps operational details out of the main README.

## Native Windows PowerShell (v0.8.0+)

Native Windows support begins with v0.8.0. The Windows controller and rollback behavior remain unchanged in v0.8.2.

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

Without `-Version`, the installer selects the newest compatible stable release, currently `v0.11.0`, and skips drafts and prereleases. Use `-Version` only when you want to pin a specific release.

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
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installer -Version v0.11.0
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
image-prompt-library update --version v0.11.0  # pin a specific release
image-prompt-library rollback
image-prompt-library backup
image-prompt-library verify-backup C:\path\to\backup.tar.gz
image-prompt-library restore C:\path\to\backup.tar.gz --yes
image-prompt-library sample-data en
image-prompt-library sample-data zh_hans
image-prompt-library sample-data zh_hant awesome-gpt-image-2
image-prompt-library uninstall
```

Update, rollback, start, stop, and uninstall operations share one per-prefix transaction lock. Backup and restore additionally share the active-library lock with the running app, so run `stop` first. An update switches version pointers transactionally and restores the prior version and runtime after a handled setup, switch, or health failure. A retry also reconciles exact installer-owned `.staging-<GUID>` and `<version>.backup` remnants while preserving near-match or ambiguous paths; `doctor` reports any exact remnants that still need attention. This is not durable power-loss recovery: an OS or power interruption can still require `image-prompt-library doctor` followed by a retry or rollback. `rollback` validates the previous payload and version-local Python before changing either pointer. Default uninstall removes only the app state and preserves `%USERPROFILE%\ImagePromptLibrary`; use `image-prompt-library uninstall --delete-library` only to remove the private library too, and add `--yes` for non-interactive use. See [`BACKUP_AND_RESTORE.md`](BACKUP_AND_RESTORE.md) before the first restore.

## Unix and WSL 2

macOS and Linux use the Bash installer below. Windows users who prefer Linux tooling can use the same path through **WSL 2**.

If the server starts in WSL but the Windows browser cannot open `http://127.0.0.1:8000/`, stop the server with Ctrl-C and run:

```bash
image-prompt-library start --host 0.0.0.0
```

Then open <http://localhost:8000/>. Binding to `0.0.0.0` can expose the app outside WSL, so use it only on a trusted machine/network.

Localhost and literal LAN IP addresses work without additional configuration. If you use a custom hostname, set `IMAGE_PROMPT_LIBRARY_ALLOWED_HOSTS` before starting the server, for example `IMAGE_PROMPT_LIBRARY_ALLOWED_HOSTS=library.home`. Multiple names are comma-separated; use exact names without a scheme, port, or wildcard. Only add names you control. This setting does not enable authentication or make public internet access safe.

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

The command above selects the newest compatible stable release, currently `v0.11.0`, and skips drafts and prereleases. Use `--version` only when you want to pin a specific release.

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

Release tags use `v<major>.<minor>.<patch>` with an optional SemVer prerelease suffix; build-metadata suffixes (`+...`) are not accepted so GitHub asset filenames stay exact. The release workflow binds a schema-v2 manifest to the exact tag commit. The installer verifies the manifest identity and schema, exact checksum sidecar filename, archive SHA256, required payload, and safe archive-member rules before switching `app/current` to the new version.

Publishing a release as a prerelease does not make it the default update. After the same tag and assets pass the Windows, macOS, and Linux release gate, that existing GitHub release can be promoted to stable without retagging or re-uploading it.

On Unix/WSL, custom install-prefix and private-library paths must be dedicated Image Prompt Library directories. The private library must be a physical directory separate from the install prefix; a symlinked path, either directory nested inside the other, filesystem root, or any delete target that contains your home directory is rejected. If an older local configuration uses one of those layouts, move the app and library to separate dedicated physical directories, update `IMAGE_PROMPT_LIBRARY_PATH`, and rerun the update. Uninstall also refuses an `IMAGE_PROMPT_LIBRARY_PREFIX` symlink; invoke it through the physical installed path instead.

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

## Portable backup and restore (v0.9.0+)

Stop the app, then use the installed command on Windows, macOS, or Linux:

```text
image-prompt-library backup
image-prompt-library verify-backup <archive>
image-prompt-library restore <archive> --yes
```

Backup and restore fail if the same library is in use by the app or another archive operation. Restore validates and stages the complete archive before replacement and keeps the previous library as a sibling for review. It does not automatically stop or restart the app. See [`BACKUP_AND_RESTORE.md`](BACKUP_AND_RESTORE.md) for the payload, credential boundary, legacy-format behavior, and recovery limits.

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

This selects the newest compatible stable release, currently `v0.11.0`. Use `--version` only when you want to pin a specific release.

Install or switch to a specific version:

```bash
image-prompt-library update --version <version>
```

Rollback to the previous installed version:

```bash
image-prompt-library rollback
```

Install, update, and rollback share a per-prefix lock. The updater keeps the selected old runtime available until the candidate payload, version-local Python, and an offline health check pass. It publishes `current` and `previous` with atomic symlink replacements and restores their prior values after a handled error, `HUP`, `INT`, or `TERM`. Exact installer-owned staging and backup remnants are reconciled on retry; ambiguous names, symlinks, or paths outside `app/versions` are retained and rejected.

This is deliberately not a durable journal. `SIGKILL`, an OS crash, or power loss between the two pointer replacements can still require `image-prompt-library doctor`, followed by a normal update retry or a validated rollback. The updater never treats a similarly named user directory as safe cleanup work.

When a POSIX rollback target is exactly `v0.8.0`, v0.8.2 first checks the legacy files and runtime. A first migration is allowed only when `scripts/load-env.sh` is absent and the three public v0.8.0 management scripts match their shipped SHA256 fingerprints; an existing migration is allowed only when its marker and file hashes prove a valid complete or safely resumable state. The controller then overlays only the four installed-command management scripts (`scripts/install.sh`, `scripts/load-env.sh`, `scripts/install-sample-data.sh`, and `scripts/appctl.sh`). Writes stay anchored to already-open physical directories, use no-follow same-directory temporaries and atomic replacement, and replace `appctl.sh` last. A `prepared` marker is fsynced before the first overlay write so an interrupted migration can safely reconcile on retry; it becomes `complete` only after all four files are durable. The app backend, frontend, `VERSION`, `.venv`, private library, auth/config files, and `current`/`previous` pointers are unchanged by this compatibility migration. The literal allow-listed environment loader prevents controller `.env` values from being evaluated as shell code. Other incomplete, modified, or ambiguous targets fail closed, and the migration does not copy `backup.sh` or development-only scripts.

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
