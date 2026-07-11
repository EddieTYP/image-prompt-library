# Native Windows Quick Start QA

Status: `LOCAL QA PASS - PR CI PENDING`

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
- PASS: cache-disabled selected pytest command covering
  `tests/test_windows_installer.py`, `tests/test_installer_release.py`, and
  `tests/test_public_mvp.py` reported `185 passed, 1 warning in 237.27s`.
  The warning was the known Starlette/httpx `TestClient` deprecation.
- PASS: `npm run build` transformed `1,751` modules; Vite reported `built in
  941ms`.
- PASS: the external-network native smoke exited `0` in `225.2s` and ended
  with the exact success line `Native Windows installer smoke passed.`
- PASS: `git diff --check` completed without whitespace errors. Existing CRLF
  conversion notices were limited to unrelated dirty files.

## Native Smoke Coverage

The successful smoke exercised and asserted all of the following:

- Update moved the current pointer to the target version, retained the previous
  pointer, and became healthy at the target version.
- Rollback restored the original current version, swapped the previous pointer,
  and became healthy at the restored version.
- A deliberately broken update failed, reported automatic recovery, restored
  the expected pointers and health version, and retained fresh non-empty failed
  launch error-log evidence.
- A mismatched live PID record was refused by `stop`; the unowned sleeper
  process remained alive.
- Default-preserve uninstall removed the app prefix and its User PATH entry
  while retaining the private-library sentinel. Delete-library uninstall then
  removed both the prefix and the private library with no PATH residue.

The earlier local PyPI access block was an environment limitation and was
resolved for the successful external-network smoke; it is not a final QA
failure.

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

## Residual Risks And Pending Work

- Unsigned PowerShell bootstrap remains subject to SmartScreen and local
  execution-policy behavior.
- GitHub and PyPI availability remain external release-install dependencies.
- Post-release real-asset QA remains pending Task 12.
- Whole-branch final review and GitHub Ubuntu plus Windows CI remain pending.
- No release, tag, or merge is included in this milestone.
