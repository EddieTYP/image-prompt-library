# Native Windows Task 11 Final-Review Fix Report

Date: 2026-07-12
Branch: `codex/native-windows-quick-start`
Starting HEAD: `d63d815`

## Result

Status: `PASS WITH CONCERNS`

This report records the targeted fixes and verification performed for the
review findings received to date. It does not claim that further independent
review cannot identify additional issues. Unrelated pre-existing SDD reports
and QA logs were not staged or modified by this work.

## Fixes

1. Restricted-policy command path: the public bare command is only
   `image-prompt-library.cmd`; the internal delegate is
   `image-prompt-library-delegate.ps1`. Setup, controller, update, sample-data,
   and startup child scripts use `powershell.exe -NoProfile -ExecutionPolicy
   Bypass -File`. The smoke installs from a Restricted parent and runs the bare
   command under Restricted policy.
2. Transaction serialization: install/update, start, stop, rollback, and
   uninstall share one named per-prefix mutex. Internal start/stop helpers are
   non-reentrant. A live runtime must match the selected version, app root, and
   executable; health is required only when `start` reuses it. Update and
   rollback can stop and recover an unhealthy but identity-owned runtime.
   Deterministic race tests cover public mutation waiting.
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

Public-shim uninstall retires the old install generation while the original
prefix mutex is held. The active CMD bin remains only as a generation-marked
residual until CMD exits; the helper then reacquires the same physical-prefix
mutex and removes that residual only when its marker still matches. A
concurrent reinstall clears the old marker while holding the mutex, so deferred
cleanup cannot delete the new generation. Cleanup failures retain the
tombstone and write explicit failure evidence instead of claiming completed
deletion.

## Follow-up Release-Blocker Fixes

- Prefix locks and prefix/library disjointness now use final physical path
  identity, including practical SUBST coverage. Drive roots and the user
  profile root are rejected for either managed target.
- Release downloads follow redirects manually, validate every next location,
  retain bytes only after a successful validated response, and reject remote
  UNC `file:` sources plus existing UNC literal paths.
- CMD uninstall/start/reinstall overlap and deferred-helper failure are covered
  behaviorally. A two-way test barrier proves both contenders reach the held
  physical-prefix mutex before uninstall is released. Helper launch/readiness
  failures are asserted directly. The 8.3 identity test skips deterministically
  when short names are disabled on the test volume.
- The QA note now distinguishes warning suppression and LF normalization used
  only for disposable browser packaging setup from the later clean committed-
  tree Restricted-policy smoke that superseded them for installer validation.

## TDD Evidence

- Restricted/source/diagnostic slice: RED `11 failed`; GREEN `11 passed`.
- Lock/rollback/runtime/reparse/PATH slice: RED `17 failed`; GREEN `17 passed`.
- Full Windows compatibility pass exposed fixture contract changes, then
  reached `187 passed`; the corrected cleanup fixture passed independently.
- Real smoke exposed missing explicit `run` directory creation and public CMD
  self-deletion exit-code handling before reaching its final PASS.
- Final strict-mode regression set: RED through the selected gate; GREEN
  `8 passed` after fileless controller-path handling was corrected.
- Follow-up deferred-uninstall set: GREEN `3 passed in 13.45s`, covering CMD
  self-removal, retained helper-failure evidence, and concurrent CMD
  uninstall/start/reinstall.
- Follow-up path/process/source slice: RED `2 failed, 8 passed`; GREEN
  `18 passed in 18.52s` after physical profile aliases, persistent CMD process
  identity, and existing UNC literal sources were handled.
- Deterministic lifecycle overlap: the first timing-based test was rejected by
  independent review; the explicit two-way lock barrier passed in `6.11s`.
- The final selected gate exposed two dangling-reparse diagnostic regressions;
  both focused tests passed in `3.19s` after reordering fail-closed preflight.

## Verification

- PowerShell parser: all five required files parsed with `0` errors.
- Selected pytest, cache disabled:
  `235 passed, 1 skipped, 1 warning in 323.64s`.
- Skip: 8.3 aliases unavailable on the test volume; SUBST physical-alias
  coverage passed. Warning: known Starlette/httpx `TestClient` deprecation.
- Native Windows smoke with external network: exit `0` in `241.11s`, exact final
  line `Native Windows installer smoke passed.`
- Restricted install and bare-command path: included in the native smoke.
- Frontend build: `1,751` modules, Vite `872ms`, full command `3.95s`.
- Residue audit: `0` smoke roots, `0` uninstall ready markers, and `0` temporary
  User PATH matches after exact cleanup of the earlier failed-smoke tombstone.
- Independent final review: approved after the deterministic barrier replaced
  the rejected timing-based overlap test.

## Concerns

- Unsigned PowerShell/SmartScreen behavior depends on local policy.
- Initial sandbox PyPI access was blocked; the identical smoke passed after an
  approved external-network rerun.
- GitHub/PyPI availability remains external.
- Durable OS/power-loss crash recovery is not implemented.
- Post-release real-asset QA and GitHub CI remain pending.
