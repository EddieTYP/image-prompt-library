from __future__ import annotations
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from PIL import Image

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
    (library / original_rel).parent.mkdir(parents=True, exist_ok=True)
    (library / thumb_rel).parent.mkdir(parents=True, exist_ok=True)
    (library / preview_rel).parent.mkdir(parents=True, exist_ok=True)
    if not (library / original_rel).exists():
        (library / original_rel).write_bytes(data)
    thumb = image.copy(); thumb.thumbnail((420, 420))
    thumb.save(library / thumb_rel, "WEBP", quality=82)
    preview = image.copy(); preview.thumbnail((1400, 1400))
    preview.save(library / preview_rel, "WEBP", quality=88)
    return StoredImage(str(original_rel), str(thumb_rel), str(preview_rel), width, height, sha)
