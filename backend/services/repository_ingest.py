from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image

from backend.repositories import new_id
from backend.schemas import (
    ImportDraftCreate,
    ImportDraftMedia,
    PromptIn,
    RepositoryIngestRequest,
    RepositoryIngestResult,
)
from backend.services.import_drafts import ImportDraftRepository

HEADING_RE = re.compile(r"^(?P<marks>#{1,6})\s+(?P<title>.+?)\s*$", re.MULTILINE)
IMAGE_RE = re.compile(r"!\[[^\]]*\]\((?P<path>[^)\s]+)(?:\s+\"[^\"]*\")?\)")
FENCE_RE = re.compile(r"```(?:text|prompt|markdown)?\s*\n(?P<text>.*?)\n```", re.DOTALL | re.IGNORECASE)
BACKTICK_IMAGE_RE = re.compile(r"`(?P<path>[^`]+\.(?:png|jpe?g|webp|gif))`", re.IGNORECASE)


def _clean_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _repo_name(path: Path, repo_url: str | None) -> str:
    if repo_url:
        parsed = urlparse(repo_url.rstrip("/"))
        name = Path(parsed.path).name.removesuffix(".git")
        if name:
            return name
    return path.name


def _source_url(repo_url: str | None, ref: str | None, relative: str) -> str | None:
    if not repo_url:
        return None
    clean = repo_url.rstrip("/").removesuffix(".git")
    branch = ref or "main"
    return f"{clean}/blob/{branch}/{relative}"


def _language_for_prompt(text: str) -> str:
    return "zh_hans" if re.search(r"[\u4e00-\u9fff]", text) else "en"


def _sections(markdown: str) -> list[dict[str, object]]:
    headings = list(HEADING_RE.finditer(markdown))
    top_title: str | None = None
    sections: list[dict[str, object]] = []
    for index, heading in enumerate(headings):
        level = len(heading.group("marks"))
        title = heading.group("title").strip()
        if level == 1 and top_title is None:
            top_title = title
            continue
        end = headings[index + 1].start() if index + 1 < len(headings) else len(markdown)
        body = markdown[heading.end():end]
        if FENCE_RE.search(body):
            sections.append({"title": title, "cluster": top_title, "body": body})
    if sections:
        return sections
    prompt = FENCE_RE.search(markdown)
    if prompt:
        return [{"title": top_title or "Untitled repository prompt", "cluster": top_title, "body": markdown}]
    return []


def _image_paths(body: str) -> list[str]:
    values = [match.group("path").strip() for match in IMAGE_RE.finditer(body)]
    values += [match.group("path").strip() for match in BACKTICK_IMAGE_RE.finditer(body)]
    return list(dict.fromkeys(value for value in values if value))


def _stage_image(library_path: Path, source_root: Path, image_value: str, batch_id: str, warnings: list[str]) -> ImportDraftMedia | None:
    source_path = (source_root / image_value).resolve()
    try:
        source_path.relative_to(source_root)
    except ValueError:
        warnings.append(f"Image path escapes repository root: {image_value}")
        return None
    if not source_path.is_file():
        warnings.append(f"Image file not found: {image_value}")
        return None
    sha = hashlib.sha256(source_path.read_bytes()).hexdigest()
    staged_rel = Path("import-staging") / batch_id / f"{source_path.stem}-{sha[:12]}{source_path.suffix.lower()}"
    staged_abs = library_path / staged_rel
    staged_abs.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, staged_abs)
    width = None
    height = None
    try:
        with Image.open(source_path) as image:
            width, height = image.size
    except Exception:
        warnings.append(f"Could not read image dimensions: {image_value}")
    return ImportDraftMedia(
        original_path=image_value,
        staged_path=staged_rel.as_posix(),
        kind="local_file",
        role="result_image",
        width=width,
        height=height,
        file_sha256=sha,
    )


def ingest_repository_to_drafts(request: RepositoryIngestRequest, library_path: Path | str) -> RepositoryIngestResult:
    source_root = Path(request.path).expanduser().resolve()
    if not source_root.is_dir():
        raise FileNotFoundError(f"Repository path not found: {request.path}")
    library = Path(library_path)
    repo = ImportDraftRepository(library)
    batch_id = new_id("rimp")
    drafts = []
    log: list[str] = []
    source_name = _repo_name(source_root, request.repo_url)

    for markdown_path in sorted(source_root.rglob("*.md")):
        if any(part.startswith(".") for part in markdown_path.relative_to(source_root).parts):
            continue
        relative = markdown_path.relative_to(source_root).as_posix()
        markdown = markdown_path.read_text(encoding="utf-8")
        for section in _sections(markdown):
            body = str(section["body"])
            prompt_match = FENCE_RE.search(body)
            if not prompt_match:
                continue
            prompt_text = prompt_match.group("text").strip()
            if not prompt_text:
                continue
            warnings: list[str] = []
            media = [
                media_item
                for image_value in _image_paths(body)
                if (media_item := _stage_image(library, source_root, image_value, batch_id, warnings)) is not None
            ]
            language = _language_for_prompt(prompt_text)
            draft = repo.create_draft(ImportDraftCreate(
                source_type="repository",
                source_name=source_name,
                source_url=_source_url(request.repo_url, request.source_ref, relative),
                source_ref=request.source_ref,
                source_path=relative,
                title=str(section["title"]),
                suggested_cluster_name=_clean_text(section.get("cluster")) or source_name,
                prompts=[PromptIn(
                    language=language,
                    text=prompt_text,
                    is_primary=True,
                    is_original=True,
                    provenance={
                        "kind": "source",
                        "source_language": language,
                        "derived_from": None,
                        "method": None,
                    },
                )],
                media=media,
                warnings=warnings,
                confidence=0.85 if media else 0.65,
            ))
            drafts.append(draft)
    if not drafts:
        log.append("No markdown prompt sections found")
    return RepositoryIngestResult(id=batch_id, draft_count=len(drafts), status="completed", drafts=drafts, log="\n".join(log))
