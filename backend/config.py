from pathlib import Path

APP_VERSION = "0.1.0"
DEFAULT_LIBRARY_PATH = Path(__file__).resolve().parents[1] / "library"

def resolve_library_path(library_path=None) -> Path:
    path = Path(library_path) if library_path is not None else DEFAULT_LIBRARY_PATH
    path.mkdir(parents=True, exist_ok=True)
    for child in ("originals", "thumbs", "previews"):
        (path / child).mkdir(parents=True, exist_ok=True)
    return path
