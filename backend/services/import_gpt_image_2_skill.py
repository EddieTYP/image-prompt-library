from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Literal

from backend.db import connect, init_db
from backend.repositories import ItemRepository, StoredImageInput, new_id, now
from backend.schemas import ImportResult, ItemCreate, PromptIn
from backend.services.image_store import store_image
from backend.services.text_normalize import to_traditional

SOURCE_NAME = "wuyoscar/gpt_image_2_skill"
SOURCE_LICENSE = "CC BY 4.0"
DEFAULT_PICKS_PATH = Path("docs") / "community-prompt-picks.json"
REFERENCES_PATH = Path("skills") / "gpt-image" / "references"
SourceMode = Literal["full", "community-picks"]
PromptEdition = Literal["all", "en", "zh_hans", "zh_hant"]


NO_SECTION_RE = re.compile(r"^### No\.\s*(?P<number>\d+)\s*·\s*(?P<title>.+?)\s*$", re.MULTILINE)
IMAGE_RE = re.compile(r"-\s*Image:\s*`(?P<file>[^`]+)`")
ANY_IMAGE_PATH_RE = re.compile(r"`(?P<file>docs/[^`]+\.(?:png|jpe?g|webp|gif))`")
METADATA_RE = re.compile(r"-\s*Metadata:\s*(?P<metadata>.+)")
README_ZH_HEADING_RE = re.compile(r"^####\s+.+$", re.MULTILINE)
README_ZH_IMAGE_RE = re.compile(r"<a\s+href=\"(?P<file>docs/[^\"]+\.(?:png|jpe?g|webp|gif))\"", re.IGNORECASE)
TEXT_FENCE_RE = re.compile(r"```text\s*\n(?P<text>.*?)\n```", re.DOTALL)


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or new_id("sample")


def _strip_heading_emoji(value: str) -> str:
    text = value.strip().lstrip("#").strip()
    return re.sub(r"^[^A-Za-z0-9\u4e00-\u9fff]+", "", text).strip() or value.strip()


def _readme_zh_prompts_by_file(source_root: Path) -> dict[str, dict[str, str]]:
    readme = source_root / "README.zh.md"
    if not readme.is_file():
        return {}
    text = readme.read_text(encoding="utf-8")
    prompts: dict[str, dict[str, str]] = {}
    headings = list(README_ZH_HEADING_RE.finditer(text))
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        heading_text = _strip_heading_emoji(heading.group(0).lstrip("#").strip())
        body = text[heading.end():end]
        image_files = list(dict.fromkeys(match.group("file").strip() for match in README_ZH_IMAGE_RE.finditer(body)))
        prompt_blocks = [match.group("text").strip() for match in TEXT_FENCE_RE.finditer(body)]
        prompt_blocks = [
            prompt
            for prompt in prompt_blocks
            if prompt and not prompt.startswith("/") and not prompt.startswith("$")
        ]
        if not image_files or not prompt_blocks:
            continue
        if len(image_files) == len(prompt_blocks):
            pairs = zip(image_files, prompt_blocks, strict=True)
        elif len(image_files) == 1:
            pairs = [(image_files[0], prompt_blocks[-1])]
        else:
            pairs = zip(image_files, prompt_blocks, strict=False)
        for file_value, prompt in pairs:
            prompts.setdefault(
                file_value,
                {
                    "prompt_zh_hans": prompt,
                    "category_zh_hans": heading_text,
                    "category_zh_hant": to_traditional(heading_text),
                },
            )
    return prompts


def _markdown_sections(text: str) -> list[tuple[int, str, str]]:
    matches = list(NO_SECTION_RE.finditer(text))
    sections: list[tuple[int, str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections.append((int(match.group("number")), match.group("title").strip(), text[match.end():end]))
    return sections


def _category_from_gallery_file(path: Path, text: str, metadata: str | None) -> str:
    if metadata:
        first = metadata.split("·", 1)[0].strip()
        if first:
            return first.strip("` ")
    first_heading = next((line for line in text.splitlines() if line.startswith("# ")), "")
    if first_heading:
        return _strip_heading_emoji(first_heading)
    stem = path.stem.removeprefix("gallery-").replace("-", " ").title()
    return stem or "GPT Image 2"


def _image_file_from_body(body: str) -> str | None:
    image_match = IMAGE_RE.search(body)
    if image_match:
        return image_match.group("file").strip()
    all_images = [match.group("file").strip() for match in ANY_IMAGE_PATH_RE.finditer(body)]
    return all_images[-1] if all_images else None


def load_full_gallery_records(source: Path | str) -> list[dict[str, Any]]:
    """Parse the canonical 162-reference GPT Image 2 gallery markdown files."""
    source_root = Path(source).resolve()
    refs_root = source_root / REFERENCES_PATH
    if not refs_root.is_dir():
        raise FileNotFoundError(f"Expected {refs_root}; clone or pass the root of wuyoscar/gpt_image_2_skill")
    zh_by_file = _readme_zh_prompts_by_file(source_root)
    records: list[dict[str, Any]] = []
    for gallery_path in sorted(refs_root.glob("gallery-*.md")):
        if gallery_path.name == "gallery.md":
            continue
        text = gallery_path.read_text(encoding="utf-8")
        for number, title, body in _markdown_sections(text):
            file_value = _image_file_from_body(body)
            prompt_match = TEXT_FENCE_RE.search(body)
            if not file_value or not prompt_match:
                continue
            metadata = _clean_text(METADATA_RE.search(body).group("metadata") if METADATA_RE.search(body) else None)
            zh_info = zh_by_file.get(file_value, {})
            zh_hans = zh_info.get("prompt_zh_hans")
            zh_hant = to_traditional(zh_hans) if zh_hans else None
            records.append(
                {
                    "id": f"no-{number}",
                    "number": number,
                    "category": _category_from_gallery_file(gallery_path, text, metadata),
                    "category_zh_hans": zh_info.get("category_zh_hans"),
                    "category_zh_hant": zh_info.get("category_zh_hant"),
                    "title": title,
                    "source_title": f"Full catalog No. {number}: {title}",
                    "source_url": f"https://github.com/wuyoscar/gpt_image_2_skill/blob/main/{gallery_path.relative_to(source_root).as_posix()}",
                    "source_excerpt": None,
                    "prompt_en": prompt_match.group("text").strip(),
                    "prompt_zh_hans": zh_hans,
                    "prompt_zh_hant": zh_hant,
                    "size": metadata,
                    "file": file_value,
                    "platform": None,
                    "mode": "full",
                }
            )
    return sorted(records, key=lambda record: int(record["number"]))


def _load_community_records(source_root: Path) -> list[dict[str, Any]]:
    picks_path = source_root / DEFAULT_PICKS_PATH
    if not picks_path.is_file():
        raise FileNotFoundError(f"Expected {picks_path}; clone or pass the root of wuyoscar/gpt_image_2_skill")
    data = json.loads(picks_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Expected {picks_path} to contain a JSON list")
    records: list[dict[str, Any]] = []
    for record in data:
        if not isinstance(record, dict):
            continue
        prompt = _clean_text(record.get("prompt"))
        records.append({**record, "prompt_en": prompt, "mode": "community-picks"})
    return records


def _load_records(source_root: Path, source_mode: SourceMode = "full") -> list[dict[str, Any]]:
    if source_mode == "community-picks":
        return _load_community_records(source_root)
    return load_full_gallery_records(source_root)


def _record_slug(record: dict[str, Any], edition: PromptEdition = "all") -> str:
    number = record.get("number")
    edition_suffix = "" if edition == "all" else f"-{edition.replace('_', '-')}"
    if number is not None:
        return f"gpt-image-2-skill-no-{number}{edition_suffix}"
    record_id = _clean_text(record.get("id")) or _clean_text(record.get("title")) or new_id("sample")
    return f"gpt-image-2-skill-{_slugify(record_id)}{edition_suffix}"


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


def _prompts_for_record(record: dict[str, Any], edition: PromptEdition = "all") -> list[PromptIn]:
    prompts: list[PromptIn] = []
    en = _clean_text(record.get("prompt_en") or record.get("prompt"))
    zh_hans = _clean_text(record.get("prompt_zh_hans"))
    zh_hant = _clean_text(record.get("prompt_zh_hant")) or (to_traditional(zh_hans) if zh_hans else None)
    if edition == "en":
        return [PromptIn(language="en", text=en, is_primary=True)] if en else []
    if edition == "zh_hans":
        return [PromptIn(language="zh_hans", text=zh_hans, is_primary=True)] if zh_hans else []
    if edition == "zh_hant":
        return [PromptIn(language="zh_hant", text=zh_hant, is_primary=True)] if zh_hant else []
    if en:
        prompts.append(PromptIn(language="en", text=en, is_primary=True))
    if zh_hant:
        prompts.append(PromptIn(language="zh_hant", text=zh_hant, is_primary=not bool(en)))
    if zh_hans:
        prompts.append(PromptIn(language="zh_hans", text=zh_hans, is_primary=not bool(en or zh_hant)))
    if not prompts:
        title = _clean_text(record.get("title")) or "Untitled GPT Image 2 sample"
        prompts.append(PromptIn(language="en", text=title, is_primary=True))
    return prompts


def _replace_prompts_exactly(library_path: Path, repo: ItemRepository, item_id: str, prompts: list[PromptIn]) -> None:
    ts = now()
    with connect(library_path) as conn:
        conn.execute("DELETE FROM prompts WHERE item_id=?", (item_id,))
        for idx, prompt in enumerate(prompts):
            conn.execute(
                "INSERT INTO prompts(id,item_id,language,text,is_primary,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                (new_id("prm"), item_id, prompt.language, prompt.text, int(prompt.is_primary or idx == 0), ts, ts),
            )
        repo.rebuild_search(conn, item_id)
        conn.commit()

def _category_for_record(record: dict[str, Any], edition: PromptEdition = "all") -> str:
    if edition == "zh_hans":
        return _clean_text(record.get("category_zh_hans")) or _clean_text(record.get("category")) or "Sample prompts"
    if edition == "zh_hant":
        zh_hant_category = _clean_text(record.get("category_zh_hant"))
        zh_hans_category = _clean_text(record.get("category_zh_hans"))
        return (
            zh_hant_category
            or (to_traditional(zh_hans_category) if zh_hans_category else None)
            or _clean_text(record.get("category"))
            or "Sample prompts"
        )
    return _clean_text(record.get("category")) or "Sample prompts"


def import_gpt_image_2_skill(source: Path | str, library: Path | str, source_mode: SourceMode = "full", edition: PromptEdition = "all") -> ImportResult:
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

    for record in _load_records(source_root, source_mode):
        title = _clean_text(record.get("title")) or "Untitled GPT Image 2 sample"
        prompts = _prompts_for_record(record, edition)
        if not prompts:
            log.append(f"Skipping {record.get('id') or title}: missing {edition} prompt")
            continue
        slug = _record_slug(record, edition)
        if _already_imported(library_path, slug):
            continue
        category = _category_for_record(record, edition)
        platform = _clean_text(record.get("platform"))
        source_url = _clean_text(record.get("source_url"))
        tags = ["sample", "gpt_image_2_skill"]
        if record.get("mode") == "full":
            tags.append("full_catalog")
        tags.append(f"edition_{edition}")
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
                prompts=prompts,
                source_name=SOURCE_NAME,
                source_url=source_url,
                author=platform or SOURCE_NAME,
                notes=_notes(record),
            ),
            imported=True,
        )
        if edition != "all":
            _replace_prompts_exactly(library_path, repo, created.id, prompts)
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
    parser = argparse.ArgumentParser(description="Import wuyoscar/gpt_image_2_skill into a local Image Prompt Library.")
    parser.add_argument("--source", required=True, help="Path to a local clone of https://github.com/wuyoscar/gpt_image_2_skill")
    parser.add_argument("--library", default="library", help="Image Prompt Library data path, defaults to ./library")
    parser.add_argument("--source-mode", choices=["full", "community-picks"], default="full", help="Import the canonical full 162-reference gallery by default, or the 17-item community-picks JSON subset")
    parser.add_argument("--edition", choices=["all", "en", "zh_hans", "zh_hant"], default="all", help="Prompt/collection language edition to import. The three sample wrappers use en, zh_hans, or zh_hant.")
    args = parser.parse_args()
    print(import_gpt_image_2_skill(args.source, args.library, source_mode=args.source_mode, edition=args.edition).model_dump_json(indent=2))


if __name__ == "__main__":
    main()
