import os
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from backend.config import resolve_library_path
from backend.main import create_app

ROOT = Path(__file__).resolve().parents[1]


def test_public_docs_do_not_use_edward_specific_setup_paths():
    readme = (ROOT / "README.md").read_text()
    public_docs = "\n".join(
        (ROOT / path).read_text()
        for path in (
            "README.md",
            "README_zh-TW.md",
            "README_zh-CN.md",
            "ROADMAP.md",
            "docs/INSTALLATION.md",
            "docs/DEVELOPMENT.md",
            "docs/TROUBLESHOOTING.md",
        )
    )
    assert "/Users/" not in public_docs
    assert "edward" + "tsoi" not in public_docs.lower()
    assert "scripts/install.sh" in (ROOT / "docs" / "INSTALLATION.md").read_text()
    assert "Quick start" in readme
    assert "Privacy" in readme
    assert "Documentation" in readme
    assert "Troubleshooting" in (ROOT / "docs" / "TROUBLESHOOTING.md").read_text()
    installation = (ROOT / "docs" / "INSTALLATION.md").read_text()
    assert "Windows" in installation
    assert "WSL" in installation
    assert "IMAGE_PROMPT_LIBRARY_PATH" in (ROOT / "docs" / "DEVELOPMENT.md").read_text()
    assert "AGPL-3.0-or-later" in readme
    assert "Commercial licenses" in readme
    assert "Sample data and third-party assets are licensed separately" in (ROOT / "NOTICE").read_text()
    assert "source-available" not in readme.lower()
    assert "not open-source" not in readme.lower()
    assert "not licensed for redistribution" not in readme.lower()


def test_public_readme_badges_use_public_status_urls():
    readme = (ROOT / "README.md").read_text()

    assert "https://github.com/EddieTYP/image-prompt-library/workflows/CI/badge.svg" in readme
    assert "https://github.com/EddieTYP/image-prompt-library/workflows/Deploy%20GitHub%20Pages%20demo/badge.svg" in readme
    assert "actions/workflows/ci.yml/badge.svg" not in readme
    assert "actions/workflows/pages.yml/badge.svg" not in readme
    assert "https://img.shields.io/github/v/release/EddieTYP/image-prompt-library?label=release" in readme
    assert "https://github.com/EddieTYP/image-prompt-library/releases/latest" in readme


def test_public_import_and_example_data_section_prefers_attributed_demo_source():
    readme = (ROOT / "README.md").read_text()

    assert "Sample data and attribution" in readme
    assert "wuyoscar/gpt_image_2_skill" in readme
    assert "optional sample bundles" in readme
    assert "image-prompt-library sample-data en" in readme
    assert "CC BY 4.0" in readme
    assert "demo references" in readme
    assert "your own private prompt/image library" in readme
    removed_source_name = "Open" + "Nana"
    assert "Sample screenshot/demo dataset" not in readme
    assert removed_source_name not in readme
    assert f"{removed_source_name} scrape" not in readme
    assert "## Sample data and attribution" in readme
    sample_section = readme.split("## Sample data and attribution", 1)[1].split("## Documentation", 1)[0]
    assert "GitHub Release asset" not in sample_section
    assert "bootstrapping a library" not in sample_section
    assert "local/exported source" not in sample_section


def test_public_docs_explain_first_run_status_and_doctor():
    readme = (ROOT / "README.md").read_text()
    installation = (ROOT / "docs" / "INSTALLATION.md").read_text()
    troubleshooting = (ROOT / "docs" / "TROUBLESHOOTING.md").read_text()
    roadmap = (ROOT / "ROADMAP.md").read_text()

    assert "v0.8.0" in roadmap
    for doc in (readme, installation, troubleshooting):
        assert "image-prompt-library status" in doc
        assert "image-prompt-library doctor" in doc
    assert "A fresh local library starts empty" in readme
    assert "image-prompt-library sample-data zh_hans" in readme
    assert "image-prompt-library sample-data zh_hant" in readme
    assert "image-prompt-library sample-data zh_hant awesome-gpt-image-2" in readme
    assert "First run" in installation
    assert "Native Windows PowerShell" in installation
    assert "WSL 2" in installation
    assert "sample-data en" in troubleshooting


def test_public_readme_explains_current_workflows_and_screenshots():
    readme = (ROOT / "README.md").read_text()

    assert "local-first" in readme
    assert "SQLite" in readme
    assert "local image files" in readme
    assert "provider's servers" in readme
    for label in (
        "Explore", "Library", "Config → Providers", "ChatGPT / Codex OAuth",
        "Grok OAuth", "Default AI provider", "Suggest title", "Use title",
        "via ChatGPT", "via Grok", "Work queue", "Save as new item",
    ):
        assert label in readme
    assert "copy public sample prompts" in readme
    assert "`{{variables}}`" in readme
    assert "`{{subject}}`" in readme
    assert "structured search filters" in readme
    assert "**Tag**" in readme
    assert "**Move**" in readme
    assert "multiple images in one card" in readme
    assert "unchanged source card" in readme
    assert "review completed results from the **work queue**" in readme.lower()
    assert "online read-only demo" in readme.lower()
    assert "## Privacy" in readme
    assert "only prompt text" in readme
    assert "excluded from portable backups" in readme
    assert "does not silently send" in readme
    assert "127.0.0.1" in readme
    assert "Editing, private-library management, and generation are available only in a local install" in readme
    assert "openai_codex_oauth_native" not in readme
    assert "GenerationJob" not in readme
    assert "IMAGE_PROMPT_LIBRARY_CODEX_CLIENT_ID" not in readme
    assert "Use the next release tag" not in readme
    assert "main` release-ready" not in readme
    assert "npm run build:demo" not in readme
    assert "## Verification" not in readme
    assert "## Repository layout" not in readme
    assert "For the next version, the default is therefore" not in readme
    assert "current stable release" in readme.lower()

    screenshots = [
        "local-app-library-overview.jpg",
        "local-app-explore.jpg",
        "local-app-detail.jpg",
        "generation-grok-provider.png",
        "public-demo-explore.png",
    ]
    for filename in screenshots:
        relative_path = f"docs/assets/screenshots/{filename}"
        assert relative_path in readme
        assert (ROOT / relative_path).exists()


def test_readmes_lead_with_the_local_product_and_label_the_online_demo():
    readmes = {
        "README.md": ("## Online read-only demo", "## Sample data and attribution"),
        "README_zh-TW.md": ("## 線上唯讀 demo", "## Sample data 與 attribution"),
        "README_zh-CN.md": ("## 线上只读 demo", "## Sample data 与 attribution"),
    }
    screenshot_paths = [
        "docs/assets/screenshots/local-app-library-overview.jpg",
        "docs/assets/screenshots/local-app-explore.jpg",
        "docs/assets/screenshots/local-app-detail.jpg",
        "docs/assets/screenshots/public-demo-explore.png",
    ]

    for filename, (demo_heading, sample_heading) in readmes.items():
        content = (ROOT / filename).read_text()
        positions = [content.index(path) for path in screenshot_paths]

        assert positions == sorted(positions)
        assert screenshot_paths[0] in content[: content.index("## ")]
        assert content.count(screenshot_paths[3]) == 1
        assert content.index(demo_heading) < positions[3] < content.index(sample_heading)


def test_generation_guide_uses_current_product_screenshots():
    guide = (ROOT / "docs" / "GENERATION.md").read_text()

    for filename in [
        "generation-review-result.jpg", "generation-save-as-new-item.jpg",
        "generation-grok-provider.png", "default-ai-provider.png",
        "library-image-management.png",
    ]:
        relative_path = f"assets/screenshots/{filename}"
        assert relative_path in guide
        assert (ROOT / "docs" / relative_path).exists()

    assert "generation-provider-connected.png" not in guide
    assert "generation-composer-running.png" not in guide
    assert "generation-composer-result.png" not in guide
    assert guide.index("generation-review-result.jpg") < guide.index("generation-save-as-new-item.jpg")


def test_documentation_screenshot_extensions_match_file_content():
    screenshots = [
        "docs/assets/screenshots/local-app-library-overview.jpg",
        "docs/assets/screenshots/local-app-explore.jpg",
        "docs/assets/screenshots/local-app-detail.jpg",
        "docs/assets/screenshots/generation-review-result.jpg",
        "docs/assets/screenshots/generation-save-as-new-item.jpg",
        "docs/assets/screenshots/generation-grok-provider.png",
        "docs/assets/screenshots/default-ai-provider.png",
        "docs/assets/screenshots/library-image-management.png",
        "docs/assets/screenshots/public-demo-explore.png",
    ]

    for relative_path in screenshots:
        path = ROOT / relative_path
        data = path.read_bytes()
        if path.suffix == ".jpg":
            assert data.startswith(b"\xff\xd8\xff")
        else:
            assert data.startswith(b"\x89PNG\r\n\x1a\n")


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
    roadmap = (ROOT / "ROADMAP.md").read_text()
    assert removed_source_name not in readme
    assert removed_source_name not in roadmap


def test_public_install_helper_files_exist_and_document_local_data():
    env_example = (ROOT / ".env.example").read_text()
    setup_script = (ROOT / "scripts" / "setup.sh").read_text()
    start_script = (ROOT / "scripts" / "start.sh").read_text()
    dev_script = (ROOT / "scripts" / "dev.sh").read_text()
    backup_script = (ROOT / "scripts" / "backup.sh").read_text()
    archive_script = (ROOT / "backend" / "services" / "library_archives.py").read_text()
    smoke_script = (ROOT / "scripts" / "smoke-test.sh").read_text()

    for windows_script in (
        "scripts/appctl.ps1",
        "scripts/install.ps1",
        "scripts/install-sample-data.ps1",
        "scripts/setup-runtime.ps1",
    ):
        assert (ROOT / windows_script).is_file()
    assert "install.ps1" in (ROOT / "docs" / "INSTALLATION.md").read_text()

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

    assert "library-archive.py" in backup_script
    assert "db.sqlite" in archive_script
    assert '"originals"' in archive_script
    assert '"thumbs"' in archive_script
    assert '"previews"' in archive_script
    assert '"generation-results"' in archive_script
    assert '"generation-references"' in archive_script
    assert "tarfile" in archive_script

    assert "/api/health" in smoke_script
    assert "/media/db.sqlite" in smoke_script


def test_public_python_version_requirement_matches_runtime_syntax():
    pyproject = (ROOT / "pyproject.toml").read_text()
    setup_script = (ROOT / "scripts" / "setup.sh").read_text()
    readme = (ROOT / "README.md").read_text()

    assert 'requires-python = ">=3.10"' in pyproject
    assert "Python 3.10" in readme
    assert "Python 3.10" in (ROOT / "docs" / "INSTALLATION.md").read_text()
    assert "python3.12" in setup_script
    assert "PYTHON=/path/to/python3.12 ./scripts/setup.sh" in (ROOT / "docs" / "DEVELOPMENT.md").read_text()
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
    assert '"vite": "8.2.2"' in package_json


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
    assert "Current stable direction" in roadmap
    assert "commercial licensing" in roadmap.lower()
    assert "provider state" in roadmap
    assert "Reporting a vulnerability" in security
    assert "127.0.0.1" in security
    assert "do not expose the app directly to the public internet" in security
    assert "private prompt-library data" in bug_template
    assert "Python version" in bug_template
    assert "Local-first/privacy impact" in feature_template
    assert ".env" in gitignore
    assert "backups/" in gitignore
    for local_only_path in (".codex/", ".codebase-memory/", ".qa-*", ".superpowers/", "docs/qa/"):
        assert local_only_path in gitignore
    assert "Stage explicit paths only" in (ROOT / "AGENTS.md").read_text()
    assert "git diff --cached --name-status" in contributing


def test_public_repo_does_not_track_ignored_local_artifacts():
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    tracked = [path for path in result.stdout.split("\0") if path and (ROOT / path).exists()]
    ignored_result = subprocess.run(
        ["git", "check-ignore", "--no-index", "-z", "--stdin"],
        cwd=ROOT,
        input="\0".join(tracked) + "\0",
        text=True,
        capture_output=True,
    )
    ignored_tracked = [path for path in ignored_result.stdout.split("\0") if path]
    forbidden_prefixes = (
        ".agents/",
        ".codex/",
        ".codex-qa-",
        ".codebase-memory/",
        ".qa-",
        ".superpowers/",
        "docs/plans/",
        "docs/qa/",
        "docs/superpowers/",
    )
    forbidden_files = {"docs/PROJECT_STATUS.md", "docs/README_SCREENSHOT_AUDIT.md"}
    forbidden_tracked = [
        path
        for path in tracked
        if path in forbidden_files or path.startswith(forbidden_prefixes)
    ]

    assert sorted(set(ignored_tracked + forbidden_tracked)) == []


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

    root_response = client.get("/")
    assert root_response.status_code == 200
    assert root_response.headers["cache-control"] == "no-store, no-cache, must-revalidate, max-age=0"
    assert root_response.headers["pragma"] == "no-cache"
    assert root_response.headers["expires"] == "0"
    asset_response = client.get("/assets/app.js")
    assert asset_response.status_code == 200
    assert "console.log" in asset_response.text
    assert asset_response.headers["cache-control"] == "public, max-age=31536000, immutable"
    spa_response = client.get("/some/spa/route")
    assert spa_response.status_code == 200
    assert spa_response.headers["cache-control"] == "no-store, no-cache, must-revalidate, max-age=0"
    assert client.get("/api/not-a-real-route").status_code == 404
    assert client.get("/media/db.sqlite").status_code == 404
