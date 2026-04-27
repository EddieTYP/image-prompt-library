#!/usr/bin/env python3
"""Export a compact, static, read-only demo bundle for GitHub Pages.

The bundle intentionally uses compressed WebP images instead of local originals.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageOps

from backend.repositories import ItemRepository

DEFAULT_OUTPUT = ROOT / "frontend" / "public" / "demo-data"  # frontend/public/demo-data
DEMO_IMAGE_MAX_WIDTH = int(os.environ.get("DEMO_IMAGE_MAX_WIDTH", "900"))
DEMO_IMAGE_QUALITY = int(os.environ.get("DEMO_IMAGE_QUALITY", "62"))


def _resolve_library_path() -> Path:
    configured = os.environ.get("IMAGE_PROMPT_LIBRARY_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    default = ROOT / "library"
    if (default / "db.sqlite").exists():
        return default
    raise SystemExit(
        "No sample library found. Set IMAGE_PROMPT_LIBRARY_PATH to a library containing db.sqlite, "
        "or run ./scripts/install-sample-data.sh first."
    )


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


def _rewrite_item(library_path: Path, media_dir: Path, detail: dict) -> dict:
    images = [_rewrite_image_record(library_path, media_dir, image) for image in detail.get("images", [])]
    detail = dict(detail)
    detail["images"] = images
    detail["first_image"] = images[0] if images else None
    return detail


def _rewrite_cluster_previews(clusters: list[dict], items: list[dict]) -> list[dict]:
    preview_by_cluster: dict[str, list[str]] = {}
    for item in items:
        cluster = item.get("cluster")
        first = item.get("first_image")
        if not cluster or not first:
            continue
        preview_by_cluster.setdefault(cluster["id"], [])
        if len(preview_by_cluster[cluster["id"]]) < 4:
            preview_by_cluster[cluster["id"]].append(first["thumb_path"])
    rewritten = []
    for cluster in clusters:
        next_cluster = dict(cluster)
        next_cluster["preview_images"] = preview_by_cluster.get(cluster["id"], [])
        rewritten.append(next_cluster)
    return rewritten


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def export_demo(library_path: Path, output: Path = DEFAULT_OUTPUT) -> None:
    repo = ItemRepository(library_path)
    media_dir = output / "media"
    if output.exists():
        shutil.rmtree(output)
    media_dir.mkdir(parents=True, exist_ok=True)

    item_list = repo.list_items(limit=1000, offset=0)
    items = [_rewrite_item(library_path, media_dir, repo.get_item(item.id).model_dump(mode="json")) for item in item_list.items]
    clusters = _rewrite_cluster_previews([cluster.model_dump(mode="json") for cluster in repo.list_clusters()], items)
    tags = [tag.model_dump(mode="json") for tag in repo.list_tags()]
    metadata = {
        "title": "Image Prompt Library online sandbox",
        "mode": "read-only",
        "image_note": "Images are compressed for the web demo.",
        "source": "wuyoscar/gpt_image_2_skill sample data, CC BY 4.0",
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


if __name__ == "__main__":
    export_demo(_resolve_library_path())
