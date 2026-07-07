# Generation Hardening Design

Date: 2026-07-08

## Summary

This milestone hardens the existing generation experience without replacing the queue, provider, or job repository architecture.

The goal is to make local generation reliable and understandable across provider connection, model/settings selection, queued/running/failed/retry states, result acceptance, and backend restart recovery.

## Scope

In scope:

- Provider status and OAuth refresh clarity
- Generation job lifecycle hardening
- Retry, discard, cancel, and stale-failed clarity
- Model, quality, aspect ratio, and attachment setting UI hardening
- Existing restart recovery verification
- Full live generation QA
- Desktop and mobile visual QA

Out of scope:

- New provider architecture
- New import features
- New account/onboarding system
- Major queue rewrite
- Multi-provider marketplace
- Automatic paid-generation reruns after restart

## Backend Behavior

The milestone keeps the existing generation job repository, queue runner, and provider router structure. It does not replace the queue architecture.

Backend changes should focus on tightening observable job behavior.

### Provider Status

- Return clear provider availability and auth state for the frontend.
- Distinguish at least:
  - provider available
  - provider unavailable
  - auth missing
  - auth expired or refresh failed, if detectable
- Preserve the existing manual upload provider path.

### Job Lifecycle Clarity

- Keep the existing states: `queued`, `running`, `succeeded`, `failed`, `accepted`, `discarded`, `cancelled`.
- Ensure transitions remain valid and user-facing failures include actionable messages.
- Failed generation jobs should be retryable where the current system already supports retry.

### Retry, Discard, And Cancel

- Reuse existing repository and queue methods where possible.
- Avoid adding a new retry framework.
- Make retry behavior clear:
  - retry failed job
  - discard and retry successful, accepted, or discarded results where already supported
  - cancel queued or running jobs where supported

### Restart Recovery

- Do not redesign restart recovery in this milestone.
- Verify the existing backend behavior:
  - interrupted running provider jobs are marked failed on backend startup
  - the failure message tells the user to retry
- Add or adjust tests only where coverage is missing.

### Stale Running Jobs

- Reduce the stale-running threshold from 30 minutes to 10 minutes.
- Use a clear failure message when a job is marked stale:
  - `Generation took too long and may have stalled. Retry to run it again.`
- Preserve retry support for stale-failed jobs.
- Do not auto-retry stale jobs in this milestone.

### API Compatibility

- Avoid breaking existing frontend endpoints.
- Prefer extending response fields only when needed for clearer UI states.

## Frontend UX Behavior

The milestone keeps the existing `GenerationPanel` and `GenerationQueueDrawer` structure. It should harden the current experience instead of replacing it.

### Provider Readiness

- Show a clear provider readiness state before generation.
- Distinguish:
  - ready
  - unavailable
  - login required
  - auth expired or refresh failed, if backend exposes it
- Keep manual upload visible as a fallback path.

### Model And Settings Controls

- Make model, quality, aspect ratio, and attachment settings explicit before submit.
- Preserve existing defaults.
- Avoid adding advanced settings unless already supported by the backend/provider.
- If a setting is unavailable, disable it with a concise reason.

### Submit And Queue Feedback

- Prevent duplicate accidental submits while a request is being created.
- Show when a job is queued versus running.
- Make the queue drawer state obvious on desktop and mobile.

### Failed Jobs And Retry

- Show actionable failed-job messages.
- Provide retry where backend allows retry.
- For stale timeout failures, show that the job may have stalled and can be retried.

### Result Management

- Keep accept, discard, and discard-and-retry actions visible where valid.
- Do not introduce batch generation result management in this milestone.

### Mobile Behavior

- Generation controls, queue drawer, and action buttons must be usable on mobile.
- No overlapping floating controls.
- Long provider/model/status text must wrap or truncate cleanly.

## Data / API Contract

The milestone should preserve existing generation endpoints and response shapes unless a small additive field is needed for clearer UI behavior.

### Provider Status Payload

- Extend the provider status response only if needed to represent clearer frontend states.
- Suggested additive fields:
  - `status`: `"ready" | "unavailable" | "login_required" | "auth_error"`
  - `message`: optional user-facing explanation
  - `can_generate`: boolean
- Existing fields should remain available for compatibility.

### Generation Job Payload

- Preserve existing job identifiers, status values, timestamps, prompt metadata, result metadata, and error fields.
- If needed, normalize frontend-facing error text so failed, stale, and restart-interrupted jobs show useful messages.

### Retry And Cancellation Responses

- Preserve current retry, discard-and-retry, cancel, accept, and discard endpoints.
- Responses should return the updated job state where the current route pattern already does so.
- Do not add new bulk generation endpoints in this milestone.

### Settings Payload

- Model, quality, aspect ratio, and attachment settings should use the existing submit payload where possible.
- If the backend ignores unsupported settings, the frontend should not present them as active controls.

## Testing / QA Plan

The milestone is not complete until automated checks and live visual QA both pass.

### Backend Tests

- Cover provider status mapping.
- Cover failed job retry behavior.
- Cover stale running job timeout at the new 10-minute threshold.
- Cover restart recovery for interrupted running provider jobs.
- Cover cancel behavior where supported.

### Frontend / Static Tests

- Cover generation panel rendering for provider-ready, login-required, unavailable, and auth-error states where practical.
- Cover model/settings control visibility and disabled states.
- Cover failed-job retry affordances.
- Cover queue drawer state labels and actions.

### Build Checks

- Run the existing Python test suite.
- Run the existing frontend build.
- Run the existing frontend/static tests.

### Desktop Visual QA

- Start the local app.
- Verify provider readiness display.
- Verify model/settings controls.
- Submit a live generation job.
- Verify queued/running/succeeded flow.
- Verify accept/discard/retry affordances.
- Verify no action overlap at desktop viewport.

### Mobile Visual QA

- Repeat the main generation flow on mobile viewport.
- Verify the queue drawer is usable.
- Verify long status/provider/model text wraps or truncates cleanly.
- Verify no floating controls overlap core actions.

### Live OAuth And Full Live Generation QA

- Use the authenticated live provider path.
- Confirm OAuth/session state is recognized.
- Run at least one real generation attempt.
- Record the observed result:
  - succeeded
  - failed with a clear provider/auth/error message that matches expected behavior
- Do not mark the milestone complete based only on mocked provider tests.

## Risks / Guardrails

### Avoid Queue Rewrite

- Do not replace the existing generation queue or repository architecture.
- Only adjust lifecycle behavior needed for clearer states, retry, stale timeout, and recovery verification.

### Avoid Provider Expansion

- Do not add new providers in this milestone.
- Do not build a provider marketplace or multi-provider routing layer.
- Preserve manual upload as the fallback path.

### Avoid Advanced Setting Sprawl

- Do not expose settings that the backend/provider cannot actually honor.
- Do not add speculative controls for future model features.

### Avoid Automatic Paid Reruns

- Do not auto-retry failed, stale, or restart-interrupted jobs.
- User must explicitly retry to avoid duplicate generation cost or surprise provider usage.

### Live QA Risk

- Live generation may fail for provider-side reasons outside the app.
- A live failure is acceptable only if:
  - auth/provider state is detected correctly
  - the error message is clear
  - retry/recovery behavior remains usable

### Release Risk

- This milestone should not be released until desktop QA, mobile QA, automated tests, and live provider QA are all recorded.
