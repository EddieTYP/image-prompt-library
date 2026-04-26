from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from backend.db import connect, init_db
from backend.repositories import ItemRepository, StoredImageInput, new_id, now
from backend.schemas import ImportResult, ItemCreate, PromptIn
from backend.services.image_store import store_image


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _load_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Sample manifest must be a JSON object")
    if data.get("schema_version") != 1:
        raise ValueError("Unsupported sample manifest schema_version")
    if not isinstance(data.get("items"), list):
        raise ValueError("Sample manifest must contain an items list")
    if not isinstance(data.get("collections"), list):
        raise ValueError("Sample manifest must contain a collections list")
    return data


def _collections_by_id(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    collections: dict[str, dict[str, Any]] = {}
    for collection in manifest.get("collections", []):
        if not isinstance(collection, dict):
            continue
        cid = _clean_text(collection.get("id"))
        if cid:
            collections[cid] = collection
    return collections


def _collection_name(collection: dict[str, Any] | None, language: str) -> str:
    if not collection:
        return "Sample prompts"
    names = collection.get("names") if isinstance(collection.get("names"), dict) else {}
    return (
        _clean_text(collection.get("name"))
        or _clean_text(names.get(language))
        or _clean_text(names.get("en"))
        or "Sample prompts"
    )


def _prompts(item: dict[str, Any]) -> list[PromptIn]:
    prompts: list[PromptIn] = []
    for index, prompt in enumerate(item.get("prompts", [])):
        if not isinstance(prompt, dict):
            continue
        language = _clean_text(prompt.get("language")) or "en"
        text = _clean_text(prompt.get("text"))
        if not text:
            continue
        prompts.append(PromptIn(language=language, text=text, is_primary=bool(prompt.get("is_primary", index == 0))))
    if not prompts:
        title = _clean_text(item.get("title")) or "Untitled sample prompt"
        prompts.append(PromptIn(language="en", text=title, is_primary=True))
    if not any(prompt.is_primary for prompt in prompts):
        prompts[0].is_primary = True
    return prompts


def _replace_prompts_exactly(library_path: Path, repo: ItemRepository, item_id: str, prompts: list[PromptIn]) -> None:
    """Avoid repository auto-adding translated prompt fields for sample manifests.

    Sample manifest prompt languages are intentionally truthful to the source. If an
    item only has English, importing a Chinese-localized manifest must keep English
    only rather than generating an artificial Chinese prompt field.
    """
    timestamp = now()
    with connect(library_path) as conn:
        conn.execute("DELETE FROM prompts WHERE item_id=?", (item_id,))
        for index, prompt in enumerate(prompts):
            conn.execute(
                "INSERT INTO prompts(id,item_id,language,text,is_primary,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                (new_id("prm"), item_id, prompt.language, prompt.text, int(prompt.is_primary or index == 0), timestamp, timestamp),
            )
        repo.rebuild_search(conn, item_id)
        conn.commit()


def _already_imported(library_path: Path, slug: str) -> bool:
    with connect(library_path) as conn:
        return conn.execute("SELECT 1 FROM items WHERE slug=?", (slug,)).fetchone() is not None


def _notes(manifest: dict[str, Any], item: dict[str, Any]) -> str:
    source = manifest.get("source") if isinstance(manifest.get("source"), dict) else {}
    manifest_id = _clean_text(manifest.get("id")) or "sample-data"
    source_name = _clean_text(item.get("source_name")) or _clean_text(source.get("name"))
    license_name = _clean_text(item.get("license")) or _clean_text(source.get("license"))
    if source_name and license_name:
        return f"Sample demo item from {source_name} ({license_name}); preserve attribution when publishing screenshots or fixtures. Manifest: {manifest_id}."
    if license_name:
        return f"Sample demo item ({license_name}); preserve attribution when publishing screenshots or fixtures. Manifest: {manifest_id}."
    return f"Sample demo item. Manifest: {manifest_id}."


def import_sample_bundle(manifest_path: Path | str, assets_dir: Path | str, library: Path | str) -> ImportResult:
    manifest_file = Path(manifest_path).resolve()
    asset_root = Path(assets_dir).resolve()
    library_path = Path(library)
    manifest = _load_manifest(manifest_file)
    language = _clean_text(manifest.get("language")) or "en"
    collections = _collections_by_id(manifest)

    init_db(library_path)
    repo = ItemRepository(library_path)
    batch_id = new_id("imp")
    started = now()
    item_count = 0
    image_count = 0
    log: list[str] = []

    with connect(library_path) as conn:
        conn.execute(
            "INSERT INTO imports(id,source_name,source_path,status,started_at,log) VALUES(?,?,?,?,?,?)",
            (batch_id, "sample-data", str(manifest_file), "running", started, ""),
        )
        conn.commit()

    for item in manifest.get("items", []):
        if not isinstance(item, dict):
            continue
        title = _clean_text(item.get("title")) or "Untitled sample prompt"
        slug = _clean_text(item.get("slug")) or _clean_text(item.get("id")) or title
        if _already_imported(library_path, slug):
            continue
        prompt_values = _prompts(item)
        collection = collections.get(_clean_text(item.get("collection_id")) or "")
        created = repo.create_item(
            ItemCreate(
                title=title,
                slug=slug,
                model=_clean_text(item.get("model")) or "GPT Image 2 sample",
                cluster_name=_collection_name(collection, language),
                tags=list(dict.fromkeys([str(tag).strip() for tag in item.get("tags", []) if str(tag).strip()])),
                prompts=prompt_values,
                source_name=_clean_text(item.get("source_name")) or _clean_text((manifest.get("source") or {}).get("name")),
                source_url=_clean_text(item.get("source_url")),
                author=_clean_text(item.get("author")) or _clean_text((manifest.get("source") or {}).get("name")),
                notes=_notes(manifest, item),
            ),
            imported=True,
        )
        _replace_prompts_exactly(library_path, repo, created.id, prompt_values)
        item_count += 1

        image_value = _clean_text(item.get("image"))
        if not image_value:
            log.append(f"Missing image field for {slug}")
            continue
        image_path = (asset_root / image_value).resolve()
        try:
            image_path.relative_to(asset_root)
        except ValueError:
            log.append(f"Image path escapes sample asset root for {slug}: {image_value}")
            continue
        if not image_path.is_file():
            log.append(f"Missing image for {slug}: {image_value}")
            continue
        stored = store_image(library_path, image_path.read_bytes(), image_path.name)
        repo.add_image(
            created.id,
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
        image_count += 1

    with connect(library_path) as conn:
        conn.execute(
            "UPDATE imports SET status=?, item_count=?, image_count=?, finished_at=?, log=? WHERE id=?",
            ("completed", item_count, image_count, now(), "\n".join(log), batch_id),
        )
        conn.commit()

    return ImportResult(id=batch_id, item_count=item_count, image_count=image_count, status="completed", log="\n".join(log))


def main() -> None:
    parser = argparse.ArgumentParser(description="Install a curated Image Prompt Library sample-data manifest into a local library.")
    parser.add_argument("--manifest", required=True, help="Path to sample-data manifest JSON")
    parser.add_argument("--assets", required=True, help="Directory containing sample image assets referenced by the manifest")
    parser.add_argument("--library", default="library", help="Image Prompt Library data path")
    args = parser.parse_args()
    print(import_sample_bundle(args.manifest, args.assets, args.library).model_dump_json(indent=2))


if __name__ == "__main__":
    main()
