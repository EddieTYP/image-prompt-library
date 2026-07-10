# Task 1 Report: Provider Readiness Contract

## Scope

Implemented Task 1 on branch `codex/generation-hardening` in the exact files listed by the brief:

- `backend/services/openai_codex_native.py`
- `backend/routers/generation_providers.py`
- `frontend/src/types.ts`
- `frontend/src/api/client.ts`
- `tests/test_openai_codex_native.py`
- `tests/test_frontend_static.py`

No other repo files were modified.

## TDD Evidence

### Red

Added the required failing tests first:

- `test_codex_native_status_exposes_generation_readiness_fields`
- `test_codex_native_missing_login_maps_to_login_required`
- `test_generation_providers_manual_upload_is_always_generation_ready`
- `test_generation_provider_status_has_readiness_contract`

Initial red run command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_openai_codex_native.py::test_codex_native_status_exposes_generation_readiness_fields tests/test_openai_codex_native.py::test_codex_native_missing_login_maps_to_login_required tests/test_openai_codex_native.py::test_generation_providers_manual_upload_is_always_generation_ready -q
```

Observed failures:

- Missing backend readiness keys:
  - `KeyError: 'status'`
  - `KeyError: 'can_generate'`
  - missing manual provider readiness fields
- Additional blocking Windows issue inside the touched backend file:
  - `AttributeError: module 'os' has no attribute 'fchmod'`
  - temp auth file cleanup then hit `PermissionError` because the fd-backed handle had not been closed

That Windows auth-store issue prevented the new ready-state test from reaching the contract assertions, so I fixed it locally in `backend/services/openai_codex_native.py` while implementing the required contract.

### Green

Verification command from the brief:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_openai_codex_native.py::test_codex_native_status_exposes_generation_readiness_fields tests/test_openai_codex_native.py::test_codex_native_missing_login_maps_to_login_required tests/test_openai_codex_native.py::test_generation_providers_manual_upload_is_always_generation_ready tests/test_frontend_static.py::test_generation_provider_status_has_readiness_contract -q
```

Result:

- `4 passed, 2 warnings in 1.74s`

Warnings were existing environment/tooling warnings:

- FastAPI `TestClient` deprecation warning from site-packages
- pytest cache write warning under `.pytest_cache`

## Changes Made

### `backend/services/openai_codex_native.py`

- Added `_generation_readiness(configured, token_present, state)` exactly per the task brief values.
- Merged readiness fields into `CodexNativeAuthStore.status()`:
  - `status`
  - `message`
  - `can_generate`
- Kept existing status fields backward-compatible and additive-only.
- Made temp auth file writing work on Windows by:
  - guarding `os.fchmod` behind `hasattr(os, "fchmod")`
  - explicitly closing the opened file handle before replace/cleanup

### `backend/routers/generation_providers.py`

- Added manual upload readiness fields:
  - `status: "ready"`
  - `message: None`
  - `can_generate: True`

### `frontend/src/types.ts`

- Extended `GenerationProviderStatus` with optional readiness contract fields:
  - `status?: 'ready' | 'unavailable' | 'login_required' | 'auth_error'`
  - `message?: string | null`
  - `can_generate?: boolean`

### `frontend/src/api/client.ts`

- Added matching demo payload readiness fields for both demo providers.

### Tests

- Added the three backend readiness assertions required by the brief.
- Added the static frontend readiness contract assertion required by the brief.

## Files Changed

- `backend/services/openai_codex_native.py`
- `backend/routers/generation_providers.py`
- `frontend/src/types.ts`
- `frontend/src/api/client.ts`
- `tests/test_openai_codex_native.py`
- `tests/test_frontend_static.py`

## Self-Review

### Backward compatibility

- Existing provider status fields remain unchanged.
- New readiness fields are additive only.
- No provider auth flow, queue flow, or generation job contract was redesigned.

### Scope control

- Stayed inside the six files named in the brief.
- Did not touch unrelated frontend/backend behavior.

### Risk check

- The only non-brief code adjustment is the Windows-safe temp auth file handling in the same backend file.
- That change was necessary to let the new ready-state test execute in this environment and is narrowly scoped to file write/cleanup behavior.

## Commit

Planned commit message per brief:

```text
feat: clarify generation provider readiness
```

## Review Follow-Up Fix

Addressed the Task 1 review finding that saved-but-unusable credentials were being flattened into `login_required`.

### Root cause

- `CodexNativeAuthStore.status()` treated every `read_tokens()` failure as if no usable credentials existed.
- That made expired tokens with a failed refresh path look identical to a true "never connected" state.
- As a result, `_generation_readiness()` never reached the `auth_error` branch for saved-but-broken credentials.

### Fix

- Added backend coverage for a saved auth store whose refresh fails:
  - expected `status == "auth_error"`
  - expected `can_generate is False`
  - expected the generic attention message
  - verified the response does not echo the refresh-secret text
- Updated `CodexNativeAuthStore.status()` to distinguish:
  - no saved credential store -> `not_connected` / `login_required`
  - saved credential store that fails read/refresh -> `credentials_need_attention` / `auth_error`
- Strengthened the frontend static contract test to assert demo `status`, `message`, and `can_generate` strings instead of only checking for `can_generate:`.

### Focused verification

Command run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_openai_codex_native.py::test_codex_native_status_exposes_generation_readiness_fields tests/test_openai_codex_native.py::test_codex_native_missing_login_maps_to_login_required tests/test_openai_codex_native.py::test_codex_native_broken_saved_login_maps_to_auth_error tests/test_openai_codex_native.py::test_generation_providers_manual_upload_is_always_generation_ready tests/test_frontend_static.py::test_generation_provider_status_has_readiness_contract -q
```

Result:

- `5 passed, 2 warnings in 2.02s`

Warnings remained unchanged:

- FastAPI / Starlette `TestClient` deprecation warning from site-packages
- pytest cache write warning under `.pytest_cache`

## Re-review Fix

Addressed the additive-only follow-up finding on the broken-saved-credentials path.

### Root cause

- The previous follow-up fix used new public `state` / `reason` values to distinguish broken saved credentials.
- That made the readiness fix work, but it violated the compatibility requirement for existing provider response fields and introduced a `state` value the current ConfigPanel does not label.

### Fix

- Preserved the legacy public contract for configured-but-unusable saved credentials:
  - `state == "not_connected"`
  - `reason == "not_authenticated"`
- Kept `status == "auth_error"` by driving `_generation_readiness(...)` from a separate internal boolean:
  - `credentials_present_but_unusable`
- Updated the focused broken-saved-credentials test to assert both the legacy compatibility fields and the additive readiness field.

### Focused verification

Command run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_openai_codex_native.py::test_codex_native_status_exposes_generation_readiness_fields tests/test_openai_codex_native.py::test_codex_native_missing_login_maps_to_login_required tests/test_openai_codex_native.py::test_codex_native_broken_saved_login_maps_to_auth_error tests/test_openai_codex_native.py::test_generation_providers_manual_upload_is_always_generation_ready tests/test_frontend_static.py::test_generation_provider_status_has_readiness_contract -q
```

- Result:

- `5 passed, 2 warnings in 1.98s`

Warnings remained unchanged:

- FastAPI / Starlette `TestClient` deprecation warning from site-packages
- pytest cache write warning under `.pytest_cache`

- fix_task1_review_findings_2026-07-09:
  - changed_files:
    - frontend/src/components/CardsView.tsx
    - frontend/src/utils/i18n.ts
    - tests/test_frontend_static.py
  - fixes:
    - repaired `TranslationKey` union by removing the stray semicolon that terminated after `firstRunGenerationHelp`
    - added `firstRunLocalInstall` to all locales and switched the `CardsView` first-run eyebrow text to `t('firstRunLocalInstall')`
    - added static assertions for `t('firstRunLocalInstall')` and `firstRunLocalInstall` in the focused test
  - tests_run:
    - `PYTHONUTF8=1 .\\.venv\\Scripts\\python.exe -m pytest tests/test_frontend_static.py::test_local_empty_library_uses_first_run_panel_without_replacing_search_no_results -q` -> `1 passed, 1 warning in 0.44s`
    - `npm run build` -> build succeeded (`tsc && vite build`)

## OAuth Session Reliability Regression Tests (2026-07-10)

### Changed Paths

- `tests/test_openai_codex_native.py`
- `.superpowers/sdd/task-1-report.md`

No production code, dependencies, providers, queue behavior, or generation retry behavior changed.

### Test Coverage Added

- Two genuinely independent Python processes instantiate `CodexNativeAuthStore(auth_path)` and call `read_tokens()` against one local HTTP token endpoint. The first endpoint response waits until the second process has started. The test requires exactly one refresh request and identical refreshed access tokens in both subprocess results.
- A stale `<auth-file>.refresh.lock` directory is aged to 31 seconds with `os.utime`; refresh must succeed and remove the stale lock. A fresh lock with `AUTH_REFRESH_LOCK_WAIT_SECONDS` monkeypatched to `0` must remain present and make `read_tokens()` raise the temporary refresh error.
- An expired saved credential whose refresh raises the temporary refresh error must remain authenticated and connected while reporting unavailable with the required retry-soon message. The response must not contain the refresh token.
- The existing credential-failure status regression now explicitly asserts `authenticated is False`; it continues to require `auth_error` and refresh-token redaction.

### Commands And Results

Command run from `G:\Codex\image-prompt-library`:

```powershell
$env:PYTHONUTF8='1'; .\.venv\Scripts\python.exe -m pytest tests\test_openai_codex_native.py -q -p no:cacheprovider
```

Result: `5 failed, 24 passed, 1 warning in 7.16s` (exit code 1).

Expected new-test failures:

- `test_codex_native_refresh_coordinates_independent_processes`: received `refresh_requests == 2`, proving current production has no cross-process refresh lock.
- `test_codex_native_refresh_recovers_stale_lock_but_preserves_fresh_lock`: the stale named lock still existed after refresh, proving current production does not recover stale refresh locks.
- `test_codex_native_temporary_refresh_failure_remains_connected_and_redacted`: `authenticated` was `False` rather than `True`, proving current status handling collapses temporary refresh failures into a disconnected authentication failure.

Unrelated existing failures observed during the focused suite:

- `test_codex_native_token_store_is_app_owned_redacted_and_permissioned`: expected POSIX mode `0o600`, received `0o666` on Windows.
- `test_codex_native_marks_failed_when_stage_result_rejects_unsafe_result_root`: Windows refused symlink creation with `WinError 1314` because the current user does not have the required privilege.

### Concerns

- The new lock tests intentionally reference the planned `AUTH_REFRESH_LOCK_WAIT_SECONDS` and `CodexNativeTemporaryError` contracts with compatibility fallbacks so that they fail as behavior assertions before Task 2 introduces those names. Task 2 should add the named constant and temporary-error class for the tests to exercise the exact final interface.
- The full focused file is not green before Task 2 because this task deliberately adds regression tests ahead of the production implementation, and the two unrelated Windows-specific failures remain present.

## OAuth Session Reliability Test Review Fixes (2026-07-10)

### Test Changes

- The second subprocess now signals from inside `_token_expires_soon()` while `read_tokens()` evaluates the expired credential, proving it has entered the refresh path before the first token endpoint response is released.
- Failure cleanup now terminates and reaps both subprocesses, escalating to `kill()` if a process does not exit within five seconds.
- The lock test now pins `AUTH_REFRESH_LOCK_POLL_SECONDS == 0.1`, `AUTH_REFRESH_LOCK_WAIT_SECONDS == 20.0`, and `AUTH_REFRESH_LOCK_STALE_SECONDS == 30.0`. Its stale fixture derives from the asserted 30-second threshold.
- Both temporary and credential status payload tests assert that the exact `<auth-file>.refresh.lock` path is redacted.

### Focused Red Verification

Command run from `G:\Codex\image-prompt-library`:

```powershell
$env:PYTHONUTF8='1'; .\.venv\Scripts\python.exe -m pytest tests\test_openai_codex_native.py -q -p no:cacheprovider
```

Result: `5 failed, 24 passed, 1 warning in 7.24s` (exit code 1).

Expected Task 1 failures:

- `test_codex_native_refresh_coordinates_independent_processes`: `refresh_requests == 2`, with the second child having signalled from within its refresh path before the first response was released.
- `test_codex_native_refresh_recovers_stale_lock_but_preserves_fresh_lock`: `AUTH_REFRESH_LOCK_POLL_SECONDS` is currently absent instead of `0.1`; the remaining exact timing checks will exercise Task 2 once that constant is added.
- `test_codex_native_temporary_refresh_failure_remains_connected_and_redacted`: temporary refresh failure still reports `authenticated == False` instead of preserving connected authentication state.

Unrelated existing Windows failures remained unchanged:

- Auth-file permission mode observed as `0o666` rather than the POSIX expectation `0o600`.
- Symlink creation was denied with `WinError 1314`.
