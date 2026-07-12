# Native Windows Quick Start QA

Status: `PASS WITH CONCERNS`

## Environment

- Windows: Windows 10 Pro 25H2, build 26200.8737 (kernel 10.0.26200.0).
- Shell: Windows PowerShell 5.1.26100.8737, Desktop edition.
- Test runner: pre-existing Python 3.11.4; the native QA install used an
  existing compatible Python to create a temporary version-local environment.
- Node.js: v22.22.3; npm: 10.9.8.
- Python was not installed or modified by this QA run.

## Terminal Verification

- PASS: Windows PowerShell parsed all five required files with `0` errors:
  `scripts/setup-runtime.ps1`, `scripts/appctl.ps1`, `scripts/install.ps1`,
  `scripts/install-sample-data.ps1`, and `tests/windows-installer-smoke.ps1`.
- PASS: the final cache-disabled selected pytest command covering
  `tests/test_windows_installer.py`, `tests/test_installer_release.py`, and
  `tests/test_public_mvp.py` reported
  `235 passed, 1 skipped, 1 warning in 323.64s`. The deterministic skip records
  that 8.3 aliases are disabled on the test volume; practical SUBST alias
  coverage passed. The warning was the known Starlette/httpx `TestClient`
  deprecation.
- PASS: `npm run build` transformed `1,751` modules and completed the Vite
  production build in `872ms` (`3.95s` for the full command). The first
  sandbox attempt could not write Vite's repo-local temporary config; the
  identical approved rerun passed.
- PASS: the final external-network native smoke exited `0` in `241.11s` and ended
  with the exact success line `Native Windows installer smoke passed.`
- PASS: `git diff --check` completed without whitespace errors. Existing CRLF
  conversion notices were limited to unrelated dirty files.

## Native Smoke Coverage

The successful smoke exercised and asserted all of the following:

- Installation from a `Restricted` parent PowerShell through the documented
  explicit Bypass `-File` path, followed by bare `image-prompt-library`
  commands under `Restricted`; the public command resolved to `.cmd`, and the
  differently named internal PowerShell delegate remained private.

- Update moved the current pointer to the target version, retained the previous
  pointer, and became healthy at the target version.
- Rollback restored the original current version, swapped the previous pointer,
  and became healthy at the restored version.
- A deliberately broken update failed, reported automatic recovery, restored
  the expected pointers and health version, and retained fresh non-empty failed
  launch error-log evidence.
- A mismatched live PID record was refused by `stop`; the unowned sleeper
  process remained alive.
- A deterministic lock barrier proved uninstall held the physical-prefix mutex
  while stale start and reinstall contenders both reached their lock entrance;
  only then did the test release uninstall to finish retirement and cleanup.
- Default-preserve uninstall removed the app prefix and its User PATH entry
  while retaining the private-library sentinel. Delete-library uninstall then
  removed both the prefix and the private library with no PATH residue.

The initial sandbox smoke was blocked from PyPI by the managed network policy.
The identical command was rerun with external-network permission and passed;
this environment workaround is disclosed as a concern rather than hidden as a
final QA failure.

## Desktop Browser QA

- Local packaged release health matched
  `v0.1.0-task11-2388e660ca45` at its loopback URL.
- Desktop viewport: `1280x720`.
- Document `scrollWidth` equaled `clientWidth`; no horizontal overflow was
  observed.
- The first-run empty-library panel was fully visible. `Add your first prompt`
  and `Open Config` were enabled.
- The Config drawer opened and closed, showing the expected version, library,
  database, and status information.
- The Add CTA opened a usable Add prompt card modal.
- Native QA status and doctor both exited `0`. Redacted headings confirmed the
  expected version and loopback URL, a running process, an OK private library
  and database, version-local Python, command shim, User PATH, and logs.
- The owned controller then stopped the recorded PID, released the owned port,
  and uninstalled with `--yes`. The default-preserve uninstall retained the
  private-library sentinel until it was explicitly verified; the QA-generated
  private library was then removed as final cleanup.

No sensitive session data, private library content, usernames, or absolute
temporary paths are recorded here.

## Residue Audit

After the browser-QA teardown and exact generated-resource cleanup, the final
audit verified zero owned artifacts:

- Generated Task 11 temp roots: `0`.
- Test-release artifacts and detached package worktree: `0`.
- Owned app prefixes: `0`.
- Owned User PATH entries: `0`.
- Owned runtime processes: `0`.
- Owned loopback listeners: `0`.
- QA-generated private-library sentinel path: `0` after preservation was
  recorded and final cleanup was requested.

The deferred-cleanup failure regression intentionally retains a tombstone
inside pytest's own temporary test directory so the assertion can inspect its
failure evidence. That fixture is not an installed prefix, PATH entry, owned
process, listener, or Task 11 smoke root.

Browser QA used a locally packaged test release and the already built
`frontend/dist` output, then attached the browser after the local service was
healthy. This setup avoided changing committed frontend evidence and did not
use OAuth data; the Restricted-policy installer and command handoff were
verified separately by the native behavioral smoke.

During browser-QA setup, expected warning output was temporarily suppressed and
a disposable packager checkout was LF-normalized so local packaging could run
on Windows. Those setup workarounds were not counted as installer validation.
The later clean Restricted-policy behavioral smoke from the committed tree
superseded them for installer and command-path evidence.

## Residual Risks And Pending Work

- Unsigned PowerShell bootstrap remains subject to SmartScreen and local
  execution-policy behavior.
- GitHub and PyPI availability remain external release-install dependencies.
- Handled update failures recover transactionally, but there is no durable
  write-ahead crash journal for OS or power loss; `doctor` and manual retry or
  rollback may still be required after an interruption.

## Published Release Verification

- GitHub release `v0.8.0` was published from commit `527d148`, and its release-assets workflow completed successfully with the archive, SHA256 file, and manifest.
- The published manifest advertised `windows-powershell-v1`; its artifact SHA matched the uploaded asset digest.
- An explicit-version install from raw `main` selected `v0.8.0`; status, doctor, health, homepage, stop/start, desktop rendering, and 390px mobile rendering passed before uninstall cleanup removed the isolated app and library.
- A PowerShell 5.1 stable-discovery regression found during promotion was fixed in PR #11. CI run #121 passed both Ubuntu and native Windows jobs, including the Windows installer contracts and smoke test.
- A second fresh raw-main install without `-Version` selected stable `v0.8.0`, returned healthy `v0.8.0`, and uninstalled with no app prefix, private library, or listener left behind.
