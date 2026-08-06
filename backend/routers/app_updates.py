from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname, urlopen

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.config import resolve_app_version
from backend.db import connect
from backend.services.generation_jobs import GenerationJobRepository

router = APIRouter(tags=["app-updates"])

SEMVER_NUMBER = r"(?:0|[1-9]\d*)"
SEMVER_PRERELEASE_ID = rf"(?:{SEMVER_NUMBER}|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)"
RELEASE_RE = re.compile(
    rf"^v({SEMVER_NUMBER})\.({SEMVER_NUMBER})\.({SEMVER_NUMBER})"
    rf"(?:-({SEMVER_PRERELEASE_ID}(?:\.{SEMVER_PRERELEASE_ID})*))?"
    r"$"
)
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
DEFAULT_RELEASE_BASE_URL = "https://github.com/EddieTYP/image-prompt-library/releases/download"
UPDATE_TIMEOUT_SECONDS = 180
UPDATE_LOCK = threading.Lock()


class ReleaseCheckError(RuntimeError):
    """The release source could not be checked or its metadata was incomplete."""


class ActiveGenerationJobs(BaseModel):
    running: int = 0
    queued: int = 0

    @property
    def total(self) -> int:
        return self.running + self.queued


class UpdateStatus(BaseModel):
    current_version: str
    latest_version: str | None = None
    update_available: bool = False
    release_url: str | None = None
    update_command: str | None = None
    checked_at: str
    error: str | None = None
    update_capability: str = "unknown"
    update_reason: str | None = None
    service_mode: str = "unknown"
    active_generation_jobs: ActiveGenerationJobs = Field(default_factory=ActiveGenerationJobs)
    can_restart: bool = False
    requires_manual_restart: bool = True


class AppUpdateRequest(BaseModel):
    target_version: str | None = None
    cancel_active_generation_jobs: bool = False


class AppUpdateResult(BaseModel):
    status: str
    target_version: str
    cancelled_generation_jobs: int = 0
    restart_mode: str = "manual"
    requires_manual_restart: bool = True
    message: str
    stdout: str = ""
    stderr: str = ""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def release_base_url() -> str:
    return os.environ.get("IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL", DEFAULT_RELEASE_BASE_URL).rstrip("/")


def app_root() -> Path:
    return Path(__file__).resolve().parents[2]


def appctl_path() -> Path:
    return app_root() / "scripts" / "appctl.sh"



def release_asset_urls(version: str) -> dict[str, str]:
    base = release_base_url()
    if base.startswith("file://"):
        return {
            "artifact": f"{base}/image-prompt-library-{version}.tar.gz",
            "checksum": f"{base}/image-prompt-library-{version}.tar.gz.sha256",
            "manifest": f"{base}/image-prompt-library-{version}.manifest.json",
        }
    return {
        "artifact": f"{base}/{version}/image-prompt-library-{version}.tar.gz",
        "checksum": f"{base}/{version}/image-prompt-library-{version}.tar.gz.sha256",
        "manifest": f"{base}/{version}/image-prompt-library-{version}.manifest.json",
    }


def open_url_text(url: str, timeout: int = 5) -> str:
    with urlopen(url, timeout=timeout) as response:  # noqa: S310 - controlled release URLs or local file:// override.
        return response.read().decode("utf-8")


def open_url_bytes(url: str, timeout: int = 5) -> bytes:
    with urlopen(url, timeout=timeout) as response:  # noqa: S310 - controlled release URLs or local file:// override.
        return response.read()


def validate_version(version: str) -> str:
    version = version.strip()
    if not RELEASE_RE.match(version):
        raise HTTPException(status_code=400, detail="Invalid update version")
    return version


def version_sort_key(version: str) -> tuple[int, int, int, int, tuple[tuple[int, int | str], ...]]:
    match = RELEASE_RE.match(version)
    if not match:
        return (0, 0, 0, 0, ((1, version),))
    prerelease = match.group(4)
    if not prerelease:
        return (int(match.group(1)), int(match.group(2)), int(match.group(3)), 1, ())
    segments: list[tuple[int, int | str]] = []
    for segment in prerelease.split("."):
        segments.append((0, int(segment)) if segment.isdigit() else (1, segment))
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)), 0, tuple(segments))


def is_stable_version(version: str) -> bool:
    return "-" not in version.split("+", 1)[0]


def local_release_root() -> Path | None:
    base = release_base_url()
    parsed = urlparse(base)
    if parsed.scheme != "file":
        return None
    path = unquote(parsed.path)
    if parsed.netloc and parsed.netloc.lower() not in {"", "localhost"}:
        path = f"//{parsed.netloc}{path}"
    return Path(url2pathname(path))


def local_release_versions() -> list[str]:
    root = local_release_root()
    if root is None:
        return []
    if not root.is_dir():
        raise ReleaseCheckError("Local release directory is unavailable")
    versions: list[str] = []
    failures: list[str] = []
    for manifest in root.glob("image-prompt-library-*.manifest.json"):
        version = manifest.name.removeprefix("image-prompt-library-").removesuffix(".manifest.json")
        if not RELEASE_RE.match(version) or not is_stable_version(version):
            continue
        try:
            verify_complete_release(version)
        except Exception as exc:
            failures.append(str(exc))
            continue
        versions.append(version)
    if failures and not versions:
        raise ReleaseCheckError("Local release assets failed verification")
    return sorted(versions, key=version_sort_key, reverse=True)


def github_release_versions(limit: int = 10) -> list[str]:
    api_url = "https://api.github.com/repos/EddieTYP/image-prompt-library/releases?per_page=100"
    try:
        data = json.loads(open_url_text(api_url, timeout=5))
    except Exception as exc:
        raise ReleaseCheckError("Release check failed") from exc
    if not isinstance(data, list):
        raise ReleaseCheckError("Release check returned invalid data")
    versions: list[str] = []
    accepted = 0
    for release in data:
        if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
            continue
        tag = str(release.get("tag_name") or "").strip()
        if not tag or not RELEASE_RE.match(tag) or not is_stable_version(tag):
            continue
        assets = release.get("assets")
        if not isinstance(assets, list):
            raise ReleaseCheckError("Release check returned invalid asset data")
        asset_names = {str(asset.get("name")) for asset in assets if isinstance(asset, dict)}
        required = {
            f"image-prompt-library-{tag}.tar.gz",
            f"image-prompt-library-{tag}.tar.gz.sha256",
            f"image-prompt-library-{tag}.manifest.json",
        }
        if required.issubset(asset_names):
            versions.append(tag)
            accepted += 1
            if accepted >= limit:
                break
    return sorted(set(versions), key=version_sort_key, reverse=True)


def latest_complete_release() -> str | None:
    if local_release_root() is not None:
        local_versions = local_release_versions()
        return local_versions[0] if local_versions else None
    versions = github_release_versions()
    return versions[0] if versions else None


def verify_complete_release(version: str) -> dict[str, str]:
    version = validate_version(version)
    urls = release_asset_urls(version)
    manifest_raw = open_url_text(urls["manifest"])
    checksum_raw = open_url_text(urls["checksum"])
    try:
        manifest = json.loads(manifest_raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=409, detail="Release manifest is not valid JSON") from exc
    if not isinstance(manifest, dict):
        raise HTTPException(status_code=409, detail="Release manifest is not an object")
    expected_artifact = f"image-prompt-library-{version}.tar.gz"
    if (
        manifest.get("name") != "image-prompt-library"
        or manifest.get("version") != version
        or manifest.get("artifact") != expected_artifact
    ):
        raise HTTPException(status_code=409, detail="Release manifest identity mismatch")
    artifact_bytes = open_url_bytes(urls["artifact"])
    actual_sha = hashlib.sha256(artifact_bytes).hexdigest()
    expected_sha = str(manifest.get("sha256") or "").strip()
    checksum_lines = [line.strip() for line in checksum_raw.splitlines() if line.strip()]
    checksum_match = re.match(r"^([0-9a-fA-F]{64})(?:\s+.*)?$", checksum_lines[0]) if len(checksum_lines) == 1 else None
    if not SHA256_RE.match(expected_sha):
        raise HTTPException(status_code=409, detail="Release manifest SHA256 is invalid")
    if checksum_match is None:
        raise HTTPException(status_code=409, detail="Release checksum sidecar is invalid")
    checksum_sha = checksum_match.group(1)
    if expected_sha.lower() != checksum_sha.lower():
        raise HTTPException(status_code=409, detail="Release checksum sidecar mismatch")
    if expected_sha.lower() != actual_sha.lower():
        raise HTTPException(status_code=409, detail="Release manifest checksum mismatch")
    return {"artifact_url": urls["artifact"], "sha256": actual_sha}


def active_generation_jobs(library_path: Path) -> ActiveGenerationJobs:
    with connect(library_path) as conn:
        queued = conn.execute("SELECT COUNT(*) FROM generation_jobs WHERE status='queued'").fetchone()[0]
        running = conn.execute("SELECT COUNT(*) FROM generation_jobs WHERE status='running'").fetchone()[0]
    return ActiveGenerationJobs(queued=int(queued), running=int(running))


def cancel_active_generation_jobs(library_path: Path) -> int:
    repo = GenerationJobRepository(library_path)
    return repo.cancel_active_jobs()


def launchd_candidate_labels() -> list[str]:
    labels = [
        os.environ.get("IMAGE_PROMPT_LIBRARY_SERVICE_LABEL", ""),
        "com.eddietyp.image-prompt-library",
        "com.edward.image-prompt-library",
    ]
    seen: set[str] = set()
    return [label for label in labels if label and not (label in seen or seen.add(label))]


def detected_launchd_service_label() -> str | None:
    if sys.platform != "darwin" or not appctl_path().exists():
        return None
    for label in launchd_candidate_labels():
        result = subprocess.run(["bash", str(appctl_path()), "service", "status", "--label", label], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and "state =" in result.stdout:
            return label
    return None


def detect_service_mode() -> str:
    if sys.platform != "darwin":
        return "not_applicable"
    if not appctl_path().exists():
        return "unknown"
    return "launchd" if detected_launchd_service_label() else "foreground"


def detect_update_capability() -> tuple[str, str | None]:
    """Return the truthful update path for this app checkout."""
    root = app_root()
    if (root / ".git").exists() or not (root / "VERSION").is_file():
        return "source", "source_checkout_managed_outside_app"
    if sys.platform == "win32":
        return "command_only", "windows_requires_powershell_cli"
    return "in_app", None


def run_installer_update(*, target_version: str) -> dict[str, str | bool]:
    update_capability, update_reason = detect_update_capability()
    if update_capability != "in_app":
        raise HTTPException(
            status_code=409,
            detail={"error": "update_unavailable", "update_capability": update_capability, "reason": update_reason},
        )
    env = os.environ.copy()
    env.setdefault("PYTHON", sys.executable)
    command = ["bash", str(appctl_path()), "update", "--version", target_version]
    result = subprocess.run(command, cwd=str(app_root()), env=env, text=True, capture_output=True, timeout=UPDATE_TIMEOUT_SECONDS)
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail={"error": "update_failed", "stderr": result.stderr[-2000:]})
    return {"ok": True, "target_version": target_version, "stdout": result.stdout[-4000:], "stderr": result.stderr[-4000:]}


def schedule_launchd_restart() -> None:
    label = os.environ.get("IMAGE_PROMPT_LIBRARY_SERVICE_LABEL") or detected_launchd_service_label() or "com.eddietyp.image-prompt-library"
    command = 'sleep 1; exec "$1" service restart --label "$2"'
    subprocess.Popen(
        ["/bin/sh", "-c", command, "image-prompt-library-restart", str(appctl_path()), label],
        cwd=str(app_root()),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


@router.get("/update-status", response_model=UpdateStatus)
def get_update_status(request: Request):
    current = os.environ.get("IMAGE_PROMPT_LIBRARY_VERSION") or resolve_app_version(app_root())
    active = active_generation_jobs(request.app.state.library_path)
    update_capability, update_reason = detect_update_capability()
    service_mode = detect_service_mode()
    if update_capability == "source":
        return UpdateStatus(
            current_version=current,
            checked_at=utc_now(),
            update_capability=update_capability,
            update_reason=update_reason,
            service_mode=service_mode,
            active_generation_jobs=active,
            can_restart=service_mode == "launchd",
            requires_manual_restart=service_mode != "launchd",
        )
    try:
        latest = latest_complete_release()
    except (ReleaseCheckError, HTTPException, URLError, OSError, ValueError, json.JSONDecodeError) as exc:
        return UpdateStatus(
            current_version=current,
            checked_at=utc_now(),
            error="Could not check for updates",
            update_capability=update_capability,
            update_reason=update_reason,
            service_mode=service_mode,
            active_generation_jobs=active,
            can_restart=service_mode == "launchd",
            requires_manual_restart=service_mode != "launchd",
        )
    update_available = bool(latest and version_sort_key(latest) > version_sort_key(current))
    return UpdateStatus(
        current_version=current,
        latest_version=latest,
        update_available=update_available,
        release_url=f"https://github.com/EddieTYP/image-prompt-library/releases/tag/{latest}" if latest else None,
        update_command=f"image-prompt-library update --version {latest}" if latest and update_capability != "source" else None,
        checked_at=utc_now(),
        update_capability=update_capability,
        update_reason=update_reason,
        service_mode=service_mode,
        active_generation_jobs=active,
        can_restart=service_mode == "launchd",
        requires_manual_restart=service_mode != "launchd",
    )


@router.post("/app-update/jobs", response_model=AppUpdateResult)
def start_app_update(payload: AppUpdateRequest, request: Request):
    update_capability, update_reason = detect_update_capability()
    if update_capability != "in_app":
        raise HTTPException(
            status_code=409,
            detail={
                "error": "update_unavailable",
                "update_capability": update_capability,
                "reason": update_reason,
            },
        )
    if not UPDATE_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail={"error": "update_in_progress"})
    try:
        if payload.target_version:
            target_version = validate_version(payload.target_version)
        else:
            try:
                target_version = validate_version(latest_complete_release() or "")
            except (ReleaseCheckError, HTTPException, URLError, OSError, ValueError, json.JSONDecodeError) as exc:
                raise HTTPException(status_code=503, detail={"error": "release_check_failed"}) from exc
        active = active_generation_jobs(request.app.state.library_path)
        if active.total and not payload.cancel_active_generation_jobs:
            raise HTTPException(status_code=409, detail={"error": "active_generation_jobs", "running_count": active.running, "queued_count": active.queued})
        verify_complete_release(target_version)
        cancelled = cancel_active_generation_jobs(request.app.state.library_path) if payload.cancel_active_generation_jobs else 0
        active = active_generation_jobs(request.app.state.library_path)
        if active.total:
            raise HTTPException(status_code=409, detail={"error": "active_generation_jobs", "running_count": active.running, "queued_count": active.queued})
        update_result = run_installer_update(target_version=target_version)
        service_mode = detect_service_mode()
        restart_mode = "launchd" if service_mode == "launchd" else "manual"
        if restart_mode == "launchd":
            schedule_launchd_restart()
        return AppUpdateResult(
            status="installed",
            target_version=target_version,
            cancelled_generation_jobs=cancelled,
            restart_mode=restart_mode,
            requires_manual_restart=restart_mode != "launchd",
            message="Update installed. Restart the app to use the new version." if restart_mode != "launchd" else "Update installed. The macOS service will restart automatically.",
            stdout=str(update_result.get("stdout") or ""),
            stderr=str(update_result.get("stderr") or ""),
        )
    finally:
        UPDATE_LOCK.release()
