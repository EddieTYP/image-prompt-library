# OAuth Session Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make normal ChatGPT / Codex OAuth renewal invisible by serializing refreshes and preserving login state for temporary provider outages.

**Architecture:** Keep all behavior in `CodexNativeAuthStore`. A private OS-advisory lock file beside the auth file gives one caller refresh ownership; waiters reread the atomically replaced token file. Existing Config and generation UI consume `authenticated`, `status`, and `message`, so no new controls are needed.

**Tech Stack:** Python 3.10+, `pathlib`, `os`, `time`, `httpx`, FastAPI, pytest.

## Global Constraints

- No dependency, provider, queue rewrite, automatic paid-generation retry, account system, or public-demo generation.
- Name the regular lock file `<auth-file>.refresh.lock`; poll every 100ms for at most 20s; use OS-managed exclusive advisory locks with `msvcrt` on Windows and `fcntl` on macOS/Linux.
- Keep atomic credential writes and redact tokens, lock paths, and upstream secrets.
- OAuth 400/401/403 and malformed credentials map to `auth_error`; network, timeout, upstream 5xx, and lock expiry map to `unavailable`.
- Temporary errors preserve stored credentials and must not offer reconnect as the normal remedy.

---

### Task 1: Auth Store Regression Tests

**Files:**
- Modify: `tests/test_openai_codex_native.py:193-220,340-391`

**Interfaces:**
- Consumes: `CodexNativeAuthStore(path)`, `read_tokens(http_client)`, `status()`.
- Produces: coverage for one-owner refresh, OS crash release, and status classification.

- [ ] **Step 1: Write failing concurrency tests**

Start two independent Python processes that each create `CodexNativeAuthStore(auth_path)` and call `read_tokens()` against one local token-endpoint test server. Block the first endpoint response with `threading.Event` until the second process begins, then assert:

```python
assert refresh_requests == 1
assert first_result["access_token"] == refreshed_access_token
assert second_result["access_token"] == refreshed_access_token
```

Start a helper process that acquires the real advisory lock, then terminate that process without an application-level release. Assert a subsequent caller can acquire the lock and refresh. Also hold the real lock while monkeypatching the wait limit to `0` and assert `read_tokens()` raises the temporary error without deleting the lock file.

- [ ] **Step 2: Verify the new tests fail**

Run `PYTHONUTF8=1 .\.venv\Scripts\python.exe -m pytest tests/test_openai_codex_native.py -q -p no:cacheprovider`.

Expected: FAIL because the current store has no cross-process refresh lock.

- [ ] **Step 3: Write failing status tests**

With expired saved credentials, monkeypatch refresh to raise temporary and credential errors. The temporary payload must satisfy:

```python
assert payload["authenticated"] is True
assert payload["state"] == "connected"
assert payload["available"] is False
assert payload["status"] == "unavailable"
assert payload["message"] == "ChatGPT / Codex OAuth is temporarily unavailable. Try again shortly."
```

Assert rejected refresh returns `auth_error` and neither payload contains the refresh token.

### Task 2: Private Lock And Provider Status Semantics

**Files:**
- Modify: `backend/services/openai_codex_native.py:294-460`
- Test: `tests/test_openai_codex_native.py`

**Interfaces:**
- Consumes: `_token_expires_soon()`, atomic `save_tokens()`, `CodexNativeAuthError`.
- Produces: `CodexNativeTemporaryError`, cross-platform OS lock helpers, coordinated `read_tokens()`, and temporary-unavailable provider status.

- [ ] **Step 1: Implement one private lock helper**

Add module-private constants:

```python
AUTH_REFRESH_LOCK_POLL_SECONDS = 0.1
AUTH_REFRESH_LOCK_WAIT_SECONDS = 20.0
```

Add `_refresh_lock_path(auth_path)` returning `auth_path.with_name(f"{auth_path.name}.refresh.lock")`. Open that regular file with the standard library, acquire an exclusive nonblocking advisory lock using `msvcrt` on Windows and `fcntl` on macOS/Linux, and retry acquire on the polling interval until the wait limit expires. Always unlock and close the owned file descriptor in `finally`; never delete a held lock file or infer ownership from age.

- [ ] **Step 2: Coordinate `read_tokens()`**

Return valid raw credentials immediately. Otherwise acquire or wait on the lock, reread after acquisition, and refresh only if the reread access token is still near expiry:

```python
with self._refresh_lock():
    tokens = self._read_raw_tokens()
    return self.refresh_tokens(tokens["refresh_token"], http_client=http_client) if _token_expires_soon(tokens["access_token"]) else tokens
```

Release only a lock this caller owns, including on raised exceptions. Convert wait expiry to `CodexNativeTemporaryError`.

- [ ] **Step 3: Distinguish temporary and credential failures**

Have `refresh_tokens()` raise `CodexNativeTemporaryError` for `httpx.HTTPError` and 5xx. Keep local malformed credentials and OAuth 400/401/403 as `CodexNativeAuthError`.

In `status()`, retain successful raw-token discovery independently from `read_tokens()`. A temporary error returns `authenticated=True`, `state="connected"`, `available=False`, `status="unavailable"`, and the exact temporary-unavailable message. A genuine credential failure remains `auth_error`.

- [ ] **Step 4: Verify green and commit**

Run `PYTHONUTF8=1 .\.venv\Scripts\python.exe -m pytest tests/test_openai_codex_native.py -q -p no:cacheprovider`.

Expected: PASS.

```powershell
git add backend/services/openai_codex_native.py tests/test_openai_codex_native.py
git commit -m "fix: coordinate OAuth token refresh"
```

### Task 3: Guard Existing UX And Record QA

**Files:**
- Modify: `tests/test_frontend_static.py`
- Modify: `docs/GENERATION.md`
- Create: `docs/qa/2026-07-10-oauth-session-reliability-qa.md`

**Interfaces:**
- Consumes: current provider `message`, `authenticated`, and Config/GenerationPanel UI.
- Produces: a static UX guard, user documentation, and a public-safe QA record.

- [ ] **Step 1: Add and run the static UX guard**

Assert in a new frontend-static test:

```python
assert "if (provider.message) return provider.message;" in panel
assert "!provider.authenticated && !authStart" in config
assert "provider.authenticated && <button" in config
```

Run `PYTHONUTF8=1 .\.venv\Scripts\python.exe -m pytest tests/test_frontend_static.py -q -p no:cacheprovider`.

Expected: PASS without frontend production changes.

- [ ] **Step 2: Document the user contract**

Replace the completed `Cross-process token refresh locking` follow-up in `docs/GENERATION.md` with:

```markdown
- Normal OAuth token renewal is coordinated locally and should not interrupt Config or generation. If the provider is temporarily unreachable, try again shortly; reconnect only when the app explicitly says OAuth needs attention.
```

- [ ] **Step 3: Run checks, build, and live QA**

Run `PYTHONUTF8=1 .\.venv\Scripts\python.exe -m pytest tests/test_openai_codex_native.py tests/test_frontend_static.py -q -p no:cacheprovider`, then run `npm run build` and `git diff --check`.

On desktop and a 375px-wide mobile content viewport, verify connected Config, provider-ready composer, queued/running/result flow, wrapped provider text, and no overlaps. Use a fresh browser tab and ordinary viewport screenshots after drawer transitions settle.

Run one live OAuth generation attempt. Record only public-safe observations in `docs/qa/2026-07-10-oauth-session-reliability-qa.md`; omit accounts, tokens, URLs, user codes, private prompts, and private images.

- [ ] **Step 4: Commit the UX guard, docs, and QA record**

```powershell
git add tests/test_frontend_static.py docs/GENERATION.md docs/qa/2026-07-10-oauth-session-reliability-qa.md
git commit -m "docs: record OAuth session QA"
```
