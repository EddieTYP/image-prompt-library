import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import create_app
from backend.services.generation_jobs import GenerationJobRepository
from backend.schemas import GenerationJobCreate


def write_release_assets(root: Path, version: str = "v9.9.9-beta"):
    root.mkdir(parents=True, exist_ok=True)
    artifact = root / f"image-prompt-library-{version}.tar.gz"
    checksum = root / f"image-prompt-library-{version}.tar.gz.sha256"
    manifest = root / f"image-prompt-library-{version}.manifest.json"
    artifact.write_bytes(b"fake release artifact")
    digest = "6266cf02ee273cac9e41c184e209377d603ef8d7242298cfa37a314f695a3e5c"
    checksum.write_text(digest + f"  {artifact.name}\n", encoding="utf-8")
    manifest.write_text(json.dumps({"version": version, "sha256": digest}), encoding="utf-8")
    return root


def test_update_status_detects_complete_local_release_assets(tmp_path, monkeypatch):
    release_dir = write_release_assets(tmp_path / "release", "v9.9.9-beta")
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL", release_dir.as_uri())
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_VERSION", "v9.9.8-beta")
    app = create_app(library_path=tmp_path / "library")
    client = TestClient(app)

    payload = client.get("/api/update-status").json()

    assert payload["current_version"] == "v9.9.8-beta"
    assert payload["latest_version"] == "v9.9.9-beta"
    assert payload["update_available"] is True
    assert payload["update_command"] == "image-prompt-library update --version v9.9.9-beta"
    assert payload["active_generation_jobs"]["running"] == 0
    assert payload["active_generation_jobs"]["queued"] == 0
    assert payload["service_mode"] in {"launchd", "foreground", "unknown", "not_applicable"}


def test_update_requires_explicit_cancel_when_generation_jobs_are_active(tmp_path, monkeypatch):
    release_dir = write_release_assets(tmp_path / "release", "v9.9.9-beta")
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL", release_dir.as_uri())
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_VERSION", "v9.9.8-beta")
    library = tmp_path / "library"
    repo = GenerationJobRepository(library)
    repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="queued prompt"))
    running = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="running prompt"))
    repo.mark_running(running.id)
    app = create_app(library_path=library)
    client = TestClient(app)

    response = client.post("/api/app-update/jobs", json={"target_version": "v9.9.9-beta", "cancel_active_generation_jobs": False})

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["error"] == "active_generation_jobs"
    assert detail["running_count"] == 1
    assert detail["queued_count"] == 1


def test_cancel_and_update_cancels_active_jobs_and_runs_installer(tmp_path, monkeypatch):
    release_dir = write_release_assets(tmp_path / "release", "v9.9.9-beta")
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL", release_dir.as_uri())
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_VERSION", "v9.9.8-beta")
    library = tmp_path / "library"
    repo = GenerationJobRepository(library)
    queued = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="queued prompt"))
    running = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="running prompt"))
    repo.mark_running(running.id)
    calls = []

    def fake_run_installer_update(*, target_version: str):
        calls.append(target_version)
        return {"ok": True, "target_version": target_version, "stdout": "installed", "stderr": ""}

    monkeypatch.setattr("backend.routers.app_updates.run_installer_update", fake_run_installer_update)
    app = create_app(library_path=library)
    client = TestClient(app)

    response = client.post("/api/app-update/jobs", json={"target_version": "v9.9.9-beta", "cancel_active_generation_jobs": True})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "installed"
    assert payload["target_version"] == "v9.9.9-beta"
    assert payload["cancelled_generation_jobs"] == 2
    assert calls == ["v9.9.9-beta"]
    assert repo.get_job(queued.id).status == "cancelled"
    assert repo.get_job(running.id).status == "cancelled"


def test_frontend_static_update_wizard_contract():
    root = Path(__file__).resolve().parents[1]
    client = (root / "frontend" / "src" / "api" / "client.ts").read_text(encoding="utf-8")
    config = (root / "frontend" / "src" / "components" / "ConfigPanel.tsx").read_text(encoding="utf-8")
    topbar = (root / "frontend" / "src" / "components" / "TopBar.tsx").read_text(encoding="utf-8")
    app = (root / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")

    assert "updateStatus:" in client
    assert "startAppUpdate:" in client
    assert "App update" in config
    assert "Cancel jobs and update" in config
    assert "Update later" in config
    assert "Wait" not in config and "等待" not in config
    assert "Restart required" in config
    assert "Update available" in app
    assert "Restart required" in app
    assert "updateBadgeLabel" in topbar
