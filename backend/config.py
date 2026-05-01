import os
import subprocess
from pathlib import Path

SOURCE_APP_VERSION = "0.1.0"
DEFAULT_LIBRARY_PATH = Path(__file__).resolve().parents[1] / "library"


def _git_describe_version(app_root: Path) -> str | None:
    if not (app_root / ".git").exists():
        return None
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--always", "--dirty"],
            cwd=str(app_root),
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    version = result.stdout.strip()
    return version or None


def resolve_app_version(root: Path | None = None) -> str:
    app_root = root if root is not None else Path(__file__).resolve().parents[1]
    version_file = app_root / "VERSION"
    if version_file.exists():
        version = version_file.read_text(encoding="utf-8").strip()
        if version:
            return version
    env_version = os.environ.get("IMAGE_PROMPT_LIBRARY_VERSION")
    if env_version:
        return env_version
    return _git_describe_version(app_root) or SOURCE_APP_VERSION


APP_VERSION = resolve_app_version()


def resolve_library_path(library_path=None) -> Path:
    configured_path = library_path if library_path is not None else os.environ.get("IMAGE_PROMPT_LIBRARY_PATH")
    path = Path(configured_path).expanduser() if configured_path is not None else DEFAULT_LIBRARY_PATH
    path.mkdir(parents=True, exist_ok=True)
    for child in ("originals", "thumbs", "previews"):
        (path / child).mkdir(parents=True, exist_ok=True)
    return path
