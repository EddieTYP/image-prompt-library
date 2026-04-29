import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text()


def test_installer_and_runtime_scripts_define_versioned_install_contract():
    install_script = ROOT / "scripts" / "install.sh"
    appctl_script = ROOT / "scripts" / "appctl.sh"
    setup_runtime_script = ROOT / "scripts" / "setup-runtime.sh"
    package_script = ROOT / "scripts" / "package-release.sh"

    assert install_script.exists()
    assert appctl_script.exists()
    assert setup_runtime_script.exists()
    assert package_script.exists()

    install = install_script.read_text()
    appctl = appctl_script.read_text()
    setup_runtime = setup_runtime_script.read_text()
    package = package_script.read_text()

    for script in (install, appctl, setup_runtime, package):
        assert "set -euo pipefail" in script
        assert "8787" not in script
        assert "token" not in script.lower()
        assert "secret" not in script.lower()

    assert "--version" in install
    assert "--prefix" in install
    assert "--library-path" in install
    assert "IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL" in install
    assert "api.github.com/repos/EddieTYP/image-prompt-library/releases/latest" in install
    assert "sha256" in install.lower()
    assert "~/.image-prompt-library" in install
    assert "app/versions" in install
    assert "app/current" in install
    assert "~/ImagePromptLibrary" in install
    assert "git pull" not in install
    assert "git clone" not in install

    assert "start)" in appctl
    assert "version)" in appctl
    assert "update)" in appctl
    assert "rollback)" in appctl
    assert "IMAGE_PROMPT_LIBRARY_PATH" in appctl
    assert "~/ImagePromptLibrary" in appctl
    assert "uvicorn backend.main:app" in appctl
    assert "app/previous" in appctl

    assert "python -m pip install ." in setup_runtime
    assert "npm install" not in setup_runtime
    assert "npm run build" not in setup_runtime

    assert "npm run build" in package
    assert "dist-release" in package
    assert "manifest.json" in package
    assert "tar.gz" in package
    for excluded in (".env", ".local-work", "library", "node_modules", ".venv", "backups"):
        assert excluded in package


def test_release_assets_workflow_builds_and_uploads_tagged_artifacts():
    workflow_path = ROOT / ".github" / "workflows" / "release-assets.yml"
    assert workflow_path.exists()
    workflow = workflow_path.read_text()

    assert "tags:" in workflow
    assert "v*" in workflow
    assert "workflow_dispatch:" in workflow
    assert "actions/checkout@v5" in workflow
    assert "actions/setup-python@v6" in workflow
    assert "actions/setup-node@v5" in workflow
    assert "python -m pytest -q" in workflow
    assert "npm run build" in workflow
    assert "scripts/package-release.sh" in workflow
    assert "softprops/action-gh-release" in workflow or "gh release upload" in workflow
    assert "contents: write" in workflow


def test_readme_prefers_installer_for_users_and_keeps_source_setup_for_developers():
    readme = read("README.md")

    assert "Quick start for normal users" in readme
    assert "scripts/install.sh" in readme
    assert "image-prompt-library start" in readme
    assert "image-prompt-library update" in readme
    assert "image-prompt-library update --version v0.5.0-beta" in readme
    assert "curl -fsSL https://raw.githubusercontent.com/EddieTYP/image-prompt-library/main/scripts/install.sh | bash -s -- --version v0.5.0-beta" in readme
    assert "image-prompt-library rollback" in readme
    assert "GitHub Release assets" in readme
    assert "Developer setup from source" in readme
    assert "git clone https://github.com/EddieTYP/image-prompt-library.git" in readme
    assert "Node.js" in readme
    assert "normal release installs do not require Node.js" in readme
    assert "~/ImagePromptLibrary" in readme
    assert "~/.image-prompt-library/app/versions" in readme
    assert "Add, edit, and private library management are local-only" in readme


def test_package_release_creates_manifest_and_excludes_private_runtime_data(tmp_path):
    result = subprocess.run(
        ["bash", "scripts/package-release.sh", "v9.9.9-test", "--skip-build"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    release_dir = ROOT / "dist-release"
    manifest_path = release_dir / "image-prompt-library-v9.9.9-test.manifest.json"
    tarball_path = release_dir / "image-prompt-library-v9.9.9-test.tar.gz"
    checksum_path = release_dir / "image-prompt-library-v9.9.9-test.tar.gz.sha256"

    assert manifest_path.exists()
    assert tarball_path.exists()
    assert checksum_path.exists()

    manifest = json.loads(manifest_path.read_text())
    assert manifest["name"] == "image-prompt-library"
    assert manifest["version"] == "v9.9.9-test"
    assert manifest["artifact"] == tarball_path.name
    assert manifest["sha256"] in checksum_path.read_text()
    assert manifest["node_required_for_runtime"] is False
    assert manifest["built_frontend"] is True

    listing = subprocess.check_output(
        ["tar", "-tzf", str(tarball_path)], cwd=ROOT, text=True, timeout=30
    )
    assert "backend/" in listing
    assert "frontend/dist/index.html" in listing
    assert "frontend/dist/assets/" in listing
    assert "scripts/appctl.sh" in listing
    assert "scripts/setup-runtime.sh" in listing
    assert "pyproject.toml" in listing
    assert "README.md" in listing
    assert "LICENSE" in listing
    assert ".env" not in listing
    assert ".local-work" not in listing
    assert "node_modules" not in listing
    assert ".venv" not in listing
    assert "library/db.sqlite" not in listing
    assert "backups/" not in listing


def test_installer_supports_file_release_base_and_installs_without_git(tmp_path):
    subprocess.run(
        ["bash", "scripts/package-release.sh", "v9.9.8-test", "--skip-build"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
        timeout=120,
    )

    prefix = tmp_path / "prefix"
    library = tmp_path / "library-data"
    env = os.environ.copy()
    env["IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL"] = (ROOT / "dist-release").as_uri()
    env["IMAGE_PROMPT_LIBRARY_INSTALL_SKIP_RUNTIME_SETUP"] = "1"
    env["PYTHON"] = sys.executable

    result = subprocess.run(
        [
            "bash",
            "scripts/install.sh",
            "--version",
            "v9.9.8-test",
            "--prefix",
            str(prefix),
            "--library-path",
            str(library),
            "--no-shim",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    current = prefix / "app" / "current"
    previous = prefix / "app" / "previous"
    installed = prefix / "app" / "versions" / "v9.9.8-test"
    assert installed.is_dir()
    assert current.is_symlink()
    assert current.resolve() == installed.resolve()
    assert not previous.exists() or previous.is_symlink()

    env_file = prefix / ".env"
    assert env_file.exists()
    env_text = env_file.read_text()
    assert f"IMAGE_PROMPT_LIBRARY_PATH={library}" in env_text
    assert "BACKEND_PORT=8000" in env_text
    assert str(library) not in str(installed)

    version = subprocess.check_output(
        ["bash", str(current / "scripts" / "appctl.sh"), "version"],
        text=True,
        timeout=30,
    ).strip()
    assert "v9.9.8-test" in version
