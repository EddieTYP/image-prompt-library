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
