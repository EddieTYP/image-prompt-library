# Batch 4.7 Generation Workflow Polish Implementation Plan

> **For Hermes:** Use test-driven-development and systematic-debugging skills while implementing this plan. Keep public demo read-only; generation remains local-only.

**Goal:** Improve generation as a first-class workflow: separate Add/Generate entry points, editable metadata before saving a generated result as a new item, mobile Generate variant access, a compact visual work queue drawer, and clearer failed-generation UX.

**Architecture:** Keep the current GenerationJob/result-inbox model. Add a reusable generation panel that supports either an existing source item or a standalone prompt. Add a global work queue drawer in `App.tsx` that polls/list jobs and uses icons/badges instead of verbose text. Extend `accept-as-new-item` with optional metadata overrides so the frontend can show a focused review/edit panel before item creation while preserving provenance.

**Tech Stack:** FastAPI + Pydantic + SQLite backend; React/Vite/TypeScript frontend; static frontend tests plus backend pytest; browser QA on local non-demo app.

---

## Requirements

1. Add a separate local-only `Generate` entrance beside/near `Add`.
2. `Save as new item` must open a metadata review/edit panel before creating the item.
3. Mobile item detail must expose `Generate variant`.
4. Active/finished generation should be visible from a compact visual work queue drawer; avoid text like `1 generating` as primary UI.
5. Failed generation should show friendly categories:
   - policy/refusal
   - rate limit / too frequent
   - auth/provider unavailable
   - generic failure
6. Public demo must remain read-only and not expose generation controls.
7. Preserve provenance metadata even when the user edits title/collection/prompt/notes before save-as-new.

---

## Task 1: Backend metadata override for save-as-new

**Objective:** Allow `POST /api/generation-jobs/{job_id}/accept-as-new-item` to receive optional item metadata.

**Files:**
- Modify: `backend/schemas.py`
- Modify: `backend/services/generation_jobs.py`
- Modify: `backend/routers/generation_jobs.py`
- Test: `tests/test_generation_jobs.py`

**Steps:**
1. Add `GenerationJobAcceptAsNewItemRequest` schema with optional `title`, `cluster_name`, `tags`, `prompts`, `model`, `source_name`, `source_url`, `author`, `notes`.
2. Write failing pytest proving overrides are used and provenance still includes `kind`, `source_item_id`, `source_generation_job_id`, `provider`, `model`, `mode`, `parameters`.
3. Implement service method parameter `overrides`.
4. Router accepts JSON body default `{}`.
5. Run targeted pytest.

---

## Task 2: Friendly generation error classification

**Objective:** Normalize raw backend/provider errors into frontend-safe categories without leaking secrets.

**Files:**
- Modify: `backend/services/generation_jobs.py`
- Test: `tests/test_generation_jobs.py`
- Modify: `frontend/src/components/GenerationPanel.tsx`

**Steps:**
1. Add tests for policy-like error and rate-limit-like error using `mark_failed`.
2. Store classification in `job.metadata.error_kind` while keeping redacted `job.error`.
3. Add frontend helper that maps `error_kind` / error text to friendly title + guidance.
4. Show retry guidance on failed job cards.

---

## Task 3: Save-as-new metadata review panel

**Objective:** Replace instant save-as-new with a focused review form.

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/components/GenerationPanel.tsx`
- Modify: `frontend/src/styles.css`
- Test: `tests/test_frontend_static.py`

**Steps:**
1. Add TS type for accept-as-new metadata payload.
2. Update API client to pass optional payload.
3. Add static tests for strings/classes: `save-new-metadata-panel`, `Save generated image as new item`, `Review metadata`, `api.acceptGenerationJobAsNewItem(job.id, metadataPayload)`, `readonly-provenance`.
4. Implement panel with title, collection, prompt language/text, model, source, author, notes, tags string, result image preview, readonly provenance block.
5. Confirm button posts payload; cancel returns to result card.

---

## Task 4: Standalone Generate entrance

**Objective:** Add local-only Generate entry beside Add that creates a standalone generation job from scratch.

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/GenerationPanel.tsx`
- Modify: `frontend/src/styles.css`
- Test: `tests/test_frontend_static.py`

**Steps:**
1. Make `GenerationPanel` accept optional `item`; when absent, title is `Generate image`, source item is omitted, default prompt is blank, and save-as-new is the primary accept path.
2. Add local-only `[Add] [Generate]` floating actions / action rail in `App.tsx`.
3. Static tests verify demo mode hides standalone Generate.
4. Standalone jobs can be reviewed in the same result inbox and saved as new via metadata panel.

---

## Task 5: Mobile Generate variant affordance

**Objective:** Ensure mobile detail has a visible Generate action.

**Files:**
- Modify: `frontend/src/components/ItemDetailModal.tsx`
- Modify: `frontend/src/styles.css`
- Test: `tests/test_frontend_static.py`

**Steps:**
1. Add `mobile-generate-variant-button` inside mobile hero primary actions or sticky mobile action row.
2. Static test verifies the button opens `setGenerationOpen(true)` and CSS displays on mobile.
3. Keep public/demo mutation controls hidden.

---

## Task 6: Global work queue drawer

**Objective:** Add a compact visual generation work queue drawer for active/succeeded/failed jobs.

**Files:**
- Create: `frontend/src/components/GenerationQueueDrawer.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Test: `tests/test_frontend_static.py`

**Steps:**
1. Add component polling/listing generation jobs using `api.generationJobs({ limit: 50 })`.
2. Add compact queue trigger button with icon/badges/dots, not text-first `1 generating`.
3. Drawer sections: running/queued, ready for review, failed, recent accepted/discarded.
4. Clicking a source-item job opens item detail where applicable; standalone jobs are reviewable from drawer.
5. Public/demo mode hides queue trigger.

---

## Task 7: Verification and LAN QA

**Commands:**

```bash
pytest tests/test_generation_jobs.py tests/test_frontend_static.py -q
npm run build
pytest -q
python -m compileall -q backend scripts
git diff --check
```

**Browser QA:**
1. Start backend on non-8787 port, preferably `8001`.
2. Start frontend non-demo on `5178`.
3. Verify Add and Generate separate controls.
4. Verify mobile-width detail exposes Generate variant.
5. Create/stage a succeeded job and verify Save as new opens metadata panel, edits persist.
6. Verify queue drawer shows visual active/ready/failed indicators without primary verbose count text.
7. Verify failed policy/rate-limit messages are friendly.
8. Verify browser console has 0 JS errors.

---

## Acceptance criteria

- Backend metadata override tests pass.
- Frontend static tests pass for all new UI affordances.
- Build and full pytest pass.
- Browser QA confirms local non-demo flow.
- Commit is created locally; push only if Edward asks.

---

## Revisit note: Generation tab layout polish

Captured for a later design pass; do not implement until we revisit the direction.

### Problem

The current Generation tab works functionally, but it feels too rough/debug-panel-like. The issue is mainly information hierarchy and visual rhythm rather than missing core capability.

### Preferred direction

Use a clearer creative-workspace layout:

1. **Desktop two-column layout**
   - Left column: composer card for creating a new image.
   - Right column: result workbench / active and recent jobs.

2. **Composer card hierarchy**
   - Prompt textarea is the primary focus.
   - Secondary settings sit below the prompt in a compact row:
     - Aspect ratio dropdown.
     - Quality dropdown, if exposed.
   - Primary action: `Generate`.
   - Provider status should be compact, e.g. `ChatGPT connected`, not a large technical block.

3. **Result workbench**
   - Show current running job, ready-to-review results, failures, and recent jobs as compact cards.
   - Result review should own the save actions:
     - `Save as new`.
     - `Attach to existing`.
     - `Discard`.
   - Metadata/provenance should be visible during review but not dominate the composer.

4. **Mobile layout**
   - Keep a single-column card flow:
     - Header.
     - Composer card.
     - Active job compact card.
     - Result inbox cards.
   - Avoid cramped controls; keep aspect ratio / quality compact.

### Avoid for now

- Heavy wizard flow.
- Photoshop-like editor sidebars.
- Always-visible provider/debug metadata.
- Too many collapsible advanced panels.

### Product framing

Generation should feel like a lightweight creative entry point plus result inbox inside the prompt library, not a separate full image studio.
