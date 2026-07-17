import json
import os
import subprocess
from pathlib import Path
from typing import Any

SOURCE_APP_VERSION = "0.1.0"
DEFAULT_LIBRARY_PATH = Path(__file__).resolve().parents[1] / "library"
DEFAULT_APP_STATE_PATH = Path.home() / ".image-prompt-library"
DEFAULT_AUTH_PATH = DEFAULT_APP_STATE_PATH / "auth.json"
DEFAULT_CONFIG_PATH = DEFAULT_APP_STATE_PATH / "config.json"
LIBRARY_STORAGE_ROOTS = frozenset({"originals", "thumbs", "previews", "generation-results", "generation-references"})


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


def resolve_auth_path() -> Path:
    configured = os.environ.get("IMAGE_PROMPT_LIBRARY_AUTH_PATH")
    return Path(configured).expanduser() if configured else DEFAULT_AUTH_PATH


def resolve_config_path() -> Path:
    configured = os.environ.get("IMAGE_PROMPT_LIBRARY_CONFIG_PATH")
    return Path(configured).expanduser() if configured else DEFAULT_CONFIG_PATH


def _path_identities(path: Path | str) -> tuple[Path, Path]:
    absolute = Path(os.path.abspath(Path(path).expanduser()))
    try:
        return absolute, absolute.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise ValueError(f"Could not safely resolve app-owned path boundary for {absolute}") from exc


def _path_is_within(candidate: Path, root: Path) -> bool:
    candidate_key = os.path.normcase(str(candidate))
    root_key = os.path.normcase(str(root))
    try:
        return os.path.commonpath((candidate_key, root_key)) == root_key
    except ValueError:
        return False


def resolve_library_storage_path(library_path: Path | str, relative_path: Path | str) -> Path:
    relative = Path(relative_path)
    if not relative.parts or relative.is_absolute() or ".." in relative.parts or relative.parts[0] not in LIBRARY_STORAGE_ROOTS:
        raise ValueError("Library storage path is invalid")
    library_absolute, library_resolved = _path_identities(library_path)
    _, storage_root_resolved = _path_identities(library_absolute / relative.parts[0])
    candidate_absolute, candidate_resolved = _path_identities(library_absolute / relative)
    expected_storage_root = library_resolved / relative.parts[0]
    if (
        os.path.normcase(str(storage_root_resolved)) != os.path.normcase(str(expected_storage_root))
        or not _path_is_within(storage_root_resolved, library_resolved)
        or not _path_is_within(candidate_absolute, library_absolute)
        or not _path_is_within(candidate_resolved, storage_root_resolved)
    ):
        raise ValueError(
            f"Active library storage path {relative.parts[0]} must resolve inside the active library. "
            "Move the library storage back inside the library, then restart. No database or credential files were changed."
        )
    return candidate_resolved


def validate_app_owned_paths(library_path: Path | str) -> None:
    library_absolute, library_resolved = _path_identities(library_path)
    for root_name in LIBRARY_STORAGE_ROOTS:
        resolve_library_storage_path(library_absolute, root_name)
    unsafe: list[tuple[str, Path, Path]] = []
    for env_name, configured_path in (
        ("IMAGE_PROMPT_LIBRARY_AUTH_PATH", resolve_auth_path()),
        ("IMAGE_PROMPT_LIBRARY_CONFIG_PATH", resolve_config_path()),
    ):
        path_absolute, path_resolved = _path_identities(configured_path)
        if _path_is_within(path_absolute, library_absolute) or _path_is_within(path_resolved, library_resolved):
            unsafe.append((env_name, path_absolute, path_resolved))
    if not unsafe:
        return
    problems = "; ".join(
        f"{env_name} must resolve outside the active library (configured path: {absolute}; resolved path: {resolved})"
        for env_name, absolute, resolved in unsafe
    )
    raise ValueError(
        f"{problems}. Move the app-owned file or active library so they do not overlap, set an external path "
        "or unset an unsafe override, then restart. No database or credential files were changed."
    )


def _read_local_config() -> dict[str, Any]:
    path = resolve_config_path()
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
