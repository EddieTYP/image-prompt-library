from __future__ import annotations

import json
import re
from pathlib import Path

from backend.db import connect, init_db
from backend.repositories import ItemRepository, StoredImageInput, new_id, now
from backend.schemas import (
    ImportDraftAcceptResult,
    ImportDraftCreate,
    ImportDraftList,
    ImportDraftMedia,
    ImportDraftRecord,
    ItemCreate,
    PromptIn,
)
from backend.services.image_store import store_image
from backend.services.text_normalize import to_traditional


def _json_default(value):
    if hasattr(value, "model_dump"):
        return value.model_dump()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _to_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=_json_default)


def _from_json(raw: str | None, fallback):
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return fallback


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", to_traditional(text).casefold())


class ImportDraftConflict(ValueError):
    pass


class ImportDraftRepository:
    def __init__(self, library_path: Path | str):
        self.library_path = Path(library_path)
        init_db(self.library_path)
        self.items = ItemRepository(self.library_path)

    def create_draft(self, payload: ImportDraftCreate) -> ImportDraftRecord:
        draft_id = new_id("drf")
        timestamp = now()
        duplicate_of = self._find_duplicate(payload)
        status = "duplicate" if duplicate_of else "staged"
        with connect(self.library_path) as conn:
            conn.execute(
                """
                INSERT INTO import_drafts(
                    id,status,source_type,source_name,source_url,source_ref,source_path,title,model,author,
                    suggested_cluster_name,suggested_tags,prompts,media,warnings,confidence,
                    duplicate_of_item_id,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    draft_id,
                    status,
                    payload.source_type,
                    payload.source_name,
                    payload.source_url,
                    payload.source_ref,
                    payload.source_path,
                    payload.title,
                    payload.model,
                    payload.author,
                    payload.suggested_cluster_name,
                    _to_json(payload.suggested_tags),
                    _to_json(payload.prompts),
                    _to_json(payload.media),
                    _to_json(payload.warnings),
                    payload.confidence,
                    duplicate_of,
                    timestamp,
                    timestamp,
                ),
            )
            conn.commit()
        return self.get_draft(draft_id)

    def get_draft(self, draft_id: str) -> ImportDraftRecord:
        with connect(self.library_path) as conn:
            row = conn.execute("SELECT * FROM import_drafts WHERE id=?", (draft_id,)).fetchone()
        if row is None:
            raise KeyError(draft_id)
        return self._record_from_row(row)

    def list_drafts(self, *, status: str | None = None, limit: int = 100, offset: int = 0) -> ImportDraftList:
        where = "WHERE status=?" if status else ""
        params: list[object] = [status] if status else []
        with connect(self.library_path) as conn:
            total = conn.execute(f"SELECT COUNT(*) FROM import_drafts {where}", params).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM import_drafts {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (*params, limit, offset),
            ).fetchall()
        return ImportDraftList(drafts=[self._record_from_row(row) for row in rows], total=total, limit=limit, offset=offset)

    def accept_draft(self, draft_id: str) -> ImportDraftAcceptResult:
        draft = self.get_draft(draft_id)
        if draft.status == "accepted":
            raise ImportDraftConflict("Import draft has already been accepted")
        if draft.status == "duplicate" or draft.duplicate_of_item_id:
            raise ImportDraftConflict("Import draft is marked as duplicate and cannot be accepted")
        duplicate_of = self._find_duplicate(draft)
        if duplicate_of:
            timestamp = now()
            with connect(self.library_path) as conn:
                conn.execute(
                    "UPDATE import_drafts SET status='duplicate', duplicate_of_item_id=?, updated_at=? WHERE id=?",
                    (duplicate_of, timestamp, draft_id),
                )
                conn.commit()
            raise ImportDraftConflict("Import draft is marked as duplicate and cannot be accepted")
        payload = ItemCreate(
            title=draft.title,
            model=draft.model,
            source_name=draft.source_name,
            source_url=draft.source_url,
            author=draft.author,
            cluster_name=draft.suggested_cluster_name,
            tags=draft.suggested_tags,
            prompts=draft.prompts,
        )
        item = self.items.create_item(payload, imported=True)
        for media in draft.media:
            original_path = media.staged_path or media.original_path
            if not original_path:
                continue
            image_input = StoredImageInput(
                original_path=original_path,
                remote_url=media.url,
                width=media.width,
                height=media.height,
                file_sha256=media.file_sha256,
                role=media.role,
            )
            local_file = self.library_path / original_path
            if media.staged_path and local_file.is_file():
                stored = store_image(self.library_path, local_file.read_bytes(), Path(original_path).name)
                image_input = StoredImageInput(
                    original_path=stored.original_path,
                    thumb_path=stored.thumb_path,
                    preview_path=stored.preview_path,
                    remote_url=media.url,
                    width=stored.width,
                    height=stored.height,
                    file_sha256=stored.file_sha256,
                    role=media.role,
                )
            self.items.add_image(item.id, image_input)
        timestamp = now()
        with connect(self.library_path) as conn:
            conn.execute(
                "UPDATE import_drafts SET status='accepted', accepted_item_id=?, accepted_at=?, updated_at=? WHERE id=?",
                (item.id, timestamp, timestamp, draft_id),
            )
            conn.commit()
        return ImportDraftAcceptResult(draft=self.get_draft(draft_id), item=self.items.get_item(item.id))

    def _find_duplicate(self, payload: ImportDraftCreate) -> str | None:
        with connect(self.library_path) as conn:
            if payload.source_url:
                row = conn.execute(
                    "SELECT id FROM items WHERE source_url=? AND archived=0 ORDER BY created_at LIMIT 1",
                    (payload.source_url,),
                ).fetchone()
                if row:
                    return row["id"]
            draft_texts = {_normalize_text(prompt.text) for prompt in payload.prompts if prompt.text.strip()}
            if draft_texts:
                rows = conn.execute(
                    """
                    SELECT i.id, p.text
                    FROM items i
                    JOIN prompts p ON p.item_id=i.id
                    WHERE i.archived=0
                    ORDER BY i.created_at
                    """
                ).fetchall()
        for row in rows if draft_texts else []:
            if _normalize_text(row["text"]) in draft_texts:
                return row["id"]
        return None

    def _record_from_row(self, row) -> ImportDraftRecord:
        data = dict(row)
        data["suggested_tags"] = [str(tag) for tag in _from_json(data.get("suggested_tags"), [])]
        data["prompts"] = [PromptIn.model_validate(prompt) for prompt in _from_json(data.get("prompts"), [])]
        data["media"] = [ImportDraftMedia.model_validate(media) for media in _from_json(data.get("media"), [])]
        data["warnings"] = [str(warning) for warning in _from_json(data.get("warnings"), [])]
        return ImportDraftRecord(**data)
