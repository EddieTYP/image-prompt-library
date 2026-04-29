from pathlib import Path

from backend.config import resolve_app_version


def test_resolve_app_version_prefers_packaged_version_file(tmp_path):
    version_file = tmp_path / "VERSION"
    version_file.write_text("v9.9.9-test\n", encoding="utf-8")

    assert resolve_app_version(tmp_path) == "v9.9.9-test"


def test_resolve_app_version_falls_back_to_source_version(tmp_path):
    assert resolve_app_version(tmp_path) == "0.1.0"
