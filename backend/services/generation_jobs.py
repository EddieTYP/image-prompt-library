from __future__ import annotations

import hashlib
import base64
import binascii
import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from contextlib import suppress
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from backend.config import resolve_library_storage_path
from backend.db import connect, init_db
from backend.repositories import ItemRepository, StoredImageInput, new_id, now
from backend.schemas import (
    GenerationJobAcceptAsNewItemRequest,
    GenerationJobAcceptResult,
    GenerationJobCreate,
    GenerationJobList,
    GenerationJobRecord,
    GenerationJobSetRecord,
    GenerationJobRetryResult,
    GenerationProviderQueueState,
    ItemCreate,
    PromptIn,
)
from backend.services.image_store import MAX_IMAGE_PIXELS, store_image


class GenerationJobConflict(ValueError):
    pass


MAX_GENERATION_INPUT_IMAGES = 4
STALE_RUNNING_JOB_AFTER = timedelta(minutes=10)
STALE_RUNNING_JOB_ERROR = "Generation took too long and may have stalled. Retry to run it again."
GENERATION_RESULT_ROOT = "generation-results"
GENERATION_REFERENCE_ROOT = "generation-references"
GENERATION_INPUT_IMAGE_ROOTS = {GENERATION_RESULT_ROOT, GENERATION_REFERENCE_ROOT}


def _verify_image_file(path: Path) -> str:
    try:
        with Image.open(path) as image:
            image_format = image.format
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise GenerationJobConflict("Generation edit input image is invalid") from exc
    return Image.MIME.get(image_format or "", "image/png")


def _validate_storeable_image_bytes(data: bytes) -> None:
    try:
        with Image.open(BytesIO(data)) as image:
            width, height = image.size
            if width * height > MAX_IMAGE_PIXELS:
                raise GenerationJobConflict(f"Generation image is too large: {width}x{height}")
            image.verify()
    except GenerationJobConflict:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise GenerationJobConflict("Generation image is invalid") from exc


def _ensure_resolved_child(path: Path, parent: Path) -> None:
    try:
        path.relative_to(parent)
    except ValueError as exc:
        raise GenerationJobConflict("Generation image path is invalid") from exc


def _reject_symlink_path_components(base: Path, relative_path: Path, *, message: str) -> None:
    current = base
    for part in relative_path.parts:
        current = current / part
        if current.is_symlink():
            raise GenerationJobConflict(message)


def resolve_generation_write_path(
    library_path: Path | str,
    relative_path: str,
    *,
    allowed_root: str,
) -> Path:
    rel = Path(relative_path)
    if not relative_path or rel.is_absolute() or ".." in rel.parts or len(rel.parts) < 3 or rel.parts[0] != allowed_root:
        raise GenerationJobConflict("Generation image path is invalid")
    library_abs = Path(library_path).resolve()
    root_path = library_abs / allowed_root
    if root_path.is_symlink():
        raise GenerationJobConflict("Generation image path is invalid")
    _reject_symlink_path_components(library_abs, rel.parent, message="Generation image path is invalid")
    try:
        root_abs = resolve_library_storage_path(library_abs, allowed_root)
        dest_abs = resolve_library_storage_path(library_abs, rel)
    except ValueError as exc:
        raise GenerationJobConflict("Generation image path is invalid") from exc
    if dest_abs.is_symlink():
        raise GenerationJobConflict("Generation image path is invalid")
    if dest_abs.exists():
        _ensure_resolved_child(dest_abs.resolve(), root_abs)
    return dest_abs


def resolve_generation_input_image_path(
    library_path: Path | str,
    result_path: str,
    *,
    allowed_roots: set[str] | None = None,
) -> tuple[Path, str]:
    roots = allowed_roots or GENERATION_INPUT_IMAGE_ROOTS
    rel = Path(result_path)
    if not result_path or rel.is_absolute() or ".." in rel.parts or len(rel.parts) < 3 or rel.parts[0] not in roots:
        raise GenerationJobConflict("Generation edit input image path is invalid")
    library_abs = Path(library_path).resolve()
    allowed_root_path = library_abs / rel.parts[0]
    if allowed_root_path.is_symlink():
        raise GenerationJobConflict("Generation edit input image path is invalid")
    _reject_symlink_path_components(library_abs, rel, message="Generation edit input image path is invalid")
    try:
        allowed_root = resolve_library_storage_path(library_abs, rel.parts[0])
        candidate = resolve_library_storage_path(library_abs, rel)
    except ValueError as exc:
        raise GenerationJobConflict("Generation edit input image path is invalid") from exc
    if not candidate.is_file():
        raise GenerationJobConflict("Generation edit input image is missing")
    return candidate, _verify_image_file(candidate)


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
    if any(term in lowered for term in ("rate limit", "rate_limit", "rate-limit", "too many", "slow down", "retry later", "429")):
        return "rate_limited"
    if any(term in lowered for term in ("unavailable", "timeout", "temporarily", "gateway", "500", "502", "503", "504")):
        return "provider_unavailable"
    if any(term in lowered for term in ("policy", "safety", "not allowed", "violat")):
        return "policy_violation"
    if any(term in lowered for term in (
        "auth",
        "login",
        "token",
        "credential",
        "unauthorized",
        "forbidden",
        "permission denied",
        "invalid_grant",
        "invalid grant",
        "api key",
        "api_key",
        "apikey",
        "401",
        "403",
    )) or _contains_sensitive_error_material(message):
        return "auth_required"
    if "refus" in lowered:
        return "policy_violation"
    return "unknown"


_SENSITIVE_ERROR_MARKERS = (
    "bearer",
    "authorization",
    "access_token",
    "refresh_token",
    "id_token",
    "authorization_code",
    "code_verifier",
    "device_auth_id",
    "user_code",
    "api key",
    "api_key",
    "apikey",
    "client secret",
    "client_secret",
    "cookie",
    "session",
    "session token",
    "session_token",
    "session id",
    "session_id",
    "password",
)
_SENSITIVE_ERROR_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b", re.IGNORECASE),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"(?:^|[?&,\s{])[\"']?(?:token|secret|password|key)[\"']?\s*[:=]\s*[\"']?[^\s,;&}\"']+", re.IGNORECASE),
)


def _contains_sensitive_error_material(error: str) -> bool:
    message = str(error or "")
    lowered = message.lower()
    return any(marker in lowered for marker in _SENSITIVE_ERROR_MARKERS) or any(
        pattern.search(message) for pattern in _SENSITIVE_ERROR_PATTERNS
    )


def sanitize_generation_error(error: str) -> str:
    message = str(error or "Generation failed")
    if _contains_sensitive_error_material(message):
        return "Generation failed; provider returned a credential-related error"
    return message[:1000]


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class GenerationJobRepository:

    def __init__(self, library_path: Path | str):
        self.library_path = Path(library_path)
        init_db(self.library_path)
        self.items = ItemRepository(self.library_path)

    def create_job(self, payload: GenerationJobCreate) -> GenerationJobRecord:
        if payload.source_item_id:
            self.items.get_item(payload.source_item_id)
        parameters = dict(payload.parameters or {})
        input_images = parameters.get("input_images")
        if isinstance(input_images, list) and len(input_images) > MAX_GENERATION_INPUT_IMAGES:
            raise GenerationJobConflict(f"Generation edit supports up to {MAX_GENERATION_INPUT_IMAGES} input images")
        job_id = new_id("gen")
        prepared_parameters, library_reference_ids = self._prepare_library_reference_inputs(job_id, parameters)
        prepared_parameters, reference_image_copies = self._prepare_reference_input_clones(job_id, prepared_parameters)
        metadata = {"reference_image_copies": reference_image_copies} if reference_image_copies else {}
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
                    _to_json(library_reference_ids or payload.reference_image_ids),
                    _to_json(prepared_parameters),
                    _to_json(metadata),
                    timestamp,
                    timestamp,
                ),
            )
            conn.commit()
        return self.get_job(job_id)

    def _prepare_library_reference_inputs(self, job_id: str, parameters: dict) -> tuple[dict, list[str]]:
        prepared = dict(parameters or {})
        raw_images = prepared.get("input_images")
        if not isinstance(raw_images, list):
            return prepared, []
        library_reference_ids: list[str] = []
        input_specs = []
        for raw in raw_images:
            if not isinstance(raw, dict):
                input_specs.append(raw)
                continue
            spec = dict(raw)
            image_id = spec.get("image_id")
            if spec.get("source") == "library" or image_id:
                if not isinstance(image_id, str) or not image_id:
                    raise GenerationJobConflict("Library generation reference requires image_id")
                try:
                    image = self.items.get_image(image_id)
                except KeyError as exc:
                    preserved_result_path = spec.get("result_path")
                    if isinstance(preserved_result_path, str) and preserved_result_path:
                        resolve_generation_input_image_path(self.library_path, preserved_result_path)
                        input_specs.append(spec)
                        continue
                    raise GenerationJobConflict("Library generation reference image not found") from exc
                source_path, _ = resolve_generation_input_image_path(
                    self.library_path,
                    image.original_path,
                    allowed_roots={"originals"},
                )
                data = source_path.read_bytes()
                sha = hashlib.sha256(data).hexdigest()
                suffix = Path(image.original_path).suffix.lower()
                if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
                    suffix = ".png"
                copied_rel = Path(GENERATION_REFERENCE_ROOT) / job_id / f"from-library-{image.id}-{sha[:12]}{suffix}"
                copied_path = resolve_generation_write_path(
                    self.library_path,
                    copied_rel.as_posix(),
                    allowed_root=GENERATION_REFERENCE_ROOT,
                )
                copied_path.parent.mkdir(parents=True, exist_ok=True)
                if copied_path.exists() and hashlib.sha256(copied_path.read_bytes()).hexdigest() != sha:
                    raise GenerationJobConflict("Reference clone path collision")
                if not copied_path.exists():
                    copied_path.write_bytes(data)
                spec.update({
                    "source": "library",
                    "image_id": image.id,
                    "source_item_id": image.item_id,
                    "role": image.role,
                    "name": str(spec.get("name") or f"Library image {len(library_reference_ids) + 1}"),
                    "source_original_path": image.original_path,
                    "result_path": copied_rel.as_posix(),
                    "preview_path": copied_rel.as_posix(),
                    "cloned_from_library": True,
                })
                library_reference_ids.append(image.id)
            input_specs.append(spec)
        prepared["input_images"] = input_specs
        return prepared, library_reference_ids

    def resolve_library_reference(self, image_id: str):
        try:
            image = self.items.get_image(image_id)
        except KeyError as exc:
            raise GenerationJobConflict("Library generation reference image not found") from exc
        path, mime_type = resolve_generation_input_image_path(
            self.library_path,
            image.original_path,
            allowed_roots={"originals"},
        )
        return image, path, mime_type

    def _is_generation_result_path(self, value: str) -> bool:
        path = Path(value)
        return (
            not path.is_absolute()
            and ".." not in path.parts
            and len(path.parts) >= 3
            and path.parts[0] == GENERATION_RESULT_ROOT
        )

    def _clone_generation_result_input(self, *, job_id: str, result_path: str, name: str | None = None) -> tuple[str, dict] | None:
        if not self._is_generation_result_path(result_path):
            return None
        source_rel = Path(result_path)
        source_abs, _ = resolve_generation_input_image_path(
            self.library_path,
            result_path,
            allowed_roots={GENERATION_RESULT_ROOT},
        )
        data = source_abs.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        suffix = source_rel.suffix.lower() or Path(name or "reference.png").suffix.lower() or ".png"
        if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
            suffix = ".png"
        source_job_id = source_rel.parts[1]
        dest_rel = Path(GENERATION_REFERENCE_ROOT) / job_id / f"from-{source_job_id}-{sha[:12]}{suffix}"
        dest_abs = resolve_generation_write_path(
            self.library_path,
            dest_rel.as_posix(),
            allowed_root=GENERATION_REFERENCE_ROOT,
        )
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
                else:
                    resolve_generation_input_image_path(self.library_path, result_path)
            cloned_specs.append(spec)
        prepared["input_images"] = cloned_specs
        return prepared, copy_metadata

    def get_job(self, job_id: str) -> GenerationJobRecord:
        with connect(self.library_path) as conn:
            row = conn.execute("SELECT * FROM generation_jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return self._record_from_row(row)

    def get_generation_set(self, generation_group_id: str) -> GenerationJobSetRecord:
        with connect(self.library_path) as conn:
            group = conn.execute(
                "SELECT * FROM generation_sets WHERE generation_group_id=?",
                (generation_group_id,),
            ).fetchone()
            if group is None:
                raise KeyError(generation_group_id)
            rows = conn.execute(
                "SELECT * FROM generation_jobs WHERE generation_group_id=? ORDER BY generation_group_index ASC",
                (generation_group_id,),
            ).fetchall()
        return self._generation_set_from_rows(group, rows)

    def cancel_generation_set(self, generation_group_id: str) -> GenerationJobSetRecord:
        timestamp = now()
        with connect(self.library_path) as conn:
            group = conn.execute(
                "SELECT * FROM generation_sets WHERE generation_group_id=?",
                (generation_group_id,),
            ).fetchone()
            if group is None:
                raise KeyError(generation_group_id)
            conn.execute(
                """
                UPDATE generation_jobs
                SET status='cancelled', cancelled_at=?, completed_at=?, updated_at=?
                WHERE generation_group_id=? AND status IN ('queued', 'running')
                """,
                (timestamp, timestamp, timestamp, generation_group_id),
            )
            conn.execute(
                "UPDATE generation_sets SET updated_at=? WHERE generation_group_id=?",
                (timestamp, generation_group_id),
            )
            conn.commit()
        return self.get_generation_set(generation_group_id)

    def _generation_set_from_rows(self, group, rows) -> GenerationJobSetRecord:
        counts = {status: 0 for status in ("queued", "running", "succeeded", "failed", "accepted", "discarded", "cancelled")}
        jobs = []
        for row in rows:
            record = self._record_from_row(row)
            jobs.append(record)
            counts[record.status] = counts.get(record.status, 0) + 1
        total = int(group["total"])
        completed = counts["succeeded"] + counts["failed"] + counts["accepted"] + counts["discarded"] + counts["cancelled"]
        return GenerationJobSetRecord(
            generation_group_id=group["generation_group_id"],
            provider=group["provider"],
            created_at=group["created_at"],
            total=total,
            queued=counts["queued"],
            running=counts["running"],
            succeeded=counts["succeeded"],
            failed=counts["failed"],
            accepted=counts["accepted"],
            discarded=counts["discarded"],
            cancelled=counts["cancelled"],
            completed=completed,
            remaining=max(0, total - completed),
            jobs=jobs,
        )

    def _generation_set_summary_from_row(self, row) -> GenerationJobSetRecord:
        total = int(row["total"])
        completed = sum(int(row[status]) for status in ("succeeded", "failed", "accepted", "discarded", "cancelled"))
        return GenerationJobSetRecord(
            generation_group_id=row["generation_group_id"],
            provider=row["provider"],
            created_at=row["created_at"],
            total=total,
            queued=int(row["queued"]),
            running=int(row["running"]),
            succeeded=int(row["succeeded"]),
            failed=int(row["failed"]),
            accepted=int(row["accepted"]),
            discarded=int(row["discarded"]),
            cancelled=int(row["cancelled"]),
            completed=completed,
            remaining=max(0, total - completed),
            jobs=[],
        )

    def list_jobs(self, *, status: str | None = None, limit: int = 100, offset: int = 0) -> GenerationJobList:
        where = "WHERE status=?" if status else ""
        params: list[object] = [status] if status else []
        with connect(self.library_path) as conn:
            total = conn.execute(f"SELECT COUNT(*) FROM generation_jobs {where}", params).fetchone()[0]
            status_rows = conn.execute(
                "SELECT status, COUNT(*) AS count FROM generation_jobs GROUP BY status"
            ).fetchall()
            rows = conn.execute(
                f"SELECT * FROM generation_jobs {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (*params, limit, offset),
            ).fetchall()
            page_group_ids = list(dict.fromkeys(
                row["generation_group_id"] for row in rows if row["generation_group_id"]
            ))
            visibility = []
            summary_params: list[object] = []
            if status is None:
                visibility.append("SUM(CASE WHEN jobs.status IN ('queued', 'running') THEN 1 ELSE 0 END) > 0")
            if page_group_ids:
                visibility.append(f"sets.generation_group_id IN ({','.join('?' for _ in page_group_ids)})")
                summary_params.extend(page_group_ids)
            if visibility:
                set_rows = conn.execute(
                    f"""
                    SELECT
                        sets.generation_group_id,
                        sets.provider,
                        sets.created_at,
                        sets.total,
                        SUM(CASE WHEN jobs.status='queued' THEN 1 ELSE 0 END) AS queued,
                        SUM(CASE WHEN jobs.status='running' THEN 1 ELSE 0 END) AS running,
                        SUM(CASE WHEN jobs.status='succeeded' THEN 1 ELSE 0 END) AS succeeded,
                        SUM(CASE WHEN jobs.status='failed' THEN 1 ELSE 0 END) AS failed,
                        SUM(CASE WHEN jobs.status='accepted' THEN 1 ELSE 0 END) AS accepted,
                        SUM(CASE WHEN jobs.status='discarded' THEN 1 ELSE 0 END) AS discarded,
                        SUM(CASE WHEN jobs.status='cancelled' THEN 1 ELSE 0 END) AS cancelled
                    FROM generation_sets AS sets
                    JOIN generation_jobs AS jobs
                      ON jobs.generation_group_id = sets.generation_group_id
                    GROUP BY sets.generation_group_id, sets.provider, sets.created_at, sets.total
                    HAVING {' OR '.join(visibility)}
                    ORDER BY sets.created_at DESC
                    """,
                    summary_params,
                ).fetchall()
            else:
                set_rows = []
        jobs = [self._record_from_row(row) for row in rows]
        generation_sets = [self._generation_set_summary_from_row(row) for row in set_rows]
        status_counts = {
            "queued": 0,
            "running": 0,
            "succeeded": 0,
            "failed": 0,
            "accepted": 0,
            "discarded": 0,
            "cancelled": 0,
        }
        for row in status_rows:
            if row["status"] in status_counts:
                status_counts[row["status"]] = int(row["count"])
        return GenerationJobList(
            jobs=jobs,
            total=total,
            limit=limit,
            offset=offset,
            status_counts=status_counts,
            generation_sets=generation_sets,
            provider_queue_states=self.list_provider_queue_states(),
        )

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

    def mark_failed(self, job_id: str, error: str, retry_after_seconds: int | None = None) -> GenerationJobRecord:
        timestamp = now()
        redacted_error = sanitize_generation_error(error)
        existing = self.get_job(job_id)
        metadata = dict(existing.metadata or {})
        metadata["error_kind"] = _classify_error(str(error or ""))
        if retry_after_seconds is not None:
            metadata["retry_after_seconds"] = max(0, min(300, int(retry_after_seconds)))
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

    def mark_running_provider_jobs_failed(self, provider: str, error: str) -> list[GenerationJobRecord]:
        with connect(self.library_path) as conn:
            rows = conn.execute(
                """
                SELECT id FROM generation_jobs
                WHERE provider=? AND status='running'
                ORDER BY created_at ASC
                """,
                (provider,),
            ).fetchall()
        return [self.mark_failed(row["id"], error) for row in rows]

    def mark_stale_running_failed(self, job_id: str) -> GenerationJobRecord:
        job = self.get_job(job_id)
        if job.status != "running":
            raise GenerationJobConflict(f"Only running generation jobs can be marked failed; current status is {job.status}")
        started_at = _parse_timestamp(job.started_at or job.updated_at)
        if started_at is None:
            raise GenerationJobConflict("Running generation job has no start timestamp yet")
        age = datetime.now(timezone.utc) - started_at
        if age < STALE_RUNNING_JOB_AFTER:
            remaining = int((STALE_RUNNING_JOB_AFTER - age).total_seconds() // 60) + 1
            raise GenerationJobConflict(f"Generation job is not stale yet; wait about {remaining} more minute(s)")
        timestamp = now()
        redacted_error = sanitize_generation_error(STALE_RUNNING_JOB_ERROR)
        metadata = dict(job.metadata or {})
        metadata["error_kind"] = _classify_error(redacted_error)
        metadata["stale_running_marked_failed"] = True
        metadata["stale_running_threshold_minutes"] = int(STALE_RUNNING_JOB_AFTER.total_seconds() // 60)
        with connect(self.library_path) as conn:
            cursor = conn.execute(
                """
                UPDATE generation_jobs
                SET status='failed', error=?, metadata=?, updated_at=?, completed_at=?
                WHERE id=? AND status='running'
                """,
                (redacted_error, _to_json(metadata), timestamp, timestamp, job_id),
            )
            conn.commit()
        if cursor.rowcount != 1:
            current = self.get_job(job_id)
            raise GenerationJobConflict(f"Only running generation jobs can be marked failed; current status is {current.status}")
        return self.get_job(job_id)

    def stage_result(self, job_id: str, data: bytes, filename: str, metadata: dict | None = None) -> GenerationJobRecord:
        job = self.get_job(job_id)
        if job.status in {"accepted", "discarded", "cancelled"}:
            raise GenerationJobConflict("Generation job is already finalized")
        suffix = Path(filename).suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
            suffix = ".png"
        sha = hashlib.sha256(data).hexdigest()
        result_rel = Path(GENERATION_RESULT_ROOT) / job_id / f"result-{sha[:12]}{suffix}"
        result_abs = resolve_generation_write_path(
            self.library_path,
            result_rel.as_posix(),
            allowed_root=GENERATION_RESULT_ROOT,
        )
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

    def _resolve_job_result_image_path(self, job: GenerationJobRecord) -> Path:
        if not job.result_path:
            raise GenerationJobConflict("Generation result file is missing")
        result_rel = Path(job.result_path)
        if (
            result_rel.is_absolute()
            or ".." in result_rel.parts
            or len(result_rel.parts) < 3
            or result_rel.parts[0] != GENERATION_RESULT_ROOT
            or result_rel.parts[1] != job.id
        ):
            raise GenerationJobConflict("Generation result file path is invalid")
        result_abs, _ = resolve_generation_input_image_path(
            self.library_path,
            job.result_path,
            allowed_roots={GENERATION_RESULT_ROOT},
        )
        return result_abs

    def _prepare_result_image(self, job: GenerationJobRecord) -> tuple[bytes, str]:
        result_abs = self._resolve_job_result_image_path(job)
        data = result_abs.read_bytes()
        _validate_storeable_image_bytes(data)
        return data, Path(job.result_path or "generated.png").name

    def _store_prepared_image(self, prepared_image: tuple[bytes, str]):
        data, name = prepared_image
        return store_image(self.library_path, data, name)

    def _input_image_specs(self, job: GenerationJobRecord) -> list[dict]:
        raw_images = job.parameters.get("input_images") if isinstance(job.parameters, dict) else None
        if not isinstance(raw_images, list):
            return []
        return [raw for raw in raw_images[:MAX_GENERATION_INPUT_IMAGES] if isinstance(raw, dict)]

    def _prepare_input_reference_images(self, job: GenerationJobRecord) -> list[tuple[bytes, str, str | None]]:
        prepared: list[tuple[bytes, str, str | None]] = []
        for index, spec in enumerate(self._input_image_specs(job)):
            name = str(spec.get("name") or f"generation-reference-{index + 1}.png")
            data: bytes | None = None
            source_image_id: str | None = None
            image_id = spec.get("image_id")
            if spec.get("source") == "library" and isinstance(image_id, str) and image_id:
                result_path = spec.get("result_path")
                if isinstance(result_path, str) and result_path:
                    source_path, _ = resolve_generation_input_image_path(
                        self.library_path,
                        result_path,
                        allowed_roots={GENERATION_REFERENCE_ROOT},
                    )
                    data = source_path.read_bytes()
                    name = Path(result_path).name
                else:
                    image, source_path, _ = self.resolve_library_reference(image_id)
                    data = source_path.read_bytes()
                    name = Path(image.original_path).name
                source_image_id = image_id
            result_path = spec.get("result_path")
            if data is None and isinstance(result_path, str) and result_path:
                source_path, _ = resolve_generation_input_image_path(self.library_path, result_path)
                data = source_path.read_bytes()
                name = Path(result_path).name
            data_url = spec.get("data_url")
            if data is None and isinstance(data_url, str) and data_url:
                if not data_url.startswith("data:image/"):
                    raise GenerationJobConflict("Generation edit input image must be a data URL image")
                _, _, encoded = data_url.partition(",")
                if not encoded:
                    raise GenerationJobConflict("Generation edit input image contains invalid image data")
                try:
                    data = base64.b64decode(encoded, validate=True)
                except (binascii.Error, ValueError) as exc:
                    raise GenerationJobConflict("Generation edit input image contains invalid image data") from exc
            if data:
                _validate_storeable_image_bytes(data)
                prepared.append((data, name, source_image_id))
        return prepared

    def _store_input_reference_images(self, prepared_images: list[tuple[bytes, str, str | None]], item_id: str, *, copy_library_images: bool) -> None:
        for data, name, source_image_id in prepared_images:
            if source_image_id and not copy_library_images:
                try:
                    if self.items.get_image(source_image_id).item_id == item_id:
                        continue
                except KeyError:
                    pass
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
        input_reference_images = self._prepare_input_reference_images(job)
        result_image = self._prepare_result_image(job)
        stored = self._store_prepared_image(result_image)
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
        self._store_input_reference_images(input_reference_images, job.source_item_id, copy_library_images=False)
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
        input_reference_images = self._prepare_input_reference_images(job)
        result_image = self._prepare_result_image(job)
        new_item = self.items.create_item(ItemCreate(
            title=(overrides.title or default_title).strip() or default_title,
            model=overrides.model or job.model or (source_item.model if source_item else "ChatGPT Image2"),
            source_name=overrides.source_name if overrides.source_name is not None else "Generation variant",
            source_url=overrides.source_url if overrides.source_url is not None else (source_item.source_url if source_item else None),
            author=overrides.author if overrides.author is not None else "User",
            cluster_id=None if overrides.cluster_name else (source_item.cluster.id if source_item and source_item.cluster else None),
            cluster_name=overrides.cluster_name,
            tags=overrides.tags if overrides.tags is not None else ([tag.name for tag in source_item.tags] if source_item else []),
            prompts=prompts,
            notes=overrides.notes if overrides.notes is not None else default_notes,
        ))
        stored = self._store_prepared_image(result_image)
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
        self._store_input_reference_images(input_reference_images, new_item.id, copy_library_images=True)
        return GenerationJobAcceptResult(job=self._mark_accepted(job_id, image.id), item=self.items.get_item(new_item.id))

    def _result_path_is_discardable(self, job: GenerationJobRecord) -> bool:
        if job.status != "succeeded" or not job.result_path or job.accepted_image_id:
            return False
        result_rel = Path(job.result_path)
        if not (
            not result_rel.is_absolute()
            and ".." not in result_rel.parts
            and len(result_rel.parts) >= 3
            and result_rel.parts[0] == GENERATION_RESULT_ROOT
            and result_rel.parts[1] == job.id
        ):
            return False
        try:
            self._resolve_job_result_image_path(job)
        except GenerationJobConflict:
            return False
        return True

    def _result_path_has_item_image_references(self, result_path: str) -> bool:
        with connect(self.library_path) as conn:
            image_ref = conn.execute(
                """SELECT 1 FROM images
                   WHERE original_path=? OR thumb_path=? OR preview_path=?
                   LIMIT 1""",
                (result_path, result_path, result_path),
            ).fetchone()
            return image_ref is not None

    def _generation_jobs_referencing_result_path(self, job: GenerationJobRecord) -> list[GenerationJobRecord]:
        if not job.result_path:
            return []
        matches: list[GenerationJobRecord] = []
        with connect(self.library_path) as conn:
            rows = conn.execute(
                """SELECT * FROM generation_jobs
                   WHERE id<>?
                   ORDER BY created_at ASC""",
                (job.id,),
            ).fetchall()
        for row in rows:
            candidate = self._record_from_row(row)
            raw_images = candidate.parameters.get("input_images") if isinstance(candidate.parameters, dict) else None
            if not isinstance(raw_images, list):
                continue
            for raw in raw_images:
                if isinstance(raw, dict) and raw.get("result_path") == job.result_path:
                    matches.append(candidate)
                    break
        return matches

    def _repair_generation_job_references_to_result(self, job: GenerationJobRecord) -> int:
        if not job.result_path:
            return 0
        repaired_count = 0
        for downstream in self._generation_jobs_referencing_result_path(job):
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
                    if clone is not None:
                        copied_path, meta = clone
                        spec["result_path"] = copied_path
                        spec["source_result_path"] = job.result_path
                        spec["source_generation_job_id"] = job.id
                        spec["cloned_from_generation_result"] = True
                        copy_metadata.append(meta)
                        changed = True
                new_images.append(spec)
            if not changed:
                continue
            parameters["input_images"] = new_images
            metadata = dict(downstream.metadata or {})
            existing_copies = metadata.get("reference_image_copies")
            if not isinstance(existing_copies, list):
                existing_copies = []
            existing_copies.extend(copy_metadata)
            metadata["reference_image_copies"] = existing_copies
            metadata["reference_image_repair"] = {
                "repaired_from_discard_job_id": job.id,
                "source_result_path": job.result_path,
                "repaired_at": now(),
            }
            timestamp = now()
            with connect(self.library_path) as conn:
                conn.execute(
                    "UPDATE generation_jobs SET parameters=?, metadata=?, updated_at=? WHERE id=?",
                    (_to_json(parameters), _to_json(metadata), timestamp, downstream.id),
                )
                conn.commit()
            repaired_count += 1
        return repaired_count

    def discard_job(self, job_id: str) -> GenerationJobRecord:
        job = self.get_job(job_id)
        if job.status == "accepted" or job.accepted_image_id:
            raise GenerationJobConflict("Accepted generation jobs cannot be discarded")
        if not self._result_path_is_discardable(job):
            raise GenerationJobConflict("Only transient generation results in a safe path can be discarded")
        if self._result_path_has_item_image_references(job.result_path or ""):
            raise GenerationJobConflict("Generation result is saved to library data and cannot be discarded")
        self._repair_generation_job_references_to_result(job)
        if self._generation_jobs_referencing_result_path(job):
            raise GenerationJobConflict("Generation result is still used as a generation reference and cannot be discarded")
        result_abs = self._resolve_job_result_image_path(job)
        timestamp = now()
        metadata = dict(job.metadata or {})
        metadata["discarded_result_path"] = job.result_path
        with connect(self.library_path) as conn:
            cursor = conn.execute(
                """
                UPDATE generation_jobs
                SET status='discarded', result_path=NULL, result_width=NULL, result_height=NULL, result_sha256=NULL,
                    metadata=?, discarded_at=?, updated_at=?
                WHERE id=? AND status='succeeded' AND accepted_image_id IS NULL
                """,
                (_to_json(metadata), timestamp, timestamp, job_id),
            )
            conn.commit()
        if cursor.rowcount != 1:
            current = self.get_job(job_id)
            raise GenerationJobConflict(f"Only transient succeeded generation results can be discarded; current status is {current.status}")
        with suppress(OSError):
            result_abs.unlink()
        with suppress(OSError):
            result_abs.parent.rmdir()
        return self.get_job(job_id)

    def retry_failed_job(self, job_id: str) -> GenerationJobRecord:
        job = self.get_job(job_id)
        if job.status != "failed":
            raise GenerationJobConflict(f"Only failed generation jobs can be retried; current status is {job.status}")
        if job.metadata.get("retried_by_generation_job_id"):
            raise GenerationJobConflict("Failed generation job has already been retried")
        retry_id = new_id("gen")
        timestamp = now()
        retry_metadata = {
            "retry_of_generation_job_id": job.id,
            "retry_reason": "failed_retry",
        }
        original_metadata = dict(job.metadata or {})
        original_metadata["retried_by_generation_job_id"] = retry_id
        with connect(self.library_path) as conn:
            conn.execute(
                """
                UPDATE generation_jobs
                SET metadata=?, updated_at=?
                WHERE id=? AND status='failed'
                """,
                (_to_json(original_metadata), timestamp, job.id),
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
        return self.get_job(retry_id)

    def discard_and_retry_job(self, job_id: str) -> GenerationJobRetryResult:
        job = self.get_job(job_id)
        if job.status == "accepted" or job.accepted_image_id:
            raise GenerationJobConflict("Saved generation jobs cannot be retried. Create a variant instead.")
        if job.status != "succeeded" or not job.result_path:
            raise GenerationJobConflict("Only unsaved ready generation results can be retried")
        if not self._result_path_is_discardable(job):
            raise GenerationJobConflict("Only transient generation results in a safe path can be retried")
        if self._result_path_has_item_image_references(job.result_path or ""):
            raise GenerationJobConflict("Generation result is saved to library data and cannot be retried")
        self._repair_generation_job_references_to_result(job)
        if self._generation_jobs_referencing_result_path(job):
            raise GenerationJobConflict("Generation result is still used as a generation reference and cannot be retried")
        result_abs = self._resolve_job_result_image_path(job)
        retry_id = new_id("gen")
        timestamp = now()
        retry_metadata = {
            "retry_of_generation_job_id": job.id,
            "retry_reason": "discard_and_retry",
        }
        discarded_metadata = dict(job.metadata or {})
        discarded_metadata["discarded_result_path"] = job.result_path
        discarded_metadata["retried_by_generation_job_id"] = retry_id
        with connect(self.library_path) as conn:
            cursor = conn.execute(
                """
                UPDATE generation_jobs
                SET status='discarded', result_path=NULL, result_width=NULL, result_height=NULL, result_sha256=NULL,
                    metadata=?, discarded_at=?, updated_at=?
                WHERE id=? AND status='succeeded' AND accepted_image_id IS NULL
                """,
                (_to_json(discarded_metadata), timestamp, timestamp, job.id),
            )
            if cursor.rowcount != 1:
                conn.rollback()
                current = self.get_job(job_id)
                raise GenerationJobConflict(f"Only unsaved ready generation results can be retried; current status is {current.status}")
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
        with suppress(OSError):
            result_abs.unlink()
        with suppress(OSError):
            result_abs.parent.rmdir()
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

    def create_job_set(self, payload: GenerationJobCreate, count: int) -> GenerationJobSetRecord:
        if count not in {1, 3, 5, 10}:
            raise GenerationJobConflict("Generation set count must be one of 1, 3, 5, or 10")
        if payload.provider == "manual_upload" and count != 1:
            raise GenerationJobConflict("Manual result upload supports one image at a time")
        if payload.source_item_id:
            self.items.get_item(payload.source_item_id)
        parameters = dict(payload.parameters or {})
        input_images = parameters.get("input_images")
        if isinstance(input_images, list) and len(input_images) > MAX_GENERATION_INPUT_IMAGES:
            raise GenerationJobConflict(f"Generation edit supports up to {MAX_GENERATION_INPUT_IMAGES} input images")
        generation_group_id = new_id("gen-group")
        prepared_rows = []
        job_ids: list[str] = []
        preexisting_reference_paths: dict[str, set[Path]] = {}
        timestamp = now()
        try:
            for index in range(1, count + 1):
                job_id = new_id("gen")
                job_ids.append(job_id)
                reference_root = self.library_path / GENERATION_REFERENCE_ROOT / job_id
                if reference_root.is_dir() and not reference_root.is_symlink():
                    preexisting_reference_paths[job_id] = {
                        path for path in reference_root.rglob("*")
                    }
                else:
                    preexisting_reference_paths[job_id] = set()
                prepared_parameters, library_reference_ids = self._prepare_library_reference_inputs(job_id, parameters)
                prepared_parameters, reference_image_copies = self._prepare_reference_input_clones(job_id, prepared_parameters)
                metadata = {"reference_image_copies": reference_image_copies} if reference_image_copies else {}
                prepared_rows.append((
                    job_id,
                    payload.source_item_id,
                    payload.mode,
                    payload.provider,
                    payload.model,
                    "queued",
                    payload.prompt_language,
                    payload.prompt_text,
                    payload.edited_prompt_text,
                    _to_json(library_reference_ids or payload.reference_image_ids),
                    _to_json(prepared_parameters),
                    _to_json(metadata),
                    generation_group_id,
                    index,
                    count,
                    timestamp,
                    timestamp,
                ))
            with connect(self.library_path) as conn:
                conn.execute(
                    "INSERT INTO generation_sets(generation_group_id, provider, total, created_at, updated_at) VALUES(?,?,?,?,?)",
                    (generation_group_id, payload.provider, count, timestamp, timestamp),
                )
                conn.executemany(
                    """
                    INSERT INTO generation_jobs(
                        id, source_item_id, mode, provider, model, status, prompt_language,
                        prompt_text, edited_prompt_text, reference_image_ids, parameters,
                        metadata, generation_group_id, generation_group_index, generation_group_size,
                        created_at, updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    prepared_rows,
                )
                conn.commit()
        except Exception:
            for job_id in job_ids:
                self._cleanup_generation_reference_clones(job_id, preserve_paths=preexisting_reference_paths.get(job_id, set()))
            raise
        return self.get_generation_set(generation_group_id)

    def _cleanup_generation_reference_clones(self, job_id: str, *, preserve_paths: set[Path] | None = None) -> None:
        preserved = preserve_paths or set()
        root = self.library_path / GENERATION_REFERENCE_ROOT / job_id
        if not root.is_dir() or root.is_symlink():
            return
        for path in sorted(root.rglob("*"), key=lambda value: len(value.parts), reverse=True):
            if path in preserved or path.is_symlink() or not path.is_file():
                continue
            with suppress(OSError):
                path.unlink()
        for path in sorted(root.rglob("*"), key=lambda value: len(value.parts), reverse=True):
            if path in preserved or path.is_symlink() or not path.is_dir():
                continue
            with suppress(OSError):
                path.rmdir()
        with suppress(OSError):
            root.rmdir()

    def cancel_active_jobs(self) -> int:
        """Cancel every queued or running job in one database update."""
        timestamp = now()
        with connect(self.library_path) as conn:
            cursor = conn.execute(
                """
                UPDATE generation_jobs
                SET status='cancelled', cancelled_at=?, completed_at=?, updated_at=?
                WHERE status IN ('queued', 'running')
                """,
                (timestamp, timestamp, timestamp),
            )
            conn.commit()
        return int(cursor.rowcount)

    def get_provider_queue_state(self, provider: str) -> GenerationProviderQueueState:
        with connect(self.library_path) as conn:
            row = conn.execute("SELECT * FROM provider_queue_states WHERE provider=?", (provider,)).fetchone()
        return self._provider_queue_state_from_row(provider, row)

    def list_provider_queue_states(self, providers: list[str] | None = None) -> list[GenerationProviderQueueState]:
        requested = list(dict.fromkeys(str(provider) for provider in (providers or []) if provider))
        with connect(self.library_path) as conn:
            rows = conn.execute("SELECT * FROM provider_queue_states ORDER BY provider ASC").fetchall()
        by_provider = {row["provider"]: row for row in rows}
        names = requested or list(by_provider)
        return [self._provider_queue_state_from_row(provider, by_provider.get(provider)) for provider in names]

    def record_provider_rate_limit(self, provider: str, retry_after_seconds: int | None = None) -> GenerationProviderQueueState:
        timestamp = now()
        current_time = datetime.now(timezone.utc)
        with connect(self.library_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM provider_queue_states WHERE provider=?", (provider,)).fetchone()
            existing_until = _parse_timestamp(row["paused_until"]) if row else None
            if existing_until and existing_until > current_time:
                if retry_after_seconds is not None:
                    delay = max(0, min(300, int(retry_after_seconds)))
                    extended_until = current_time + timedelta(seconds=delay)
                    if extended_until > existing_until:
                        conn.execute(
                            """
                            UPDATE provider_queue_states
                            SET paused_until=?, retry_after_seconds=?, backoff_seconds=?, updated_at=?
                            WHERE provider=?
                            """,
                            (extended_until.isoformat(), delay, delay, timestamp, provider),
                        )
                conn.commit()
                return self.get_provider_queue_state(provider)
            incident_count = (int(row["incident_count"]) if row else 0) + 1
            fallback = (60, 120, 240, 300)[min(incident_count - 1, 3)]
            delay = max(0, min(300, int(retry_after_seconds))) if retry_after_seconds is not None else fallback
            paused_until = (current_time + timedelta(seconds=delay)).isoformat()
            conn.execute(
                """
                INSERT INTO provider_queue_states(
                    provider, paused_until, retry_after_seconds, backoff_seconds,
                    incident_count, wave_active, updated_at
                ) VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(provider) DO UPDATE SET
                    paused_until=excluded.paused_until,
                    retry_after_seconds=excluded.retry_after_seconds,
                    backoff_seconds=excluded.backoff_seconds,
                    incident_count=excluded.incident_count,
                    wave_active=0,
                    updated_at=excluded.updated_at
                """,
                (provider, paused_until, delay, delay, incident_count, 0, timestamp),
            )
            conn.commit()
        return self.get_provider_queue_state(provider)

    def mark_provider_wave_started(self, provider: str) -> None:
        timestamp = now()
        with connect(self.library_path) as conn:
            conn.execute(
                "UPDATE provider_queue_states SET wave_active=1, updated_at=? WHERE provider=? AND backoff_seconds > 0",
                (timestamp, provider),
            )
            conn.commit()

    def clear_provider_backoff_if_drained(self, provider: str, *, active_count: int) -> None:
        if active_count:
            return
        timestamp = now()
        with connect(self.library_path) as conn:
            row = conn.execute("SELECT * FROM provider_queue_states WHERE provider=?", (provider,)).fetchone()
            if row is None or not row["wave_active"]:
                return
            queued = conn.execute(
                "SELECT COUNT(*) FROM generation_jobs WHERE provider=? AND status='queued'",
                (provider,),
            ).fetchone()[0]
            if queued:
                return
            conn.execute(
                """
                UPDATE provider_queue_states
                SET paused_until=NULL, retry_after_seconds=0, backoff_seconds=0,
                    incident_count=0, wave_active=0, updated_at=?
                WHERE provider=?
                """,
                (timestamp, provider),
            )
            conn.commit()

    def _provider_queue_state_from_row(self, provider: str, row) -> GenerationProviderQueueState:
        if row is None:
            return GenerationProviderQueueState(provider=provider)
        paused_until = row["paused_until"]
        expiry = _parse_timestamp(paused_until)
        remaining = max(0, math.ceil((expiry - datetime.now(timezone.utc)).total_seconds())) if expiry else 0
        return GenerationProviderQueueState(
            provider=provider,
            paused=bool(expiry and expiry > datetime.now(timezone.utc)),
            paused_until=paused_until,
            retry_after_seconds=remaining,
            backoff_seconds=int(row["backoff_seconds"] or 0),
        )

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
