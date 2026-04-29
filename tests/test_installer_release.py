import json
import os
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

from PIL import Image

from backend.repositories import ItemRepository

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
    assert "api.github.com/repos/{repo}/releases?per_page=20" in install
    assert "releases/latest" not in install
    assert "image-prompt-library-{tag}.manifest.json" in install
    assert "image-prompt-library-{tag}.tar.gz" in install
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
    assert "sample-data)" in appctl
    assert "uninstall)" in appctl
    assert "install-sample-data.sh" in appctl
    assert "IMAGE_PROMPT_LIBRARY_PATH" in appctl
    assert "~/ImagePromptLibrary" in appctl
    assert "uvicorn backend.main:app" in appctl
    assert "app/previous" in appctl

    assert "python -m pip install ." in setup_runtime
    assert "npm install" not in setup_runtime
    assert "npm run build" not in setup_runtime

    assert "npm run build" in package
    assert "/image-prompt-library/assets/" in package
    assert "GitHub Pages demo build" in package
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
    assert "image-prompt-library sample-data en" in readme
    assert "image-prompt-library uninstall" in readme
    assert "TL;DR" in readme
    assert "Keep your private library" in readme
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
    with tarfile.open(tarball_path, "r:gz") as archive:
        index_html = archive.extractfile("./frontend/dist/index.html").read().decode("utf-8")
    assert '/image-prompt-library/assets/' not in index_html
    assert '/assets/' in index_html
    assert "frontend/dist/assets/" in listing
    assert "scripts/appctl.sh" in listing
    assert "scripts/setup-runtime.sh" in listing
    assert "scripts/install-sample-data.sh" in listing
    assert "sample-data/manifests/en.json" in listing
    assert "sample-data/manifests/zh_hant.json" in listing
    assert "sample-data/manifests/zh_hans.json" in listing
    assert "sample-data/manifests/awesome-gpt-image-2/zh_hant.json" in listing
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


def test_installed_uninstall_removes_app_but_keeps_library_by_default(tmp_path):
    subprocess.run(
        ["bash", "scripts/package-release.sh", "v9.9.6-test", "--skip-build"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
        timeout=120,
    )

    prefix = tmp_path / "prefix"
    library = tmp_path / "installer-library"
    env = os.environ.copy()
    env["IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL"] = (ROOT / "dist-release").as_uri()
    env["IMAGE_PROMPT_LIBRARY_INSTALL_SKIP_RUNTIME_SETUP"] = "1"
    env["PYTHON"] = sys.executable
    install = subprocess.run(
        [
            "bash",
            "scripts/install.sh",
            "--version",
            "v9.9.6-test",
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
    assert install.returncode == 0, install.stdout + install.stderr
    (library / "keep.txt").write_text("private data", encoding="utf-8")
    appctl = prefix / "app" / "current" / "scripts" / "appctl.sh"

    uninstall = subprocess.run(
        ["bash", str(appctl), "uninstall"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
    )

    assert uninstall.returncode == 0, uninstall.stdout + uninstall.stderr
    assert "Private library kept" in uninstall.stdout
    assert not prefix.exists()
    assert (library / "keep.txt").read_text(encoding="utf-8") == "private data"


def test_installed_uninstall_can_delete_library_with_explicit_flag(tmp_path):
    subprocess.run(
        ["bash", "scripts/package-release.sh", "v9.9.5-test", "--skip-build"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
        timeout=120,
    )

    prefix = tmp_path / "prefix"
    library = tmp_path / "installer-library"
    env = os.environ.copy()
    env["IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL"] = (ROOT / "dist-release").as_uri()
    env["IMAGE_PROMPT_LIBRARY_INSTALL_SKIP_RUNTIME_SETUP"] = "1"
    env["PYTHON"] = sys.executable
    install = subprocess.run(
        [
            "bash",
            "scripts/install.sh",
            "--version",
            "v9.9.5-test",
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
    assert install.returncode == 0, install.stdout + install.stderr
    (library / "delete.txt").write_text("private data", encoding="utf-8")
    appctl = prefix / "app" / "current" / "scripts" / "appctl.sh"

    uninstall = subprocess.run(
        ["bash", str(appctl), "uninstall", "--delete-library", "--yes"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
    )

    assert uninstall.returncode == 0, uninstall.stdout + uninstall.stderr
    assert "Private library deleted" in uninstall.stdout
    assert not prefix.exists()
    assert not library.exists()


def test_installed_sample_data_script_imports_into_installer_library_by_default(tmp_path):
    subprocess.run(
        ["bash", "scripts/package-release.sh", "v9.9.7-test", "--skip-build"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
        timeout=120,
    )

    prefix = tmp_path / "prefix"
    library = tmp_path / "installer-library"
    env = os.environ.copy()
    env["IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL"] = (ROOT / "dist-release").as_uri()
    env["IMAGE_PROMPT_LIBRARY_INSTALL_SKIP_RUNTIME_SETUP"] = "1"
    env["PYTHON"] = sys.executable
    install = subprocess.run(
        [
            "bash",
            "scripts/install.sh",
            "--version",
            "v9.9.7-test",
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
    assert install.returncode == 0, install.stdout + install.stderr

    assets = tmp_path / "assets"
    image_dir = assets / "images"
    image_dir.mkdir(parents=True)
    Image.new("RGB", (10, 10), "green").save(image_dir / "fixture.png")
    manifest = tmp_path / "fixture-manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": 2,
        "id": "installed-fixture",
        "language": "en",
        "source": {"name": "fixture", "license": "CC BY 4.0"},
        "collections": [{"id": "demo", "name": "Demo", "names": {"en": "Demo"}}],
        "items": [{
            "id": "installed-fixture-001",
            "title": "Installed sample fixture",
            "slug": "installed-sample-fixture",
            "collection_id": "demo",
            "image": "images/fixture.png",
            "source_name": "fixture",
            "tags": ["sample"],
            "prompts": [{
                "language": "en",
                "text": "A green square",
                "is_primary": True,
                "is_original": True,
                "provenance": {"kind": "source", "source_language": "en", "derived_from": None, "method": None},
            }],
        }],
    }), encoding="utf-8")
    zip_path = tmp_path / "sample-images.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.write(image_dir / "fixture.png", "images/fixture.png")

    result = subprocess.run(
        ["bash", str(prefix / "app" / "current" / "scripts" / "appctl.sh"), "sample-data", "en"],
        cwd=tmp_path,
        env={
            **env,
            "SAMPLE_DATA_MANIFEST": str(manifest),
            "SAMPLE_DATA_IMAGE_ZIP": str(zip_path),
        },
        text=True,
        capture_output=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Imported 1 items" in result.stdout
    assert str(library) in result.stdout
    assert ItemRepository(library).list_items(limit=5).total == 1
