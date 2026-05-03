import json
import os
import subprocess
from pathlib import Path
from typing import Any

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


def _config_path() -> Path:
    configured = os.environ.get("IMAGE_PROMPT_LIBRARY_CONFIG_PATH")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".image-prompt-library" / "config.json"


def _read_local_config() -> dict[str, Any]:
    path = _config_path()
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _bool_from_env(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def resolve_hidden_features() -> dict[str, dict[str, bool]]:
    payload = _read_local_config()
    camelot = payload.get("camelot") if isinstance(payload, dict) else None
    percival = True
    if isinstance(camelot, dict) and isinstance(camelot.get("percival"), bool):
        percival = camelot["percival"]
    env_percival = _bool_from_env(os.environ.get("IMAGE_PROMPT_LIBRARY_CAMELOT_PERCIVAL"))
    if env_percival is not None:
        percival = env_percival
    return {"camelot": {"percival": percival}}


def resolve_library_path(library_path=None) -> Path:
    configured_path = library_path if library_path is not None else os.environ.get("IMAGE_PROMPT_LIBRARY_PATH")
    path = Path(configured_path).expanduser() if configured_path is not None else DEFAULT_LIBRARY_PATH
    path.mkdir(parents=True, exist_ok=True)
    for child in ("originals", "thumbs", "previews"):
        (path / child).mkdir(parents=True, exist_ok=True)
    return path
