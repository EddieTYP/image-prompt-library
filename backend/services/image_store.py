from __future__ import annotations
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from PIL import Image

from backend.config import resolve_library_storage_path

MAX_IMAGE_PIXELS = 16_000_000

@dataclass
class StoredImage:
    original_path: str
    thumb_path: str
    preview_path: str
    width: int
    height: int
    file_sha256: str

def _rel(kind: str, sha: str, ext: str) -> Path:
    now = datetime.now(timezone.utc)
    return Path(kind) / f"{now.year:04d}" / f"{now.month:02d}" / f"{sha}{ext}"

def store_image(library_path: Path | str, data: bytes, filename: str = "image.png") -> StoredImage:
    library = Path(library_path)
    sha = hashlib.sha256(data).hexdigest()
    suffix = Path(filename).suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        suffix = ".png"
    with Image.open(BytesIO(data)) as im:
        width, height = im.size
        if width * height > MAX_IMAGE_PIXELS:
            raise ValueError(f"image too large: {width}x{height}")
        image = im.convert("RGB")
    original_rel = _rel("originals", sha, suffix)
    thumb_rel = _rel("thumbs", sha, ".webp")
    preview_rel = _rel("previews", sha, ".webp")
    original_path = resolve_library_storage_path(library, original_rel)
    thumb_path = resolve_library_storage_path(library, thumb_rel)
    preview_path = resolve_library_storage_path(library, preview_rel)
    original_path.parent.mkdir(parents=True, exist_ok=True)
    thumb_path.parent.mkdir(parents=True, exist_ok=True)
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    if not original_path.exists():
        original_path.write_bytes(data)
    thumb = image.copy(); thumb.thumbnail((420, 420))
    thumb.save(thumb_path, "WEBP", quality=82)
    preview = image.copy(); preview.thumbnail((1400, 1400))
    preview.save(preview_path, "WEBP", quality=88)
    return StoredImage(original_rel.as_posix(), thumb_rel.as_posix(), preview_rel.as_posix(), width, height, sha)
