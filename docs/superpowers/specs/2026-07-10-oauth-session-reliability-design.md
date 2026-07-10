# OAuth Session Reliability Design

## Goal

Keep normal ChatGPT / Codex OAuth access-token renewal invisible to local users while making genuine credential loss clear and actionable.

When two local callers need a refresh at the same time, only one may contact the OAuth token endpoint. The others must reuse the refreshed credentials instead of presenting a false re-login state.

## Context

The existing `CodexNativeAuthStore` refreshes an access token when it is close to expiry and writes the replacement token pair atomically. It has no cross-process coordination, so a local service, Config status request, and generation request can refresh the same rotating refresh token concurrently.

The existing provider status contract already supports `ready`, `login_required`, `auth_error`, and `unavailable`. The existing UI already has provider readiness and Connect flows. This milestone should use those surfaces rather than introduce a new generation queue or provider architecture.

## Scope

### Single-Owner Refresh

- Store a regular refresh-lock file named `<auth-file>.refresh.lock` beside the app-owned OAuth credential file.
- Acquire an OS-managed exclusive advisory lock on that file: `msvcrt` on Windows and `fcntl` on macOS/Linux. Use only the Python standard library.
- The lock owner must reread the credential file after acquisition. If another caller refreshed before the lock was acquired, return the fresh token pair without calling the OAuth endpoint again.
- The lock owner refreshes only when the reread access token is still near expiry.
- Keep the existing atomic credential-file replacement for successful refreshes.
- Always release the lock after success, failure, or raised exception.

### Waiting Callers

- A caller that cannot acquire the lock polls every 100 milliseconds for up to 20 seconds, then rereads the credential file.
- If the reread access token is no longer near expiry, return it without an OAuth request.
- Waiting must be bounded. A caller must not wait indefinitely for a crashed service or abandoned lock.
- If waiting expires, raise a retryable temporary-availability error, not a credential-loss error.

### Crash Recovery

- Do not use lock age, marker files, stale-lock deletion, or lock-directory cleanup.
- The operating system releases the advisory lock when its owning process exits or crashes.
- A caller that cannot obtain the lock within the bounded wait period returns a retryable temporary-availability error.

### Provider Status And User Experience

- Successful background refresh keeps provider status `ready`; Config continues to show the existing connected state.
- A generation request waiting for another caller's refresh remains in the existing queued/running flow. It must not expose a false auth error.
- Credential-specific refresh failures map to `auth_error` and retain the existing reconnect path.
- Network errors, OAuth timeouts, upstream 5xx responses, and refresh-lock wait expiry map to `unavailable` with concise temporary-unavailability copy. Stored credentials remain intact.
- No token, refresh token, lock path, or upstream secret is exposed through API payloads, UI copy, or errors.

## Non-Goals

- No new generation provider or OAuth protocol.
- No queue rewrite, job-state redesign, automatic paid-generation retry, or new retry framework.
- No saved-reference/input-image UX work.
- No token deletion on temporary network or upstream errors.
- No account system, cloud sync, or public-demo generation.
- No new dependency.

## Implementation Boundaries

### Backend

`backend/services/openai_codex_native.py` remains the only owner of credential read, refresh, and status classification behavior.

Use a small private lock helper adjacent to `CodexNativeAuthStore`; do not create a general-purpose locking subsystem. The helper owns cross-platform exclusive acquire, bounded wait, release, and file-descriptor cleanup for one auth-store path.

Keep `read_tokens()` as the shared entry point for provider status and generation. This ensures every caller follows the same single-owner refresh behavior.

Add a private retryable refresh exception that distinguishes temporary OAuth availability from credential failure. Reuse the existing provider `status` and `message` fields; do not extend the API shape.

### Frontend

Keep the existing Config provider card and generation readiness UI. Update copy or status presentation only if the current `unavailable` state does not clearly tell users that they can wait and try again without reconnecting.

Do not add a modal, global spinner, new settings, or a foreground token-renewal step. Normal refresh remains background work.

## Error Classification

| Condition | Provider state | User-facing behavior | Credential file |
| --- | --- | --- | --- |
| Refresh succeeds | `ready` | No new interruption | Atomically replace with the new token pair |
| Another caller completes refresh | `ready` | No new interruption | Reread and reuse the new token pair |
| Refresh token rejected, credentials malformed, or OAuth 400/401/403 | `auth_error` | Existing reconnect action | Preserve file until an explicit reconnect/disconnect action |
| Network error, timeout, or upstream 5xx | `unavailable` | Explain that generation is temporarily unavailable and can be tried again | Preserve file |
| Lock wait expires | `unavailable` | Explain that generation is temporarily unavailable and can be tried again | Preserve file |

## Testing And QA

### Automated Tests

- Two independent auth-store callers sharing one credential path trigger exactly one refresh request and both receive the resulting access token.
- A caller that acquires the lock after another refresh rereads the new token and does not issue a second refresh request.
- A process that holds the advisory lock can exit, after which a new caller acquires the lock and refreshes normally.
- Lock release occurs after refresh success and after refresh failure.
- Credential rejection maps to `auth_error`; timeout, network, upstream 5xx, and lock wait expiry map to `unavailable`.
- Temporary failures keep the credential file and redact all secrets from returned status/error payloads.
- Existing provider-ready, login-required, and manual-upload behavior stays covered.

### Desktop And Mobile QA

- With a connected provider, open Config and the generation composer on desktop and mobile. Both remain in the normal connected/ready state.
- Submit a generation and confirm the existing queued/running/result flow has no new blocking OAuth UI.
- Exercise controlled temporary-unavailable and credential-error states; confirm the first says to try again and the second shows reconnect guidance.
- Verify provider/error text wraps cleanly and no controls overlap at a 375px-wide mobile content viewport.

### Live QA

- Use the authenticated ChatGPT / Codex OAuth path.
- Confirm Config recognizes the session and run one real generation attempt.
- Record the observed session and generation result without logging account data or secrets.
- A naturally expired or revoked session may require browser approval from the user; do not simulate this against the live account by corrupting credentials.

## Acceptance Criteria

- Concurrent local refresh callers make one OAuth refresh request and all reuse the resulting token pair.
- Normal token renewal does not show a re-login prompt or interrupt generation.
- A true credential failure gives a clear reconnect path.
- A transient refresh failure says to try again and does not delete saved credentials.
- The public GitHub Pages demo remains read-only and generation-free.
- Automated checks, desktop/mobile visual QA, and live OAuth generation QA are recorded before release.
