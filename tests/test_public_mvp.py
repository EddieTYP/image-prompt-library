import os
from pathlib import Path

from fastapi.testclient import TestClient

from backend.config import resolve_library_path
from backend.main import create_app

ROOT = Path(__file__).resolve().parents[1]


def test_public_docs_do_not_use_edward_specific_setup_paths():
    readme = (ROOT / "README.md").read_text()
    assert "cd /Users/edwardtsoi/image-prompt-library" not in readme
    assert "git clone" in readme
    assert "Quick start" in readme
    assert "Privacy" in readme
    assert "Backup" in readme
    assert "Troubleshooting" in readme
    assert "Windows" in readme
    assert "WSL" in readme
    assert "IMAGE_PROMPT_LIBRARY_PATH" in readme


def test_public_import_and_example_data_section_prefers_attributed_demo_source():
    readme = (ROOT / "README.md").read_text()

    assert "Sample screenshot/demo dataset" in readme
    assert "wuyoscar/gpt_image_2_skill" in readme
    assert "import-gpt-image-2-skill.sh" in readme
    assert "IMAGE_PROMPT_LIBRARY_PATH=.local-work/demo-library" in readme
    assert "CC BY 4.0" in readme
    assert "Attribution" in readme
    assert "OpenNana" in readme
    assert "not a universal webpage scraper" in readme
    assert "does not ship third-party prompt-gallery data" in readme


def test_public_install_helper_files_exist_and_document_local_data():
    env_example = (ROOT / ".env.example").read_text()
    setup_script = (ROOT / "scripts" / "setup.sh").read_text()
    start_script = (ROOT / "scripts" / "start.sh").read_text()
    dev_script = (ROOT / "scripts" / "dev.sh").read_text()
    backup_script = (ROOT / "scripts" / "backup.sh").read_text()
    smoke_script = (ROOT / "scripts" / "smoke-test.sh").read_text()

    assert "IMAGE_PROMPT_LIBRARY_PATH=./library" in env_example
    assert "BACKEND_HOST=127.0.0.1" in env_example
    assert "BACKEND_PORT=8000" in env_example
    assert "FRONTEND_PORT=5177" in env_example
    assert "8787" not in env_example

    assert "python3 -m venv .venv" in setup_script
    assert "python -m pip install -e '.[dev]'" in setup_script
    assert "npm install" in setup_script

    assert "npm run build" in start_script
    assert "backend.main:app" in start_script
    assert "IMAGE_PROMPT_LIBRARY_PATH" in start_script
    assert "INCOMING_BACKEND_PORT" in start_script
    assert "INCOMING_IMAGE_PROMPT_LIBRARY_PATH" in start_script
    assert "FRONTEND_PORT" in dev_script
    assert "BACKEND_PORT" in dev_script
    assert "export BACKEND_HOST" in dev_script
    assert "export BACKEND_PORT" in dev_script
    assert "--port \"$FRONTEND_PORT\"" in dev_script

    vite_config = (ROOT / "vite.config.ts").read_text()
    assert "process.env.BACKEND_PORT" in vite_config
    assert "process.env.BACKEND_HOST" in vite_config
    assert "backendProxyTarget" in vite_config
    assert "'/api': backendProxyTarget" in vite_config
    assert "'/media': backendProxyTarget" in vite_config

    assert "library/db.sqlite" in backup_script
    assert "library/originals" in backup_script
    assert "library/thumbs" in backup_script
    assert "library/previews" in backup_script
    assert "tar" in backup_script

    assert "/api/health" in smoke_script
    assert "/media/db.sqlite" in smoke_script


def test_public_python_version_requirement_matches_runtime_syntax():
    pyproject = (ROOT / "pyproject.toml").read_text()
    setup_script = (ROOT / "scripts" / "setup.sh").read_text()
    readme = (ROOT / "README.md").read_text()

    assert 'requires-python = ">=3.10"' in pyproject
    assert "Python 3.10" in readme
    assert "sys.version_info < (3, 10)" in setup_script
    assert "requires Python 3.10" in setup_script


def test_public_repo_hygiene_files_exist():
    license_text = (ROOT / "LICENSE").read_text()
    contributing = (ROOT / "CONTRIBUTING.md").read_text()
    roadmap = (ROOT / "ROADMAP.md").read_text()
    gitignore = (ROOT / ".gitignore").read_text()

    assert "MIT License" in license_text
    assert "Local-first" in contributing
    assert "Run tests" in contributing
    assert "Public local-install MVP" in roadmap
    assert "runtime data" in roadmap
    assert ".env" in gitignore
    assert "backups/" in gitignore


def test_library_path_can_be_configured_with_environment(monkeypatch, tmp_path):
    configured = tmp_path / "custom-library"
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_PATH", str(configured))

    resolved = resolve_library_path()

    assert resolved == configured
    assert (configured / "originals").is_dir()
    assert (configured / "thumbs").is_dir()
    assert (configured / "previews").is_dir()


def test_built_frontend_can_be_served_by_fastapi(tmp_path):
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text("<html><body>Image Prompt Library</body></html>")
    (assets / "app.js").write_text("console.log('ok')")

    app = create_app(tmp_path / "library", frontend_dist_path=dist)
    client = TestClient(app)

    assert client.get("/").status_code == 200
    asset_response = client.get("/assets/app.js")
    assert asset_response.status_code == 200
    assert "console.log" in asset_response.text
    assert client.get("/some/spa/route").status_code == 200
    assert client.get("/api/not-a-real-route").status_code == 404
    assert client.get("/media/db.sqlite").status_code == 404
