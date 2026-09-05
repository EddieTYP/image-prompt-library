#!/usr/bin/env python3
"""Export a compact, static, read-only demo bundle for GitHub Pages.

The bundle intentionally uses compressed WebP images instead of local originals.
"""
from __future__ import annotations

import json
import argparse
import hashlib
import gc
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageOps

from backend.repositories import ItemRepository
from backend.services.credential_safety import normalize_structured_key, sanitize_structured_credentials
from backend.services.import_sample_bundle import import_sample_bundle


def _to_simplified(value: str) -> str:
    try:
        from opencc import OpenCC  # type: ignore

        return OpenCC("t2s").convert(value)
    except Exception:
        return value

DEFAULT_OUTPUT = ROOT / "frontend" / "public" / "demo-data"  # frontend/public/demo-data
PUBLIC_DEMO_SOURCES = {"wuyoscar/gpt_image_2_skill", "freestylefly/awesome-gpt-image-2"}
SAMPLE_PACKAGES = (
    (ROOT / "sample-data/manifests/zh_hant.json", "8a458f6c8c96079f40fbc46c689e7de0bd2eb464ee7f800f94f3ca60131d5035"),
    (ROOT / "sample-data/manifests/awesome-gpt-image-2/zh_hant.json", "153714b7611524d7b98b4b0452baa86c8d05053477bb670b731953e8d26a8c9c"),
)
PRIVATE_RUNTIME_KEYS = {
    "access_token",
    "account_id",
    "auth_mode",
    "auth_store_path",
    "authorization_code",
    "client_id",
    "code_verifier",
    "device_auth_id",
    "id_token",
    "providers",
    "refresh_token",
    "session_id",
    "token_present",
    "tokens",
    "user_code",
}
DEMO_IMAGE_MAX_WIDTH = int(os.environ.get("DEMO_IMAGE_MAX_WIDTH", "900"))
DEMO_IMAGE_QUALITY = int(os.environ.get("DEMO_IMAGE_QUALITY", "62"))


def _compress_image(source: Path, destination: Path) -> tuple[int | None, int | None]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image)
        if image.mode not in {"RGB", "RGBA"}:
            image = image.convert("RGB")
        if image.width > DEMO_IMAGE_MAX_WIDTH:
            ratio = DEMO_IMAGE_MAX_WIDTH / image.width
            height = max(1, round(image.height * ratio))
            image = image.resize((DEMO_IMAGE_MAX_WIDTH, height), Image.Resampling.LANCZOS)
        if image.mode == "RGBA":
            background = Image.new("RGB", image.size, (255, 255, 255))
            background.paste(image, mask=image.getchannel("A"))
            image = background
        image.save(destination, "WEBP", quality=DEMO_IMAGE_QUALITY, method=6)
        return image.width, image.height


def _source_for_image(library_path: Path, image: dict) -> Path:
    for key in ("preview_path", "thumb_path", "original_path"):
        value = image.get(key)
        if value:
            candidate = library_path / value
            if candidate.exists():
                return candidate
    raise FileNotFoundError(f"No source image found for {image.get('id')}")


def _rewrite_image_record(library_path: Path, media_dir: Path, image: dict) -> dict:
    destination_rel = f"demo-data/media/{image['id']}.webp"
    destination = media_dir / f"{image['id']}.webp"
    width, height = _compress_image(_source_for_image(library_path, image), destination)
    rewritten = dict(image)
    rewritten.update({
        "original_path": destination_rel,
        "preview_path": destination_rel,
        "thumb_path": destination_rel,
        "remote_url": None,
        "width": width,
        "height": height,
        "file_sha256": None,
    })
    return rewritten


def build_demo_titles(detail: dict) -> dict[str, str]:
    """Build demo-only localized display titles without changing app DB/API schema."""
    title = str(detail.get("title") or "").strip()
    titles = {
        "zh_hant": title,
        "zh_hans": _to_simplified(title),
    }
    english_prompt = next(
        (
            str(prompt.get("text") or "").strip()
            for prompt in detail.get("prompts", [])
            if prompt.get("language") == "en" and str(prompt.get("text") or "").strip()
        ),
        "",
    )
    if english_prompt and "\n" not in english_prompt and len(english_prompt) <= 96:
        titles["en"] = english_prompt
    return {key: value for key, value in titles.items() if value}


def _demo_id(kind: str, *parts: str) -> str:
    key = json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
    return f"{kind}_{hashlib.sha256(key.encode('utf-8')).hexdigest()[:24]}"


def _stable_cluster(cluster: dict) -> dict:
    return {**cluster, "id": _demo_id("clu", cluster["name"])}


def _stable_item(detail: dict) -> dict:
    detail = dict(detail)
    item_id = _demo_id("itm", detail.get("source_name") or "", detail["slug"])
    # Demo build times are not user edit times. Keep fixture dates stable.
    timestamp = "1970-01-01T00:00:00+00:00"
    detail.update(id=item_id, created_at=timestamp, updated_at=timestamp)
    if detail.get("cluster"):
        detail["cluster"] = _stable_cluster(detail["cluster"])
    detail["tags"] = [{**tag, "id": _demo_id("tag", tag["kind"], tag["name"])} for tag in detail.get("tags", [])]
    detail["prompts"] = [
        {**prompt, "id": _demo_id("prm", item_id, prompt["language"], str(index)),
         "item_id": item_id, "created_at": timestamp, "updated_at": timestamp}
        for index, prompt in enumerate(detail.get("prompts", []))
    ]
    detail["images"] = [
        {**image, "id": _demo_id("img", item_id, str(index)), "item_id": item_id, "created_at": timestamp}
        for index, image in enumerate(detail.get("images", []))
    ]
    return detail


def _rewrite_item(library_path: Path, media_dir: Path, detail: dict) -> dict:
    detail = _stable_item(detail)
    images = [_rewrite_image_record(library_path, media_dir, image) for image in detail.get("images", [])]
    detail = dict(detail)
    detail["images"] = images
    detail["first_image"] = images[0] if images else None
    detail["demo_titles"] = build_demo_titles(detail)
    return detail


def _rewrite_cluster_previews(clusters: list[dict], items: list[dict]) -> list[dict]:
    preview_by_cluster: dict[str, list[str]] = {}
    preview_item_ids_by_cluster: dict[str, list[str]] = {}
    item_count_by_cluster: dict[str, int] = {}
    for item in items:
        cluster = item.get("cluster")
        first = item.get("first_image")
        if not cluster:
            continue
        item_count_by_cluster[cluster["id"]] = item_count_by_cluster.get(cluster["id"], 0) + 1
        if not first:
            continue
        preview_by_cluster.setdefault(cluster["id"], [])
        if len(preview_by_cluster[cluster["id"]]) < 4:
            preview_by_cluster[cluster["id"]].append(first["thumb_path"])
            preview_item_ids_by_cluster.setdefault(cluster["id"], []).append(item["id"])
    rewritten = []
    for cluster in clusters:
        if cluster["id"] not in item_count_by_cluster:
            continue
        next_cluster = dict(cluster)
        next_cluster["count"] = item_count_by_cluster[cluster["id"]]
        next_cluster["preview_images"] = preview_by_cluster.get(cluster["id"], [])
        next_cluster["preview_item_ids"] = preview_item_ids_by_cluster.get(cluster["id"], [])
        rewritten.append(next_cluster)
    return rewritten


def _public_tags(items: list[dict]) -> list[dict]:
    tags_by_id: dict[str, dict] = {}
    for item in items:
        for tag in item.get("tags", []):
            tag_id = str(tag.get("id") or "")
            if not tag_id:
                continue
            public_tag = tags_by_id.setdefault(tag_id, {**tag, "count": 0})
            public_tag["count"] += 1
    return sorted(tags_by_id.values(), key=lambda tag: str(tag.get("name") or "").casefold())


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _strip_private_runtime_fields(value):
    if isinstance(value, dict):
        return {
            key: _strip_private_runtime_fields(child)
            for key, child in value.items()
            if normalize_structured_key(key) not in PRIVATE_RUNTIME_KEYS
        }
    if isinstance(value, list):
        return [_strip_private_runtime_fields(child) for child in value]
    return value


def _public_item(detail: dict) -> dict:
    public_detail = _strip_private_runtime_fields(detail)
    for prompt in public_detail.get("prompts", []):
        if isinstance(prompt, dict) and isinstance(prompt.get("provenance"), dict):
            prompt["provenance"] = sanitize_structured_credentials(
                prompt["provenance"],
                redact_image_data=True,
            )
    return public_detail


def _write_demo(library_path: Path, output: Path) -> None:
    repo = ItemRepository(library_path)
    media_dir = output / "media"
    if output.exists():
        shutil.rmtree(output)
    media_dir.mkdir(parents=True, exist_ok=True)

    item_list = repo.list_items(limit=1000, offset=0)
    public_items = sorted(
        (item for item in item_list.items if item.source_name in PUBLIC_DEMO_SOURCES),
        key=lambda item: (item.source_name or "", item.slug),
    )
    items = [
        _rewrite_item(
            library_path,
            media_dir,
            _public_item(repo.get_item(item.id).model_dump(mode="json")),
        )
        for item in public_items
    ]
    clusters = _rewrite_cluster_previews([_stable_cluster(cluster.model_dump(mode="json")) for cluster in repo.list_clusters()], items)
    clusters.sort(key=lambda cluster: (cluster["sort_order"], cluster["name"], cluster["id"]))
    tags = _public_tags(items)
    sources = sorted({item.source_name for item in public_items if item.source_name})
    source_label = "; ".join(sources) if sources else "sample data"
    metadata = {
        "title": "Image Prompt Library online sandbox",
        "mode": "read-only",
        "image_note": "Images are compressed for the web demo.",
        "source": source_label,
        "item_count": len(items),
        "image_max_width": DEMO_IMAGE_MAX_WIDTH,
        "image_quality": DEMO_IMAGE_QUALITY,
    }

    write_json(output / "items.json", items)
    write_json(output / "clusters.json", clusters)
    write_json(output / "tags.json", tags)
    write_json(output / "metadata.json", metadata)
    print(f"Exported {len(items)} items to {output}")
    print(f"Compressed media files: {len(list(media_dir.glob('*.webp')))}")


def export_demo(sample_images: Path, awesome_images: Path, output: Path = DEFAULT_OUTPUT) -> None:
    """Build only from pinned public sample assets, never an existing Library."""
    with tempfile.TemporaryDirectory(prefix="image-prompt-library-demo-") as directory:
        workspace = Path(directory)
        library = workspace / "library"
        try:
            for index, (archive, (manifest, expected_hash)) in enumerate(
                zip((sample_images, awesome_images), SAMPLE_PACKAGES, strict=True)
            ):
                with Path(archive).open("rb") as source:
                    digest = hashlib.sha256()
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        digest.update(chunk)
                    if digest.hexdigest() != expected_hash:
                        raise ValueError("Sample image archive checksum mismatch; use the published sample image packages")
                    source.seek(0)
                    assets = workspace / f"assets-{index}"
                    with zipfile.ZipFile(source) as bundle:
                        bundle.extractall(assets)
                import_sample_bundle(manifest, assets, library)
            _write_demo(library, output)
        finally:
            # Existing repository helpers leave SQLite connections to GC; release
            # their handles before TemporaryDirectory removes the DB on Windows.
            gc.collect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the public demo from verified sample image packages; existing libraries are never read.")
    parser.add_argument("--sample-images", type=Path, required=True)
    parser.add_argument("--awesome-images", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    export_demo(args.sample_images, args.awesome_images, args.output)
