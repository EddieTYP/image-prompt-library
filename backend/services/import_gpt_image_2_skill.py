from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from backend.db import connect, init_db
from backend.repositories import ItemRepository, StoredImageInput, new_id, now
from backend.schemas import ImportResult, ItemCreate, PromptIn
from backend.services.image_store import store_image

SOURCE_NAME = "wuyoscar/gpt_image_2_skill"
SOURCE_LICENSE = "CC BY 4.0"
DEFAULT_PICKS_PATH = Path("docs") / "community-prompt-picks.json"


def _load_records(source_root: Path) -> list[dict[str, Any]]:
    picks_path = source_root / DEFAULT_PICKS_PATH
    if not picks_path.is_file():
        raise FileNotFoundError(f"Expected {picks_path}; clone or pass the root of wuyoscar/gpt_image_2_skill")
    data = json.loads(picks_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Expected {picks_path} to contain a JSON list")
    return [record for record in data if isinstance(record, dict)]


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _record_slug(record: dict[str, Any]) -> str:
    record_id = _clean_text(record.get("id")) or _clean_text(record.get("title")) or new_id("sample")
    return f"gpt-image-2-skill-{record_id}"


def _already_imported(library: Path, slug: str) -> bool:
    with connect(library) as conn:
        return conn.execute("SELECT 1 FROM items WHERE slug=?", (slug,)).fetchone() is not None


def _notes(record: dict[str, Any]) -> str:
    parts = [
        f"Imported from {SOURCE_NAME} for sample/demo use.",
        f"License: {SOURCE_LICENSE}. Preserve attribution when publishing screenshots, demo GIFs, or fixtures.",
    ]
    source_title = _clean_text(record.get("source_title"))
    source_url = _clean_text(record.get("source_url"))
    source_excerpt = _clean_text(record.get("source_excerpt"))
    size = _clean_text(record.get("size"))
    if source_title:
        parts.append(f"Original source title: {source_title}")
    if source_url:
        parts.append(f"Original source URL: {source_url}")
    if source_excerpt:
        parts.append(f"Source excerpt: {source_excerpt}")
    if size:
        parts.append(f"Original size hint: {size}")
    return "\n".join(parts)


def _image_path(source_root: Path, record: dict[str, Any]) -> Path | None:
    file_value = _clean_text(record.get("file"))
    if not file_value:
        return None
    path = Path(file_value)
    if path.is_absolute():
        return path if path.is_file() else None
    candidate = source_root / path
    return candidate if candidate.is_file() else None


def import_gpt_image_2_skill(source: Path | str, library: Path | str) -> ImportResult:
    source_root = Path(source).resolve()
    library_path = Path(library)
    init_db(library_path)
    repo = ItemRepository(library_path)
    batch_id = new_id("imp")
    started = now()
    log: list[str] = []
    item_count = 0
    image_count = 0

    with connect(library_path) as conn:
        conn.execute(
            "INSERT INTO imports(id,source_name,source_path,status,started_at,log) VALUES(?,?,?,?,?,?)",
            (batch_id, SOURCE_NAME, str(source_root), "running", started, ""),
        )
        conn.commit()

    for record in _load_records(source_root):
        title = _clean_text(record.get("title")) or "Untitled GPT Image 2 sample"
        slug = _record_slug(record)
        if _already_imported(library_path, slug):
            continue
        prompt_text = _clean_text(record.get("prompt")) or title
        category = _clean_text(record.get("category")) or "Sample prompts"
        platform = _clean_text(record.get("platform"))
        source_url = _clean_text(record.get("source_url"))
        tags = ["sample", "gpt_image_2_skill"]
        if platform:
            tags.append(platform)
        size = _clean_text(record.get("size"))
        if size:
            tags.append(size)

        created = repo.create_item(
            ItemCreate(
                title=title,
                slug=slug,
                model="GPT Image 2 sample",
                cluster_name=category,
                tags=list(dict.fromkeys(tags)),
                prompts=[PromptIn(language="en", text=prompt_text, is_primary=True)],
                source_name=SOURCE_NAME,
                source_url=source_url,
                author=platform or SOURCE_NAME,
                notes=_notes(record),
            ),
            imported=True,
        )
        item_count += 1

        found_image = _image_path(source_root, record)
        if not found_image:
            log.append(f"Missing image for {slug}: {record.get('file')}")
            continue
        stored = store_image(library_path, found_image.read_bytes(), found_image.name)
        repo.add_image(
            created.id,
            StoredImageInput(
                stored.original_path,
                stored.thumb_path,
                stored.preview_path,
                width=stored.width,
                height=stored.height,
                file_sha256=stored.file_sha256,
                role="result_image",
            ),
        )
        image_count += 1

    finished = now()
    with connect(library_path) as conn:
        conn.execute(
            "UPDATE imports SET status=?, item_count=?, image_count=?, finished_at=?, log=? WHERE id=?",
            ("completed", item_count, image_count, finished, "\n".join(log), batch_id),
        )
        conn.commit()
    return ImportResult(id=batch_id, item_count=item_count, image_count=image_count, status="completed", log="\n".join(log))


def main() -> None:
    parser = argparse.ArgumentParser(description="Import wuyoscar/gpt_image_2_skill community prompt picks into a local Image Prompt Library.")
    parser.add_argument("--source", required=True, help="Path to a local clone of https://github.com/wuyoscar/gpt_image_2_skill")
    parser.add_argument("--library", default="library", help="Image Prompt Library data path, defaults to ./library")
    args = parser.parse_args()
    print(import_gpt_image_2_skill(args.source, args.library).model_dump_json(indent=2))


if __name__ == "__main__":
    main()
