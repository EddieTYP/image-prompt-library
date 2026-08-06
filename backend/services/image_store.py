from __future__ import annotations
import hashlib
import os
import tempfile
from contextlib import suppress
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

def _atomic_write_bytes(path: Path, data: bytes) -> None:
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        with suppress(OSError):
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)

def _file_sha256(path: Path) -> str | None:
    try:
        with path.open("rb") as stream:
            digest = hashlib.sha256()
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
            return digest.hexdigest()
    except FileNotFoundError:
        return None

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
    if _file_sha256(original_path) != sha:
        _atomic_write_bytes(original_path, data)
    thumb = image.copy(); thumb.thumbnail((420, 420))
    thumb_bytes = BytesIO()
    thumb.save(thumb_bytes, "WEBP", quality=82)
    _atomic_write_bytes(thumb_path, thumb_bytes.getvalue())
    preview = image.copy(); preview.thumbnail((1400, 1400))
    preview_bytes = BytesIO()
    preview.save(preview_bytes, "WEBP", quality=88)
    _atomic_write_bytes(preview_path, preview_bytes.getvalue())
    return StoredImage(original_rel.as_posix(), thumb_rel.as_posix(), preview_rel.as_posix(), width, height, sha)
