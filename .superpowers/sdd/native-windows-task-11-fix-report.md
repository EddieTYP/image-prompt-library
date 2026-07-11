# Native Windows Task 11 Final-Review Fix Report

Date: 2026-07-12
Branch: `codex/native-windows-quick-start`
Starting HEAD: `d63d815`

## Result

Status: `PASS WITH CONCERNS`

All eight final-review findings were addressed. Unrelated pre-existing SDD
reports and QA logs were not staged or modified by this work.

## Fixes

1. Restricted-policy command path: the public bare command is only
   `image-prompt-library.cmd`; the internal delegate is
   `image-prompt-library-delegate.ps1`. Setup, controller, update, sample-data,
   and startup child scripts use `powershell.exe -NoProfile -ExecutionPolicy
   Bypass -File`. The smoke installs from a Restricted parent and runs the bare
   command under Restricted policy.
2. Transaction serialization: install/update, start, stop, rollback, and
   uninstall share one named per-prefix mutex. Internal start/stop helpers are
   non-reentrant. Owned runtime state must be healthy and match selected
   version, app root, and executable. Deterministic race tests cover public
   mutation waiting.
3. Rollback validation: stopped rollback validates the target `VERSION`,
   controller, expected payload, and version-local Python before pointer
   mutation. Doctor validates the previous pointer and target.
4. Canonical and junction safety: extended path aliases normalize to one
   comparison form; every existing reparse ancestor is rejected before managed
   prefix/library mutation and checked again immediately before deletion.
5. PATH rollback: installation records whether it added the exact bin entry.
   Failure rollback removes only that entry from current User/process PATH and
   preserves concurrent edits.
6. Release override transport: local literal paths and `file:` URLs are
   accepted; loopback HTTP is allowed for tests; non-loopback remote sources
   require HTTPS.
7. QA accuracy: the QA status is `PASS WITH CONCERNS`; the initial sandbox PyPI
   block, external-network rerun, known Starlette warning, and browser setup are
   disclosed without usernames, temporary paths, OAuth payloads, or private
   library content.
8. Diagnostics/docs: unsupported Python versions and launcher guidance are
   reported; failed starts list current and previous stdout/stderr logs; Chinese
   `curl` prerequisites are under Unix/WSL; interruption recovery is explicitly
   qualified as non-durable.

Public-shim uninstall uses a loaded deferred helper because a Windows batch
file cannot synchronously delete itself and still return a reliable exit code.
The helper handshakes before return, acquires the same prefix mutex, waits for
the controller to exit, rechecks target safety, and then removes the prefix.

## TDD Evidence

- Restricted/source/diagnostic slice: RED `11 failed`; GREEN `11 passed`.
- Lock/rollback/runtime/reparse/PATH slice: RED `17 failed`; GREEN `17 passed`.
- Full Windows compatibility pass exposed fixture contract changes, then
  reached `187 passed`; the corrected cleanup fixture passed independently.
- Real smoke exposed missing explicit `run` directory creation and public CMD
  self-deletion exit-code handling before reaching its final PASS.
- Final strict-mode regression set: RED through the selected gate; GREEN
  `8 passed` after fileless controller-path handling was corrected.

## Verification

- PowerShell parser: all five required files parsed with `0` errors.
- Selected pytest, cache disabled: `215 passed, 1 warning in 280.52s`.
- Warning: known Starlette/httpx `TestClient` deprecation only.
- Native Windows smoke with external network: exit `0` in `241.2s`, exact final
  line `Native Windows installer smoke passed.`
- Restricted install and bare-command path: included in the native smoke.
- Frontend build: not rerun because no frontend source, dependency, or build
  input changed; prior committed QA build evidence remains applicable.

## Concerns

- Unsigned PowerShell/SmartScreen behavior depends on local policy.
- Initial sandbox PyPI access was blocked; the identical smoke passed after an
  approved external-network rerun.
- GitHub/PyPI availability remains external.
- Durable OS/power-loss crash recovery is not implemented.
- Post-release real-asset QA and GitHub CI remain pending.
