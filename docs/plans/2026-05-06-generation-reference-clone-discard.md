# Generation Reference Clone + Discard UX Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Keep generated queue results disposable even when they are used as inputs for later edits/generations, while preserving saved library items and existing referenced data safely.

**Architecture:** Introduce backend clone-on-reference for generation-result inputs. New generation/edit jobs must copy any `generation-results/{source_job_id}/...` input into a downstream job-owned reference file before storing the job, so the source result can still be discarded. Existing user data is repaired lazily: if discard finds old references to a transient generation result, backend attempts to clone those references away before deleting the original result.

**Tech Stack:** FastAPI backend, SQLite JSON/text fields, local media files under the library path, Vite/React frontend, pytest + static frontend assertions.

---

## Current Findings

Relevant files:

- `backend/services/generation_jobs.py`
  - `create_job()` currently inserts `payload.parameters` and `payload.reference_image_ids` as-is.
  - `stage_result()` writes queue outputs to `generation-results/{job_id}/result-{sha}.{ext}`.
  - `_input_image_specs()` reads `job.parameters["input_images"]`.
  - `_store_input_reference_images()` currently copies input image bytes into library item images when accepting a generated result.
  - `_result_path_has_library_references()` blocks discard if:
    - `images.original_path/thumb_path/preview_path` equals the job result path; or
    - another `generation_jobs.parameters` JSON string contains the job result path.
  - `discard_job()` currently rejects referenced results with: `Generation result is referenced by library data and cannot be discarded`.
- `frontend/src/components/GenerationQueueDrawer.tsx`
  - queue quick discard is optimistic.
  - frontend treats succeeded, unaccepted, `generation-results/{job.id}/...` results as discardable.
- `tests/test_generation_jobs.py`
  - existing coverage for stage/accept/discard/retry lives here.
- `tests/test_frontend_static.py`
  - static expectations for queue quick discard live here.

## Implementation Guardrails for Codex Spark

Follow these constraints exactly. They exist to avoid data loss and to prevent the implementation from drifting into a risky migration.

### Supported `parameters.input_images` shape

The only reference-input shape this plan requires handling is a dict inside `generation_jobs.parameters["input_images"]` with a generation result path:

```json
{
  "result_path": "generation-results/gen_source/result-abc123.png",
  "name": "source.png"
}
```

After clone-on-reference, the downstream job must store the cloned path while preserving provenance:

```json
{
  "result_path": "generation-references/gen_downstream/from-gen_source-abc123.png",
  "name": "source.png",
  "source_result_path": "generation-results/gen_source/result-abc123.png",
  "source_generation_job_id": "gen_source",
  "cloned_from_generation_result": true
}
```

The downstream job metadata must also record `reference_image_copies` entries:

```json
{
  "reference_image_copies": [
    {
      "source_generation_job_id": "gen_source",
      "source_result_path": "generation-results/gen_source/result-abc123.png",
      "copied_path": "generation-references/gen_downstream/from-gen_source-abc123.png",
      "sha256": "..."
    }
  ]
}
```

Do not invent alternate field names unless an existing type/test requires it.

### Reference repair boundary

Lazy repair may rewrite only:

- `generation_jobs.parameters.input_images[].result_path`
- the same job's `generation_jobs.metadata`

Lazy repair must **not** rewrite rows in the `images` table. `images.original_path`, `images.thumb_path`, and `images.preview_path` represent saved/library-owned data. If an `images` row points at the source generation result, treat the source result as saved/protected and do not discard it.

### Idempotency and deletion safety

Clone/repair must be idempotent and safe:

- Clone path must be deterministic enough to avoid duplicate copies on retry: include downstream job id, source job id, and source sha prefix.
- If the clone file already exists with the same hash, reuse it.
- If the clone file already exists with a different hash, abort with a conflict; do not overwrite.
- Always copy first, then update DB references, then re-check references.
- Delete the original generation result only after:
  - no `images` table row references it; and
  - no other `generation_jobs.parameters` still contains the original result path.
- Never delete the original before clone verification.

### Migration policy

Do not add install-time or startup bulk migration. Existing users are handled only through lazy repair during discard.

Do not add a broad repair command in this implementation unless Edward explicitly asks later. The plan mentions it only as a possible future maintainer tool.

### Documentation boundary

Do not update public README/release docs in this implementation unless explicitly asked. This is implementation work first; public release notes can be prepared separately.

### Commit and testing discipline

Use strict TDD for behavior changes:

1. Add failing test.
2. Run it and confirm expected failure.
3. Implement minimal code.
4. Run targeted test to pass.
5. Run wider test/build commands.

Prefer small commits:

- backend clone/repair tests + implementation
- frontend saved/protected UX tests + implementation, only if frontend changes are needed

## Product Decision

User-facing model:

- A queue result that has not been explicitly accepted/saved should remain discardable.
- Using a queue result as an edit/reference input should not make the original queue result protected.
- When a generation result is used as a reference, the downstream generation owns a clone of that image.
- Saved/accepted generation jobs remain protected and should show `Saved`/disabled discard in UI if surfaced.
- Existing libraries must not be bulk-rewritten on install/update. Repair legacy references lazily during discard.

Non-goals for this implementation:

- No install-time bulk migration.
- No public docs claiming future syntax before shipped.
- No destructive deletion before references are cloned and verified.
- No schema migration unless implementation proves metadata-only tracking is insufficient.

---

## Task 1: Add a failing backend test for clone-on-reference at job creation

**Objective:** Prove a new generation job clones any input image spec that points at an earlier `generation-results/...` file, so the original source job is still discardable.

**Files:**

- Modify: `tests/test_generation_jobs.py`
- Later modify: `backend/services/generation_jobs.py`

**Step 1: Write failing test**

Add a test near existing generation job tests:

```python
def test_generation_job_clones_generation_result_inputs_so_source_stays_discardable(tmp_path, monkeypatch):
    c = client(tmp_path)
    enqueue_calls = []

    def fake_enqueue(library_path, *, provider):
        enqueue_calls.append((Path(library_path), provider))

    monkeypatch.setattr("backend.routers.generation_jobs.enqueue_generation_jobs", fake_enqueue)

    source = c.post("/api/generation-jobs", json={
        "provider": "manual_upload",
        "prompt_text": "first draft",
    }).json()
    c.post(
        f"/api/generation-jobs/{source['id']}/result",
        files={"file": ("source.png", png_bytes("blue"), "image/png")},
    )
    source = c.get(f"/api/generation-jobs/{source['id']}").json()
    source_path = source["result_path"]

    downstream = c.post("/api/generation-jobs", json={
        "provider": "manual_upload",
        "prompt_text": "refine first draft",
        "parameters": {
            "input_images": [{"result_path": source_path, "name": "source.png"}],
        },
    }).json()

    cloned_input = downstream["parameters"]["input_images"][0]
    assert cloned_input["result_path"] != source_path
    assert cloned_input["result_path"].startswith(f"generation-references/{downstream['id']}/")
    assert (tmp_path / "library" / cloned_input["result_path"]).is_file()
    assert (tmp_path / "library" / cloned_input["result_path"]).read_bytes() == (tmp_path / "library" / source_path).read_bytes()
    assert downstream["metadata"]["reference_image_copies"][0]["source_generation_job_id"] == source["id"]
    assert downstream["metadata"]["reference_image_copies"][0]["source_result_path"] == source_path
    assert downstream["metadata"]["reference_image_copies"][0]["copied_path"] == cloned_input["result_path"]

    discard = c.post(f"/api/generation-jobs/{source['id']}/discard")
    assert discard.status_code == 200
    assert discard.json()["status"] == "discarded"
    assert not (tmp_path / "library" / source_path).exists()
    assert (tmp_path / "library" / cloned_input["result_path"]).is_file()
```

**Step 2: Run RED**

Run:

```bash
python -m pytest tests/test_generation_jobs.py::test_generation_job_clones_generation_result_inputs_so_source_stays_discardable -q
```

Expected: FAIL because `create_job()` currently stores the original `result_path` unchanged and the source discard is blocked.

---

## Task 2: Implement clone-on-reference during `create_job()`

**Objective:** Clone generation-result input image specs into a downstream job-owned folder before the job is inserted.

**Files:**

- Modify: `backend/services/generation_jobs.py`

**Design details:**

Add helper functions inside `GenerationJobRepository`:

```python
def _is_generation_result_path(self, value: str) -> bool:
    path = Path(value)
    return (
        not path.is_absolute()
        and ".." not in path.parts
        and len(path.parts) >= 3
        and path.parts[0] == "generation-results"
    )
```

```python
def _clone_generation_result_input(self, *, job_id: str, result_path: str, name: str | None = None) -> tuple[str, dict] | None:
    if not self._is_generation_result_path(result_path):
        return None
    source_rel = Path(result_path)
    source_abs = (self.library_path / source_rel).resolve()
    library_abs = self.library_path.resolve()
    if not source_abs.is_file() or library_abs not in source_abs.parents:
        return None
    data = source_abs.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    suffix = source_rel.suffix.lower() or Path(name or "reference.png").suffix.lower() or ".png"
    if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        suffix = ".png"
    source_job_id = source_rel.parts[1]
    dest_rel = Path("generation-references") / job_id / f"from-{source_job_id}-{sha[:12]}{suffix}"
    dest_abs = self.library_path / dest_rel
    dest_abs.parent.mkdir(parents=True, exist_ok=True)
    if dest_abs.exists():
        if hashlib.sha256(dest_abs.read_bytes()).hexdigest() != sha:
            raise GenerationJobConflict("Reference clone path collision")
    else:
        dest_abs.write_bytes(data)
    copy_meta = {
        "source_generation_job_id": source_job_id,
        "source_result_path": source_rel.as_posix(),
        "copied_path": dest_rel.as_posix(),
        "sha256": sha,
    }
    return dest_rel.as_posix(), copy_meta
```

Add a payload preparation helper:

```python
def _prepare_reference_input_clones(self, job_id: str, parameters: dict) -> tuple[dict, list[dict]]:
    prepared = dict(parameters or {})
    raw_images = prepared.get("input_images")
    if not isinstance(raw_images, list):
        return prepared, []
    cloned_specs = []
    copy_metadata = []
    for raw in raw_images:
        if not isinstance(raw, dict):
            cloned_specs.append(raw)
            continue
        spec = dict(raw)
        result_path = spec.get("result_path")
        if isinstance(result_path, str) and result_path:
            clone = self._clone_generation_result_input(job_id=job_id, result_path=result_path, name=str(spec.get("name") or ""))
            if clone is not None:
                copied_path, meta = clone
                spec["result_path"] = copied_path
                spec["source_result_path"] = result_path
                spec["source_generation_job_id"] = meta["source_generation_job_id"]
                spec["cloned_from_generation_result"] = True
                copy_metadata.append(meta)
        cloned_specs.append(spec)
    prepared["input_images"] = cloned_specs
    return prepared, copy_metadata
```

Update `create_job()`:

1. Generate `job_id` before preparing parameters (already true).
2. Copy `payload.parameters` into a mutable dict.
3. Validate `input_images` count before or after clone; count should remain the same.
4. Call `_prepare_reference_input_clones(job_id, parameters)`.
5. Store prepared parameters in DB.
6. Store metadata with `reference_image_copies` when non-empty.

Pseudo-change:

```python
parameters = dict(payload.parameters or {})
input_images = parameters.get("input_images")
if isinstance(input_images, list) and len(input_images) > MAX_GENERATION_INPUT_IMAGES:
    raise GenerationJobConflict(...)
parameters, reference_image_copies = self._prepare_reference_input_clones(job_id, parameters)
metadata = {"reference_image_copies": reference_image_copies} if reference_image_copies else {}
```

Use `_to_json(parameters)` and `_to_json(metadata)` in the insert.

**Step 3: Run GREEN**

Run:

```bash
python -m pytest tests/test_generation_jobs.py::test_generation_job_clones_generation_result_inputs_so_source_stays_discardable -q
```

Expected: PASS.

---

## Task 3: Add a failing backend test for lazy repair of legacy generation-job references

**Objective:** Prove existing jobs that already reference an old generation result path can be repaired during discard.

**Files:**

- Modify: `tests/test_generation_jobs.py`
- Later modify: `backend/services/generation_jobs.py`

**Step 1: Write failing test**

Create the source job first. Then insert or update a downstream job to simulate pre-clone legacy data by manually writing the old `source_path` into `generation_jobs.parameters`.

```python
def test_discard_lazily_repairs_legacy_generation_job_references(tmp_path, monkeypatch):
    c = client(tmp_path)
    monkeypatch.setattr("backend.routers.generation_jobs.enqueue_generation_jobs", lambda library_path, *, provider: None)

    source = c.post("/api/generation-jobs", json={"provider": "manual_upload", "prompt_text": "legacy source"}).json()
    c.post(f"/api/generation-jobs/{source['id']}/result", files={"file": ("source.png", png_bytes("blue"), "image/png")})
    source = c.get(f"/api/generation-jobs/{source['id']}").json()
    source_path = source["result_path"]

    downstream = c.post("/api/generation-jobs", json={"provider": "manual_upload", "prompt_text": "legacy downstream"}).json()
    legacy_parameters = {"input_images": [{"result_path": source_path, "name": "legacy-source.png"}]}
    with connect(tmp_path / "library") as conn:
        conn.execute("UPDATE generation_jobs SET parameters=? WHERE id=?", (json.dumps(legacy_parameters), downstream["id"]))
        conn.commit()

    response = c.post(f"/api/generation-jobs/{source['id']}/discard")

    assert response.status_code == 200
    discarded = response.json()
    assert discarded["status"] == "discarded"
    assert not (tmp_path / "library" / source_path).exists()

    repaired = c.get(f"/api/generation-jobs/{downstream['id']}").json()
    repaired_spec = repaired["parameters"]["input_images"][0]
    assert repaired_spec["result_path"] != source_path
    assert repaired_spec["result_path"].startswith(f"generation-references/{downstream['id']}/")
    assert (tmp_path / "library" / repaired_spec["result_path"]).is_file()
    assert repaired["metadata"]["reference_image_copies"][0]["source_result_path"] == source_path
    assert repaired["metadata"]["reference_image_repair"]["repaired_from_discard_job_id"] == source["id"]
```

Remember to import `json` at the top of the test file if needed.

**Step 2: Run RED**

Run:

```bash
python -m pytest tests/test_generation_jobs.py::test_discard_lazily_repairs_legacy_generation_job_references -q
```

Expected: FAIL because `discard_job()` still rejects referenced results.

---

## Task 4: Implement lazy repair for legacy generation-job parameter references

**Objective:** Before rejecting discard due to generation-job parameter references, clone those references into each downstream job and rewrite its parameters/metadata.

**Files:**

- Modify: `backend/services/generation_jobs.py`

**Implementation notes:**

Split `_result_path_has_library_references()` into more specific helpers:

```python
def _result_path_has_item_image_references(self, result_path: str) -> bool: ...
def _generation_jobs_referencing_result_path(self, job: GenerationJobRecord) -> list[GenerationJobRecord]: ...
```

For lazy repair:

```python
def _repair_generation_job_references_to_result(self, job: GenerationJobRecord) -> int:
    if not job.result_path:
        return 0
    downstream_jobs = self._generation_jobs_referencing_result_path(job)
    repaired_count = 0
    for downstream in downstream_jobs:
        parameters = dict(downstream.parameters or {})
        raw_images = parameters.get("input_images")
        if not isinstance(raw_images, list):
            continue
        changed = False
        copy_metadata = []
        new_images = []
        for raw in raw_images:
            if not isinstance(raw, dict):
                new_images.append(raw)
                continue
            spec = dict(raw)
            if spec.get("result_path") == job.result_path:
                clone = self._clone_generation_result_input(job_id=downstream.id, result_path=job.result_path, name=str(spec.get("name") or ""))
                if clone is None:
                    new_images.append(spec)
                    continue
                copied_path, meta = clone
                spec["result_path"] = copied_path
                spec["source_result_path"] = job.result_path
                spec["source_generation_job_id"] = job.id
                spec["cloned_from_generation_result"] = True
                copy_metadata.append(meta)
                changed = True
            new_images.append(spec)
        if changed:
            parameters["input_images"] = new_images
            metadata = dict(downstream.metadata or {})
            metadata.setdefault("reference_image_copies", [])
            metadata["reference_image_copies"].extend(copy_metadata)
            metadata["reference_image_repair"] = {
                "repaired_from_discard_job_id": job.id,
                "source_result_path": job.result_path,
                "repaired_at": now(),
            }
            with connect(self.library_path) as conn:
                conn.execute(
                    "UPDATE generation_jobs SET parameters=?, metadata=?, updated_at=? WHERE id=?",
                    (_to_json(parameters), _to_json(metadata), now(), downstream.id),
                )
                conn.commit()
            repaired_count += 1
    return repaired_count
```

Update `discard_job()` flow:

```python
if self._result_path_has_item_image_references(job.result_path):
    raise GenerationJobConflict("Generation result is saved to library data and cannot be discarded")
self._repair_generation_job_references_to_result(job)
if self._generation_jobs_referencing_result_path(job):
    raise GenerationJobConflict("Generation result is still used as a generation reference and cannot be discarded")
```

Important:

- Do not repair accepted/saved source jobs. Existing early `accepted_image_id` guard remains.
- Do not delete original until after re-query confirms no generation job parameters still reference `job.result_path`.
- Keep `images` table references protected; those are accepted/saved library images, not transient edit references.

**Step 3: Run GREEN**

Run:

```bash
python -m pytest tests/test_generation_jobs.py::test_discard_lazily_repairs_legacy_generation_job_references -q
```

Expected: PASS.

---

## Task 5: Add a test that saved/accepted library references remain protected

**Objective:** Ensure lazy repair never makes explicitly saved results discardable.

**Files:**

- Modify: `tests/test_generation_jobs.py`

**Step 1: Write test**

Add/extend coverage:

```python
def test_discard_keeps_saved_generation_results_protected(tmp_path):
    c = client(tmp_path)
    source_item = create_source_item(c)
    saved = c.post("/api/generation-jobs", json={
        "source_item_id": source_item["id"],
        "provider": "manual_upload",
        "prompt_text": "saved source",
    }).json()
    c.post(f"/api/generation-jobs/{saved['id']}/result", files={"file": ("saved.png", png_bytes("blue"), "image/png")})
    c.post(f"/api/generation-jobs/{saved['id']}/accept")

    response = c.post(f"/api/generation-jobs/{saved['id']}/discard")

    assert response.status_code == 409
    assert "Accepted generation jobs cannot be discarded" in response.json()["detail"]
```

**Step 2: Run**

Run:

```bash
python -m pytest tests/test_generation_jobs.py::test_discard_keeps_saved_generation_results_protected -q
```

Expected: PASS if existing guard remains intact.

---

## Task 6: Add a frontend static test for Saved/protected UI semantics

**Objective:** Queue UI should not label generation-reference use as `Saved`; `Saved` is only for accepted jobs. Transient succeeded cards remain discardable.

**Files:**

- Modify: `tests/test_frontend_static.py`
- Later modify: `frontend/src/components/GenerationQueueDrawer.tsx`
- Later modify: `frontend/src/styles.css` if visual badge/disabled button is added

**Recommended UI behavior:**

- `isSavedGenerationResult(job)` returns `job.status === 'accepted' || Boolean(job.accepted_image_id)`.
- Accepted jobs in Recent can show `Saved` and a disabled discard state if a discard affordance is ever shown there.
- Ready/succeeded transient jobs keep active trash.
- Do not add `Used as ref` as a permanent blocking state for new data; clone-on-reference should remove that need.
- If lazy repair fails due to true saved `images` table references, catch error and restore optimistic card, then mark local metadata with a protected reason and show a small `Saved` or `Protected` label depending on message.

**Step 1: Add static expectations**

Add expectations such as:

```python
assert "function isSavedGenerationResult" in queue
assert "job.status === 'accepted' || Boolean(job.accepted_image_id)" in queue
assert "result_protected_reason" in queue
assert "Saved" in queue
assert "Used as ref" not in queue  # optional if we choose not to ship this label
```

**Step 2: Run RED**

```bash
python -m pytest tests/test_frontend_static.py::test_generation_work_queue_and_standalone_generate_entry_are_local_only -q
```

Expected: FAIL until UI helper/labels are added.

---

## Task 7: Update frontend protected-error handling without blocking normal trash

**Objective:** If backend still returns a true protected/saved conflict, restore optimistic card and show an explanatory disabled state/label instead of leaving repeated click errors.

**Files:**

- Modify: `frontend/src/components/GenerationQueueDrawer.tsx`
- Modify: `frontend/src/styles.css`
- Test: `tests/test_frontend_static.py`

**Implementation shape:**

Add helpers:

```tsx
function isSavedGenerationResult(job: GenerationJobRecord) {
  return job.status === 'accepted' || Boolean(job.accepted_image_id);
}

function protectedResultReason(job: GenerationJobRecord) {
  const value = job.metadata?.result_protected_reason;
  return typeof value === 'string' ? value : '';
}
```

In discard catch:

```tsx
const message = error instanceof Error ? error.message : 'Could not discard generation result.';
const protectedReason = message.includes('saved to library') || message.includes('referenced by library data')
  ? 'saved'
  : '';
setJobs(current => current.map(candidate => candidate.id === job.id ? {
  ...job,
  metadata: protectedReason ? { ...(job.metadata || {}), result_protected_reason: protectedReason } : job.metadata,
} : candidate));
setLoadError(message);
```

Render small label if saved/protected:

```tsx
{(isSavedGenerationResult(job) || protectedResultReason(job) === 'saved') && (
  <span className="generation-queue-result-badge">Saved</span>
)}
```

Do not disable active trash for normal transient jobs. Disable/omit trash only when `!canDiscardTransientResult(job)` or protected reason exists.

**Verification:**

Run:

```bash
python -m pytest tests/test_frontend_static.py::test_generation_work_queue_and_standalone_generate_entry_are_local_only -q
npm run build
```

---

## Task 8: Full backend/frontend verification

**Objective:** Ensure no regressions in generation queue, retry, discard, accept, and frontend build.

**Commands:**

```bash
python -m pytest tests/test_generation_jobs.py -q
python -m pytest tests/test_frontend_static.py -q
python -m pytest -q
npm run build
python -m compileall -q backend scripts
git diff --check
```

Expected:

- `tests/test_generation_jobs.py`: PASS
- `tests/test_frontend_static.py`: PASS
- full suite: PASS (current baseline: 195 tests before this feature)
- build/compile/diff: PASS

---

## Task 9: Browser QA with real clone/discard flow

**Objective:** Prove user-facing behavior in the browser.

**Setup:**

Use temporary ports, not live 7500:

- Backend: `127.0.0.1:8044`
- Frontend: `127.0.0.1:5194`
- Temporary library path under `/tmp/ipl-reference-clone-qa.*`

Seed data:

1. Create generation result A via manual upload.
2. Create generation B with `parameters.input_images[0].result_path` pointing to A.
3. Confirm backend stored B input as `generation-references/{B}/...`.
4. Open queue drawer.
5. Click A trash.
6. Confirm A card disappears immediately.
7. Confirm B cloned reference file still exists.
8. Confirm console JS errors = 0.

**Verification expressions:**

- `document.querySelectorAll('.generation-queue-result.status-succeeded').length` drops within two animation frames.
- `/api/generation-jobs/{B}` parameters show cloned `generation-references/{B}/...` path.

---

## Task 10: Commit and ship

**Objective:** Keep commits reviewable and deploy live frontend only after tests/CI pass.

**Commit sequence:**

Preferred commits:

```bash
git add tests/test_generation_jobs.py backend/services/generation_jobs.py
git commit -m "fix: clone generation result references"

git add tests/test_frontend_static.py frontend/src/components/GenerationQueueDrawer.tsx frontend/src/styles.css
git commit -m "fix: clarify saved generation discard state"
```

Push:

```bash
git push origin main
```

Watch CI:

```bash
gh run list --branch main --limit 4 --json databaseId,workflowName,status,conclusion,displayTitle,headSha
gh run watch <CI_RUN_ID> --exit-status
gh run watch <PAGES_RUN_ID> --exit-status
```

If clean and CI passes, hot-update live 7500 frontend assets if frontend changed:

```bash
LIVE=/Users/edwardtsoi/.image-prompt-library/app/current
mkdir -p "$LIVE/frontend/dist"
cp -R frontend/dist/. "$LIVE/frontend/dist/"
```

Verify live:

```bash
python - <<'PY'
import json, re, urllib.request
base='http://127.0.0.1:7500'
with urllib.request.urlopen(base+'/api/health', timeout=5) as r:
    health=json.load(r)
html=urllib.request.urlopen(base+'/', timeout=5).read().decode()
print({'health': health, 'assets': re.findall(r'/assets/index-[^"<>]+', html)})
PY
```

Note: live install may still report `v0.7.2-beta` if only frontend assets are hot-patched; state that clearly.

---

## Acceptance Criteria

- New generation/edit jobs clone generation-result input images into `generation-references/{new_job_id}/...`.
- Source queue results remain discardable after being used as downstream edit references.
- Lazy repair lets old generation-job parameter references be cloned away during discard.
- Accepted/saved jobs remain protected and cannot be discarded.
- No install-time bulk migration.
- No physical result file is deleted until reference checks pass after clone/repair.
- Tests and build pass.
- Browser QA confirms immediate discard UI and preserved downstream reference clone.
