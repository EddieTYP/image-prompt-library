import os
from io import BytesIO
from pathlib import Path
import subprocess

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from backend.config import resolve_app_version, validate_app_owned_paths


def test_resolve_app_version_prefers_packaged_version_file(tmp_path):
    version_file = tmp_path / "VERSION"
    version_file.write_text("v9.9.9-test\n", encoding="utf-8")

    assert resolve_app_version(tmp_path) == "v9.9.9-test"


def test_resolve_app_version_falls_back_to_source_version(tmp_path):
    assert resolve_app_version(tmp_path) == "0.1.0"


def test_resolve_app_version_uses_git_describe_for_source_checkout(tmp_path, monkeypatch):
    import backend.config as config

    (tmp_path / ".git").mkdir()

    class Result:
        returncode = 0
        stdout = "v0.5.0-beta-8-gabc1234\n"

    monkeypatch.delenv("IMAGE_PROMPT_LIBRARY_VERSION", raising=False)
    monkeypatch.setattr(config.subprocess, "run", lambda *args, **kwargs: Result())

    assert resolve_app_version(tmp_path) == "v0.5.0-beta-8-gabc1234"


@pytest.mark.parametrize(
    ("env_name", "relative_path"),
    (
        ("IMAGE_PROMPT_LIBRARY_AUTH_PATH", "auth.json"),
        ("IMAGE_PROMPT_LIBRARY_CONFIG_PATH", "settings/config.json"),
    ),
)
def test_app_owned_paths_reject_files_inside_library(tmp_path, monkeypatch, env_name, relative_path):
    library = tmp_path / "library"
    unsafe_path = library / relative_path
    monkeypatch.setenv(env_name, str(unsafe_path))

    with pytest.raises(ValueError, match=env_name) as exc_info:
        validate_app_owned_paths(library)

    assert str(unsafe_path) in str(exc_info.value)
    assert "No database or credential files were changed" in str(exc_info.value)


def test_app_owned_paths_report_auth_and_config_together(tmp_path, monkeypatch):
    library = tmp_path / "library"
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(library / "auth.json"))
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_CONFIG_PATH", str(library / "config.json"))

    with pytest.raises(ValueError) as exc_info:
        validate_app_owned_paths(library)

    message = str(exc_info.value)
    assert "IMAGE_PROMPT_LIBRARY_AUTH_PATH" in message
    assert "IMAGE_PROMPT_LIBRARY_CONFIG_PATH" in message


def test_app_owned_path_cannot_equal_library(tmp_path, monkeypatch):
    library = tmp_path / "library"
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(library))

    with pytest.raises(ValueError, match="IMAGE_PROMPT_LIBRARY_AUTH_PATH"):
        validate_app_owned_paths(library)


def test_app_owned_paths_reject_relative_path_inside_library(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", "library/auth.json")

    with pytest.raises(ValueError, match="IMAGE_PROMPT_LIBRARY_AUTH_PATH"):
        validate_app_owned_paths("library")


def test_app_owned_paths_allow_external_existing_and_missing_files(tmp_path, monkeypatch):
    library = tmp_path / "library"
    auth_path = tmp_path / "app-state" / "auth.json"
    auth_path.parent.mkdir()
    auth_path.write_text("auth-canary", encoding="utf-8")
    config_path = tmp_path / "future-app-state" / "config.json"
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(auth_path))
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_CONFIG_PATH", str(config_path))

    validate_app_owned_paths(library)

    assert auth_path.read_text(encoding="utf-8") == "auth-canary"
    assert not config_path.exists()


def test_app_owned_paths_fail_closed_when_canonical_resolution_fails(tmp_path, monkeypatch):
    original_resolve = Path.resolve
    auth_path = tmp_path / "app-state" / "auth.json"

    def fail_auth_resolution(path, *args, **kwargs):
        if path == auth_path:
            raise OSError("simulated path resolution failure")
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(auth_path))
    monkeypatch.setattr(Path, "resolve", fail_auth_resolution)

    with pytest.raises(ValueError, match="Could not safely resolve app-owned path boundary"):
        validate_app_owned_paths(tmp_path / "library")


def test_app_owned_paths_reject_external_symlink_pointing_into_library(tmp_path, monkeypatch):
    library = tmp_path / "library"
    library.mkdir()
    alias = tmp_path / "app-state-alias"
    try:
        alias.symlink_to(library, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"directory symlinks are unavailable: {exc}")
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(alias / "future-auth.json"))

    with pytest.raises(ValueError, match="IMAGE_PROMPT_LIBRARY_AUTH_PATH"):
        validate_app_owned_paths(library)


def test_app_owned_paths_reject_library_symlink_pointing_outside(tmp_path, monkeypatch):
    library = tmp_path / "library"
    library.mkdir()
    external = tmp_path / "app-state"
    external.mkdir()
    alias = library / "auth-alias"
    try:
        alias.symlink_to(external, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"directory symlinks are unavailable: {exc}")
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(alias / "auth.json"))

    with pytest.raises(ValueError, match="IMAGE_PROMPT_LIBRARY_AUTH_PATH"):
        validate_app_owned_paths(library)


def test_library_storage_root_cannot_resolve_outside_library(tmp_path, monkeypatch):
    library = tmp_path / "library"
    library.mkdir()
    external = tmp_path / "external-originals"
    external.mkdir()
    try:
        (library / "originals").symlink_to(external, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"directory symlinks are unavailable: {exc}")
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(tmp_path / "app-state" / "auth.json"))
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_CONFIG_PATH", str(tmp_path / "app-state" / "config.json"))

    with pytest.raises(ValueError, match="originals"):
        validate_app_owned_paths(library)


def test_library_storage_root_cannot_resolve_to_library_root(tmp_path, monkeypatch):
    library = tmp_path / "library"
    library.mkdir()
    try:
        (library / "originals").symlink_to(library, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"directory symlinks are unavailable: {exc}")
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(tmp_path / "app-state" / "auth.json"))
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_CONFIG_PATH", str(tmp_path / "app-state" / "config.json"))

    with pytest.raises(ValueError, match="originals"):
        validate_app_owned_paths(library)


def test_media_and_image_store_reject_runtime_storage_root_escape(tmp_path, monkeypatch):
    from backend.main import create_app
    from backend.services.image_store import store_image

    library = tmp_path / "library"
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(tmp_path / "app-state" / "auth.json"))
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_CONFIG_PATH", str(tmp_path / "app-state" / "config.json"))
    app = create_app(library_path=library)
    external = tmp_path / "external-originals"
    external.mkdir()
    (external / "auth.json").write_text("credential-canary", encoding="utf-8")
    (library / "originals").rmdir()
    try:
        (library / "originals").symlink_to(external, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        if os.name != "nt":
            pytest.skip(f"directory symlinks are unavailable: {exc}")
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(library / "originals"), str(external)],
            check=False,
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            pytest.skip(f"directory links are unavailable: {result.stderr or result.stdout}")

    response = TestClient(app).get("/media/originals/auth.json")
    image_bytes = BytesIO()
    Image.new("RGB", (2, 2), "red").save(image_bytes, format="PNG")

    assert response.status_code == 404
    with pytest.raises(ValueError, match="originals"):
        store_image(library, image_bytes.getvalue(), "image.png")
    assert (external / "auth.json").read_text(encoding="utf-8") == "credential-canary"


@pytest.mark.skipif(os.name != "nt", reason="Windows path comparison is case-insensitive")
def test_app_owned_paths_reject_case_only_library_variant(tmp_path, monkeypatch):
    library = tmp_path / "Library"
    unsafe_path = Path(str(library / "AUTH.JSON").swapcase())
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(unsafe_path))

    with pytest.raises(ValueError, match="IMAGE_PROMPT_LIBRARY_AUTH_PATH"):
        validate_app_owned_paths(library)


@pytest.mark.skipif(os.name != "nt", reason="Windows junction behavior")
def test_app_owned_paths_reject_junction_pointing_into_library(tmp_path, monkeypatch):
    library = tmp_path / "library"
    library.mkdir()
    junction = tmp_path / "app-state-junction"
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(library)],
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        pytest.skip(f"junctions are unavailable: {result.stderr or result.stdout}")
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_CONFIG_PATH", str(junction / "future-config.json"))

    with pytest.raises(ValueError, match="IMAGE_PROMPT_LIBRARY_CONFIG_PATH"):
        validate_app_owned_paths(library)


@pytest.mark.skipif(os.name != "nt", reason="Windows junction behavior")
def test_library_storage_root_cannot_be_external_junction(tmp_path, monkeypatch):
    library = tmp_path / "library"
    library.mkdir()
    external = tmp_path / "external-originals"
    external.mkdir()
    junction = library / "originals"
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(external)],
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        pytest.skip(f"junctions are unavailable: {result.stderr or result.stdout}")
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(external / "auth.json"))
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_CONFIG_PATH", str(tmp_path / "app-state" / "config.json"))

    with pytest.raises(ValueError, match="originals"):
        validate_app_owned_paths(library)


def test_create_app_rejects_unsafe_path_before_database_initialization(tmp_path, monkeypatch):
    from backend.main import create_app

    library = tmp_path / "library"
    unsafe_auth = library / "originals" / "auth.json"
    unsafe_auth.parent.mkdir(parents=True)
    unsafe_auth.write_text("do-not-read-or-change", encoding="utf-8")
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_AUTH_PATH", str(unsafe_auth))
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_CONFIG_PATH", str(tmp_path / "app-state" / "config.json"))

    with pytest.raises(ValueError, match="IMAGE_PROMPT_LIBRARY_AUTH_PATH"):
        create_app(library_path=library)

    assert unsafe_auth.read_text(encoding="utf-8") == "do-not-read-or-change"
    assert not (library / "db.sqlite").exists()
