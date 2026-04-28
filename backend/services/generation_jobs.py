from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image

from backend.db import connect, init_db
from backend.repositories import ItemRepository, StoredImageInput, new_id, now
from backend.schemas import (
    GenerationJobAcceptResult,
    GenerationJobCreate,
    GenerationJobList,
    GenerationJobRecord,
)
from backend.services.image_store import store_image


class GenerationJobConflict(ValueError):
    pass


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


class GenerationJobRepository:
    def __init__(self, library_path: Path | str):
        self.library_path = Path(library_path)
        init_db(self.library_path)
        self.items = ItemRepository(self.library_path)

    def create_job(self, payload: GenerationJobCreate) -> GenerationJobRecord:
        if payload.source_item_id:
            self.items.get_item(payload.source_item_id)
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

    def stage_result(self, job_id: str, data: bytes, filename: str, metadata: dict | None = None) -> GenerationJobRecord:
        job = self.get_job(job_id)
        if job.status in {"accepted", "discarded"}:
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
        with Image.open(result_abs) as image:
            width, height = image.size
        timestamp = now()
        with connect(self.library_path) as conn:
            conn.execute(
                """
                UPDATE generation_jobs
                SET status='succeeded', result_path=?, result_width=?, result_height=?, result_sha256=?,
                    metadata=?, updated_at=?, completed_at=?
                WHERE id=?
                """,
                (result_rel.as_posix(), width, height, sha, _to_json(metadata or {}), timestamp, timestamp, job_id),
            )
            conn.commit()
        return self.get_job(job_id)

    def accept_result(self, job_id: str) -> GenerationJobAcceptResult:
        job = self.get_job(job_id)
        if not job.source_item_id:
            raise GenerationJobConflict("Generation job has no source item to attach to")
        if job.status != "succeeded" or not job.result_path:
            raise GenerationJobConflict("Generation job must be succeeded before accept")
        result_abs = self.library_path / job.result_path
        if not result_abs.is_file():
            raise GenerationJobConflict("Generation result file is missing")
        stored = store_image(self.library_path, result_abs.read_bytes(), Path(job.result_path).name)
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
        timestamp = now()
        with connect(self.library_path) as conn:
            conn.execute(
                "UPDATE generation_jobs SET status='accepted', accepted_image_id=?, accepted_at=?, updated_at=? WHERE id=?",
                (image.id, timestamp, timestamp, job_id),
            )
            conn.commit()
        return GenerationJobAcceptResult(job=self.get_job(job_id), item=self.items.get_item(job.source_item_id))

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

    def _record_from_row(self, row) -> GenerationJobRecord:
        data = dict(row)
        data["reference_image_ids"] = [str(value) for value in _from_json(data.get("reference_image_ids"), [])]
        params = _from_json(data.get("parameters"), {})
        meta = _from_json(data.get("metadata"), {})
        data["parameters"] = params if isinstance(params, dict) else {}
        data["metadata"] = meta if isinstance(meta, dict) else {}
        return GenerationJobRecord(**data)
