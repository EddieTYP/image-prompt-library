from __future__ import annotations

import hashlib
import base64
import binascii
import json
import logging
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from contextlib import suppress
from io import BytesIO
from threading import RLock

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
from backend.services.credential_safety import contains_embedded_credential, sanitize_structured_credentials
from backend.services.image_store import MAX_IMAGE_PIXELS, _atomic_write_bytes, store_image


class GenerationJobConflict(ValueError):
    pass


MAX_GENERATION_INPUT_IMAGES = 4
STALE_RUNNING_JOB_AFTER = timedelta(minutes=10)
STALE_RUNNING_JOB_ERROR = "Generation took too long and may have stalled. Retry to run it again."
GENERATION_RESULT_ROOT = "generation-results"
GENERATION_REFERENCE_ROOT = "generation-references"
GENERATION_INPUT_IMAGE_ROOTS = {GENERATION_RESULT_ROOT, GENERATION_REFERENCE_ROOT}
_ACCEPT_CLAIM_METADATA_KEY = "_generation_accept_claim"
_ACCEPT_CLAIM_TIMESTAMP_METADATA_KEY = "_generation_accept_claim_at"
_ACCEPT_ARTIFACTS_METADATA_KEY = "_generation_accept_artifacts"
# Persist UTC wall-clock age so a lease remains recoverable after restart.
ACCEPT_CLAIM_LEASE_AFTER = timedelta(minutes=10)
_DISCARD_REPAIR_LOCK = RLock()
logger = logging.getLogger(__name__)


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
    return contains_embedded_credential(message) or any(marker in lowered for marker in _SENSITIVE_ERROR_MARKERS) or any(
        pattern.search(message) for pattern in _SENSITIVE_ERROR_PATTERNS
    )


def sanitize_generation_error(error: str) -> str:
    message = str(error or "Generation failed")
    if _contains_sensitive_error_material(message):
        return "Generation failed; provider returned a credential-related error"
    return message[:1000]


def sanitize_generation_parameters(parameters: object, *, redact_image_data: bool = False) -> dict:
    return sanitize_structured_credentials(parameters, redact_image_data=redact_image_data)


def _generation_provenance_parameters(parameters: dict) -> dict:
    return sanitize_generation_parameters(parameters, redact_image_data=True)


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


def _accept_claim_info(metadata: dict, updated_at: str | None) -> tuple[object, datetime | None, bool]:
    """Return (token, claimed_at, present), including legacy bare-token claims.

    New claims keep the token in the existing metadata key and persist their
    wall-clock lease start in a companion key. Older claims have no companion
    timestamp, so their row update time is the safest available age signal.
    """
    if not isinstance(metadata, dict):
        return None, None, False
    raw_claim = metadata.get(_ACCEPT_CLAIM_METADATA_KEY)
    if not raw_claim:
        return None, None, False
    token = raw_claim
    timestamp_value = metadata.get(_ACCEPT_CLAIM_TIMESTAMP_METADATA_KEY)
    claimed_at = _parse_timestamp(timestamp_value) if isinstance(timestamp_value, str) else None
    if isinstance(raw_claim, dict):
        token = raw_claim.get("token") or raw_claim.get("claim_token")
        if claimed_at is None:
            for key in ("claimed_at", "created_at", "timestamp"):
                nested_timestamp = raw_claim.get(key)
                if isinstance(nested_timestamp, str):
                    claimed_at = _parse_timestamp(nested_timestamp)
                    if claimed_at is not None:
                        break
    if claimed_at is None:
        claimed_at = _parse_timestamp(updated_at)
    return token, claimed_at, True


def _accept_claim_mode(metadata: dict) -> str | None:
    if not isinstance(metadata, dict):
        return None
    raw_claim = metadata.get(_ACCEPT_CLAIM_METADATA_KEY)
    if isinstance(raw_claim, dict) and raw_claim.get("mode") in {"existing_item", "new_item"}:
        return raw_claim["mode"]
    artifacts = metadata.get(_ACCEPT_ARTIFACTS_METADATA_KEY)
    if isinstance(artifacts, dict) and artifacts.get("mode") in {"existing_item", "new_item"}:
        return artifacts["mode"]
    return None


def _accept_claim_is_stale(metadata: dict, updated_at: str | None) -> bool:
    _, claimed_at, present = _accept_claim_info(metadata, updated_at)
    if not present or claimed_at is None:
        return False
    return datetime.now(timezone.utc) - claimed_at >= ACCEPT_CLAIM_LEASE_AFTER


class GenerationJobRepository:

    def __init__(self, library_path: Path | str):
        self.library_path = Path(library_path)
        init_db(self.library_path)
        self.items = ItemRepository(self.library_path)

    def create_job(self, payload: GenerationJobCreate) -> GenerationJobRecord:
        if payload.source_item_id:
            self.items.get_item(payload.source_item_id)
        parameters = sanitize_generation_parameters(payload.parameters)
        input_images = parameters.get("input_images")
        if isinstance(input_images, list) and len(input_images) > MAX_GENERATION_INPUT_IMAGES:
            raise GenerationJobConflict(f"Generation edit supports up to {MAX_GENERATION_INPUT_IMAGES} input images")
        job_id = new_id("gen")
        prepared_parameters, library_reference_ids = self._prepare_library_reference_inputs(job_id, parameters)
        prepared_parameters, reference_image_copies = self._prepare_reference_input_clones(job_id, prepared_parameters)
        prepared_parameters = sanitize_generation_parameters(prepared_parameters)
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
        try:
            data = source_abs.read_bytes()
        except FileNotFoundError as exc:
            raise GenerationJobConflict("Generation reference source image is missing") from exc
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
        if not dest_abs.exists() or hashlib.sha256(dest_abs.read_bytes()).hexdigest() != sha:
            _atomic_write_bytes(dest_abs, data)
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
                    if spec.get("preview_path") == result_path:
                        spec["preview_path"] = copied_path
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

    @staticmethod
    def _current_generation_set_records(records: list[GenerationJobRecord]) -> list[GenerationJobRecord]:
        records_by_id = {record.id: record for record in records}
        valid_replacements: dict[str, str] = {}
        for record in records:
            replacement_id = record.metadata.get("retried_by_generation_job_id")
            if (
                record.status not in {"failed", "discarded"}
                or not isinstance(replacement_id, str)
                or not record.generation_group_id
                or not isinstance(record.generation_group_index, int)
                or record.generation_group_index < 1
            ):
                continue
            replacement = records_by_id.get(replacement_id)
            if (
                replacement is None
                or replacement.metadata.get("retry_of_generation_job_id") != record.id
                or replacement.generation_group_id != record.generation_group_id
                or replacement.generation_group_index != record.generation_group_index
            ):
                continue
            valid_replacements[record.id] = replacement.id

        superseded_ids: set[str] = set()
        for record_id in valid_replacements:
            chain: set[str] = set()
            current_id = record_id
            while current_id in valid_replacements:
                if current_id in chain:
                    chain.clear()
                    break
                chain.add(current_id)
                current_id = valid_replacements[current_id]
            superseded_ids.update(chain)
        return [record for record in records if record.id not in superseded_ids]

    def _generation_set_from_rows(self, group, rows, *, include_jobs: bool = True) -> GenerationJobSetRecord:
        counts = {status: 0 for status in ("queued", "running", "succeeded", "failed", "accepted", "discarded", "cancelled")}
        jobs = [self._record_from_row(row) for row in rows]
        for record in self._current_generation_set_records(jobs):
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
            jobs=jobs if include_jobs else [],
        )

    def list_jobs(
        self,
        *,
        status: str | None = None,
        source_item_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> GenerationJobList:
        conditions = []
        params: list[object] = []
        if status:
            conditions.append("status=?")
            params.append(status)
        if source_item_id is not None:
            conditions.append("source_item_id=?")
            params.append(source_item_id)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
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
                source_filter = " AND jobs.source_item_id=?" if source_item_id is not None else ""
                visibility.append(
                    "EXISTS ("
                    "SELECT 1 FROM generation_jobs AS jobs "
                    "WHERE jobs.generation_group_id=sets.generation_group_id "
                    "AND jobs.status IN ('queued', 'running')"
                    f"{source_filter}"
                    ")"
                )
                if source_item_id is not None:
                    summary_params.append(source_item_id)
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
                        sets.total
                    FROM generation_sets AS sets
                    WHERE {' OR '.join(visibility)}
                    ORDER BY sets.created_at DESC
                    """,
                    summary_params,
                ).fetchall()
                summary_group_ids = [row["generation_group_id"] for row in set_rows]
                if summary_group_ids:
                    set_job_rows = []
                    for start in range(0, len(summary_group_ids), 500):
                        group_id_chunk = summary_group_ids[start:start + 500]
                        group_job_params: list[object] = list(group_id_chunk)
                        group_job_filter = ""
                        if source_item_id is not None:
                            group_job_filter = " AND source_item_id=?"
                            group_job_params.append(source_item_id)
                        set_job_rows.extend(conn.execute(
                            f"""
                            SELECT * FROM generation_jobs
                            WHERE generation_group_id IN ({','.join('?' for _ in group_id_chunk)})
                            {group_job_filter}
                            ORDER BY generation_group_id, generation_group_index ASC, created_at ASC
                            """,
                            group_job_params,
                        ).fetchall())
                else:
                    set_job_rows = []
            else:
                set_rows = []
                set_job_rows = []
        jobs = [self._record_from_row(row) for row in rows]
        set_jobs_by_group: dict[str, list[object]] = {}
        for row in set_job_rows:
            set_jobs_by_group.setdefault(row["generation_group_id"], []).append(row)
        generation_sets = [
            self._generation_set_from_rows(
                row,
                set_jobs_by_group.get(row["generation_group_id"], []),
                include_jobs=False,
            )
            for row in set_rows
        ]
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
        with connect(self.library_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT status, metadata FROM generation_jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            if row["status"] not in {"queued", "running", "failed"}:
                raise GenerationJobConflict(f"Generation job cannot be marked failed from status {row['status']}")
            metadata = _from_json(row["metadata"], {})
            if not isinstance(metadata, dict):
                metadata = {}
            metadata = sanitize_generation_parameters(metadata, redact_image_data=True)
            metadata["error_kind"] = _classify_error(str(error or ""))
            if retry_after_seconds is not None:
                metadata["retry_after_seconds"] = max(0, min(300, int(retry_after_seconds)))
            cursor = conn.execute(
                """
                UPDATE generation_jobs
                SET status='failed', error=?, metadata=?, updated_at=?, completed_at=?
                WHERE id=? AND status IN ('queued', 'running', 'failed')
                """,
                (redacted_error, _to_json(metadata), timestamp, timestamp, job_id),
            )
            conn.commit()
        if cursor.rowcount != 1:
            current = self.get_job(job_id)
            raise GenerationJobConflict(f"Generation job cannot be marked failed from status {current.status}")
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
        metadata = sanitize_generation_parameters(dict(job.metadata or {}), redact_image_data=True)
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
        _validate_storeable_image_bytes(data)
        with Image.open(BytesIO(data)) as image:
            width, height = image.size
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
        _atomic_write_bytes(result_abs, data)
        timestamp = now()
        preserve_result_file = False
        try:
            with connect(self.library_path) as conn:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute("SELECT * FROM generation_jobs WHERE id=?", (job_id,)).fetchone()
                if row is None:
                    raise KeyError(job_id)
                preserve_result_file = row["result_path"] == result_rel.as_posix()
                result_metadata = _from_json(row["metadata"], {})
                if not isinstance(result_metadata, dict):
                    result_metadata = {}
                if result_metadata.get(_ACCEPT_CLAIM_METADATA_KEY):
                    raise GenerationJobConflict("Generation job is currently being accepted")
                if row["status"] not in {"queued", "running"}:
                    raise GenerationJobConflict(f"Generation result cannot be staged from status {row['status']}")
                sanitized_metadata = sanitize_generation_parameters(metadata, redact_image_data=True)
                if sanitized_metadata:
                    for key, value in sanitized_metadata.items():
                        if key.startswith("_generation_accept_"):
                            continue
                        if key == "reference_image_copies":
                            continue
                        if key in {"retry_of_generation_job_id", "retried_by_generation_job_id"} and key in result_metadata:
                            continue
                        result_metadata[key] = value
                result_metadata = sanitize_generation_parameters(result_metadata, redact_image_data=True)
                cursor = conn.execute(
                    """
                    UPDATE generation_jobs
                    SET status='succeeded', result_path=?, result_width=?, result_height=?, result_sha256=?,
                        metadata=?, error=NULL, updated_at=?, completed_at=?
                    WHERE id=? AND status IN ('queued', 'running')
                    """,
                    (result_rel.as_posix(), width, height, sha, _to_json(result_metadata), timestamp, timestamp, job_id),
                )
                if cursor.rowcount != 1:
                    raise GenerationJobConflict("Generation job result could not be staged")
                conn.commit()
        except Exception:
            if not preserve_result_file:
                result_abs.unlink(missing_ok=True)
            raise
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
        if not re.fullmatch(r"[0-9a-f]{64}", str(job.result_sha256 or "")):
            raise GenerationJobConflict("Generation result integrity record is missing")
        if hashlib.sha256(data).hexdigest() != job.result_sha256:
            raise GenerationJobConflict("Generation result file changed after it was staged")
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

    def _prepare_input_reference_images(
        self,
        job: GenerationJobRecord,
        *,
        claim_token: str | None = None,
    ) -> list[tuple[bytes, str, str | None]]:
        prepared: list[tuple[bytes, str, str | None]] = []
        for index, spec in enumerate(self._input_image_specs(job)):
            if claim_token is not None:
                self._require_acceptance_claim(job.id, claim_token)
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

    def _remove_unreferenced_image_files(self, paths: set[str]) -> None:
        if not paths:
            return
        with connect(self.library_path) as conn:
            for rel_path in paths:
                if conn.execute(
                    """SELECT 1 FROM images
                       WHERE original_path=? OR thumb_path=? OR preview_path=?
                       LIMIT 1""",
                    (rel_path, rel_path, rel_path),
                ).fetchone() is not None:
                    continue
                candidate = self.items._safe_library_file(rel_path)
                if candidate and candidate.is_file():
                    with suppress(OSError):
                        candidate.unlink()

    def _remove_created_images(self, item_id: str, created_images: list[tuple[object, StoredImageInput]]) -> None:
        if not created_images:
            return
        paths = {
            path
            for _, image in created_images
            for path in (image.original_path, image.thumb_path, image.preview_path)
            if path
        }
        with connect(self.library_path) as conn:
            conn.executemany(
                "DELETE FROM images WHERE id=? AND item_id=?",
                [(record.id, item_id) for record, _ in created_images],
            )
            conn.commit()
        self._remove_unreferenced_image_files(paths)

    def _find_existing_image(self, item_id: str, image: StoredImageInput):
        """Find an image record created by an earlier attempt for this item."""
        with connect(self.library_path) as conn:
            row = conn.execute(
                """SELECT id FROM images
                   WHERE item_id=? AND original_path=? AND role=?
                   ORDER BY created_at ASC LIMIT 1""",
                (item_id, image.original_path, image.role),
            ).fetchone()
        return self.items.get_image(row["id"]) if row is not None else None

    def _acceptance_artifacts(self, metadata: dict) -> dict:
        artifacts = metadata.get(_ACCEPT_ARTIFACTS_METADATA_KEY)
        return dict(artifacts) if isinstance(artifacts, dict) else {}

    def _record_acceptance_artifacts(
        self,
        job_id: str,
        claim_token: str,
        *,
        mode: str,
        item_id: str,
        result_image_id: str | None = None,
        image_ids: list[str] | None = None,
        references_complete: bool | None = None,
    ) -> dict:
        """Persist side-effect identities while the acceptance lease is held."""
        with connect(self.library_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT metadata, updated_at FROM generation_jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            metadata = _from_json(row["metadata"], {})
            if not isinstance(metadata, dict):
                metadata = {}
            current_token, _, _ = _accept_claim_info(metadata, row["updated_at"])
            if current_token != claim_token:
                raise GenerationJobConflict("Generation job acceptance claim is no longer owned")
            artifacts = self._acceptance_artifacts(metadata)
            artifacts["mode"] = mode
            artifacts["item_id"] = item_id
            if result_image_id:
                artifacts["result_image_id"] = result_image_id
            existing_ids = [str(value) for value in artifacts.get("image_ids", []) if value]
            for image_id in image_ids or []:
                if image_id and image_id not in existing_ids:
                    existing_ids.append(image_id)
            artifacts["image_ids"] = existing_ids
            if references_complete is not None:
                artifacts["references_complete"] = bool(references_complete)
            metadata[_ACCEPT_ARTIFACTS_METADATA_KEY] = artifacts
            timestamp = now()
            metadata[_ACCEPT_CLAIM_TIMESTAMP_METADATA_KEY] = timestamp
            cursor = conn.execute(
                "UPDATE generation_jobs SET metadata=?, updated_at=? WHERE id=? AND metadata=?",
                (_to_json(metadata), timestamp, job_id, row["metadata"]),
            )
            if cursor.rowcount != 1:
                raise GenerationJobConflict("Generation job acceptance claim is no longer owned")
            conn.commit()
        return artifacts

    def _find_recovered_acceptance_item(self, job: GenerationJobRecord, artifacts: dict, *, mode: str):
        """Recover a new-item side effect from claim metadata or prompt provenance."""
        if artifacts.get("mode") == mode and artifacts.get("item_id"):
            try:
                return self.items.get_item(str(artifacts["item_id"]))
            except KeyError:
                pass
        if mode != "new_item":
            return None
        marker = f'"source_generation_job_id": "{job.id}"'
        with connect(self.library_path) as conn:
            row = conn.execute(
                """SELECT DISTINCT i.id
                   FROM items AS i JOIN prompts AS p ON p.item_id=i.id
                   WHERE p.provenance LIKE ?
                   ORDER BY i.created_at ASC LIMIT 1""",
                (f"%{marker}%",),
            ).fetchone()
        if row is None:
            return None
        try:
            return self.items.get_item(row["id"])
        except KeyError:
            return None

    def _store_input_reference_images(
        self,
        prepared_images: list[tuple[bytes, str, str | None]],
        item_id: str,
        *,
        copy_library_images: bool,
        image_ids: list[str] | None = None,
        claim_job_id: str | None = None,
        claim_token: str | None = None,
    ) -> list[tuple[object, StoredImageInput]]:
        created_images: list[tuple[object, StoredImageInput]] = []

        def claim_still_owned() -> bool:
            return not claim_job_id or not claim_token or self._refresh_acceptance_claim(claim_job_id, claim_token)

        def cleanup_lost_claim(extra_images: list[tuple[object, StoredImageInput]] | None = None, paths: set[str] | None = None) -> None:
            if not claim_job_id or not claim_token or not self._acceptance_claim_can_cleanup(claim_job_id, claim_token):
                return
            if paths:
                self._remove_unreferenced_image_files(paths)
            self._remove_created_images(item_id, [*created_images, *(extra_images or [])])

        for data, name, source_image_id in prepared_images:
            if not claim_still_owned():
                cleanup_lost_claim()
                raise GenerationJobConflict("Generation job acceptance claim is no longer owned")
            if source_image_id and not copy_library_images:
                try:
                    if self.items.get_image(source_image_id).item_id == item_id:
                        if image_ids is not None and source_image_id not in image_ids:
                            image_ids.append(source_image_id)
                        continue
                except KeyError:
                    pass
            try:
                stored = store_image(self.library_path, data, name)
            except Exception:
                if claim_still_owned():
                    self._remove_created_images(item_id, created_images)
                raise
            stored_paths = {path for path in (stored.original_path, stored.thumb_path, stored.preview_path) if path}
            if not claim_still_owned():
                cleanup_lost_claim(paths=stored_paths)
                raise GenerationJobConflict("Generation job acceptance claim is no longer owned")
            image_input = StoredImageInput(
                original_path=stored.original_path,
                thumb_path=stored.thumb_path,
                preview_path=stored.preview_path,
                width=stored.width,
                height=stored.height,
                file_sha256=stored.file_sha256,
                role="reference_image",
            )
            existing = self._find_existing_image(item_id, image_input)
            if existing is not None:
                if image_ids is not None and existing.id not in image_ids:
                    image_ids.append(existing.id)
                continue
            if not claim_still_owned():
                cleanup_lost_claim(paths=stored_paths)
                raise GenerationJobConflict("Generation job acceptance claim is no longer owned")
            try:
                image = self.items.add_image(item_id, image_input)
            except Exception:
                if claim_still_owned():
                    self._remove_unreferenced_image_files({
                        path for path in (stored.original_path, stored.thumb_path, stored.preview_path) if path
                    })
                    self._remove_created_images(item_id, created_images)
                raise
            created_images.append((image, image_input))
            if not claim_still_owned():
                cleanup_lost_claim()
                raise GenerationJobConflict("Generation job acceptance claim is no longer owned")
            if image_ids is not None:
                image_ids.append(image.id)
        return created_images

    def _claim_acceptance(self, job_id: str, *, require_source_item: bool) -> tuple[GenerationJobRecord, str]:
        claim_token = new_id("accept")
        requested_mode = "existing_item" if require_source_item else "new_item"
        with connect(self.library_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM generation_jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            if require_source_item and not row["source_item_id"]:
                raise GenerationJobConflict("Generation job has no source item to attach to")
            if row["status"] != "succeeded" or not row["result_path"]:
                raise GenerationJobConflict("Generation job must be succeeded before accept")
            if row["accepted_image_id"]:
                raise GenerationJobConflict("Generation job is already finalized")
            metadata = _from_json(row["metadata"], {})
            if not isinstance(metadata, dict):
                metadata = {}
            if metadata.get(_ACCEPT_CLAIM_METADATA_KEY):
                if not _accept_claim_is_stale(metadata, row["updated_at"]):
                    raise GenerationJobConflict("Generation job is already being accepted")
                existing_mode = _accept_claim_mode(metadata)
                if existing_mode is not None and existing_mode != requested_mode:
                    raise GenerationJobConflict(
                        "This result has an interrupted save. Resume the same save action before choosing another."
                    )
            metadata.pop(_ACCEPT_CLAIM_METADATA_KEY, None)
            metadata.pop(_ACCEPT_CLAIM_TIMESTAMP_METADATA_KEY, None)
            claim_timestamp = now()
            metadata[_ACCEPT_CLAIM_METADATA_KEY] = {"token": claim_token, "mode": requested_mode}
            metadata[_ACCEPT_CLAIM_TIMESTAMP_METADATA_KEY] = claim_timestamp
            cursor = conn.execute(
                """UPDATE generation_jobs
                   SET metadata=?, updated_at=?
                   WHERE id=? AND status='succeeded' AND accepted_image_id IS NULL AND metadata=?""",
                (_to_json(metadata), claim_timestamp, job_id, row["metadata"]),
            )
            if cursor.rowcount != 1:
                raise GenerationJobConflict("Generation job is already being accepted")
            conn.commit()
        return self.get_job(job_id), claim_token

    def _clear_stale_acceptance_claim(self, job_id: str) -> GenerationJobRecord:
        with connect(self.library_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM generation_jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            metadata = _from_json(row["metadata"], {})
            if not isinstance(metadata, dict):
                metadata = {}
            if not _accept_claim_is_stale(metadata, row["updated_at"]):
                conn.commit()
                return self._record_from_row(row)
            marker = f'"source_generation_job_id": "{job_id}"'
            recovered_item = conn.execute(
                """SELECT 1
                   FROM items AS i JOIN prompts AS p ON p.item_id=i.id
                   WHERE p.provenance LIKE ?
                   LIMIT 1""",
                (f"%{marker}%",),
            ).fetchone()
            recovered_image = None
            if row["source_item_id"] and row["result_sha256"]:
                recovered_image = conn.execute(
                    """SELECT 1 FROM images
                       WHERE item_id=? AND role='result_image' AND file_sha256=?
                       LIMIT 1""",
                    (row["source_item_id"], row["result_sha256"]),
                ).fetchone()
            if (
                self._acceptance_artifacts(metadata)
                or recovered_item is not None
                or recovered_image is not None
            ):
                conn.commit()
                raise GenerationJobConflict(
                    "This result has an interrupted save. Save it again before discarding or retrying."
                )
            metadata.pop(_ACCEPT_CLAIM_METADATA_KEY, None)
            metadata.pop(_ACCEPT_CLAIM_TIMESTAMP_METADATA_KEY, None)
            cursor = conn.execute(
                "UPDATE generation_jobs SET metadata=?, updated_at=? WHERE id=? AND metadata=?",
                (_to_json(metadata), now(), job_id, row["metadata"]),
            )
            conn.commit()
        if cursor.rowcount != 1:
            return self.get_job(job_id)
        return self.get_job(job_id)

    def _release_acceptance(self, job_id: str, claim_token: str) -> None:
        with connect(self.library_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT status, metadata, updated_at FROM generation_jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                conn.commit()
                return
            metadata = _from_json(row["metadata"], {})
            if not isinstance(metadata, dict):
                conn.commit()
                return
            current_token, _, _ = _accept_claim_info(metadata, row["updated_at"])
            if current_token != claim_token:
                conn.commit()
                return
            metadata.pop(_ACCEPT_CLAIM_METADATA_KEY, None)
            metadata.pop(_ACCEPT_CLAIM_TIMESTAMP_METADATA_KEY, None)
            conn.execute(
                "UPDATE generation_jobs SET metadata=?, updated_at=? WHERE id=?",
                (_to_json(metadata), now(), job_id),
            )
            conn.commit()

    def _acceptance_claim_owned(self, job_id: str, claim_token: str) -> bool:
        with connect(self.library_path) as conn:
            row = conn.execute("SELECT metadata, updated_at FROM generation_jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            return False
        metadata = _from_json(row["metadata"], {})
        if not isinstance(metadata, dict):
            return False
        current_token, _, _ = _accept_claim_info(metadata, row["updated_at"])
        return current_token == claim_token

    def _refresh_acceptance_claim(self, job_id: str, claim_token: str) -> bool:
        """Heartbeat a live acceptance lease without changing its ownership."""
        with connect(self.library_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT status, accepted_image_id, metadata, updated_at FROM generation_jobs WHERE id=?",
                (job_id,),
            ).fetchone()
            if row is None:
                conn.commit()
                return False
            metadata = _from_json(row["metadata"], {})
            if not isinstance(metadata, dict):
                conn.commit()
                return False
            current_token, _, _ = _accept_claim_info(metadata, row["updated_at"])
            if row["status"] != "succeeded" or row["accepted_image_id"] or current_token != claim_token:
                conn.commit()
                return False
            timestamp = now()
            metadata[_ACCEPT_CLAIM_TIMESTAMP_METADATA_KEY] = timestamp
            cursor = conn.execute(
                """UPDATE generation_jobs
                   SET metadata=?, updated_at=?
                   WHERE id=? AND status='succeeded' AND accepted_image_id IS NULL AND metadata=?""",
                (_to_json(metadata), timestamp, job_id, row["metadata"]),
            )
            conn.commit()
            return cursor.rowcount == 1

    def _acceptance_claim_can_cleanup(self, job_id: str, claim_token: str) -> bool:
        """Allow cleanup for our claim or after a terminal losing transition."""
        with connect(self.library_path) as conn:
            row = conn.execute("SELECT status, metadata, updated_at FROM generation_jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            return True
        metadata = _from_json(row["metadata"], {})
        if not isinstance(metadata, dict):
            return row["status"] in {"failed", "discarded", "cancelled"}
        current_token, _, _ = _accept_claim_info(metadata, row["updated_at"])
        if current_token == claim_token:
            return True
        return row["status"] in {"failed", "discarded", "cancelled"}

    def _require_acceptance_claim(self, job_id: str, claim_token: str) -> None:
        if not self._refresh_acceptance_claim(job_id, claim_token):
            raise GenerationJobConflict("Generation job acceptance claim is no longer owned")

    def _finalize_acceptance(self, job_id: str, image_id: str, claim_token: str) -> GenerationJobRecord:
        timestamp = now()
        with connect(self.library_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT status, accepted_image_id, metadata, updated_at FROM generation_jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            metadata = _from_json(row["metadata"], {})
            current_token, _, _ = _accept_claim_info(metadata, row["updated_at"])
            if (
                row["status"] != "succeeded"
                or row["accepted_image_id"]
                or not isinstance(metadata, dict)
                or current_token != claim_token
            ):
                raise GenerationJobConflict(f"Generation job cannot be accepted; current status is {row['status']}")
            metadata.pop(_ACCEPT_CLAIM_METADATA_KEY, None)
            metadata.pop(_ACCEPT_CLAIM_TIMESTAMP_METADATA_KEY, None)
            metadata.pop(_ACCEPT_ARTIFACTS_METADATA_KEY, None)
            cursor = conn.execute(
                """UPDATE generation_jobs
                   SET status='accepted', accepted_image_id=?, accepted_at=?, updated_at=?, metadata=?
                   WHERE id=? AND status='succeeded' AND accepted_image_id IS NULL""",
                (image_id, timestamp, timestamp, _to_json(metadata), job_id),
            )
            if cursor.rowcount != 1:
                raise GenerationJobConflict("Generation job could not be accepted")
            conn.commit()
        return self.get_job(job_id)

    def accept_result(self, job_id: str) -> GenerationJobAcceptResult:
        job, claim_token = self._claim_acceptance(job_id, require_source_item=True)
        created_images: list[tuple[object, StoredImageInput]] = []
        finalized = False
        try:
            input_reference_images = self._prepare_input_reference_images(job, claim_token=claim_token)
            self._require_acceptance_claim(job.id, claim_token)
            result_image = self._prepare_result_image(job)
            self._require_acceptance_claim(job.id, claim_token)
            artifacts = self._acceptance_artifacts(job.metadata)
            self._require_acceptance_claim(job.id, claim_token)
            result_stored = self._store_prepared_image(result_image)
            if not self._refresh_acceptance_claim(job.id, claim_token):
                if self._acceptance_claim_can_cleanup(job.id, claim_token):
                    self._remove_unreferenced_image_files({
                        path for path in (result_stored.original_path, result_stored.thumb_path, result_stored.preview_path) if path
                    })
                raise GenerationJobConflict("Generation job acceptance claim is no longer owned")
            result_input = StoredImageInput(
                original_path=result_stored.original_path,
                thumb_path=result_stored.thumb_path,
                preview_path=result_stored.preview_path,
                width=result_stored.width,
                height=result_stored.height,
                file_sha256=result_stored.file_sha256,
                role="result_image",
            )
            image = None
            if artifacts.get("mode") == "existing_item" and artifacts.get("item_id") == job.source_item_id:
                image_id = artifacts.get("result_image_id")
                if image_id:
                    try:
                        candidate = self.items.get_image(str(image_id))
                        if candidate.item_id == job.source_item_id and candidate.role == "result_image":
                            image = candidate
                    except KeyError:
                        pass
            if image is None:
                image = self._find_existing_image(job.source_item_id, result_input)
            if image is None:
                try:
                    image = self.items.add_image(job.source_item_id, result_input)
                except Exception:
                    if self._acceptance_claim_can_cleanup(job.id, claim_token):
                        self._remove_unreferenced_image_files({
                            path for path in (result_stored.original_path, result_stored.thumb_path, result_stored.preview_path) if path
                        })
                    raise
                created_images.append((image, result_input))
                if not self._refresh_acceptance_claim(job.id, claim_token):
                    if self._acceptance_claim_can_cleanup(job.id, claim_token):
                        self._remove_created_images(job.source_item_id, created_images)
                    raise GenerationJobConflict("Generation job acceptance claim is no longer owned")
            image_ids = [image.id]
            self._record_acceptance_artifacts(
                job.id,
                claim_token,
                mode="existing_item",
                item_id=job.source_item_id,
                result_image_id=image.id,
                image_ids=image_ids,
                references_complete=False,
            )
            created_images.extend(self._store_input_reference_images(
                input_reference_images,
                job.source_item_id,
                copy_library_images=False,
                image_ids=image_ids,
                claim_job_id=job.id,
                claim_token=claim_token,
            ))
            self._record_acceptance_artifacts(
                job.id,
                claim_token,
                mode="existing_item",
                item_id=job.source_item_id,
                result_image_id=image.id,
                image_ids=image_ids,
                references_complete=True,
            )
            accepted_job = self._finalize_acceptance(job_id, image.id, claim_token)
            finalized = True
            return GenerationJobAcceptResult(job=accepted_job, item=self.items.get_item(job.source_item_id))
        except Exception:
            if not finalized and self._acceptance_claim_can_cleanup(job_id, claim_token):
                try:
                    self._remove_created_images(job.source_item_id, created_images)
                finally:
                    self._release_acceptance(job_id, claim_token)
            raise

    def accept_result_as_new_item(self, job_id: str, overrides: GenerationJobAcceptAsNewItemRequest | None = None) -> GenerationJobAcceptResult:
        job, claim_token = self._claim_acceptance(job_id, require_source_item=False)
        try:
            source_item = self.items.get_item(job.source_item_id) if job.source_item_id else None
        except Exception:
            self._release_acceptance(job_id, claim_token)
            raise
        prompt_text = (job.edited_prompt_text or job.prompt_text).strip()
        if not prompt_text:
            self._release_acceptance(job_id, claim_token)
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
            "parameters": _generation_provenance_parameters(job.parameters),
        }
        try:
            if overrides.prompts:
                prompts = []
                for index, prompt in enumerate(overrides.prompts):
                    prompt_provenance = sanitize_generation_parameters(prompt.provenance, redact_image_data=True)
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
        except Exception:
            self._release_acceptance(job_id, claim_token)
            raise
        default_title = f"{source_item.title} Variant" if source_item else "Generated image"
        default_notes = f"Variant generated from item {job.source_item_id} via GenerationJob {job.id}." if source_item else f"Generated via GenerationJob {job.id}."
        new_item = self._find_recovered_acceptance_item(job, self._acceptance_artifacts(job.metadata), mode="new_item")
        created_item = False
        created_images: list[tuple[object, StoredImageInput]] = []
        finalized = False
        try:
            input_reference_images = self._prepare_input_reference_images(job, claim_token=claim_token)
            self._require_acceptance_claim(job.id, claim_token)
            result_image = self._prepare_result_image(job)
            self._require_acceptance_claim(job.id, claim_token)
            if new_item is None:
                self._require_acceptance_claim(job.id, claim_token)
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
                created_item = True
                if not self._refresh_acceptance_claim(job.id, claim_token):
                    if self._acceptance_claim_can_cleanup(job.id, claim_token):
                        self.items.delete_item(new_item.id)
                    raise GenerationJobConflict("Generation job acceptance claim is no longer owned")
                self._record_acceptance_artifacts(
                    job.id,
                    claim_token,
                    mode="new_item",
                    item_id=new_item.id,
                    references_complete=False,
                )
            artifacts = self._acceptance_artifacts(job.metadata)
            self._require_acceptance_claim(job.id, claim_token)
            result_stored = self._store_prepared_image(result_image)
            if not self._refresh_acceptance_claim(job.id, claim_token):
                if self._acceptance_claim_can_cleanup(job.id, claim_token):
                    self._remove_unreferenced_image_files({
                        path for path in (result_stored.original_path, result_stored.thumb_path, result_stored.preview_path) if path
                    })
                raise GenerationJobConflict("Generation job acceptance claim is no longer owned")
            result_input = StoredImageInput(
                original_path=result_stored.original_path,
                thumb_path=result_stored.thumb_path,
                preview_path=result_stored.preview_path,
                width=result_stored.width,
                height=result_stored.height,
                file_sha256=result_stored.file_sha256,
                role="result_image",
            )
            image = None
            if artifacts.get("mode") == "new_item" and artifacts.get("item_id") == new_item.id:
                image_id = artifacts.get("result_image_id")
                if image_id:
                    try:
                        candidate = self.items.get_image(str(image_id))
                        if candidate.item_id == new_item.id and candidate.role == "result_image":
                            image = candidate
                    except KeyError:
                        pass
            if image is None:
                image = self._find_existing_image(new_item.id, result_input)
            if image is None:
                try:
                    image = self.items.add_image(new_item.id, result_input)
                except Exception:
                    if self._acceptance_claim_can_cleanup(job.id, claim_token):
                        self._remove_unreferenced_image_files({
                            path for path in (result_stored.original_path, result_stored.thumb_path, result_stored.preview_path) if path
                        })
                    raise
                created_images.append((image, result_input))
                if not self._refresh_acceptance_claim(job.id, claim_token):
                    if self._acceptance_claim_can_cleanup(job.id, claim_token):
                        self._remove_created_images(new_item.id, created_images)
                    raise GenerationJobConflict("Generation job acceptance claim is no longer owned")
            image_ids = [image.id]
            self._record_acceptance_artifacts(
                job.id,
                claim_token,
                mode="new_item",
                item_id=new_item.id,
                result_image_id=image.id,
                image_ids=image_ids,
                references_complete=False,
            )
            created_images.extend(self._store_input_reference_images(
                input_reference_images,
                new_item.id,
                copy_library_images=True,
                image_ids=image_ids,
                claim_job_id=job.id,
                claim_token=claim_token,
            ))
            self._record_acceptance_artifacts(
                job.id,
                claim_token,
                mode="new_item",
                item_id=new_item.id,
                result_image_id=image.id,
                image_ids=image_ids,
                references_complete=True,
            )
            accepted_job = self._finalize_acceptance(job_id, image.id, claim_token)
            finalized = True
            return GenerationJobAcceptResult(job=accepted_job, item=self.items.get_item(new_item.id))
        except Exception:
            if not finalized and self._acceptance_claim_can_cleanup(job_id, claim_token):
                try:
                    if created_item and new_item:
                        self.items.delete_item(new_item.id)
                    elif new_item:
                        self._remove_created_images(new_item.id, created_images)
                finally:
                    self._release_acceptance(job_id, claim_token)
            raise

    def _result_path_is_discardable(self, job: GenerationJobRecord) -> bool:
        if (
            job.status != "succeeded"
            or not job.result_path
            or job.accepted_image_id
            or (
                job.metadata.get(_ACCEPT_CLAIM_METADATA_KEY)
                and not _accept_claim_is_stale(job.metadata, job.updated_at)
            )
        ):
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
        with _DISCARD_REPAIR_LOCK:
            repaired_count = 0
            downstream_ids = [downstream.id for downstream in self._generation_jobs_referencing_result_path(job)]
            for downstream_id in downstream_ids:
                with connect(self.library_path) as conn:
                    conn.execute("BEGIN IMMEDIATE")
                    row = conn.execute("SELECT * FROM generation_jobs WHERE id=?", (downstream_id,)).fetchone()
                    if row is None:
                        conn.commit()
                        continue
                    downstream = self._record_from_row(row)
                    parameters = dict(downstream.parameters or {})
                    raw_images = parameters.get("input_images")
                    if not isinstance(raw_images, list):
                        conn.commit()
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
                            clone = self._clone_generation_result_input(
                                job_id=downstream.id,
                                result_path=job.result_path,
                                name=str(spec.get("name") or ""),
                            )
                            if clone is not None:
                                copied_path, meta = clone
                                spec["result_path"] = copied_path
                                if spec.get("preview_path") == job.result_path:
                                    spec["preview_path"] = copied_path
                                spec["source_result_path"] = job.result_path
                                spec["source_generation_job_id"] = job.id
                                spec["cloned_from_generation_result"] = True
                                copy_metadata.append(meta)
                                changed = True
                        new_images.append(spec)
                    if not changed:
                        conn.commit()
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
                    conn.execute(
                        "UPDATE generation_jobs SET parameters=?, metadata=?, updated_at=? WHERE id=?",
                        (_to_json(parameters), _to_json(metadata), now(), downstream.id),
                    )
                    conn.commit()
                repaired_count += 1
            return repaired_count

    def _remove_discarded_result_file(self, result_abs: Path) -> None:
        try:
            result_abs.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise GenerationJobConflict("Generation result could not be removed. Retry the discard.") from exc
        with suppress(OSError):
            result_abs.parent.rmdir()

    def _mark_discard_repair_complete(self, job_id: str, result_path: str) -> None:
        with connect(self.library_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT status, metadata FROM generation_jobs WHERE id=?", (job_id,)).fetchone()
            if row is None or row["status"] != "discarded":
                conn.commit()
                return
            metadata = _from_json(row["metadata"], {})
            if not isinstance(metadata, dict):
                conn.commit()
                return
            if not metadata.get("discard_repair_pending") or metadata.get("discarded_result_path") != result_path:
                conn.commit()
                return
            metadata.pop("discard_repair_pending", None)
            conn.execute(
                "UPDATE generation_jobs SET metadata=?, updated_at=? WHERE id=?",
                (_to_json(metadata), now(), job_id),
            )
            conn.commit()

    def _resume_pending_discard_repair(self, job_id: str) -> GenerationJobRecord | None:
        with connect(self.library_path) as conn:
            row = conn.execute("SELECT * FROM generation_jobs WHERE id=?", (job_id,)).fetchone()
        if row is None or row["status"] != "discarded":
            return None
        metadata = _from_json(row["metadata"], {})
        if not isinstance(metadata, dict) or not metadata.get("discard_repair_pending"):
            return None
        result_path = metadata.get("discarded_result_path")
        if not isinstance(result_path, str) or not result_path:
            return None
        job = self._record_from_row(row).model_copy(update={"result_path": result_path})
        self._repair_generation_job_references_to_result(job)
        try:
            result_abs = self._resolve_job_result_image_path(job)
        except GenerationJobConflict as exc:
            if "missing" not in str(exc).lower():
                raise
            self._mark_discard_repair_complete(job_id, result_path)
            return self.get_job(job_id)
        self._remove_discarded_result_file(result_abs)
        self._mark_discard_repair_complete(job_id, result_path)
        return self.get_job(job_id)

    def resume_pending_discard_repairs(self) -> list[GenerationJobRecord]:
        with connect(self.library_path) as conn:
            rows = conn.execute(
                "SELECT id, metadata FROM generation_jobs WHERE status='discarded' ORDER BY created_at ASC"
            ).fetchall()
        resumed: list[GenerationJobRecord] = []
        for row in rows:
            metadata = _from_json(row["metadata"], {})
            if not isinstance(metadata, dict) or not metadata.get("discard_repair_pending"):
                continue
            try:
                repaired = self._resume_pending_discard_repair(row["id"])
            except (GenerationJobConflict, OSError):
                logger.warning("Could not resume discard repair for %s", row["id"], exc_info=True)
                continue
            if repaired is not None:
                resumed.append(repaired)
        return resumed

    def discard_job(self, job_id: str) -> GenerationJobRecord:
        pending = self._resume_pending_discard_repair(job_id)
        if pending is not None:
            return pending
        job = self._clear_stale_acceptance_claim(job_id)
        if job.status == "accepted" or job.accepted_image_id:
            raise GenerationJobConflict("Accepted generation jobs cannot be discarded")
        if not self._result_path_is_discardable(job):
            raise GenerationJobConflict("Only transient generation results in a safe path can be discarded")
        if self._result_path_has_item_image_references(job.result_path or ""):
            raise GenerationJobConflict("Generation result is saved to library data and cannot be discarded")
        # The terminal transition owns the discard before any downstream repair
        # can mutate another job. A competing status update therefore wins or
        # loses before repair, never after a side effect has been applied.
        result_abs = self._resolve_job_result_image_path(job)
        timestamp = now()
        with connect(self.library_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            current = conn.execute(
                "SELECT status, result_path, accepted_image_id, metadata, updated_at FROM generation_jobs WHERE id=?",
                (job_id,),
            ).fetchone()
            if current is None:
                raise KeyError(job_id)
            metadata = _from_json(current["metadata"], {})
            if not isinstance(metadata, dict):
                metadata = {}
            if (
                current["status"] != "succeeded"
                or current["result_path"] != job.result_path
                or current["accepted_image_id"]
                or (
                    metadata.get(_ACCEPT_CLAIM_METADATA_KEY)
                    and not _accept_claim_is_stale(metadata, current["updated_at"])
                )
            ):
                raise GenerationJobConflict(f"Only transient succeeded generation results can be discarded; current status is {current['status']}")
            metadata.pop(_ACCEPT_CLAIM_METADATA_KEY, None)
            metadata.pop(_ACCEPT_CLAIM_TIMESTAMP_METADATA_KEY, None)
            metadata = sanitize_generation_parameters(metadata, redact_image_data=True)
            metadata["discarded_result_path"] = job.result_path
            metadata["discard_repair_pending"] = True
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
        self._repair_generation_job_references_to_result(job)
        self._remove_discarded_result_file(result_abs)
        self._mark_discard_repair_complete(job_id, job.result_path or "")
        return self.get_job(job_id)

    def retry_failed_job(self, job_id: str) -> GenerationJobRecord:
        retry_id = new_id("gen")
        timestamp = now()
        inserted = False
        try:
            with connect(self.library_path) as conn:
                row = conn.execute("SELECT * FROM generation_jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            job = self._record_from_row(row)
            if job.status != "failed":
                raise GenerationJobConflict(f"Only failed generation jobs can be retried; current status is {job.status}")
            prepared_parameters, reference_image_copies = self._prepare_reference_input_clones(
                retry_id,
                sanitize_generation_parameters(job.parameters),
            )
            retry_metadata = {
                "retry_of_generation_job_id": job.id,
                "retry_reason": "failed_retry",
            }
            if reference_image_copies:
                retry_metadata["reference_image_copies"] = reference_image_copies
            with connect(self.library_path) as conn:
                conn.execute("BEGIN IMMEDIATE")
                current = conn.execute("SELECT * FROM generation_jobs WHERE id=?", (job_id,)).fetchone()
                if current is None:
                    raise KeyError(job_id)
                if current["status"] != "failed":
                    raise GenerationJobConflict(f"Only failed generation jobs can be retried; current status is {current['status']}")
                original_metadata = _from_json(current["metadata"], {})
                if not isinstance(original_metadata, dict):
                    original_metadata = {}
                original_metadata = sanitize_generation_parameters(original_metadata, redact_image_data=True)
                if original_metadata.get("retried_by_generation_job_id"):
                    raise GenerationJobConflict("Failed generation job has already been retried")
                original_metadata["retried_by_generation_job_id"] = retry_id
                cursor = conn.execute(
                    """
                    UPDATE generation_jobs
                    SET metadata=?, updated_at=?
                    WHERE id=? AND status='failed' AND metadata=?
                    """,
                    (_to_json(original_metadata), timestamp, job.id, current["metadata"]),
                )
                if cursor.rowcount != 1:
                    raise GenerationJobConflict("Failed generation job has already been retried")
                conn.execute(
                    """
                    INSERT INTO generation_jobs(
                        id, source_item_id, mode, provider, model, status, prompt_language,
                        prompt_text, edited_prompt_text, reference_image_ids, parameters,
                        metadata, generation_group_id, generation_group_index, generation_group_size,
                        created_at, updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                        _to_json(prepared_parameters),
                        _to_json(retry_metadata),
                        job.generation_group_id,
                        job.generation_group_index,
                        job.generation_group_size,
                        timestamp,
                        timestamp,
                    ),
                )
                conn.commit()
            inserted = True
            return self.get_job(retry_id)
        except Exception:
            if not inserted:
                self._cleanup_generation_reference_clones(retry_id)
            raise

    def discard_and_retry_job(self, job_id: str) -> GenerationJobRetryResult:
        pending = self._resume_pending_discard_repair(job_id)
        if pending is not None:
            retry_id = pending.metadata.get("retried_by_generation_job_id")
            if isinstance(retry_id, str) and retry_id:
                return GenerationJobRetryResult(discarded_job=pending, retry_job=self.get_job(retry_id))
        job = self._clear_stale_acceptance_claim(job_id)
        if job.status == "accepted" or job.accepted_image_id:
            raise GenerationJobConflict("Saved generation jobs cannot be retried. Create a variant instead.")
        if job.status != "succeeded" or not job.result_path:
            raise GenerationJobConflict("Only unsaved ready generation results can be retried")
        if not self._result_path_is_discardable(job):
            raise GenerationJobConflict("Only transient generation results in a safe path can be retried")
        if self._result_path_has_item_image_references(job.result_path or ""):
            raise GenerationJobConflict("Generation result is saved to library data and cannot be retried")
        # As with discard_job, claim the terminal state before repairing any
        # downstream generation references.
        result_abs = self._resolve_job_result_image_path(job)
        retry_id = new_id("gen")
        timestamp = now()
        retry_metadata = {
            "retry_of_generation_job_id": job.id,
            "retry_reason": "discard_and_retry",
        }
        with connect(self.library_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            current = conn.execute("SELECT * FROM generation_jobs WHERE id=?", (job_id,)).fetchone()
            if current is None:
                raise KeyError(job_id)
            current_metadata = _from_json(current["metadata"], {})
            if not isinstance(current_metadata, dict):
                current_metadata = {}
            if (
                current["status"] != "succeeded"
                or current["result_path"] != job.result_path
                or current["accepted_image_id"]
                or (
                    current_metadata.get(_ACCEPT_CLAIM_METADATA_KEY)
                    and not _accept_claim_is_stale(current_metadata, current["updated_at"])
                )
            ):
                raise GenerationJobConflict(f"Only unsaved ready generation results can be retried; current status is {current['status']}")
            current_metadata.pop(_ACCEPT_CLAIM_METADATA_KEY, None)
            current_metadata.pop(_ACCEPT_CLAIM_TIMESTAMP_METADATA_KEY, None)
            discarded_metadata = sanitize_generation_parameters(current_metadata, redact_image_data=True)
            discarded_metadata["discarded_result_path"] = job.result_path
            discarded_metadata["discard_repair_pending"] = True
            discarded_metadata["retried_by_generation_job_id"] = retry_id
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
                    metadata, generation_group_id, generation_group_index, generation_group_size,
                    created_at, updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                    _to_json(sanitize_generation_parameters(job.parameters)),
                    _to_json(retry_metadata),
                    job.generation_group_id,
                    job.generation_group_index,
                    job.generation_group_size,
                    timestamp,
                    timestamp,
                ),
            )
            conn.commit()
        self._repair_generation_job_references_to_result(job)
        self._remove_discarded_result_file(result_abs)
        self._mark_discard_repair_complete(job_id, job.result_path or "")
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
        parameters = sanitize_generation_parameters(payload.parameters)
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
                prepared_parameters = sanitize_generation_parameters(prepared_parameters)
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
