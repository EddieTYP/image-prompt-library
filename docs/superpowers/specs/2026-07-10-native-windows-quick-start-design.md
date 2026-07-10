# Native Windows Quick Start Design

Date: 2026-07-10

## Summary

Add a native Windows PowerShell install and runtime path for Image Prompt Library. A Windows 10 or Windows 11 user with Python 3.10 or newer should be able to install a verified stable release, start the app in the background, and open it in a browser without Git, Git Bash, WSL, Node.js, administrator access, or manual virtual-environment setup.

This milestone completes the largest remaining install/onboarding adoption gap. It does not replace the existing Bash installer or package the application as a standalone executable.

## Product Goal

The default Windows journey should be:

1. Confirm Python 3.10 or newer is installed.
2. Run one PowerShell command.
3. Wait while the installer downloads, verifies, and configures the latest compatible stable release.
4. Land directly in the local first-run experience in the default browser.
5. Use one `image-prompt-library` command for later start, stop, status, update, rollback, sample-data, diagnostics, and uninstall operations.

The installer must never install Python or another system dependency for the user. If Python is missing or too old, it must stop with a concise explanation and an official Python download link.

## Context

The current release workflow already provides:

- versioned GitHub Release artifacts;
- an artifact manifest and SHA256 checksum;
- a prebuilt frontend that does not require Node.js at runtime;
- isolated per-version Python virtual environments;
- update, rollback, status, doctor, sample-data, and uninstall behavior through Bash scripts;
- durable private library data outside versioned application code.

Windows users currently need WSL 2 or Git Bash because the release helpers assume Bash, Unix virtual-environment paths, and symlinks. Native Windows support should reuse the release model while adding Windows-specific installation, process management, and version pointers. It should not refactor the stable Linux/macOS path.

## Scope

### Included

- Native Windows PowerShell 5.1-compatible bootstrap installer.
- Explicit Python 3.10+ discovery and version validation.
- Stable-release discovery with Windows capability validation.
- Existing release artifact and checksum reuse.
- Per-version runtime setup with a Windows virtual environment.
- User-level command shim and PATH registration.
- Background start, safe stop, status, and doctor commands.
- Version, update, transactional restart, automatic failed-update recovery, and explicit rollback commands.
- Native Windows sample-data installation.
- Safe uninstall that preserves private library data by default.
- English, Traditional Chinese, and Simplified Chinese public installation guidance.
- Focused Windows GitHub Actions coverage and native Windows end-to-end QA.
- Cleanup of nearby stale roadmap claims about completed and remaining installer work.

### Excluded

- Installing Python, PowerShell, `winget`, Git, WSL, Node.js, or any other system dependency.
- A standalone `.exe`, MSI, MSIX, GUI installer, package-manager package, or signed binary.
- Windows service, Scheduled Task, login startup, system tray, or always-on daemon integration.
- Administrator elevation or machine-wide installation.
- Docker or Docker Compose.
- Rewriting the Bash installer or Bash controller.
- Changing application UI behavior.
- Adding application runtime dependencies.
- Cleaning up old installed versions automatically.

## Supported Environment

The supported native path is:

- Windows 10 or Windows 11;
- Windows PowerShell 5.1 or PowerShell 7;
- Python 3.10 or newer available through `py -3` or `python`;
- outbound HTTPS access to GitHub and Python package sources during initial runtime setup.

The scripts must use ASCII source and normal ASCII console output so Windows locale settings do not corrupt the installer. Paths containing spaces must work.

## Files and Installation Layout

Add these runtime scripts:

- `scripts/install.ps1` - remote bootstrap, release selection, verification, extraction, runtime setup, pointer switch, shim setup, and initial launch.
- `scripts/setup-runtime.ps1` - create the version-local Windows virtual environment and install the packaged application.
- `scripts/appctl.ps1` - native Windows runtime and lifecycle commands.
- `scripts/install-sample-data.ps1` - native sample bundle download, verification, safe extraction, and import.

Use this default layout:

```text
%LOCALAPPDATA%\ImagePromptLibrary\
  .env
  app\
    current-version
    previous-version
    downloads\<version>\
    versions\<version>\
  bin\
    image-prompt-library.cmd
    image-prompt-library.ps1
  logs\
    app.out.log
    app.err.log
    app.previous.out.log
    app.previous.err.log
  run\
    server.json

%USERPROFILE%\ImagePromptLibrary\
  db.sqlite
  originals\
  thumbs\
  previews\
  ...
```

`IMAGE_PROMPT_LIBRARY_PREFIX` and `IMAGE_PROMPT_LIBRARY_PATH` may override the defaults for development, CI, or advanced use. The normal public command should require neither.

Windows does not use symlinks for `current` and `previous`. `current-version` and `previous-version` are small text pointer files. Pointer replacement must use a temporary file followed by a same-directory replace so an interrupted write cannot leave a partial version value.

## Release Compatibility Contract

The release package must include all four PowerShell scripts. `scripts/package-release.sh` must copy them into the artifact.

The release manifest schema remains backward compatible and adds this capability:

```json
{
  "capabilities": ["windows-powershell-v1"]
}
```

The Bash installer may ignore the additive field.

Default Windows release discovery must:

1. inspect published GitHub releases in descending order;
2. skip drafts and prereleases;
3. require the artifact, checksum, and manifest assets;
4. fetch the manifest and require `windows-powershell-v1`;
5. choose the first complete compatible stable release.

An explicitly selected version may be a prerelease, but it must still advertise the Windows capability and provide all required assets. A legacy release such as `v0.7.10` must fail with a clear unsupported-native-Windows message instead of installing an artifact that lacks the PowerShell controller.

## Installer Entry Points

The default public command is:

```powershell
irm https://raw.githubusercontent.com/EddieTYP/image-prompt-library/main/scripts/install.ps1 | iex
```

Documentation must also provide an inspect-first path:

```powershell
$installer = Join-Path $env:TEMP "image-prompt-library-install.ps1"
irm https://raw.githubusercontent.com/EddieTYP/image-prompt-library/main/scripts/install.ps1 -OutFile $installer
notepad $installer
powershell -NoProfile -ExecutionPolicy Bypass -File $installer
```

Default remote execution installs the latest compatible stable release. Direct script execution may support focused options for selected version, prefix, library path, release base URL, PATH registration, and initial launch so CI and advanced users can exercise the same implementation. These options must not create a second install flow.

## Python Discovery

Python discovery must be direct and deterministic:

1. try `py -3`;
2. then try `python`;
3. execute a version probe and require `sys.version_info >= (3, 10)`;
4. use the first valid candidate for virtual-environment creation.

Finding a command named `python` is not sufficient. The probe must execute successfully and report a supported version.

If no valid interpreter exists, stop before downloading or modifying the installation and print:

- that Python 3.10+ is required;
- the detected unsupported version when available;
- `https://www.python.org/downloads/windows/`;
- a reminder to make the Python launcher available, then rerun the installer.

Do not invoke `winget`, open an installer, modify App Execution Aliases, or silently change PATH to locate an unsupported interpreter.

## Download and Verification

Downloads go to the selected version's download directory. The installer must use HTTPS and retry a transient download at most three times with short bounded delays.

Before extraction:

- parse the UTF-8 manifest as JSON;
- verify the manifest version matches the selected version;
- verify the manifest artifact name matches the requested artifact;
- require the Windows capability marker;
- parse the separate `.sha256` file;
- require the manifest checksum and checksum-file value to match;
- calculate the artifact SHA256 with `Get-FileHash`;
- require the calculated value to match both expected values.

Any mismatch stops installation before extraction or pointer changes.

Extract into a version-specific temporary directory with the validated Python interpreter and the standard-library `tarfile` module. Before extraction, reject absolute paths, parent traversal, links, device entries, and any member whose resolved destination leaves the temporary directory. Confirm the expected package files exist after extraction, then move only the extracted application code into the final version path before running `setup-runtime.ps1`; a Python virtual environment must never be moved after creation because its entry points contain absolute paths. If a non-current target version already exists, keep it at one exact backup path until setup in the final target succeeds. On setup failure, remove the failed final target and restore that backup. Only a fully configured final version may become current.

## Runtime Setup

`setup-runtime.ps1` must:

1. create `<version>\.venv` using the validated Python interpreter;
2. use `<version>\.venv\Scripts\python.exe` for every later package operation;
3. upgrade/install only what the existing packaged runtime setup requires;
4. install the packaged project without Node.js;
5. verify that `uvicorn` and `backend.main` can be imported while `IMAGE_PROMPT_LIBRARY_PATH` points to a new disposable directory beneath the OS temporary directory;
6. exit nonzero on any failure.

A setup failure leaves `current-version` and the running app unchanged. The import probe must restore the incoming environment value and remove only its exact generated temporary library target, so preparing an update never initializes or migrates the user's real database. Temporary extraction may be removed only by an exact literal path beneath the configured prefix.

## Command Shim and PATH

The installer creates a stable PowerShell delegator and CMD shim under the prefix `bin` directory. The delegator reads `current-version` and invokes that version's `scripts/appctl.ps1`. The shim lets both PowerShell and CMD users run:

```text
image-prompt-library <command>
```

The installer adds the exact normalized user-level `bin` directory to the user PATH only when it is absent, comparing entries case-insensitively. It must preserve all other PATH entries and also update the current PowerShell process PATH so the command works immediately.

Uninstall removes only the matching PATH entry created for this prefix.

## Configuration Loading

The first install creates `%LOCALAPPDATA%\ImagePromptLibrary\.env` only when absent, with:

```text
IMAGE_PROMPT_LIBRARY_PATH=%USERPROFILE%\ImagePromptLibrary
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000
BACKUP_DIR=%LOCALAPPDATA%\ImagePromptLibrary\backups
```

PowerShell scripts must parse only known key/value entries. They must not dot-source or execute `.env` as PowerShell. Incoming process environment variables take precedence over file values, matching the existing command-line behavior.

## Runtime Process Ownership

`start` launches the version-local Python interpreter with `uvicorn backend.main:app` through `Start-Process`, using a hidden window and redirected stdout/stderr logs.

After launch, write `run\server.json` with:

- PID;
- process start time in UTC plus its exact tick value;
- observed process executable path;
- app version and app root;
- host and port;
- creation timestamp.

`stop` may terminate a process only when all of these match the recorded process:

- PID exists;
- exact process start-time tick value matches;
- executable path matches case-insensitively.

If ownership cannot be proven, do not terminate the process. Report the stale or conflicting runtime record and the next safe action.

When the process no longer exists, a stale runtime record may be removed. A reused PID with different metadata must never be killed.

## Start, Health, and Browser Behavior

`start` supports host, port, and no-browser overrides while defaulting to `127.0.0.1:8000`.

The command must:

1. validate any existing runtime record;
2. avoid starting a duplicate owned server;
3. refuse to kill or replace an unrelated process occupying the configured port;
4. start the background server;
5. poll `/api/health` for at most 30 seconds;
6. require `ok: true` and the expected application version;
7. open the browser only after the health check passes, unless `--no-browser` was supplied.

If startup fails, stop the newly launched owned process when it is still running, retain the logs, avoid opening a blank browser tab, and print the stdout/stderr log paths.

If the app is already running and healthy under the matching runtime record, `start` should not launch another process. It should report the existing URL and open it unless `--no-browser` was supplied.

Before a new launch, rotate the current stdout/stderr files to the fixed `app.previous.*.log` paths, replacing the older previous pair. This keeps one failed launch available when automatic recovery starts the old version again without introducing unbounded log retention. Store the active output/error log paths in `server.json`.

## Command Behavior

The Windows controller supports:

```text
start [--host H] [--port P] [--no-browser]
stop
status
doctor
version
update [--version V]
rollback
sample-data <en|zh_hans|zh_hant> [gpt-image-2-skill|awesome-gpt-image-2]
uninstall [--delete-library] [--yes]
```

### Status

`status` is short and human-readable. It reports:

- installed/current version;
- library path;
- configured URL;
- process state: `running`, `stopped`, `unhealthy`, or `stale runtime record`;
- item count when available;
- generation provider state when available;
- the doctor command for deeper diagnostics.

An unavailable database or provider check must not make the whole command fail.

### Doctor

`doctor` follows the existing App, Library, Database, Generation, Updates/Runtime, and Next steps structure. It adds Windows-specific checks for:

- current and previous pointer validity;
- version-local virtual environment;
- runtime record ownership;
- health endpoint;
- command shim and user PATH;
- log locations.

It must not print OAuth tokens, secrets, full auth payloads, or private prompt content.

### Version

`version` prints the current version pointer and fails clearly when the pointer is missing or invalid.

### Sample Data

`sample-data` preserves the existing language and package validation. The native script must:

- download the same published ZIP asset;
- verify the existing pinned SHA256;
- reject absolute paths, parent traversal, and extraction outside the staging directory;
- invoke `backend.services.import_sample_bundle` with the version-local Python interpreter;
- print imported item/image counts.

It must remain optional and idempotent according to the existing importer contract.

## Transactional Update and Rollback

`update` records whether the owned app is running and, when running, its recorded host and port. It then fully downloads, verifies, extracts, and configures the target version before changing pointers.

After the target is ready:

1. stop the owned running process, if any;
2. write the old current version to `previous-version`;
3. atomically replace `current-version` with the target;
4. if the app was running, start the new version on the same recorded host and port without opening another browser;
5. require the new health check to pass.

If the new version fails to start or pass health:

1. stop only the newly started owned process;
2. restore the old current and previous pointer values;
3. restart the old version on the same recorded host and port when it was previously running;
4. report that the update failed and automatic recovery occurred;
5. print both relevant log paths.

If the app was stopped before update, it remains stopped after a successful update.

`rollback` uses the same pointer-switch and host/port-preserving restart transaction with current and previous reversed. It fails without changing anything when no valid previous version exists.

## Uninstall Safety

`uninstall` must:

1. stop only a proven owned process;
2. validate that the configured prefix is neither a drive root, user profile root, nor the private library path;
3. remove the exact matching user PATH entry;
4. remove the configured application prefix;
5. preserve the private library by default;
6. print the preserved library location.

`--delete-library` requires confirmation unless `--yes` is also present. Before deleting, validate that the library is neither a drive root, user profile root, application prefix parent, nor outside the explicitly configured library target.

All deletion code must operate on exact validated literal targets. Removing one validated app prefix or private library may recurse within that target, but wildcard deletion, recursive target discovery, and broad cleanup loops are not permitted.

## Error Handling and Console UX

Normal installation output should be concise:

```text
[1/5] Checking Python
[2/5] Finding latest stable release
[3/5] Downloading and verifying
[4/5] Installing runtime
[5/5] Starting Image Prompt Library
Ready: http://127.0.0.1:8000/
```

Expected failures must use concise messages with a next action rather than raw stack traces.

- Missing/old Python: stop and show the official download URL.
- Network failure: bounded retry, then leave current unchanged.
- No compatible stable release: explain that no native Windows-capable release is available.
- Incomplete selected release: identify the missing asset/capability.
- Checksum mismatch: refuse extraction and switching.
- Runtime setup failure: identify the failed stage and leave current unchanged.
- Port conflict: do not kill the process; suggest another port.
- Stale process record: explain whether it was safely cleared or requires user action.
- Health timeout: retain and print log paths.
- Update launch failure: automatically recover the previous version.

The default scripts should not emit PowerShell exception dumps. An advanced verbose mode may expose additional non-secret diagnostics.

When the bootstrap is executed through `irm ... | iex`, a failure must return control to the user's existing PowerShell session instead of closing that session. Direct `-File` execution and controller subprocesses must still return a nonzero process exit code on failure.

## Public Documentation

Update:

- `README.md`;
- `README_zh-TW.md`;
- `README_zh-CN.md`;
- `docs/INSTALLATION.md`;
- `docs/TROUBLESHOOTING.md`;
- `ROADMAP.md`.

Public docs must:

- present separate Windows and macOS/Linux/WSL quick starts;
- state Python 3.10+ clearly before the Windows command;
- state that the app does not install Python;
- provide the short command and inspect-first alternative;
- explain background start/stop/status behavior;
- document update, rollback, sample-data, logs, and uninstall;
- keep local-first paths and privacy behavior clear;
- stop describing WSL as the only supported Windows path once the compatible stable release exists;
- retain WSL as a supported alternative;
- remove nearby roadmap statements that incorrectly list completed search/sort, cleanup, refresh locking, or onboarding work as future work;
- keep unfinished service/update, richer generation retry/reference UX, batch image editing, mobile Explore, and URL/social import work visible.

The implementation PR must not claim that an older release supports native Windows. The public release rollout should identify the first compatible stable release and synchronize the current-release wording only after that release and its assets exist.

## Release Rollout

Native Windows support is a stable minor-release feature, not a hotfix. With `v0.7.10` as the current stable release, the expected first compatible release is `v0.8.0`, subject to the release gates below. The rollout is:

1. merge the verified implementation and capability-aware docs;
2. create the next minor tag/release from the merge commit as a prerelease so failed asset QA cannot become the stable default;
3. wait for release-assets CI to publish the capability-bearing manifest and artifact;
4. run the public raw-URL installer with the explicit prerelease version against the real GitHub assets on native Windows with a temporary prefix and library;
5. verify start, browser load, status, update/rollback behavior where applicable, stop, and uninstall;
6. promote the same tested release to stable/latest only after those checks pass;
7. use another fresh prefix to verify default stable-release discovery selects it;
8. synchronize the public current-release wording after the stable/default discovery check passes.

Do not advertise a legacy release as Windows-native merely because `install.ps1` exists on `main`. If real-asset QA fails, leave the release marked prerelease and do not update stable docs.

## Automated Verification

### Existing Ubuntu Gate

Keep the existing Ubuntu job as the authoritative full application gate:

- full Python test suite;
- local frontend build;
- read-only demo build.

No frontend behavior changes are planned, so this milestone does not require new desktop/mobile visual-layout regression coverage.

### Focused Tests

Add focused tests for:

- PowerShell scripts included in release packaging;
- manifest capability generation;
- docs and command surface;
- no Python-install or `winget install` behavior;
- no Windows service/startup-task behavior;
- safe pointer and deletion guards where testable without a live process;
- old manifests rejected as not Windows-capable;
- current release docs not claiming unsupported legacy behavior.

### Windows GitHub Actions Job

Add a `windows-latest` installer job that:

1. uses the repository's supported Python and Node versions;
2. builds the local frontend and creates a local test release;
3. installs it through native PowerShell into a runner temporary prefix/library;
4. verifies checksum, extraction, virtual environment, pointers, and command shim;
5. starts on a nondefault loopback port and waits for real `/api/health`;
6. verifies `version`, `status`, and `doctor`;
7. stops and proves the process exited;
8. installs a second local test version through `update` and verifies pointer switching;
9. verifies explicit rollback;
10. creates a private-library sentinel, uninstalls without data deletion, and proves the sentinel remains.

The job must not rely on WSL or Git Bash for installation/runtime commands. Git Bash may still be used by the packaging step because packaging remains the existing release-build responsibility; the installed-app exercise itself must be native PowerShell.

### Native Windows QA

Before release, run a fresh temporary-prefix end-to-end path on native Windows PowerShell 5.1:

- install from a locally built artifact;
- start and load the real app in a browser;
- confirm first-run empty-library content renders;
- run status and doctor;
- stop;
- update between two local test versions;
- rollback;
- uninstall while preserving a sentinel private library.

After publishing, repeat the install/start/status/stop/uninstall path against the real GitHub release assets. Record commands, versions, paths with private values redacted, health result, and any warnings in a QA note.

## Security and Privacy Guardrails

- Bind to `127.0.0.1` by default.
- Never elevate privileges.
- Never install dependencies outside the version-local virtual environment.
- Never execute `.env` as PowerShell.
- Never log OAuth tokens, auth payloads, environment secrets, or private prompt content.
- Verify every release artifact before extraction.
- Never terminate a process without matching PID, start time, and executable path.
- Never delete with wildcard or ambiguous paths.
- Keep durable private library data outside versioned application code.
- Preserve the GitHub Pages demo as static and read-only.

## Acceptance Criteria

The milestone is complete when all of the following are true:

1. A Windows 10/11 user with PowerShell 5.1 and Python 3.10+ can install without Git, Bash, WSL, Node.js, admin rights, or manual virtual-environment steps.
2. Missing or old Python causes a clear failure without installing or changing Python.
3. Default install selects only a complete stable release advertising `windows-powershell-v1`.
4. Manifest, checksum file, and calculated artifact SHA256 must agree before extraction.
5. The install uses versioned app directories and durable private data outside app code.
6. The command shim works in the current session and future terminals without damaging existing user PATH entries.
7. `start` launches in the background, validates app/version health, and opens the browser only after success.
8. `stop` cannot kill an unrelated or PID-reused process.
9. `status`, `doctor`, `version`, `sample-data`, `update`, `rollback`, and `uninstall` work natively in PowerShell.
10. A failed running-app update restores and restarts the previous version.
11. Uninstall preserves the private library unless explicit deletion and confirmation are supplied.
12. Windows public docs are accurate, multilingual, and do not claim unsupported legacy-release behavior.
13. Existing Linux/macOS/WSL Bash behavior remains unchanged.
14. Ubuntu full CI, focused Windows CI, local native Windows QA, and post-release real-asset smoke verification pass.
