import os
from pathlib import Path

from fastapi.testclient import TestClient

from backend.config import resolve_library_path
from backend.main import create_app

ROOT = Path(__file__).resolve().parents[1]


def test_public_docs_do_not_use_edward_specific_setup_paths():
    readme = (ROOT / "README.md").read_text()
    project_status = (ROOT / "docs" / "PROJECT_STATUS.md").read_text()
    public_docs = readme + "\n" + project_status
    assert "/Users/" not in public_docs
    assert "edward" + "tsoi" not in public_docs.lower()
    assert "Her" + "mes" not in project_status
    assert "tele" + "gram" not in project_status.lower()
    assert "git clone" in readme
    assert "Quick start" in readme
    assert "Privacy" in readme
    assert "Backup" in readme
    assert "Troubleshooting" in readme
    assert "Windows" in readme
    assert "WSL" in readme
    assert "IMAGE_PROMPT_LIBRARY_PATH" in readme
    assert "AGPL-3.0-or-later" in readme
    assert "Commercial licenses" in readme
    assert "Sample data and third-party assets are licensed separately" in readme
    assert "source-available" not in readme.lower()
    assert "not open-source" not in readme.lower()
    assert "not licensed for redistribution" not in readme.lower()


def test_public_readme_badges_use_public_status_urls():
    readme = (ROOT / "README.md").read_text()

    assert "https://github.com/EddieTYP/image-prompt-library/workflows/CI/badge.svg" in readme
    assert "https://github.com/EddieTYP/image-prompt-library/workflows/Deploy%20GitHub%20Pages%20demo/badge.svg" in readme
    assert "actions/workflows/ci.yml/badge.svg" not in readme
    assert "actions/workflows/pages.yml/badge.svg" not in readme
    assert "https://img.shields.io/github/v/tag/EddieTYP/image-prompt-library?sort=semver&label=release" in readme
    assert "https://img.shields.io/github/v/release/EddieTYP/image-prompt-library" not in readme


def test_public_import_and_example_data_section_prefers_attributed_demo_source():
    readme = (ROOT / "README.md").read_text()

    assert "Try the sample library" in readme
    assert "wuyoscar/gpt_image_2_skill" in readme
    assert "optional sample library" in readme
    assert "scripts/install-sample-data.sh en" in readme
    assert "CC BY 4.0" in readme
    assert "demo/sample content" in readme
    assert "your own prompt library data remains private" in readme
    removed_source_name = "Open" + "Nana"
    assert "Sample screenshot/demo dataset" not in readme
    assert removed_source_name not in readme
    assert f"{removed_source_name} scrape" not in readme
    sample_section = readme.split("## Import and example data", 1)[1].split("## Backup", 1)[0]
    assert "GitHub Release asset" not in sample_section
    assert "bootstrapping a library" not in sample_section
    assert "local/exported source" not in sample_section


def test_public_readme_includes_product_story_and_screenshots():
    readme = (ROOT / "README.md").read_text()

    assert "ChatGPT image generation has become good enough" in readme
    assert "local SQLite, local image files, no accounts, no cloud sync" in readme
    assert "Explore view" in readme
    assert "Cards view" in readme
    assert "one-click prompt copy" in readme
    assert "Generate New Image from a prompt, or generate a Variant of an existing one with ChatGPT Image 2.0 once you have completed OAuth." in readme
    assert "v0.6.4-beta" in readme
    assert "multilingual provenance-aware prompt vault" in readme
    assert "mobile browsing preview" not in readme
    assert "next-release mobile browsing and management plan" not in readme
    assert "Mobile-first browsing behavior" in readme
    assert "stable two-column masonry layout" in readme
    assert "bottom dock instead of crowding the header" in readme
    assert "review generated results before saving" in readme
    assert "Local Generation Studio" not in readme
    assert "archived 0.3 preview" not in readme
    assert "archived 0.2 preview" not in readme
    assert "archived 0.1 alpha demo" not in readme
    assert "Online Read Only Demo" in readme
    assert "ChatGPT OAuth" in readme
    assert "direct image generation" in readme
    assert "Latest v0.6.4 beta refreshes existing sample imports, fixes bilingual prompt variants, and keeps demo title localization read-only/demo-only" in readme
    assert "Online sandbox" not in readme
    assert "只读 sample library" not in readme
    assert "唯讀 sample library" not in readme
    assert "The online demo is read-only" in readme
    assert "install the app locally" in readme
    assert "Add, edit, generation, and private library management are local-only" in readme
    assert "Generate images directly in local installs" in readme
    assert "Generate with ChatGPT OAuth" in readme
    assert "generate a new image from a fresh prompt or create a variant from an existing reference" in readme
    assert "Add your own prompts & images" in readme
    assert "## Add your own prompts\n" not in readme
    assert "Save as new item" in readme
    assert "openai_codex_oauth_native" not in readme
    assert "GenerationJob" not in readme
    assert "IMAGE_PROMPT_LIBRARY_CODEX_CLIENT_ID" not in readme
    assert "Use the next release tag" not in readme
    assert "main` release-ready" not in readme
    assert "npm run build:demo" not in readme
    assert "## Verification" not in readme
    assert "## Repository layout" not in readme
    assert "For the next version, the default is therefore" not in readme
    assert "recommended default for this beta line" in readme

    screenshots = [
        "generation-provider-connected.jpeg",
        "generation-standalone-panel.jpeg",
        "generation-variant-detail.jpeg",
        "generation-result-inbox-save-new.jpeg",
        "card-view-all.png",
        "mobile-cards-view.jpg",
        "mobile-filter-drawer.jpg",
        "mobile-detail-image.jpg",
        "mobile-detail-prompt.jpg",
        "explore-view-home.png",
        "explore-view-filtered.png",
        "reference-item-detail.png",
        "add-prompt-modal.png",
    ]
    for filename in screenshots:
        relative_path = f"docs/assets/screenshots/{filename}"
        assert relative_path in readme
        assert (ROOT / relative_path).exists()


def test_gpt_image_2_skill_public_import_scripts_are_not_shipped():
    removed_scripts = [
        "import-gpt-image-2-skill.sh",
        "import-gpt-image-2-skill-en.sh",
        "import-gpt-image-2-skill-zh-hans.sh",
        "import-gpt-image-2-skill-zh-hant.sh",
    ]
    for filename in removed_scripts:
        assert not (ROOT / "scripts" / filename).exists()


def test_removed_source_specific_importer_is_not_shipped_or_exposed(tmp_path, monkeypatch):
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_PATH", str(tmp_path / "library"))
    app = create_app()
    client = TestClient(app)
    removed_source_slug = "open" + "nana"
    removed_source_name = "Open" + "Nana"

    assert not (ROOT / "scripts" / f"import-{removed_source_slug}.sh").exists()
    assert not (ROOT / "backend" / "services" / f"import_{removed_source_slug}.py").exists()
    assert not (ROOT / "backend" / "routers" / "importers.py").exists()

    response = client.post(f"/api/import/{removed_source_slug}", json={"path": "/tmp/gallery.json"})
    assert response.status_code == 404

    readme = (ROOT / "README.md").read_text()
    project_status = (ROOT / "docs" / "PROJECT_STATUS.md").read_text()
    roadmap = (ROOT / "ROADMAP.md").read_text()
    assert removed_source_name not in readme
    assert removed_source_name not in project_status
    assert removed_source_name not in roadmap


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
    assert "choose_python" in setup_script
    assert "python3.12" in setup_script
    assert "python3.10" in setup_script
    assert "Python 3.10 or newer" in setup_script
    assert "python -m pip install -e '.[dev]'" in setup_script
    assert "npm install" in setup_script

    assert "npm run build" in start_script
    assert "choose_python" in start_script
    assert "python3.12" in start_script
    assert "./scripts/setup.sh" in start_script
    assert "Python 3.10 or newer" in start_script
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
    assert "python3.12" in readme
    assert "PYTHON=/path/to/python3.12 ./scripts/setup.sh" in readme
    assert "sys.version_info < (3, 10)" in setup_script
    assert "requires Python 3.10" in setup_script


def test_public_npm_dependencies_are_pinned():
    package_json = (ROOT / "package.json").read_text()
    package_lock = (ROOT / "package-lock.json").read_text()

    assert '"latest"' not in package_json
    assert '"latest"' not in package_lock
    assert '"name": "image-prompt-library"' in package_json
    assert '"name": "image-prompt-library"' in package_lock
    assert '"react": "19.2.5"' in package_json
    assert '"vite": "8.0.10"' in package_json


def test_public_repo_hygiene_files_exist():
    license_text = (ROOT / "LICENSE").read_text()
    notice = (ROOT / "NOTICE").read_text()
    contributing = (ROOT / "CONTRIBUTING.md").read_text()
    roadmap = (ROOT / "ROADMAP.md").read_text()
    security = (ROOT / "SECURITY.md").read_text()
    bug_template = (ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.md").read_text()
    feature_template = (ROOT / ".github" / "ISSUE_TEMPLATE" / "feature_request.md").read_text()
    gitignore = (ROOT / ".gitignore").read_text()

    assert "GNU AFFERO GENERAL PUBLIC LICENSE" in license_text
    assert "Version 3" in license_text
    assert "Copyright (C) 2026 Edward Tsoi" in notice
    assert "AGPL-3.0-or-later" in notice
    assert "Sample data and third-party assets are licensed separately" in notice
    assert "AGPL-3.0-or-later" in contributing
    assert "alternative/commercial licensing terms" in contributing
    assert "Local-first" in contributing
    assert "Run tests" in contributing
    assert "Public AGPL local-install MVP" in roadmap
    assert "commercial licenses" in roadmap.lower()
    assert "runtime data" in roadmap
    assert "Reporting a vulnerability" in security
    assert "127.0.0.1" in security
    assert "do not expose the app directly to the public internet" in security
    assert "private prompt-library data" in bug_template
    assert "Python version" in bug_template
    assert "Local-first/privacy impact" in feature_template
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
