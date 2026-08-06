import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.services.generation_jobs import GenerationJobRepository
from backend.schemas import GenerationJobCreate


def write_release_assets(root: Path, version: str = "v9.9.9"):
    root.mkdir(parents=True, exist_ok=True)
    artifact = root / f"image-prompt-library-{version}.tar.gz"
    checksum = root / f"image-prompt-library-{version}.tar.gz.sha256"
    manifest = root / f"image-prompt-library-{version}.manifest.json"
    artifact.write_bytes(b"fake release artifact")
    digest = "6266cf02ee273cac9e41c184e209377d603ef8d7242298cfa37a314f695a3e5c"
    checksum.write_text(digest + f"  {artifact.name}\n", encoding="utf-8")
    manifest.write_text(json.dumps({"name": "image-prompt-library", "version": version, "artifact": artifact.name, "sha256": digest}), encoding="utf-8")
    return root


def enable_packaged_mode(tmp_path: Path, monkeypatch):
    app_root = tmp_path / "app"
    app_root.mkdir()
    (app_root / "VERSION").write_text("v9.9.8", encoding="utf-8")
    monkeypatch.setattr("backend.routers.app_updates.app_root", lambda: app_root)


def test_update_status_detects_complete_local_release_assets(tmp_path, monkeypatch):
    release_dir = write_release_assets(tmp_path / "release", "v9.9.9")
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL", release_dir.as_uri())
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_VERSION", "v9.9.8")
    enable_packaged_mode(tmp_path, monkeypatch)
    app = create_app(library_path=tmp_path / "library")
    client = TestClient(app)

    payload = client.get("/api/update-status").json()

    assert payload["current_version"] == "v9.9.8"
    assert payload["latest_version"] == "v9.9.9"
    assert payload["update_available"] is True
    assert payload["update_command"] == "image-prompt-library update --version v9.9.9"
    assert payload["active_generation_jobs"]["running"] == 0
    assert payload["active_generation_jobs"]["queued"] == 0
    assert payload["service_mode"] in {"launchd", "foreground", "unknown", "not_applicable"}


def test_update_requires_explicit_cancel_when_generation_jobs_are_active(tmp_path, monkeypatch):
    release_dir = write_release_assets(tmp_path / "release", "v9.9.9")
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL", release_dir.as_uri())
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_VERSION", "v9.9.8")
    enable_packaged_mode(tmp_path, monkeypatch)
    monkeypatch.setattr("backend.routers.app_updates.sys.platform", "darwin")
    library = tmp_path / "library"
    repo = GenerationJobRepository(library)
    repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="queued prompt"))
    running = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="running prompt"))
    repo.mark_running(running.id)
    app = create_app(library_path=library)
    client = TestClient(app)

    response = client.post("/api/app-update/jobs", json={"target_version": "v9.9.9", "cancel_active_generation_jobs": False})

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["error"] == "active_generation_jobs"
    assert detail["running_count"] == 1
    assert detail["queued_count"] == 1


def test_cancel_and_update_cancels_active_jobs_and_runs_installer(tmp_path, monkeypatch):
    release_dir = write_release_assets(tmp_path / "release", "v9.9.9")
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL", release_dir.as_uri())
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_VERSION", "v9.9.8")
    enable_packaged_mode(tmp_path, monkeypatch)
    monkeypatch.setattr("backend.routers.app_updates.sys.platform", "darwin")
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

    response = client.post("/api/app-update/jobs", json={"target_version": "v9.9.9", "cancel_active_generation_jobs": True})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "installed"
    assert payload["target_version"] == "v9.9.9"
    assert payload["cancelled_generation_jobs"] == 2
    assert calls == ["v9.9.9"]
    assert repo.get_job(queued.id).status == "cancelled"
    assert repo.get_job(running.id).status == "cancelled"


def test_run_installer_update_passes_current_python_to_installer(tmp_path, monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append({"command": command, **kwargs})
        return subprocess.CompletedProcess(command, 0, stdout="installed", stderr="")

    monkeypatch.delenv("PYTHON", raising=False)
    app_root = tmp_path / "app"
    app_root.mkdir()
    (app_root / "VERSION").write_text("v9.9.8", encoding="utf-8")
    monkeypatch.setattr("backend.routers.app_updates.app_root", lambda: app_root)
    monkeypatch.setattr("backend.routers.app_updates.sys.platform", "darwin")
    monkeypatch.setattr("backend.routers.app_updates.subprocess.run", fake_run)

    from backend.routers.app_updates import run_installer_update

    result = run_installer_update(target_version="v9.9.9-beta")

    assert result["ok"] is True
    assert calls[0]["env"]["PYTHON"] == sys.executable
    assert calls[0]["command"][-2:] == ["--version", "v9.9.9-beta"]


def test_detect_service_mode_checks_edward_custom_launchd_label(monkeypatch):
    checked = []

    def fake_run(command, **kwargs):
        checked.append(command)
        if command[-1] == "com.edward.image-prompt-library":
            return subprocess.CompletedProcess(command, 0, stdout="\tstate = running\n", stderr="")
        return subprocess.CompletedProcess(command, 113, stdout="", stderr="not found")

    monkeypatch.delenv("IMAGE_PROMPT_LIBRARY_SERVICE_LABEL", raising=False)
    monkeypatch.setattr("backend.routers.app_updates.sys.platform", "darwin")
    monkeypatch.setattr("backend.routers.app_updates.subprocess.run", fake_run)

    from backend.routers.app_updates import detect_service_mode

    assert detect_service_mode() == "launchd"
    assert any(command[-1] == "com.edward.image-prompt-library" for command in checked)


def test_local_release_root_is_authoritative_and_auto_discovery_is_stable(tmp_path, monkeypatch):
    release_dir = write_release_assets(tmp_path / "release", "v2.0.0")
    write_release_assets(release_dir, "v9.9.9-beta")
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL", release_dir.as_uri())
    monkeypatch.setattr("backend.routers.app_updates.github_release_versions", lambda: (_ for _ in ()).throw(AssertionError("github fallback")))

    from backend.routers.app_updates import latest_complete_release, version_sort_key

    assert latest_complete_release() == "v2.0.0"
    assert sorted(["v1.0.0-beta.2", "v1.0.0", "v1.0.0-beta.10"], key=version_sort_key, reverse=True) == ["v1.0.0", "v1.0.0-beta.10", "v1.0.0-beta.2"]

    beta_only = write_release_assets(tmp_path / "beta-only", "v3.0.0-beta")
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL", beta_only.as_uri())
    assert latest_complete_release() is None


@pytest.mark.parametrize(
    "version",
    ["1.2.3", "v1.02.3", "v1.2.3-01", "v1.2.3-a..b", "v1.2.3+foo", "v1.2.3+foo..bar"],
)
def test_update_version_rejects_non_semver_forms(version):
    from backend.routers.app_updates import validate_version

    with pytest.raises(HTTPException) as error:
        validate_version(version)
    assert error.value.status_code == 400


def test_github_discovery_filters_before_limit_and_skips_prerelease(monkeypatch):
    from backend.routers.app_updates import github_release_versions

    releases = [{"tag_name": f"v1.0.{index}-beta", "prerelease": True, "assets": []} for index in range(12)]
    releases.append({
        "tag_name": "v2.0.0",
        "draft": False,
        "prerelease": False,
        "assets": [{"name": name} for name in (
            "image-prompt-library-v2.0.0.tar.gz",
            "image-prompt-library-v2.0.0.tar.gz.sha256",
            "image-prompt-library-v2.0.0.manifest.json",
        )],
    })
    monkeypatch.setattr("backend.routers.app_updates.open_url_text", lambda *_args, **_kwargs: json.dumps(releases))

    assert github_release_versions(limit=1) == ["v2.0.0"]


def test_malformed_github_release_data_is_a_surfaced_check_error(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.routers.app_updates.open_url_text", lambda *_args, **_kwargs: json.dumps([{"tag_name": "v2.0.0", "assets": None}]))
    monkeypatch.setattr("backend.routers.app_updates.sys.platform", "darwin")
    enable_packaged_mode(tmp_path, monkeypatch)

    payload = TestClient(create_app(library_path=tmp_path / "library")).get("/api/update-status").json()

    assert payload["error"] == "Could not check for updates"
    assert payload["update_available"] is False
    assert payload["latest_version"] is None


def test_source_checkout_skips_release_lookup_and_rejects_update_before_mutation(tmp_path, monkeypatch):
    source_root = tmp_path / "source"
    source_root.mkdir()
    monkeypatch.setattr("backend.routers.app_updates.app_root", lambda: source_root)
    monkeypatch.setattr("backend.routers.app_updates.open_url_text", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("network")))
    library = tmp_path / "library"
    repo = GenerationJobRepository(library)
    job = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="queued"))
    app = create_app(library_path=library)
    client = TestClient(app)

    status = client.get("/api/update-status").json()
    response = client.post("/api/app-update/jobs", json={"target_version": "v2.0.0", "cancel_active_generation_jobs": True})

    assert status["update_capability"] == "source"
    assert status["error"] is None
    assert status["latest_version"] is None
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "update_unavailable"
    assert repo.get_job(job.id).status == "queued"


def test_windows_packaged_update_is_command_only(tmp_path, monkeypatch):
    release_dir = write_release_assets(tmp_path / "release", "v2.0.0")
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL", release_dir.as_uri())
    monkeypatch.setattr("backend.routers.app_updates.sys.platform", "win32")
    enable_packaged_mode(tmp_path, monkeypatch)
    library = tmp_path / "library"
    repo = GenerationJobRepository(library)
    job = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="queued"))
    client = TestClient(create_app(library_path=library))

    status = client.get("/api/update-status").json()
    response = client.post("/api/app-update/jobs", json={"target_version": "v2.0.0", "cancel_active_generation_jobs": True})

    assert status["update_capability"] == "command_only"
    assert status["update_command"] == "image-prompt-library update --version v2.0.0"
    assert response.status_code == 409
    assert repo.get_job(job.id).status == "queued"


def test_installer_helper_rejects_windows_without_spawning_bash(tmp_path, monkeypatch):
    enable_packaged_mode(tmp_path, monkeypatch)
    monkeypatch.setattr("backend.routers.app_updates.sys.platform", "win32")
    monkeypatch.setattr("backend.routers.app_updates.subprocess.run", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("bash")))

    from backend.routers.app_updates import run_installer_update

    with pytest.raises(HTTPException) as error:
        run_installer_update(target_version="v2.0.0")
    assert error.value.status_code == 409


def test_launchd_restart_uses_static_shell_and_positional_argv(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr("backend.routers.app_updates.app_root", lambda: tmp_path)
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_SERVICE_LABEL", "safe; touch SHOULD_NOT_RUN")
    monkeypatch.setattr("backend.routers.app_updates.subprocess.Popen", lambda *args, **kwargs: calls.append((args, kwargs)))

    from backend.routers.app_updates import schedule_launchd_restart

    schedule_launchd_restart()
    command = calls[0][0][0]
    assert command == ["/bin/sh", "-c", 'sleep 1; exec "$1" service restart --label "$2"', "image-prompt-library-restart", str(tmp_path / "scripts" / "appctl.sh"), "safe; touch SHOULD_NOT_RUN"]


@pytest.mark.parametrize("corruption", ["identity", "sidecar", "artifact"])
def test_release_identity_and_three_way_sha_rejection_happens_before_cancellation(tmp_path, monkeypatch, corruption):
    release_dir = write_release_assets(tmp_path / "release", "v2.0.0")
    manifest = release_dir / "image-prompt-library-v2.0.0.manifest.json"
    if corruption == "identity":
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["name"] = "wrong"
        manifest.write_text(json.dumps(payload), encoding="utf-8")
    elif corruption == "sidecar":
        (release_dir / "image-prompt-library-v2.0.0.tar.gz.sha256").write_text("0" * 64 + "  image-prompt-library-v2.0.0.tar.gz\n", encoding="utf-8")
    else:
        (release_dir / "image-prompt-library-v2.0.0.tar.gz").write_bytes(b"tampered artifact")
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL", release_dir.as_uri())
    enable_packaged_mode(tmp_path, monkeypatch)
    library = tmp_path / "library"
    repo = GenerationJobRepository(library)
    job = repo.create_job(GenerationJobCreate(provider="manual_upload", prompt_text="queued"))
    client = TestClient(create_app(library_path=library))

    response = client.post("/api/app-update/jobs", json={"target_version": "v2.0.0", "cancel_active_generation_jobs": True})

    assert response.status_code == 409
    assert repo.get_job(job.id).status == "queued"


def test_final_active_job_recheck_blocks_installer_race(tmp_path, monkeypatch):
    release_dir = write_release_assets(tmp_path / "release", "v2.0.0")
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL", release_dir.as_uri())
    monkeypatch.setattr("backend.routers.app_updates.sys.platform", "darwin")
    enable_packaged_mode(tmp_path, monkeypatch)
    library = tmp_path / "library"
    app = create_app(library_path=library)
    states = [
        {"running": 0, "queued": 0},
        {"running": 0, "queued": 1},
    ]
    from backend.routers.app_updates import ActiveGenerationJobs

    monkeypatch.setattr("backend.routers.app_updates.active_generation_jobs", lambda _path: ActiveGenerationJobs(**states.pop(0)))
    monkeypatch.setattr("backend.routers.app_updates.run_installer_update", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("installer")))

    response = TestClient(app).post("/api/app-update/jobs", json={"target_version": "v2.0.0", "cancel_active_generation_jobs": False})

    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "active_generation_jobs"


def test_frontend_static_update_wizard_contract():
    root = Path(__file__).resolve().parents[1]
    client = (root / "frontend" / "src" / "api" / "client.ts").read_text(encoding="utf-8")
    config = (root / "frontend" / "src" / "components" / "ConfigPanel.tsx").read_text(encoding="utf-8")
    topbar = (root / "frontend" / "src" / "components" / "TopBar.tsx").read_text(encoding="utf-8")
    app = (root / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
    i18n = (root / "frontend" / "src" / "utils" / "i18n.ts").read_text(encoding="utf-8")

    assert "updateStatus:" in client
    assert "startAppUpdate:" in client
    assert "t('appUpdate')" in config
    assert "t('cancelJobsAndUpdate')" in config
    assert "t('updateLater')" in config
    assert "Wait" not in config and "等待" not in config
    assert "t('updateRestartRequired')" in config
    assert "t('updateStatusFailed')" in config
    assert "t('updateSourceManaged')" in config
    assert "t('updatePowerShellHint')" in config
    assert "result.requires_manual_restart" in config
    assert "t('updateAvailable')" in app
    assert "t('restartRequired')" in app
    assert "handleUpdateInstalled" in app
    assert "updateBadgeLabel" in topbar
    assert "appUpdate: 'App update'" in i18n
    assert "cancelJobsAndUpdate: 'Cancel jobs and update'" in i18n
    assert "updateAvailable: 'Update available'" in i18n
