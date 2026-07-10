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

## Review Fix: Owner Markers And Strict Credential Parsing

### Findings Addressed

- Replaced pathname-only stale cleanup with a unique `owner-<uuid>` marker for every acquired lock.
- Stale cleanup removes only the single owner marker it observed, confirms the lock directory identity did not change, and calls `rmdir()` only after that marker removal succeeds.
- Normal release removes only its own unique marker and preserves any replacement lock.
- Converted invalid UTF-8 auth files to `CodexNativeAuthError`.
- Rejected non-string access and refresh token values instead of coercing them with `str()`.
- Added explicit coverage that OAuth 400, 401, and 403 remain credential failures.
- Added byte-for-byte checks that transport and 5xx refresh failures do not alter the saved credential file.

### RED Evidence

Command:

```powershell
$env:PYTHONUTF8='1'; .\.venv\Scripts\python.exe -m pytest tests/test_openai_codex_native.py::test_codex_native_refresh_maps_transient_failures_to_temporary_error tests/test_openai_codex_native.py::test_codex_native_refresh_keeps_oauth_credential_failures_as_auth_errors tests/test_openai_codex_native.py::test_codex_native_invalid_utf8_credentials_raise_auth_error tests/test_openai_codex_native.py::test_codex_native_non_string_token_values_raise_auth_error tests/test_openai_codex_native.py::test_codex_native_refresh_recovers_stale_lock_but_preserves_fresh_lock tests/test_openai_codex_native.py::test_codex_native_stale_cleanup_preserves_replacement_fresh_lock -q -p no:cacheprovider
```

Result: `5 failed, 5 passed, 1 warning in 21.06s`.

Expected failures:

- Invalid UTF-8 escaped as `UnicodeDecodeError`.
- Integer access tokens and list refresh tokens were accepted after string coercion.
- Marker-backed stale locks could not be recovered.
- Stale cleanup never observed or removed an owner marker, so the replacement-lock race regression failed.

Unique-marker acquisition RED command:

```powershell
$env:PYTHONUTF8='1'; .\.venv\Scripts\python.exe -m pytest tests/test_openai_codex_native.py::test_codex_native_refresh_lock_uses_a_unique_owner_marker -q -p no:cacheprovider
```

Result: `1 failed, 1 warning in 0.82s`; the acquired lock directory contained no owner marker.

### GREEN Evidence

Review-focused command:

```powershell
$env:PYTHONUTF8='1'; .\.venv\Scripts\python.exe -m pytest tests/test_openai_codex_native.py::test_codex_native_refresh_maps_transient_failures_to_temporary_error tests/test_openai_codex_native.py::test_codex_native_refresh_keeps_oauth_credential_failures_as_auth_errors tests/test_openai_codex_native.py::test_codex_native_invalid_utf8_credentials_raise_auth_error tests/test_openai_codex_native.py::test_codex_native_non_string_token_values_raise_auth_error tests/test_openai_codex_native.py::test_codex_native_refresh_recovers_stale_lock_but_preserves_fresh_lock tests/test_openai_codex_native.py::test_codex_native_stale_cleanup_preserves_replacement_fresh_lock tests/test_openai_codex_native.py::test_codex_native_refresh_lock_uses_a_unique_owner_marker -q -p no:cacheprovider
```

Result: `11 passed, 1 warning in 0.76s`.

Final focused auth-store suite:

```powershell
$env:PYTHONUTF8='1'; .\.venv\Scripts\python.exe -m pytest tests/test_openai_codex_native.py -q -p no:cacheprovider
```

Result: `39 passed, 1 skipped, 1 warning in 6.98s`.

### Files Changed

- `backend/services/openai_codex_native.py`
- `tests/test_openai_codex_native.py`
- `.superpowers/sdd/task-2-report.md` (required report append only)

### Self-Review And Concerns

- The marker filename is unique per acquisition, so a stale cleaner cannot target a replacement owner's marker.
- Both stale cleanup and normal release require successful removal of the expected marker before attempting directory removal.
- Directory identity remains a second check; `rmdir()` still requires the directory to be empty.
- No API shape, frontend, provider, queue, or dependency changes were made.
- The existing Windows symlink privilege skip and Starlette `TestClient` deprecation warning remain unchanged.

## Re-Review Fix: Empty Stale Lock Recovery

### Finding Addressed

- Added recovery for an empty refresh-lock directory older than `AUTH_REFRESH_LOCK_STALE_SECONDS`, covering crashes before owner-marker creation or after marker removal.
- Preserved a fresh empty lock as an in-progress acquisition; wait expiry raises `CodexNativeTemporaryError` without deleting it.
- Empty stale cleanup writes a unique cleanup claim, verifies the observed directory identity, atomically renames that claimed directory to a unique tombstone, then removes the claim and tombstone with `rmdir()`.
- Removed pathname-only `rmdir()` from owner-marker creation failure so a delayed creator cannot delete a replacement empty lock after its original directory was renamed.
- Existing owner-marker cleanup and replacement-fresh-lock safety remain unchanged.

### RED Evidence

Command:

```powershell
$env:PYTHONUTF8='1'; .\.venv\Scripts\python.exe -m pytest tests/test_openai_codex_native.py::test_codex_native_refresh_recovers_empty_stale_lock tests/test_openai_codex_native.py::test_codex_native_refresh_preserves_empty_fresh_lock -q -p no:cacheprovider
```

Result: `1 failed, 1 passed, 1 warning in 0.89s`.

- Empty stale recovery raised `CodexNativeTemporaryError` because markerless stale directories were ignored.
- Fresh empty preservation already passed and remained the invariant for the implementation.

### GREEN Evidence

Regression command:

```powershell
$env:PYTHONUTF8='1'; .\.venv\Scripts\python.exe -m pytest tests/test_openai_codex_native.py::test_codex_native_refresh_recovers_empty_stale_lock tests/test_openai_codex_native.py::test_codex_native_refresh_preserves_empty_fresh_lock -q -p no:cacheprovider
```

Result: `2 passed, 1 warning in 0.74s`.

Final focused auth-store suite:

```powershell
$env:PYTHONUTF8='1'; .\.venv\Scripts\python.exe -m pytest tests/test_openai_codex_native.py -q -p no:cacheprovider
```

Result: `41 passed, 1 skipped, 1 warning in 7.03s`.

### Files Changed

- `backend/services/openai_codex_native.py`
- `tests/test_openai_codex_native.py`
- `.superpowers/sdd/task-2-report.md` (required report append only)

### Concerns

- The existing Windows symlink privilege skip remains unrelated to auth locking.
- The existing Starlette `TestClient` deprecation warning remains unchanged.

## Final Review Fix: Atomic Lock Publication

### Finding Addressed

- Refactored new lock acquisition so the canonical `<auth-file>.refresh.lock` path is never created empty.
- Each contender creates a UUID-named private sibling directory, writes its unique `owner-<uuid>` marker inside, and records that prepared directory's identity before publication.
- The fully prepared directory is atomically renamed to the canonical lock path.
- A contender that loses publication because the canonical path exists removes only its private marker and private directory, then follows normal stale-check and wait behavior.
- Preserved marker-owned stale cleanup, replacement fresh-lock protection, and claimed recovery of legacy empty stale canonical directories.

### RED Evidence

Deterministic delayed-owner command:

```powershell
$env:PYTHONUTF8='1'; .\.venv\Scripts\python.exe -m pytest tests/test_openai_codex_native.py::test_codex_native_delayed_owner_cannot_enter_replacement_lock -q -p no:cacheprovider
```

Result: `1 failed, 1 warning in 0.86s`.

- Owner A created the canonical directory before its marker and was paused.
- Cleanup recovered that empty stale directory and owner B acquired the replacement lock.
- When resumed, owner A wrote its marker into owner B's canonical directory and incorrectly entered owner B's lock.

### GREEN Evidence

Delayed-owner regression:

```powershell
$env:PYTHONUTF8='1'; .\.venv\Scripts\python.exe -m pytest tests/test_openai_codex_native.py::test_codex_native_delayed_owner_cannot_enter_replacement_lock -q -p no:cacheprovider
```

Result: `1 passed, 1 warning in 0.70s`.

Combined lock-protocol regressions:

```powershell
$env:PYTHONUTF8='1'; .\.venv\Scripts\python.exe -m pytest tests/test_openai_codex_native.py::test_codex_native_refresh_coordinates_independent_processes tests/test_openai_codex_native.py::test_codex_native_refresh_recovers_stale_lock_but_preserves_fresh_lock tests/test_openai_codex_native.py::test_codex_native_refresh_recovers_empty_stale_lock tests/test_openai_codex_native.py::test_codex_native_refresh_preserves_empty_fresh_lock tests/test_openai_codex_native.py::test_codex_native_stale_cleanup_preserves_replacement_fresh_lock tests/test_openai_codex_native.py::test_codex_native_refresh_lock_uses_a_unique_owner_marker tests/test_openai_codex_native.py::test_codex_native_delayed_owner_cannot_enter_replacement_lock -q -p no:cacheprovider
```

Result: `7 passed, 1 warning in 2.31s`.

Final focused auth-store suite:

```powershell
$env:PYTHONUTF8='1'; .\.venv\Scripts\python.exe -m pytest tests/test_openai_codex_native.py -q -p no:cacheprovider
```

Result: `42 passed, 1 skipped, 1 warning in 6.97s`.

### Files Changed

- `backend/services/openai_codex_native.py`
- `tests/test_openai_codex_native.py`
- `.superpowers/sdd/task-2-report.md` (required report append only)

### Self-Review And Concerns

- The canonical lock appears only after its owner marker exists in the prepared directory.
- Publication losers cannot write into or delete the winning canonical lock.
- The deterministic race asserts the delayed owner never enters, never adds a second canonical marker, and leaves no private pending directory.
- The existing Windows symlink privilege skip and Starlette `TestClient` deprecation warning remain unchanged.

## Architecture Reset: OS Advisory Refresh Lock

### Approved Replacement

- Removed the directory, owner-marker, stale-age, pending-directory, tombstone, rename, and deletion protocol in full.
- The canonical `<auth-file>.refresh.lock` is now a persistent regular file.
- Windows uses `msvcrt.locking(..., LK_NBLCK, 1)` on a persistent byte.
- macOS and Linux use `fcntl.flock(..., LOCK_EX | LOCK_NB)`.
- Acquisition retries every `0.1` seconds for at most `20.0` seconds.
- Wait expiry raises `CodexNativeTemporaryError`.
- Owned locks are unlocked and file descriptors are closed in `finally`; operating-system process teardown releases a killed owner's lock automatically.
- Lock files are never aged, renamed, unlinked, or deleted.
- Existing coordinated token reread, temporary error mapping, credential validation, status semantics, and redaction behavior remain unchanged.

### Test Replacement

- Kept the genuine independent-process refresh test requiring exactly one token endpoint request and identical refreshed credentials.
- Removed six obsolete directory/marker/stale-cleanup tests.
- Added a real child-process holder that acquires the production advisory lock.
- Added killed-owner coverage proving immediate reacquisition after process termination.
- Added bounded-wait coverage proving a live owner yields `CodexNativeTemporaryError` within the configured wait and leaves a regular lock file.
- Pinned the required `0.1` polling and `20.0` default wait constants and asserted that no stale-age constant remains.

### RED Evidence

Command:

```powershell
$env:PYTHONUTF8='1'; .\.venv\Scripts\python.exe -m pytest tests/test_openai_codex_native.py::test_codex_native_refresh_lock_releases_when_owner_is_killed tests/test_openai_codex_native.py::test_codex_native_refresh_lock_wait_is_bounded_and_temporary -q -p no:cacheprovider
```

Result: `2 failed, 1 warning in 3.07s`.

- Killing the directory-lock owner left an unrecoverable canonical directory and reacquisition timed out.
- The held canonical path was a directory rather than the required regular advisory-lock file.

### GREEN Evidence

Core coordination and advisory-lock command:

```powershell
$env:PYTHONUTF8='1'; .\.venv\Scripts\python.exe -m pytest tests/test_openai_codex_native.py::test_codex_native_refresh_lock_releases_when_owner_is_killed tests/test_openai_codex_native.py::test_codex_native_refresh_lock_wait_is_bounded_and_temporary tests/test_openai_codex_native.py::test_codex_native_refresh_coordinates_independent_processes -q -p no:cacheprovider
```

Result: `3 passed, 1 warning in 3.29s`.

Final focused auth-store suite:

```powershell
$env:PYTHONUTF8='1'; .\.venv\Scripts\python.exe -m pytest tests/test_openai_codex_native.py -q -p no:cacheprovider
```

Result: `38 passed, 1 skipped, 1 warning in 7.99s`.

### Files Changed

- `backend/services/openai_codex_native.py`
- `tests/test_openai_codex_native.py`
- `.superpowers/sdd/task-2-report.md` (required report append only)

### Self-Review And Concerns

- Protocol scans found no stale-age, marker, pending, tombstone, rename, unlink, or directory-deletion logic in the auth lock path.
- The Windows `msvcrt` branch was exercised by the focused suite, including process-kill release and bounded contention.
- The `fcntl` branch uses the standard macOS/Linux `flock` API but could not execute in this Windows environment.
- The existing Windows symlink privilege skip and Starlette `TestClient` deprecation warning remain unchanged.
