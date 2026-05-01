from __future__ import annotations

import hashlib
import base64
import binascii
import json
from pathlib import Path

from PIL import Image

from backend.db import connect, init_db
from backend.repositories import ItemRepository, StoredImageInput, new_id, now
from backend.schemas import (
    GenerationJobAcceptAsNewItemRequest,
    GenerationJobAcceptResult,
    GenerationJobCreate,
    GenerationJobList,
    GenerationJobRecord,
    GenerationJobRetryResult,
    ItemCreate,
    PromptIn,
)
from backend.services.image_store import store_image


class GenerationJobConflict(ValueError):
    pass


MAX_GENERATION_INPUT_IMAGES = 4


def _to_json(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _from_json(raw: str | None, fallback):
    if not raw:
        return fallback
    try:
        parsed = json.loads(raw)
        return parsed if parsed is not None else fallback
    except json.JSONDecodeError:
        return fallback


def _classify_error(message: str) -> str:
    lowered = (message or "").lower()
    if any(term in lowered for term in ("policy", "safety", "refus", "not allowed", "violat")):
        return "policy_violation"
    if any(term in lowered for term in ("rate limit", "too many", "slow down", "retry later", "429")):
        return "rate_limited"
    if any(term in lowered for term in ("auth", "login", "token", "credential", "unauthorized", "forbidden", "401", "403")):
        return "auth_required"
    if any(term in lowered for term in ("unavailable", "timeout", "temporarily", "503", "502")):
        return "provider_unavailable"
    return "unknown"


def _redact_error(error: str) -> str:
    message = str(error or "Generation failed")
    for marker in ("Bearer ", "access_token", "refresh_token"):
        if marker in message:
            return "Generation failed; provider returned a credential-related error"
    return message[:1000]


class GenerationJobRepository:

    def __init__(self, library_path: Path | str):
        self.library_path = Path(library_path)
        init_db(self.library_path)
        self.items = ItemRepository(self.library_path)

    def create_job(self, payload: GenerationJobCreate) -> GenerationJobRecord:
        if payload.source_item_id:
            self.items.get_item(payload.source_item_id)
        input_images = payload.parameters.get("input_images") if isinstance(payload.parameters, dict) else None
        if isinstance(input_images, list) and len(input_images) > MAX_GENERATION_INPUT_IMAGES:
            raise GenerationJobConflict(f"Generation edit supports up to {MAX_GENERATION_INPUT_IMAGES} input images")
        job_id = new_id("gen")
        timestamp = now()
        with connect(self.library_path) as conn:
            conn.execute(
                """
                INSERT INTO generation_jobs(
                    id, source_item_id, mode, provider, model, status, prompt_language,
                    prompt_text, edited_prompt_text, reference_image_ids, parameters,
                    metadata, created_at, updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    job_id,
                    payload.source_item_id,
                    payload.mode,
                    payload.provider,
                    payload.model,
                    "queued",
                    payload.prompt_language,
                    payload.prompt_text,
                    payload.edited_prompt_text,
                    _to_json(payload.reference_image_ids),
                    _to_json(payload.parameters),
                    "{}",
                    timestamp,
                    timestamp,
                ),
            )
            conn.commit()
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> GenerationJobRecord:
        with connect(self.library_path) as conn:
            row = conn.execute("SELECT * FROM generation_jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return self._record_from_row(row)

    def list_jobs(self, *, status: str | None = None, limit: int = 100, offset: int = 0) -> GenerationJobList:
        where = "WHERE status=?" if status else ""
        params: list[object] = [status] if status else []
        with connect(self.library_path) as conn:
            total = conn.execute(f"SELECT COUNT(*) FROM generation_jobs {where}", params).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM generation_jobs {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (*params, limit, offset),
            ).fetchall()
        return GenerationJobList(jobs=[self._record_from_row(row) for row in rows], total=total, limit=limit, offset=offset)

    def mark_running(self, job_id: str) -> GenerationJobRecord:
        timestamp = now()
        with connect(self.library_path) as conn:
            cursor = conn.execute(
                """
                UPDATE generation_jobs
                SET status='running', error=NULL, started_at=COALESCE(started_at, ?), updated_at=?
                WHERE id=? AND status IN ('queued', 'failed')
                """,
                (timestamp, timestamp, job_id),
            )
            conn.commit()
        if cursor.rowcount != 1:
            current = self.get_job(job_id)
            raise GenerationJobConflict(f"Generation job must be queued or failed before run; current status is {current.status}")
        return self.get_job(job_id)

    def mark_failed(self, job_id: str, error: str) -> GenerationJobRecord:
        timestamp = now()
        redacted_error = _redact_error(error)
        existing = self.get_job(job_id)
        metadata = dict(existing.metadata or {})
        metadata["error_kind"] = _classify_error(redacted_error)
        with connect(self.library_path) as conn:
            conn.execute(
                """
                UPDATE generation_jobs
                SET status='failed', error=?, metadata=?, updated_at=?, completed_at=?
                WHERE id=? AND status NOT IN ('accepted', 'discarded', 'cancelled')
                """,
                (redacted_error, _to_json(metadata), timestamp, timestamp, job_id),
            )
            conn.commit()
        return self.get_job(job_id)

    def stage_result(self, job_id: str, data: bytes, filename: str, metadata: dict | None = None) -> GenerationJobRecord:
        job = self.get_job(job_id)
        if job.status in {"accepted", "discarded", "cancelled"}:
            raise GenerationJobConflict("Generation job is already finalized")
        suffix = Path(filename).suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
            suffix = ".png"
        sha = hashlib.sha256(data).hexdigest()
        result_rel = Path("generation-results") / job_id / f"result-{sha[:12]}{suffix}"
        result_abs = self.library_path / result_rel
        result_abs.parent.mkdir(parents=True, exist_ok=True)
        result_abs.write_bytes(data)
        width = None
        height = None
        try:
            with Image.open(result_abs) as image:
                width, height = image.size
        except Exception:
            result_abs.unlink(missing_ok=True)
            raise
        timestamp = now()
        with connect(self.library_path) as conn:
            cursor = conn.execute(
                """
                UPDATE generation_jobs
                SET status='succeeded', result_path=?, result_width=?, result_height=?, result_sha256=?,
                    metadata=?, error=NULL, updated_at=?, completed_at=?
                WHERE id=? AND status NOT IN ('accepted', 'discarded', 'cancelled')
                """,
                (result_rel.as_posix(), width, height, sha, _to_json(metadata or {}), timestamp, timestamp, job_id),
            )
            conn.commit()
        if cursor.rowcount != 1:
            result_abs.unlink(missing_ok=True)
            current = self.get_job(job_id)
            raise GenerationJobConflict(f"Generation job is already finalized with status {current.status}")
        return self.get_job(job_id)

    def _store_result_image(self, job: GenerationJobRecord):
        result_abs = self.library_path / (job.result_path or "")
        if not result_abs.is_file():
            raise GenerationJobConflict("Generation result file is missing")
        return store_image(self.library_path, result_abs.read_bytes(), Path(job.result_path or "generated.png").name)

    def _input_image_specs(self, job: GenerationJobRecord) -> list[dict]:
        raw_images = job.parameters.get("input_images") if isinstance(job.parameters, dict) else None
        if not isinstance(raw_images, list):
            return []
        return [raw for raw in raw_images[:MAX_GENERATION_INPUT_IMAGES] if isinstance(raw, dict)]

    def _store_input_reference_images(self, job: GenerationJobRecord, item_id: str) -> None:
        for index, spec in enumerate(self._input_image_specs(job)):
            name = str(spec.get("name") or f"generation-reference-{index + 1}.png")
            data: bytes | None = None
            result_path = spec.get("result_path")
            if isinstance(result_path, str) and result_path:
                source_path = self.library_path / result_path
                if source_path.is_file():
                    data = source_path.read_bytes()
                    name = Path(result_path).name
            data_url = spec.get("data_url")
            if data is None and isinstance(data_url, str) and data_url.startswith("data:image/"):
                _, _, encoded = data_url.partition(",")
                try:
                    data = base64.b64decode(encoded, validate=True)
                except (binascii.Error, ValueError):
                    data = None
            if not data:
                continue
            stored = store_image(self.library_path, data, name)
            self.items.add_image(
                item_id,
                StoredImageInput(
                    original_path=stored.original_path,
                    thumb_path=stored.thumb_path,
                    preview_path=stored.preview_path,
                    width=stored.width,
                    height=stored.height,
                    file_sha256=stored.file_sha256,
                    role="reference_image",
                ),
            )

    def _mark_accepted(self, job_id: str, image_id: str) -> GenerationJobRecord:
        timestamp = now()
        with connect(self.library_path) as conn:
            conn.execute(
                "UPDATE generation_jobs SET status='accepted', accepted_image_id=?, accepted_at=?, updated_at=? WHERE id=?",
                (image_id, timestamp, timestamp, job_id),
            )
            conn.commit()
        return self.get_job(job_id)

    def accept_result(self, job_id: str) -> GenerationJobAcceptResult:
        job = self.get_job(job_id)
        if not job.source_item_id:
            raise GenerationJobConflict("Generation job has no source item to attach to")
        if job.status != "succeeded" or not job.result_path:
            raise GenerationJobConflict("Generation job must be succeeded before accept")
        stored = self._store_result_image(job)
        image = self.items.add_image(
            job.source_item_id,
            StoredImageInput(
                original_path=stored.original_path,
                thumb_path=stored.thumb_path,
                preview_path=stored.preview_path,
                width=stored.width,
                height=stored.height,
                file_sha256=stored.file_sha256,
                role="result_image",
            ),
        )
        self._store_input_reference_images(job, job.source_item_id)
        return GenerationJobAcceptResult(job=self._mark_accepted(job_id, image.id), item=self.items.get_item(job.source_item_id))

    def accept_result_as_new_item(self, job_id: str, overrides: GenerationJobAcceptAsNewItemRequest | None = None) -> GenerationJobAcceptResult:
        job = self.get_job(job_id)
        if job.status != "succeeded" or not job.result_path:
            raise GenerationJobConflict("Generation job must be succeeded before accept")
        source_item = self.items.get_item(job.source_item_id) if job.source_item_id else None
        prompt_text = (job.edited_prompt_text or job.prompt_text).strip()
        if not prompt_text:
            raise GenerationJobConflict("Generation job has no prompt text for a new item")
        overrides = overrides or GenerationJobAcceptAsNewItemRequest()
        provenance = {
            "kind": "generation_variant" if job.source_item_id else "generation_standalone",
            "source_language": job.prompt_language or "en",
            "source_item_id": job.source_item_id,
            "source_generation_job_id": job.id,
            "provider": job.provider,
            "model": job.model,
            "mode": job.mode,
            "parameters": job.parameters,
        }
        if overrides.prompts:
            prompts = []
            for index, prompt in enumerate(overrides.prompts):
                prompt_provenance = dict(prompt.provenance or {})
                prompt_provenance.update(provenance)
                prompts.append(PromptIn(
                    language=prompt.language,
                    text=prompt.text,
                    is_primary=prompt.is_primary or index == 0,
                    is_original=prompt.is_original or index == 0,
                    provenance=prompt_provenance,
                ))
        else:
            prompts = [PromptIn(
                language=job.prompt_language or "en",
                text=prompt_text,
                is_primary=True,
                is_original=True,
                provenance=provenance,
            )]
        default_title = f"{source_item.title} Variant" if source_item else "Generated image"
        default_notes = f"Variant generated from item {job.source_item_id} via GenerationJob {job.id}." if source_item else f"Generated via GenerationJob {job.id}."
        new_item = self.items.create_item(ItemCreate(
            title=(overrides.title or default_title).strip() or default_title,
            model=overrides.model or job.model or (source_item.model if source_item else "ChatGPT Image2"),
            source_name=overrides.source_name if overrides.source_name is not None else "Generation variant",
            source_url=overrides.source_url if overrides.source_url is not None else (source_item.source_url if source_item else None),
            author=overrides.author if overrides.author is not None else (source_item.author if source_item else None),
            cluster_id=None if overrides.cluster_name else (source_item.cluster.id if source_item and source_item.cluster else None),
            cluster_name=overrides.cluster_name,
            tags=overrides.tags if overrides.tags is not None else ([tag.name for tag in source_item.tags] if source_item else []),
            prompts=prompts,
            notes=overrides.notes if overrides.notes is not None else default_notes,
        ))
        stored = self._store_result_image(job)
        image = self.items.add_image(
            new_item.id,
            StoredImageInput(
                original_path=stored.original_path,
                thumb_path=stored.thumb_path,
                preview_path=stored.preview_path,
                width=stored.width,
                height=stored.height,
                file_sha256=stored.file_sha256,
                role="result_image",
            ),
        )
        self._store_input_reference_images(job, new_item.id)
        return GenerationJobAcceptResult(job=self._mark_accepted(job_id, image.id), item=self.items.get_item(new_item.id))

    def discard_job(self, job_id: str) -> GenerationJobRecord:
        job = self.get_job(job_id)
        if job.status == "accepted":
            raise GenerationJobConflict("Accepted generation jobs cannot be discarded")
        timestamp = now()
        with connect(self.library_path) as conn:
            conn.execute(
                "UPDATE generation_jobs SET status='discarded', discarded_at=?, updated_at=? WHERE id=?",
                (timestamp, timestamp, job_id),
            )
            conn.commit()
        return self.get_job(job_id)

    def discard_and_retry_job(self, job_id: str) -> GenerationJobRetryResult:
        job = self.get_job(job_id)
        if job.status == "accepted" or job.accepted_image_id:
            raise GenerationJobConflict("Saved generation jobs cannot be retried. Create a variant instead.")
        if job.status != "succeeded" or not job.result_path:
            raise GenerationJobConflict("Only unsaved ready generation results can be retried")
        retry_id = new_id("gen")
        timestamp = now()
        retry_metadata = {
            "retry_of_generation_job_id": job.id,
            "retry_reason": "discard_and_retry",
        }
        discarded_metadata = dict(job.metadata or {})
        discarded_metadata["retried_by_generation_job_id"] = retry_id
        with connect(self.library_path) as conn:
            conn.execute(
                """
                UPDATE generation_jobs
                SET status='discarded', metadata=?, discarded_at=?, updated_at=?
                WHERE id=? AND status='succeeded' AND accepted_image_id IS NULL
                """,
                (_to_json(discarded_metadata), timestamp, timestamp, job.id),
            )
            conn.execute(
                """
                INSERT INTO generation_jobs(
                    id, source_item_id, mode, provider, model, status, prompt_language,
                    prompt_text, edited_prompt_text, reference_image_ids, parameters,
                    metadata, created_at, updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    retry_id,
                    job.source_item_id,
                    job.mode,
                    job.provider,
                    job.model,
                    "queued",
                    job.prompt_language,
                    job.prompt_text,
                    job.edited_prompt_text,
                    _to_json(job.reference_image_ids),
                    _to_json(job.parameters),
                    _to_json(retry_metadata),
                    timestamp,
                    timestamp,
                ),
            )
            conn.commit()
        return GenerationJobRetryResult(discarded_job=self.get_job(job.id), retry_job=self.get_job(retry_id))

    def cancel_job(self, job_id: str) -> GenerationJobRecord:
        job = self.get_job(job_id)
        if job.status not in {"queued", "running"}:
            raise GenerationJobConflict(f"Only queued or running generation jobs can be cancelled; current status is {job.status}")
        timestamp = now()
        with connect(self.library_path) as conn:
            cursor = conn.execute(
                """
                UPDATE generation_jobs
                SET status='cancelled', cancelled_at=?, completed_at=?, updated_at=?
                WHERE id=? AND status IN ('queued', 'running')
                """,
                (timestamp, timestamp, timestamp, job_id),
            )
            conn.commit()
        if cursor.rowcount != 1:
            current = self.get_job(job_id)
            raise GenerationJobConflict(f"Only queued or running generation jobs can be cancelled; current status is {current.status}")
        return self.get_job(job_id)

    def next_queued_provider_jobs(self, provider: str, *, limit: int) -> list[GenerationJobRecord]:
        with connect(self.library_path) as conn:
            rows = conn.execute(
                """
                SELECT * FROM generation_jobs
                WHERE provider=? AND status='queued'
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (provider, limit),
            ).fetchall()
        return [self._record_from_row(row) for row in rows]

    def _record_from_row(self, row) -> GenerationJobRecord:
        data = dict(row)
        data["reference_image_ids"] = [str(value) for value in _from_json(data.get("reference_image_ids"), [])]
        params = _from_json(data.get("parameters"), {})
        meta = _from_json(data.get("metadata"), {})
        data["parameters"] = params if isinstance(params, dict) else {}
        data["metadata"] = meta if isinstance(meta, dict) else {}
        return GenerationJobRecord(**data)
