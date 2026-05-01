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
    assert "choose_python()" in install
    assert "python3.13 python3.12 python3.11 python3.10 python3 python" in install
    assert "PYTHON=/path/to/python3.10" in install
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
    assert "--host" in appctl
    assert "--port" in appctl
    assert "Missing value for --host" in appctl
    assert "Missing value for --port" in appctl
    assert 'http://127.0.0.1:$BACKEND_PORT/' in appctl
    assert "INCOMING_BACKEND_HOST" in appctl
    assert "WSL" in appctl
    assert "version)" in appctl
    assert "doctor)" in appctl
    assert "service)" in appctl
    assert "service install" in appctl
    assert "launchctl" in appctl
    assert "LaunchAgents" in appctl
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
    assert "choose_python()" in setup_runtime
    assert "python3.13 python3.12 python3.11 python3.10 python3 python" in setup_runtime
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
    assert "image-prompt-library update --version v0.6.0-beta" in readme
    assert "curl -fsSL https://raw.githubusercontent.com/EddieTYP/image-prompt-library/main/scripts/install.sh | bash -s -- --version v0.6.0-beta" in readme
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
    assert "Add, edit, generation, and private library management are local-only" in readme
    assert "image-prompt-library start --host 0.0.0.0" in readme
    assert "Binding to `0.0.0.0` can expose the app" in readme
    assert "image-prompt-library doctor" in readme
    assert "image-prompt-library service install --host 127.0.0.1 --port 8000" in readme
    assert "image-prompt-library service install --host 0.0.0.0 --port 7500" not in readme
    assert "Use the next release tag" not in readme


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
    assert "__pycache__" not in listing
    assert ".pyc" not in listing


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


def test_installer_auto_detects_supported_python_when_python3_is_too_old(tmp_path):
    subprocess.run(
        ["bash", "scripts/package-release.sh", "v9.9.4-test", "--skip-build"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
        timeout=120,
    )

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_python3 = fake_bin / "python3"
    fake_python3.write_text(
        "#!/usr/bin/env sh\n"
        "echo 'fake old python3 should not be used by installer auto-detection' >&2\n"
        "exit 1\n",
        encoding="utf-8",
    )
    fake_python3.chmod(0o755)
    (fake_bin / "python3.12").symlink_to(sys.executable)

    prefix = tmp_path / "prefix"
    library = tmp_path / "library-data"
    env = os.environ.copy()
    env.pop("PYTHON", None)
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL"] = (ROOT / "dist-release").as_uri()
    env["IMAGE_PROMPT_LIBRARY_INSTALL_SKIP_RUNTIME_SETUP"] = "1"

    result = subprocess.run(
        [
            "bash",
            "scripts/install.sh",
            "--version",
            "v9.9.4-test",
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
    assert (prefix / "app" / "versions" / "v9.9.4-test").is_dir()
    assert "fake old python3 should not be used" not in result.stderr


def test_installed_start_flags_override_env_host_and_port(tmp_path):
    subprocess.run(
        ["bash", "scripts/package-release.sh", "v9.9.3-test", "--skip-build"],
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
    install = subprocess.run(
        [
            "bash",
            "scripts/install.sh",
            "--version",
            "v9.9.3-test",
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

    fake_python = tmp_path / "fake-python"
    fake_python.write_text(
        "#!/usr/bin/env sh\n"
        "printf '%s\\n' \"$@\"\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    start = subprocess.run(
        [
            "bash",
            str(prefix / "app" / "current" / "scripts" / "appctl.sh"),
            "start",
            "--host",
            "0.0.0.0",
            "--port",
            "8123",
        ],
        cwd=tmp_path,
        env={**env, "PYTHON": str(fake_python)},
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert start.returncode == 0, start.stdout + start.stderr
    assert "--host\n0.0.0.0" in start.stdout
    assert "--port\n8123" in start.stdout

    missing_host = subprocess.run(
        ["bash", str(prefix / "app" / "current" / "scripts" / "appctl.sh"), "start", "--host"],
        cwd=tmp_path,
        env={**env, "PYTHON": str(fake_python)},
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert missing_host.returncode == 2
    assert "Missing value for --host" in missing_host.stderr

    missing_port = subprocess.run(
        ["bash", str(prefix / "app" / "current" / "scripts" / "appctl.sh"), "start", "--port"],
        cwd=tmp_path,
        env={**env, "PYTHON": str(fake_python)},
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert missing_port.returncode == 2
    assert "Missing value for --port" in missing_port.stderr


def test_installed_doctor_reports_paths_db_and_provider_state_without_sensitive_values(tmp_path):
    subprocess.run(
        ["bash", "scripts/package-release.sh", "v9.9.2-test", "--skip-build"],
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
    install = subprocess.run(
        [
            "bash",
            "scripts/install.sh",
            "--version",
            "v9.9.2-test",
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

    appctl = prefix / "app" / "current" / "scripts" / "appctl.sh"
    doctor = subprocess.run(
        ["bash", str(appctl), "doctor"],
        cwd=tmp_path,
        env={**env, "IMAGE_PROMPT_LIBRARY_PREFIX": str(prefix)},
        text=True,
        capture_output=True,
        timeout=60,
    )

    assert doctor.returncode == 0, doctor.stdout + doctor.stderr
    assert "Image Prompt Library doctor" in doctor.stdout
    assert "Version: v9.9.2-test" in doctor.stdout
    assert f"Install prefix: {prefix}" in doctor.stdout
    assert f"Library path: {library}" in doctor.stdout
    assert "Backend: 127.0.0.1:8000" in doctor.stdout
    assert "Database integrity: ok" in doctor.stdout
    assert "Generation provider: openai_codex_oauth_native state=" in doctor.stdout
    assert "[REDACTED]" not in doctor.stdout
    assert "app_" not in doctor.stdout


def test_installed_service_commands_manage_macos_launchagent_with_fake_launchctl(tmp_path):
    subprocess.run(
        ["bash", "scripts/package-release.sh", "v9.9.1-test", "--skip-build"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
        timeout=120,
    )

    prefix = tmp_path / "prefix"
    library = tmp_path / "library-data"
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    calls = tmp_path / "launchctl-calls.log"
    (fake_bin / "launchctl").write_text(
        "#!/usr/bin/env sh\n"
        f"printf '%s ' \"$@\" >> {calls}\n"
        f"printf '\\n' >> {calls}\n"
        "if [ \"$1\" = \"print\" ]; then echo 'state = running'; fi\n",
        encoding="utf-8",
    )
    (fake_bin / "launchctl").chmod(0o755)
    (fake_bin / "plutil").write_text("#!/usr/bin/env sh\necho \"$2: OK\"\n", encoding="utf-8")
    (fake_bin / "plutil").chmod(0o755)

    env = os.environ.copy()
    env["HOME"] = str(fake_home)
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL"] = (ROOT / "dist-release").as_uri()
    env["IMAGE_PROMPT_LIBRARY_INSTALL_SKIP_RUNTIME_SETUP"] = "1"
    env["PYTHON"] = sys.executable
    install = subprocess.run(
        [
            "bash",
            "scripts/install.sh",
            "--version",
            "v9.9.1-test",
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

    appctl = prefix / "app" / "current" / "scripts" / "appctl.sh"
    service_env = {**env, "IMAGE_PROMPT_LIBRARY_PREFIX": str(prefix)}
    install_service = subprocess.run(
        [
            "bash",
            str(appctl),
            "service",
            "install",
            "--host",
            "0.0.0.0",
            "--port",
            "7500",
            "--label",
            "com.example.ipl-test",
        ],
        cwd=tmp_path,
        env=service_env,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert install_service.returncode == 0, install_service.stdout + install_service.stderr
    plist = fake_home / "Library" / "LaunchAgents" / "com.example.ipl-test.plist"
    assert plist.exists()
    plist_text = plist.read_text(encoding="utf-8")
    assert str(appctl) in plist_text
    assert "0.0.0.0" in plist_text
    assert "7500" in plist_text
    assert str(prefix) in plist_text
    assert "bootstrap gui/" in calls.read_text(encoding="utf-8")
    assert "kickstart -k gui/" in calls.read_text(encoding="utf-8")

    status = subprocess.run(
        ["bash", str(appctl), "service", "status", "--label", "com.example.ipl-test"],
        cwd=tmp_path,
        env=service_env,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert status.returncode == 0, status.stdout + status.stderr
    assert "state = running" in status.stdout

    stop = subprocess.run(
        ["bash", str(appctl), "service", "stop", "--label", "com.example.ipl-test"],
        cwd=tmp_path,
        env=service_env,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert stop.returncode == 0, stop.stdout + stop.stderr

    start = subprocess.run(
        ["bash", str(appctl), "service", "start", "--label", "com.example.ipl-test"],
        cwd=tmp_path,
        env=service_env,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert start.returncode == 0, start.stdout + start.stderr
    call_text = calls.read_text(encoding="utf-8")
    assert call_text.count("bootstrap gui/") >= 2
    assert "enable gui/" in call_text

    reinstall_without_replace = subprocess.run(
        [
            "bash",
            str(appctl),
            "service",
            "install",
            "--host",
            "127.0.0.1",
            "--port",
            "8010",
            "--label",
            "com.example.ipl-test",
        ],
        cwd=tmp_path,
        env=service_env,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert reinstall_without_replace.returncode == 2
    assert "already exists" in reinstall_without_replace.stderr

    uninstall = subprocess.run(
        ["bash", str(appctl), "service", "uninstall", "--label", "com.example.ipl-test"],
        cwd=tmp_path,
        env=service_env,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert uninstall.returncode == 0, uninstall.stdout + uninstall.stderr
    assert not plist.exists()
    assert "bootout gui/" in calls.read_text(encoding="utf-8")


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
