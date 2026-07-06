from __future__ import annotations

import hashlib
import json
import os
from contextlib import suppress
from pathlib import Path

from backend.db import connect
from backend.schemas import CleanupApplyResult, CleanupFileRecord, CleanupImageRecord, CleanupPreview

MEDIA_DIRS = ("originals", "thumbs", "previews")
IMAGE_PATH_COLUMNS = ("original_path", "thumb_path", "preview_path")


class LibraryCleanupService:
    def __init__(self, library_path: Path | str):
        self.library_path = Path(library_path)
        self.library_root = self.library_path.resolve()

    def preview(self) -> CleanupPreview:
        referenced_paths: set[str] = set()
        broken_records: list[CleanupImageRecord] = []
        with connect(self.library_path) as conn:
            rows = conn.execute("SELECT id,item_id,original_path,thumb_path,preview_path FROM images ORDER BY created_at,id").fetchall()
            for row in rows:
                broken_path = None
                broken_reason = None
                for column in IMAGE_PATH_COLUMNS:
                    rel_path = row[column]
                    if not rel_path:
                        continue
                    referenced_paths.add(self._normalize_rel_path(rel_path))
                    candidate = self._safe_media_file(rel_path)
                    if candidate is None:
                        broken_path = rel_path
                        broken_reason = "unsafe_image_path"
                        break
                    if not candidate.is_file():
                        broken_path = rel_path
                        broken_reason = "missing_image_file"
                        break
                if broken_reason is not None:
                    broken_records.append(CleanupImageRecord(image_id=row["id"], item_id=row["item_id"], path=broken_path, reason=broken_reason))

        unreferenced_files: list[CleanupFileRecord] = []
        for media_dir in MEDIA_DIRS:
            root = self.library_path / media_dir
            if not root.is_dir() or root.is_symlink():
                continue
            for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
                dirnames[:] = [name for name in dirnames if not (Path(dirpath) / name).is_symlink()]
                for filename in filenames:
                    candidate = Path(dirpath) / filename
                    if candidate.is_symlink() or not candidate.is_file():
                        continue
                    rel_path = self._relative_library_path(candidate)
                    if rel_path is None or rel_path in referenced_paths:
                        continue
                    unreferenced_files.append(CleanupFileRecord(path=rel_path, bytes=candidate.stat().st_size, reason="unreferenced_media_file"))

        unreferenced_files.sort(key=lambda record: record.path)
        preview = CleanupPreview(
            broken_image_records=broken_records,
            unreferenced_files=unreferenced_files,
            total_bytes=sum(record.bytes for record in unreferenced_files),
            preview_token="",
        )
        return preview.model_copy(update={"preview_token": self._preview_token(preview)})

    def apply(self, preview: CleanupPreview, *, remove_broken_image_records: bool, remove_unreferenced_files: bool) -> CleanupApplyResult:
        removed_records = 0
        removed_files = 0

        if remove_broken_image_records and preview.broken_image_records:
            image_ids = [record.image_id for record in preview.broken_image_records]
            placeholders = ",".join("?" for _ in image_ids)
            with connect(self.library_path) as conn:
                removed_records = conn.execute(f"DELETE FROM images WHERE id IN ({placeholders})", image_ids).rowcount
                conn.commit()

        if remove_unreferenced_files:
            for record in preview.unreferenced_files:
                candidate = self._safe_media_file(record.path)
                if candidate is None or candidate.is_symlink() or not candidate.is_file():
                    continue
                with suppress(OSError):
                    candidate.unlink()
                    removed_files += 1

        after = self.preview()
        return CleanupApplyResult(
            **after.model_dump(),
            removed_broken_image_records=removed_records,
            removed_unreferenced_files=removed_files,
        )

    def _safe_media_file(self, rel_path: str) -> Path | None:
        rel = Path(rel_path)
        if not rel.parts or rel.parts[0] not in MEDIA_DIRS or rel.is_absolute():
            return None
        media_root = Path(os.path.abspath(self.library_path / rel.parts[0]))
        candidate = Path(os.path.abspath(self.library_path / rel))
        try:
            candidate.relative_to(media_root)
        except ValueError:
            return None
        if self._has_symlink_component(media_root, candidate):
            return None
        resolved_candidate = candidate.resolve()
        resolved_media_root = (self.library_path / rel.parts[0]).resolve()
        try:
            resolved_candidate.relative_to(self.library_root)
            resolved_candidate.relative_to(resolved_media_root)
        except ValueError:
            return None
        return resolved_candidate

    def _has_symlink_component(self, root: Path, candidate: Path) -> bool:
        current = root
        if current.is_symlink():
            return True
        for part in candidate.relative_to(root).parts:
            current = current / part
            if current.is_symlink():
                return True
            if not current.exists():
                return False
        return False

    def _relative_library_path(self, path: Path) -> str | None:
        try:
            rel = path.resolve().relative_to(self.library_root)
        except ValueError:
            return None
        if not rel.parts or rel.parts[0] not in MEDIA_DIRS:
            return None
        return rel.as_posix()

    def _normalize_rel_path(self, rel_path: str) -> str:
        return Path(rel_path).as_posix()

    def _preview_token(self, preview: CleanupPreview) -> str:
        payload = {
            "broken_image_records": [record.model_dump() for record in preview.broken_image_records],
            "unreferenced_files": [record.model_dump() for record in preview.unreferenced_files],
            "total_bytes": preview.total_bytes,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
