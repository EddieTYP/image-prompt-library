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
from urllib.request import urlopen

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.config import resolve_app_version
from backend.db import connect
from backend.services.generation_jobs import GenerationJobRepository

router = APIRouter(tags=["app-updates"])

RELEASE_RE = re.compile(r"^v?\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
DEFAULT_RELEASE_BASE_URL = "https://github.com/EddieTYP/image-prompt-library/releases/download"
UPDATE_TIMEOUT_SECONDS = 180
UPDATE_LOCK = threading.Lock()


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


def version_sort_key(version: str) -> tuple[int, int, int, str]:
    match = re.match(r"^v?(\d+)\.(\d+)\.(\d+)(.*)$", version)
    if not match:
        return (0, 0, 0, version)
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)), match.group(4) or "")


def local_release_versions() -> list[str]:
    base = release_base_url()
    if not base.startswith("file://"):
        return []
    root = Path(base.removeprefix("file://"))
    if not root.is_dir():
        return []
    versions: list[str] = []
    for manifest in root.glob("image-prompt-library-*.manifest.json"):
        version = manifest.name.removeprefix("image-prompt-library-").removesuffix(".manifest.json")
        try:
            verify_complete_release(version)
        except Exception:
            continue
        versions.append(version)
    return sorted(versions, key=version_sort_key, reverse=True)


def github_release_versions(limit: int = 10) -> list[str]:
    api_url = "https://api.github.com/repos/EddieTYP/image-prompt-library/releases"
    try:
        data = json.loads(open_url_text(api_url, timeout=5))
    except Exception:
        return []
    versions: list[str] = []
    for release in data[:limit]:
        tag = str(release.get("tag_name") or "").strip()
        if not tag or not RELEASE_RE.match(tag):
            continue
        asset_names = {str(asset.get("name")) for asset in release.get("assets", []) if isinstance(asset, dict)}
        required = {
            f"image-prompt-library-{tag}.tar.gz",
            f"image-prompt-library-{tag}.tar.gz.sha256",
            f"image-prompt-library-{tag}.manifest.json",
        }
        if required.issubset(asset_names):
            versions.append(tag)
    return versions


def latest_complete_release() -> str | None:
    local_versions = local_release_versions()
    if local_versions:
        return local_versions[0]
    versions = github_release_versions()
    return versions[0] if versions else None


def verify_complete_release(version: str) -> dict[str, str]:
    version = validate_version(version)
    urls = release_asset_urls(version)
    manifest_raw = open_url_text(urls["manifest"])
    checksum_raw = open_url_text(urls["checksum"])
    manifest = json.loads(manifest_raw)
    artifact_bytes = open_url_bytes(urls["artifact"])
    actual_sha = hashlib.sha256(artifact_bytes).hexdigest()
    expected_sha = str(manifest.get("sha256") or "").strip()
    checksum_sha = checksum_raw.strip().split()[0] if checksum_raw.strip() else ""
    if expected_sha and expected_sha != actual_sha:
        raise HTTPException(status_code=409, detail="Release manifest checksum mismatch")
    if checksum_sha and checksum_sha != actual_sha:
        raise HTTPException(status_code=409, detail="Release sha256 checksum mismatch")
    return {"artifact_url": urls["artifact"], "sha256": actual_sha}


def active_generation_jobs(library_path: Path) -> ActiveGenerationJobs:
    with connect(library_path) as conn:
        queued = conn.execute("SELECT COUNT(*) FROM generation_jobs WHERE status='queued'").fetchone()[0]
        running = conn.execute("SELECT COUNT(*) FROM generation_jobs WHERE status='running'").fetchone()[0]
    return ActiveGenerationJobs(queued=int(queued), running=int(running))


def cancel_active_generation_jobs(library_path: Path) -> int:
    repo = GenerationJobRepository(library_path)
    jobs = repo.list_jobs(limit=1000).jobs
    cancelled = 0
    for job in jobs:
        if job.status in {"queued", "running"}:
            repo.cancel_job(job.id)
            cancelled += 1
    return cancelled


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


def run_installer_update(*, target_version: str) -> dict[str, str | bool]:
    env = os.environ.copy()
    env.setdefault("PYTHON", sys.executable)
    command = ["bash", str(appctl_path()), "update", "--version", target_version]
    result = subprocess.run(command, cwd=str(app_root()), env=env, text=True, capture_output=True, timeout=UPDATE_TIMEOUT_SECONDS)
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail={"error": "update_failed", "stderr": result.stderr[-2000:]})
    return {"ok": True, "target_version": target_version, "stdout": result.stdout[-4000:], "stderr": result.stderr[-4000:]}


def schedule_launchd_restart() -> None:
    label = os.environ.get("IMAGE_PROMPT_LIBRARY_SERVICE_LABEL") or detected_launchd_service_label() or "com.eddietyp.image-prompt-library"
    command = f"sleep 1; exec {str(appctl_path())!r} service restart --label {label!r}"
    subprocess.Popen(["/bin/sh", "-c", command], cwd=str(app_root()), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


@router.get("/update-status", response_model=UpdateStatus)
def get_update_status(request: Request):
    current = os.environ.get("IMAGE_PROMPT_LIBRARY_VERSION") or resolve_app_version(app_root())
    active = active_generation_jobs(request.app.state.library_path)
    service_mode = detect_service_mode()
    try:
        latest = latest_complete_release()
    except (HTTPException, URLError, OSError, ValueError, json.JSONDecodeError) as exc:
        return UpdateStatus(
            current_version=current,
            checked_at=utc_now(),
            error="Could not check for updates",
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
        update_command=f"image-prompt-library update --version {latest}" if latest else None,
        checked_at=utc_now(),
        service_mode=service_mode,
        active_generation_jobs=active,
        can_restart=service_mode == "launchd",
        requires_manual_restart=service_mode != "launchd",
    )


@router.post("/app-update/jobs", response_model=AppUpdateResult)
def start_app_update(payload: AppUpdateRequest, request: Request):
    if not UPDATE_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail={"error": "update_in_progress"})
    try:
        target_version = validate_version(payload.target_version or latest_complete_release() or "")
        active = active_generation_jobs(request.app.state.library_path)
        if active.total and not payload.cancel_active_generation_jobs:
            raise HTTPException(status_code=409, detail={"error": "active_generation_jobs", "running_count": active.running, "queued_count": active.queued})
        verify_complete_release(target_version)
        cancelled = cancel_active_generation_jobs(request.app.state.library_path) if payload.cancel_active_generation_jobs else 0
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
