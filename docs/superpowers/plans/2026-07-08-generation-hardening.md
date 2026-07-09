# Generation Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the existing generation flow so provider readiness, settings, job lifecycle, retry/cancel/recovery states, and live QA are clear and verifiable.

**Architecture:** Keep the existing FastAPI routers, `GenerationJobRepository`, process-local queue runner, and React `GenerationPanel` / `GenerationQueueDrawer`. Add only small response fields, helper functions, constants, copy, and tests needed to clarify states and reduce the stale-running timeout. Do not introduce a new queue, provider framework, or bulk generation API.

**Tech Stack:** Python, FastAPI, Pydantic, pytest, SQLite repository tests, React, TypeScript, Vite, static frontend tests, browser visual QA.

## Global Constraints

- Preserve existing generation endpoints and response shapes unless a small additive field is needed.
- Keep states: `queued`, `running`, `succeeded`, `failed`, `accepted`, `discarded`, `cancelled`.
- Reduce stale-running threshold from 30 minutes to 10 minutes.
- Stale failure message must be `Generation took too long and may have stalled. Retry to run it again.`
- Do not redesign restart recovery.
- Do not add providers, a marketplace, a queue rewrite, batch generation endpoints, or automatic paid reruns.
- Preserve manual upload as the fallback path.
- Do not expose settings the backend/provider cannot honor.
- Do desktop QA, mobile QA, automated tests, and live provider QA before release.

---

## File Structure

- Modify `backend/services/openai_codex_native.py`: add additive provider readiness fields to Codex native status.
- Modify `backend/routers/generation_providers.py`: add the same additive readiness fields to the manual upload provider payload.
- Modify `backend/services/generation_jobs.py`: change stale timeout constant and stale failure message.
- Modify `frontend/src/types.ts`: add optional provider readiness fields to `GenerationProviderStatus`.
- Modify `frontend/src/App.tsx`: use `can_generate` / `status` when deciding whether generation is available.
- Modify `frontend/src/api/client.ts`: keep demo provider payload compatible with the new optional fields.
- Modify `frontend/src/components/GenerationPanel.tsx`: display provider readiness, use the 10-minute stale timeout, keep model/settings explicit, and prevent unavailable providers from submitting.
- Modify `frontend/src/components/GenerationQueueDrawer.tsx`: use the 10-minute stale timeout and clearer stale/failed retry labels.
- Modify `frontend/src/styles.css`: only layout/copy-supporting CSS needed for provider readiness and mobile wrapping.
- Modify `tests/test_openai_codex_native.py`: provider status payload tests.
- Modify `tests/test_generation_jobs.py` or the existing generation job test file if present: stale timeout, failed retry, cancel, and restart recovery coverage.
- Modify `tests/test_frontend_static.py`: static frontend assertions for provider readiness, 10-minute stale constants, model/settings controls, and queue labels.
- Create `docs/qa/2026-07-08-generation-hardening-live-qa.md`: record desktop, mobile, OAuth, and live generation QA evidence.

---

### Task 1: Provider Readiness Contract

**Files:**
- Modify: `backend/services/openai_codex_native.py`
- Modify: `backend/routers/generation_providers.py`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api/client.ts`
- Test: `tests/test_openai_codex_native.py`
- Test: `tests/test_frontend_static.py`

**Interfaces:**
- Produces backend provider payload fields:
  - `status: "ready" | "unavailable" | "login_required" | "auth_error"`
  - `message: str | None`
  - `can_generate: bool`
- Consumes existing fields:
  - `configured: bool`
  - `authenticated: bool`
  - `available: bool`
  - `state: str`
  - `reason: str | None`
- Produces TypeScript optional fields on `GenerationProviderStatus`:
  - `status?: 'ready' | 'unavailable' | 'login_required' | 'auth_error'`
  - `message?: string | null`
  - `can_generate?: boolean`

- [ ] **Step 1: Write failing backend provider status tests**

Add these assertions to `tests/test_openai_codex_native.py`.

```python
def test_codex_native_status_exposes_generation_readiness_fields(tmp_path, monkeypatch):
    auth_path = tmp_path / "auth" / "auth.json"
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(auth_path))
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_CODEX_CLIENT_ID", "codex-client-test")

    from backend.services.openai_codex_native import CodexNativeAuthStore

    CodexNativeAuthStore().save_tokens({"access_token": fake_jwt(), "refresh_token": "refresh-secret"})
    payload = client(tmp_path).get("/api/generation-providers/openai-codex-native/status").json()

    assert payload["status"] == "ready"
    assert payload["can_generate"] is True
    assert payload["message"] is None


def test_codex_native_missing_login_maps_to_login_required(tmp_path, monkeypatch):
    auth_path = tmp_path / "auth" / "auth.json"
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(auth_path))
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_CODEX_CLIENT_ID", "codex-client-test")

    payload = client(tmp_path).get("/api/generation-providers/openai-codex-native/status").json()

    assert payload["status"] == "login_required"
    assert payload["can_generate"] is False
    assert payload["message"] == "Connect ChatGPT / Codex OAuth before generating."


def test_generation_providers_manual_upload_is_always_generation_ready(tmp_path, monkeypatch):
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_CODEX_CLIENT_ID", "codex-client-test")
    providers = client(tmp_path).get("/api/generation-providers").json()
    manual = providers[0]

    assert manual["provider"] == "manual_upload"
    assert manual["status"] == "ready"
    assert manual["can_generate"] is True
    assert manual["message"] is None
```

- [ ] **Step 2: Run backend tests and verify they fail**

Run:

```bash
pytest tests/test_openai_codex_native.py::test_codex_native_status_exposes_generation_readiness_fields tests/test_openai_codex_native.py::test_codex_native_missing_login_maps_to_login_required tests/test_openai_codex_native.py::test_generation_providers_manual_upload_is_always_generation_ready -q
```

Expected: FAIL with missing `status`, `can_generate`, or `message` keys.

- [ ] **Step 3: Implement backend additive readiness fields**

In `backend/services/openai_codex_native.py`, add this helper near `CodexNativeAuthStore.status`.

```python
def _generation_readiness(configured: bool, token_present: bool, state: str) -> dict[str, Any]:
    if configured and token_present:
        return {"status": "ready", "message": None, "can_generate": True}
    if configured and state == "not_connected":
        return {
            "status": "login_required",
            "message": "Connect ChatGPT / Codex OAuth before generating.",
            "can_generate": False,
        }
    if not configured:
        return {
            "status": "unavailable",
            "message": "ChatGPT / Codex OAuth is not configured.",
            "can_generate": False,
        }
    return {
        "status": "auth_error",
        "message": "ChatGPT / Codex OAuth needs attention before generating.",
        "can_generate": False,
    }
```

Then merge it into the returned dict in `CodexNativeAuthStore.status`.

```python
readiness = _generation_readiness(configured, token_present, state)
return {
    "provider": PROVIDER_ID,
    "display_name": DISPLAY_NAME,
    "auth_mode": AUTH_MODE,
    "optional": True,
    "configured": configured,
    "authenticated": token_present,
    "available": available,
    "state": state,
    "reason": reason,
    **readiness,
    "features": {
        "text_to_image": available,
        "text_reference_to_image": available,
        "image_edit": available,
    },
    "orchestrator_models": codex_orchestrator_models(),
    "default_orchestrator_model": codex_orchestrator_models()[0],
    "image_models": codex_image_models(),
    "default_image_model": codex_image_models()[0],
    "token_present": token_present,
    "account_id": account_id,
    "auth_store_path": str(self.path),
}
```

In `backend/routers/generation_providers.py`, add the fields to manual upload.

```python
{
    "provider": "manual_upload",
    "display_name": "Manual upload",
    "optional": False,
    "configured": True,
    "authenticated": True,
    "available": True,
    "state": "available",
    "reason": None,
    "status": "ready",
    "message": None,
    "can_generate": True,
    "features": {
        "text_to_image": False,
        "text_reference_to_image": False,
        "image_edit": False,
        "manual_result_upload": True,
    },
}
```

- [ ] **Step 4: Add frontend types and demo payload fields**

In `frontend/src/types.ts`, change `GenerationProviderStatus`.

```ts
export interface GenerationProviderStatus {
  provider: string;
  display_name: string;
  auth_mode?: string;
  optional: boolean;
  configured: boolean;
  authenticated: boolean;
  available: boolean;
  state: string;
  status?: 'ready' | 'unavailable' | 'login_required' | 'auth_error';
  message?: string | null;
  can_generate?: boolean;
  reason?: string | null;
  features: GenerationProviderFeatures;
  token_present?: boolean;
  account_id?: string | null;
  auth_store_path?: string;
  orchestrator_models?: string[];
  default_orchestrator_model?: string;
  image_models?: string[];
  default_image_model?: string;
}
```

In `frontend/src/api/client.ts`, add equivalent fields to demo `generationProviders` objects.

```ts
status: 'unavailable',
message: 'Generation requires a local install.',
can_generate: false,
```

- [ ] **Step 5: Add static frontend contract assertions**

Add to `tests/test_frontend_static.py`.

```python
def test_generation_provider_status_has_readiness_contract():
    types = (ROOT / "frontend" / "src" / "types.ts").read_text()
    api = (ROOT / "frontend" / "src" / "api" / "client.ts").read_text()

    assert "status?: 'ready' | 'unavailable' | 'login_required' | 'auth_error'" in types
    assert "can_generate?: boolean" in types
    assert "message?: string | null" in types
    assert "can_generate:" in api
```

- [ ] **Step 6: Run tests and commit**

Run:

```bash
pytest tests/test_openai_codex_native.py::test_codex_native_status_exposes_generation_readiness_fields tests/test_openai_codex_native.py::test_codex_native_missing_login_maps_to_login_required tests/test_openai_codex_native.py::test_generation_providers_manual_upload_is_always_generation_ready tests/test_frontend_static.py::test_generation_provider_status_has_readiness_contract -q
```

Expected: PASS.

Commit:

```bash
git add backend/services/openai_codex_native.py backend/routers/generation_providers.py frontend/src/types.ts frontend/src/api/client.ts tests/test_openai_codex_native.py tests/test_frontend_static.py
git commit -m "feat: clarify generation provider readiness"
```

---

### Task 2: Stale Timeout, Recovery, Retry, And Cancel Coverage

**Files:**
- Modify: `backend/services/generation_jobs.py`
- Test: `tests/test_generation_jobs.py` or existing generation job test file if present
- Test: `tests/test_openai_codex_native.py`

**Interfaces:**
- Produces constant value:
  - `STALE_RUNNING_JOB_AFTER = timedelta(minutes=10)`
- Produces stale error:
  - `STALE_RUNNING_JOB_ERROR = "Generation took too long and may have stalled. Retry to run it again."`
- Consumes existing methods:
  - `GenerationJobRepository.mark_stale_running_failed(job_id: str) -> GenerationJobRecord`
  - `GenerationJobRepository.retry_failed_job(job_id: str) -> GenerationJobRecord`
  - `GenerationJobRepository.cancel_job(job_id: str) -> GenerationJobRecord`
  - `recover_interrupted_generation_jobs(library_path: Path | str, provider: str = PROVIDER_ID) -> list[GenerationJobRecord]`

- [ ] **Step 1: Locate or create the generation job test file**

Run:

```bash
rg -n "mark_stale_running_failed|retry_failed_job|recover_interrupted_generation_jobs|cancel_job" tests
```

Expected: identify an existing generation job test file. If no focused file exists, create `tests/test_generation_jobs.py`.

- [ ] **Step 2: Write stale timeout and retry tests**

Add these tests to the chosen test file.

```python
from datetime import datetime, timedelta, timezone

from backend.db import connect
from backend.schemas import GenerationJobCreate
from backend.services.generation_jobs import GenerationJobConflict, GenerationJobRepository


def _make_running_job(tmp_path, *, started_minutes_ago: int):
    repo = GenerationJobRepository(tmp_path / "library")
    job = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="stale prompt"))
    running = repo.mark_running(job.id)
    started = (datetime.now(timezone.utc) - timedelta(minutes=started_minutes_ago)).isoformat()
    with connect(tmp_path / "library") as conn:
        conn.execute(
            "UPDATE generation_jobs SET started_at=?, updated_at=? WHERE id=?",
            (started, started, running.id),
        )
        conn.commit()
    return repo, running.id


def test_running_generation_job_is_not_stale_before_ten_minutes(tmp_path):
    repo, job_id = _make_running_job(tmp_path, started_minutes_ago=9)

    try:
        repo.mark_stale_running_failed(job_id)
    except GenerationJobConflict as exc:
        assert "not stale yet" in str(exc)
    else:
        raise AssertionError("Expected job to remain running before ten minutes")


def test_stale_running_generation_job_fails_with_retryable_message(tmp_path):
    repo, job_id = _make_running_job(tmp_path, started_minutes_ago=11)

    failed = repo.mark_stale_running_failed(job_id)
    retry = repo.retry_failed_job(job_id)

    assert failed.status == "failed"
    assert failed.error == "Generation took too long and may have stalled. Retry to run it again."
    assert failed.metadata["stale_running_marked_failed"] is True
    assert failed.metadata["stale_running_threshold_minutes"] == 10
    assert retry.status == "queued"
    assert retry.metadata["retry_of_generation_job_id"] == job_id


def test_queued_and_running_generation_jobs_can_be_cancelled(tmp_path):
    repo = GenerationJobRepository(tmp_path / "library")
    queued = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="queued"))
    running = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="running"))
    repo.mark_running(running.id)

    assert repo.cancel_job(queued.id).status == "cancelled"
    assert repo.cancel_job(running.id).status == "cancelled"
```

- [ ] **Step 3: Write restart recovery verification test**

Add this test to the same file.

```python
def test_recover_interrupted_generation_jobs_marks_only_provider_running_failed(tmp_path):
    from backend.services.generation_queue import INTERRUPTED_BY_BACKEND_RESTART_ERROR, recover_interrupted_generation_jobs
    from backend.services.openai_codex_native import PROVIDER_ID

    repo = GenerationJobRepository(tmp_path / "library")
    running_provider = repo.create_job(GenerationJobCreate(provider=PROVIDER_ID, prompt_text="provider running"))
    queued_provider = repo.create_job(GenerationJobCreate(provider=PROVIDER_ID, prompt_text="provider queued"))
    running_manual = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="manual running"))
    repo.mark_running(running_provider.id)
    repo.mark_running(running_manual.id)

    recovered = recover_interrupted_generation_jobs(tmp_path / "library")

    assert [job.id for job in recovered] == [running_provider.id]
    assert repo.get_job(running_provider.id).status == "failed"
    assert repo.get_job(running_provider.id).error == INTERRUPTED_BY_BACKEND_RESTART_ERROR
    assert repo.get_job(queued_provider.id).status == "queued"
    assert repo.get_job(running_manual.id).status == "running"
```

- [ ] **Step 4: Run tests and verify they fail before implementation**

Run:

```bash
pytest tests/test_generation_jobs.py -q
```

Expected: stale threshold test FAILS because current code uses 30 minutes and old stale error copy. Existing retry/cancel/recovery tests may already pass.

- [ ] **Step 5: Implement the timeout and message change**

In `backend/services/generation_jobs.py`, change only these constants.

```python
STALE_RUNNING_JOB_AFTER = timedelta(minutes=10)
STALE_RUNNING_JOB_ERROR = "Generation took too long and may have stalled. Retry to run it again."
```

- [ ] **Step 6: Run tests and commit**

Run:

```bash
pytest tests/test_generation_jobs.py -q
pytest tests/test_openai_codex_native.py -q
```

Expected: PASS.

Commit:

```bash
git add backend/services/generation_jobs.py tests/test_generation_jobs.py tests/test_openai_codex_native.py
git commit -m "test: cover generation stale retry and recovery"
```

---

### Task 3: Frontend Provider And Settings Hardening

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/GenerationPanel.tsx`
- Modify: `frontend/src/styles.css`
- Test: `tests/test_frontend_static.py`

**Interfaces:**
- Consumes `GenerationProviderStatus.status`, `message`, and `can_generate`.
- Produces helper behavior:
  - generation availability uses `provider.can_generate ?? provider.available && provider.authenticated && provider.configured`
  - selected unavailable provider blocks submit
  - provider readiness copy is visible in `GenerationPanel`
  - model/quality/aspect/attachment controls remain visible before submit

- [ ] **Step 1: Write frontend static tests for provider readiness and settings**

Add to `tests/test_frontend_static.py`.

```python
def test_generation_panel_surfaces_provider_readiness_and_blocks_unavailable_submit():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    panel = (ROOT / "frontend" / "src" / "components" / "GenerationPanel.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()

    assert "provider.can_generate ??" in app
    assert "providerReadinessLabel" in panel
    assert "selectedProviderCanGenerate" in panel
    assert "selectedProviderMessage" in panel
    assert "disabled={busy || !selectedProviderCanGenerate || !promptText.trim() || hasMissingTemplateValues}" in panel
    assert "generation-provider-readiness" in panel
    assert "generation-provider-readiness" in css
    assert "generation-control-value" in panel
    assert "generation-attach-trigger" in panel
```

- [ ] **Step 2: Run static test and verify it fails**

Run:

```bash
pytest tests/test_frontend_static.py::test_generation_panel_surfaces_provider_readiness_and_blocks_unavailable_submit -q
```

Expected: FAIL with missing helper strings.

- [ ] **Step 3: Harden `App.tsx` provider availability helper**

Change the existing `generationProviderConnected` helper in `frontend/src/App.tsx` to:

```ts
function generationProviderConnected(provider: GenerationProviderStatus) {
  return provider.can_generate ?? Boolean(provider.available && provider.authenticated && provider.configured);
}
```

- [ ] **Step 4: Add readiness helpers to `GenerationPanel.tsx`**

Add near `providerReady`.

```ts
function providerCanGenerate(provider?: GenerationProviderStatus) {
  if (!provider) return false;
  return provider.can_generate ?? providerReady(provider);
}

function providerReadinessLabel(provider?: GenerationProviderStatus) {
  if (!provider) return 'Provider unavailable';
  if (providerCanGenerate(provider)) return `${provider.display_name} ready`;
  if (provider.message) return provider.message;
  if (provider.status === 'login_required' || provider.state === 'not_connected') return `Connect ${provider.display_name} before generating.`;
  if (provider.status === 'auth_error') return `${provider.display_name} needs attention before generating.`;
  return `${provider.display_name} is unavailable.`;
}
```

Add these memo values after `selectedProvider`.

```ts
const selectedProviderCanGenerate = providerCanGenerate(selectedProvider);
const selectedProviderMessage = providerReadinessLabel(selectedProvider);
```

Update `createJob`.

```ts
if (!prompt || hasMissingTemplateValues || !resolvedPrompt || !selectedProviderCanGenerate) return;
```

Update the primary Generate button.

```tsx
<button className="primary generation-primary-action" onClick={createJob} disabled={busy || !selectedProviderCanGenerate || !promptText.trim() || hasMissingTemplateValues}>Generate</button>
```

Render provider readiness inside `.generation-compact-controls`, before the primary action.

```tsx
<span className={`generation-provider-readiness ${selectedProviderCanGenerate ? 'is-ready' : 'needs-attention'}`}>
  {selectedProviderMessage}
</span>
```

- [ ] **Step 5: Add minimal CSS for readiness wrapping**

Add to `frontend/src/styles.css` near generation controls.

```css
.generation-provider-readiness {
  min-width: 0;
  max-width: 220px;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.25;
  overflow-wrap: anywhere;
}
.generation-provider-readiness.is-ready { color: #2f7d51; }
.generation-provider-readiness.needs-attention { color: #9a4b16; }
```

In the existing mobile media block for generation controls, add:

```css
.generation-provider-readiness {
  flex: 1 1 100%;
  max-width: 100%;
}
```

- [ ] **Step 6: Run checks and commit**

Run:

```bash
pytest tests/test_frontend_static.py::test_generation_panel_surfaces_provider_readiness_and_blocks_unavailable_submit -q
npm run build
```

Expected: PASS and successful build.

Commit:

```bash
git add frontend/src/App.tsx frontend/src/components/GenerationPanel.tsx frontend/src/styles.css tests/test_frontend_static.py
git commit -m "feat: clarify generation provider readiness in UI"
```

---

### Task 4: Frontend Queue, Stale, And Retry Clarity

**Files:**
- Modify: `frontend/src/components/GenerationPanel.tsx`
- Modify: `frontend/src/components/GenerationQueueDrawer.tsx`
- Modify: `frontend/src/styles.css`
- Test: `tests/test_frontend_static.py`

**Interfaces:**
- Consumes backend stale threshold of 10 minutes.
- Produces UI constant:
  - `STALE_RUNNING_JOB_MS = 10 * 60 * 1000`
- Produces stale text:
  - `Generation may have stalled.`
  - `Mark failed to retry.`
- Keeps retry behavior through existing `api.retryGenerationJob` and `api.markGenerationJobFailed`.

- [ ] **Step 1: Write static tests for 10-minute stale UI and clear queue labels**

Add to `tests/test_frontend_static.py`.

```python
def test_generation_frontend_uses_ten_minute_stale_threshold_and_clear_retry_copy():
    panel = (ROOT / "frontend" / "src" / "components" / "GenerationPanel.tsx").read_text()
    drawer = (ROOT / "frontend" / "src" / "components" / "GenerationQueueDrawer.tsx").read_text()
    css = (ROOT / "frontend" / "src" / "styles.css").read_text()

    assert "const STALE_RUNNING_JOB_MS = 10 * 60 * 1000" in panel
    assert "const STALE_RUNNING_JOB_MS = 10 * 60 * 1000" in drawer
    assert "Generation may have stalled." in panel
    assert "Mark failed to retry." in panel
    assert "Generation may have stalled" in drawer
    assert "Retry failed job" in drawer
    assert "generation-stale-copy" in css
```

- [ ] **Step 2: Run static test and verify it fails**

Run:

```bash
pytest tests/test_frontend_static.py::test_generation_frontend_uses_ten_minute_stale_threshold_and_clear_retry_copy -q
```

Expected: FAIL because constants still use 30 minutes and copy is missing.

- [ ] **Step 3: Update stale timeout constants**

In both `frontend/src/components/GenerationPanel.tsx` and `frontend/src/components/GenerationQueueDrawer.tsx`, change:

```ts
const STALE_RUNNING_JOB_MS = 10 * 60 * 1000;
```

- [ ] **Step 4: Add stale copy in `GenerationPanel.tsx`**

Inside the stale running branch in `renderStage`, above the stale action button, add:

```tsx
<p className="generation-stale-copy">Generation may have stalled. Mark failed to retry.</p>
```

Keep the existing `api.markGenerationJobFailed` call path.

- [ ] **Step 5: Add stale copy and retry titles in `GenerationQueueDrawer.tsx`**

In the row action area, when `isStaleRunningJob(job)` is true, render:

```tsx
<em className="generation-stale-copy">Generation may have stalled</em>
```

Add titles and aria-labels to queue action buttons.

```tsx
aria-label="Retry failed job"
title="Retry failed job"
```

For mark failed:

```tsx
aria-label="Mark stalled generation failed"
title="Mark failed to retry"
```

- [ ] **Step 6: Add minimal CSS**

Add to `frontend/src/styles.css`.

```css
.generation-stale-copy {
  margin: 0;
  color: #9a4b16;
  font-size: 12px;
  line-height: 1.3;
  overflow-wrap: anywhere;
}
```

- [ ] **Step 7: Run checks and commit**

Run:

```bash
pytest tests/test_frontend_static.py::test_generation_frontend_uses_ten_minute_stale_threshold_and_clear_retry_copy tests/test_frontend_static.py::test_mobile_generation_queue_trigger_stays_clear_of_bottom_fabs -q
npm run build
```

Expected: PASS and successful build.

Commit:

```bash
git add frontend/src/components/GenerationPanel.tsx frontend/src/components/GenerationQueueDrawer.tsx frontend/src/styles.css tests/test_frontend_static.py
git commit -m "feat: clarify generation stale and retry states"
```

---

### Task 5: Full Verification And Live QA Record

**Files:**
- Create: `docs/qa/2026-07-08-generation-hardening-live-qa.md`
- Modify only if QA finds issues: files from earlier tasks

**Interfaces:**
- Consumes completed tasks 1-4.
- Produces QA evidence:
  - automated command output summary
  - desktop viewport result
  - mobile viewport result
  - OAuth status result
  - one live generation attempt result

- [ ] **Step 1: Run the full automated checks**

Run:

```bash
pytest -q
npm run build
```

Expected: Python tests PASS and frontend build succeeds.

- [ ] **Step 2: Start the local app for QA**

Use the repo's existing local run command. If the README or scripts specify a command, use that exact command. Otherwise use the previously working local dev command for this repo.

Expected: local app is reachable in a browser.

- [ ] **Step 3: Desktop visual QA**

At desktop viewport `1440x900`, verify and record:

```md
- Provider readiness visible before generation.
- Model, quality, aspect ratio, and attachment controls visible.
- Generate button is disabled when provider cannot generate.
- Queue drawer opens and shows queued/running/ready/failed sections.
- No floating controls overlap Config, Cleanup, Generate, or queue actions.
```

- [ ] **Step 4: Mobile visual QA**

At mobile viewport `390x844`, verify and record:

```md
- Provider readiness wraps without covering buttons.
- Model text truncates or wraps cleanly.
- Queue drawer is usable.
- Stale/retry/cancel actions fit.
- Floating controls do not overlap core actions.
```

- [ ] **Step 5: Live OAuth and full generation QA**

Use the authenticated provider path. Record:

```md
- OAuth/session status:
- Provider status:
- Prompt used:
- Settings used:
- Observed job flow:
- Result:
- If failed, user-facing error:
- Retry/recovery behavior observed:
```

A live generation failure is acceptable only when auth/provider state is detected correctly, the error is clear, and retry/recovery remains usable.

- [ ] **Step 6: Write the QA record**

Create `docs/qa/2026-07-08-generation-hardening-live-qa.md`.

```md
# Generation Hardening Live QA

Date: 2026-07-08

## Automated Checks

- `pytest -q`: PASS
- `npm run build`: PASS

## Desktop Visual QA

- Viewport: 1440x900
- Provider readiness:
- Settings controls:
- Queue drawer:
- Result actions:
- Overlap check:
- Screenshot:

## Mobile Visual QA

- Viewport: 390x844
- Provider readiness:
- Settings controls:
- Queue drawer:
- Stale/retry/cancel actions:
- Overlap check:
- Screenshot:

## Live OAuth / Generation QA

- Provider:
- OAuth/session:
- Prompt:
- Settings:
- Job flow:
- Result:
- Failure message, if any:
- Retry/recovery:

## Release Gate

- Automated tests passed:
- Desktop QA recorded:
- Mobile QA recorded:
- Live provider QA recorded:
```

- [ ] **Step 7: Fix only QA-blocking issues**

If visual or live QA finds a blocker, write the narrow failing check first when practical, fix the smallest affected file, rerun the relevant check, and update the QA record.

- [ ] **Step 8: Final full check and commit**

Run:

```bash
pytest -q
npm run build
git status --short
```

Expected: tests/build PASS, only intended files modified before commit.

Commit:

```bash
git add docs/qa/2026-07-08-generation-hardening-live-qa.md
git commit -m "docs: record generation hardening qa"
```

If QA-blocking code fixes were needed, include those exact files in the same commit only when they are inseparable from the QA result; otherwise commit them separately before the QA record.

---

## Plan Self-Review

- Spec coverage: provider readiness is Task 1 and Task 3; lifecycle retry/cancel/recovery is Task 2; model/settings UI is Task 3; stale timeout is Task 2 and Task 4; desktop/mobile/live QA is Task 5.
- Scope check: no queue rewrite, no new provider, no batch generation endpoint, no auto-retry.
- Completion marker scan: no incomplete markers or intentionally vague implementation slots remain.
- Type consistency: backend fields `status`, `message`, and `can_generate` match the TypeScript optional fields and frontend helpers.
