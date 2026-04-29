import os
from pathlib import Path

SOURCE_APP_VERSION = "0.1.0"
DEFAULT_LIBRARY_PATH = Path(__file__).resolve().parents[1] / "library"


def resolve_app_version(root: Path | None = None) -> str:
    app_root = root if root is not None else Path(__file__).resolve().parents[1]
    version_file = app_root / "VERSION"
    if version_file.exists():
        version = version_file.read_text(encoding="utf-8").strip()
        if version:
            return version
    return os.environ.get("IMAGE_PROMPT_LIBRARY_VERSION", SOURCE_APP_VERSION)


APP_VERSION = resolve_app_version()


def resolve_library_path(library_path=None) -> Path:
    configured_path = library_path if library_path is not None else os.environ.get("IMAGE_PROMPT_LIBRARY_PATH")
    path = Path(configured_path).expanduser() if configured_path is not None else DEFAULT_LIBRARY_PATH
    path.mkdir(parents=True, exist_ok=True)
    for child in ("originals", "thumbs", "previews"):
        (path / child).mkdir(parents=True, exist_ok=True)
    return path
