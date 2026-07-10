# Task 2 Report: OAuth Session Reliability

## Status

`DONE`

## Scope

Implemented the Task 2 brief on `codex/oauth-session-reliability` in the owned native Codex auth-store module. Preserved Task 1's test contracts and made only narrow test additions and Windows portability guards needed for the requested focused suite.

## RED Evidence

Initial Task 1 regression suite:

```powershell
$env:PYTHONUTF8='1'; .\.venv\Scripts\python.exe -m pytest tests/test_openai_codex_native.py -q -p no:cacheprovider
```

Result: `5 failed, 24 passed, 1 warning in 9.12s`.

Task 2 behavior failures:

- Independent processes made two refresh requests instead of one.
- Lock timing constants and stale-lock recovery were absent.
- Temporary refresh failure reported `authenticated=False` instead of remaining connected.

The other two failures were the previously recorded Windows POSIX-mode and symlink-privilege limitations.

Added direct transient-refresh coverage and confirmed RED:

```powershell
$env:PYTHONUTF8='1'; .\.venv\Scripts\python.exe -m pytest tests/test_openai_codex_native.py::test_codex_native_refresh_maps_transient_failures_to_temporary_error -q -p no:cacheprovider
```

Result: `2 failed, 1 warning in 0.82s`; both cases failed because `CodexNativeTemporaryError` did not exist.

Added malformed-local-credential coverage and confirmed RED:

```powershell
$env:PYTHONUTF8='1'; .\.venv\Scripts\python.exe -m pytest tests/test_openai_codex_native.py::test_codex_native_malformed_local_credentials_raise_auth_error -q -p no:cacheprovider
```

Result: `1 failed, 1 warning in 0.83s`; invalid JSON leaked `json.JSONDecodeError` instead of `CodexNativeAuthError`.

## Changes

- Added the required lock timing constants, `_refresh_lock_path()`, and a private directory-lock context manager.
- Coordinated `read_tokens()` across processes, rereading credentials after lock acquisition and refreshing only when still near expiry.
- Recovered one stale named lock, preserved fresh locks on timeout, and released only a lock owned by the caller.
- Added `CodexNativeTemporaryError` as a specialized auth error for HTTP transport failures, OAuth 5xx responses, and lock wait expiry.
- Preserved OAuth credential errors and malformed local credentials as `CodexNativeAuthError`.
- Kept raw credential discovery independent in `status()` so temporary refresh failures remain authenticated and connected but unavailable with the exact retry-soon message.
- Guarded the POSIX mode assertion on Windows and skipped the symlink test only for Windows error 1314.

## GREEN Evidence

Task-focused behavior run:

```powershell
$env:PYTHONUTF8='1'; .\.venv\Scripts\python.exe -m pytest tests/test_openai_codex_native.py::test_codex_native_refreshes_expired_access_token_before_use tests/test_openai_codex_native.py::test_codex_native_refresh_maps_transient_failures_to_temporary_error tests/test_openai_codex_native.py::test_codex_native_refresh_coordinates_independent_processes tests/test_openai_codex_native.py::test_codex_native_refresh_recovers_stale_lock_but_preserves_fresh_lock tests/test_openai_codex_native.py::test_codex_native_broken_saved_login_maps_to_auth_error tests/test_openai_codex_native.py::test_codex_native_temporary_refresh_failure_remains_connected_and_redacted -q -p no:cacheprovider
```

Result: `7 passed, 1 warning in 2.67s`.

Final focused auth-store suite:

```powershell
$env:PYTHONUTF8='1'; .\.venv\Scripts\python.exe -m pytest tests/test_openai_codex_native.py -q -p no:cacheprovider
```

Result: `31 passed, 1 skipped, 1 warning in 7.03s`.

## Files Changed

- `backend/services/openai_codex_native.py`
- `tests/test_openai_codex_native.py`
- `.superpowers/sdd/task-2-report.md`

## Self-Review

- Scope is limited to the auth store, its focused tests, and this report.
- No frontend, provider, queue, dependency, or unrelated production code changed.
- Lock cleanup runs in `finally`; lock identity is checked before removal.
- Status payloads expose neither token values nor lock paths.
- The temporary-error subclass preserves existing callers that catch `CodexNativeAuthError`.

## Concerns

- The Windows environment cannot validate POSIX `0600` mode bits through `stat()`, so that assertion remains active only on non-Windows systems.
- The unsafe-result-root symlink test is skipped only because this Windows account lacks symlink privilege (`WinError 1314`).
- Pytest reports the existing Starlette `TestClient` deprecation warning.
