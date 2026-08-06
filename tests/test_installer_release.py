import gc
import hashlib
import io
import json
import os
import shlex
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

from PIL import Image
import pytest

from backend.db import init_db
from backend.repositories import ItemRepository

ROOT = Path(__file__).resolve().parents[1]
GIT_BASH_SHIM = Path(tempfile.gettempdir()) / "image-prompt-library-git-bash-test-bin"
GIT_BASH_SHIM.mkdir(exist_ok=True)
(GIT_BASH_SHIM / "python3").write_text(
    f"#!/usr/bin/env sh\nexec '{Path(sys.executable).as_posix()}' \"$@\"\n",
    encoding="utf-8",
)
(GIT_BASH_SHIM / "python3").chmod(0o755)
GIT_BASH = Path(r"C:\Program Files\Git\bin\bash.exe")
if not GIT_BASH.exists():
    GIT_BASH = Path(r"C:\Program Files\Git\usr\bin\bash.exe")
if not GIT_BASH.exists():
    GIT_BASH = Path("bash")


def git_bash_arg(part: object) -> str:
    value = part.as_posix() if isinstance(part, Path) else str(part)
    return value.replace("\\", "/")


def git_bash_path(value: object) -> str:
    path = git_bash_arg(value)
    if len(path) >= 2 and path[1] == ":":
        return f"/{path[0].lower()}{path[2:]}"
    return path


def git_bash_path_entries(value: str) -> str:
    entries = []
    for entry in value.split(os.pathsep):
        if not entry:
            continue
        if "pytest-" in entry or "pytest-of-" in entry:
            entries.append(git_bash_path(entry))
    return ":".join(entries)


def git_bash_env(env: dict[str, str] | None) -> dict[str, str] | None:
    if env is None:
        return None
    patched = dict(env)
    for key in (
        "HOME",
        "PYTHON",
        "SAMPLE_DATA_MANIFEST",
        "SAMPLE_DATA_IMAGE_ZIP",
        "IMAGE_PROMPT_LIBRARY_PREFIX",
        "IMAGE_PROMPT_LIBRARY_PATH",
        "IMAGE_PROMPT_LIBRARY_AUTH_PATH",
        "IMAGE_PROMPT_LIBRARY_CONFIG_PATH",
        "BACKUP_DIR",
    ):
        if key in patched:
            patched[key] = git_bash_path(patched[key])
    return patched


def git_bash_cmd(*parts: object, env: dict[str, str] | None = None) -> list[str]:
    command = " ".join(shlex.quote(git_bash_arg(part)) for part in parts)
    python = shlex.quote(Path(sys.executable).as_posix())
    prefix = f"python3() {{ {python} \"$@\"; }}; export -f python3; export PATH={shlex.quote(git_bash_path(GIT_BASH_SHIM))}:$PATH"
    if env and "PATH" in env:
        path_entries = git_bash_path_entries(env["PATH"])
        if path_entries:
            prefix += f"; export PATH={shlex.quote(path_entries)}:$PATH"
    return [str(GIT_BASH), "-lc", f"{prefix}; {command}"]


_subprocess_run = subprocess.run
_subprocess_check_output = subprocess.check_output


def _rewrite_bash_args(args: object, kwargs: dict[str, object]) -> tuple[object, dict[str, object]]:
    if os.name != "nt":
        return args, kwargs
    if not isinstance(args, (list, tuple)) or not args or args[0] != "bash":
        return args, kwargs
    if len(args) > 1 and args[1] == "-lc":
        return args, kwargs
    env = kwargs.get("env")
    rewritten_kwargs = dict(kwargs)
    rewritten_kwargs["env"] = git_bash_env(env if isinstance(env, dict) else None)
    return git_bash_cmd(*args[1:], env=env if isinstance(env, dict) else None), rewritten_kwargs


def run_subprocess(*popenargs: object, **kwargs: object) -> subprocess.CompletedProcess:
    if popenargs:
        args, kwargs = _rewrite_bash_args(popenargs[0], kwargs)
        popenargs = (args, *popenargs[1:])
    return _subprocess_run(*popenargs, **kwargs)


def check_output_subprocess(*popenargs: object, **kwargs: object) -> str | bytes:
    if popenargs:
        args, kwargs = _rewrite_bash_args(popenargs[0], kwargs)
        popenargs = (args, *popenargs[1:])
    return _subprocess_check_output(*popenargs, **kwargs)


subprocess.run = run_subprocess
subprocess.check_output = check_output_subprocess


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def package_release(tmp_path: Path, version: str) -> Path:
    release_dir = tmp_path / "dist-release"
    env = os.environ.copy()
    env["IMAGE_PROMPT_LIBRARY_RELEASE_DIR"] = git_bash_path(release_dir)
    env["IMAGE_PROMPT_LIBRARY_SOURCE_SHA"] = "a" * 40
    result = subprocess.run(
        ["bash", "scripts/package-release.sh", version, "--skip-build"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return release_dir


def write_synthetic_release(
    release_dir: Path,
    version: str = "v1.2.3",
    *,
    extra_member: tarfile.TarInfo | None = None,
    extra_payload: bytes = b"fixture",
) -> None:
    release_dir.mkdir(parents=True, exist_ok=True)
    artifact_name = f"image-prompt-library-{version}.tar.gz"
    artifact = release_dir / artifact_name
    required = {
        "VERSION",
        "pyproject.toml",
        "backend/main.py",
        "frontend/dist/index.html",
        "scripts/appctl.sh",
        "scripts/library-archive.py",
        "scripts/install.sh",
        "scripts/load-env.sh",
        "scripts/install-sample-data.sh",
        "scripts/setup-runtime.sh",
        "scripts/verify-release-assets.py",
        "scripts/appctl.ps1",
        "scripts/install.ps1",
        "scripts/install-sample-data.ps1",
        "scripts/setup-runtime.ps1",
    }
    with tarfile.open(artifact, "w:gz") as archive:
        for name in sorted(required):
            payload = (version + "\n").encode() if name == "VERSION" else b"fixture\n"
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            info.mode = 0o755 if name.endswith(".sh") else 0o644
            archive.addfile(info, io.BytesIO(payload))
        if extra_member is not None:
            extra_member.size = len(extra_payload)
            archive.addfile(extra_member, io.BytesIO(extra_payload))
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    (release_dir / f"{artifact_name}.sha256").write_text(
        f"{digest}  {artifact_name}\n", encoding="utf-8"
    )
    (release_dir / f"image-prompt-library-{version}.manifest.json").write_text(
        json.dumps({
            "name": "image-prompt-library",
            "version": version,
            "schema_version": 2,
            "artifact": artifact_name,
            "sha256": digest,
            "source_sha": "a" * 40,
            "capabilities": ["windows-powershell-v1", "posix-shell-v1"],
        }),
        encoding="utf-8",
    )


def run_release_verifier(
    release_dir: Path,
    version: str = "v1.2.3",
    *,
    expected_source_sha: str | None = "a" * 40,
) -> subprocess.CompletedProcess:
    command = [
        sys.executable,
        "scripts/verify-release-assets.py",
        str(release_dir),
        version,
        "--capability",
        "posix-shell-v1",
    ]
    if expected_source_sha is not None:
        command.extend(["--source-sha", expected_source_sha])
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=30,
    )


def test_backup_archive_excludes_external_auth_and_config_files(tmp_path):
    library = tmp_path / "library"
    for directory in ("originals", "thumbs", "previews", "generation-results", "generation-references"):
        (library / directory).mkdir(parents=True, exist_ok=True)
    init_db(library)
    (library / "originals" / "image.txt").write_text("fixture-image", encoding="utf-8")
    auth_path = tmp_path / "app-state" / "auth.json"
    config_path = tmp_path / "app-state" / "config.json"
    auth_path.parent.mkdir()
    auth_path.write_text("backup-auth-canary", encoding="utf-8")
    config_path.write_text("backup-config-canary", encoding="utf-8")
    backup_dir = tmp_path / "backups"
    env = os.environ.copy()
    env.update({
        "PYTHON": sys.executable,
        "IMAGE_PROMPT_LIBRARY_PATH": str(library),
        "IMAGE_PROMPT_LIBRARY_AUTH_PATH": str(auth_path),
        "IMAGE_PROMPT_LIBRARY_CONFIG_PATH": str(config_path),
        "BACKUP_DIR": str(backup_dir),
    })

    result = subprocess.run(
        ["bash", "scripts/backup.sh"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    archives = list(backup_dir.glob("image-prompt-library-*.tar.gz"))
    assert len(archives) == 1
    with tarfile.open(archives[0], "r:gz") as archive:
        archive_bytes = b"".join(
            extracted.read()
            for member in archive.getmembers()
            if member.isfile()
            for extracted in (archive.extractfile(member),)
            if extracted is not None
        )
    assert b"backup-auth-canary" not in archive_bytes
    assert b"backup-config-canary" not in archive_bytes


@pytest.mark.parametrize(
    ("env_name", "relative_path"),
    (
        ("IMAGE_PROMPT_LIBRARY_AUTH_PATH", "originals/auth.json"),
        ("IMAGE_PROMPT_LIBRARY_CONFIG_PATH", "config.json"),
    ),
)
def test_backup_refuses_app_owned_path_inside_library(tmp_path, env_name, relative_path):
    library = tmp_path / "library"
    init_db(library)
    unsafe_path = library / relative_path
    unsafe_path.parent.mkdir(parents=True, exist_ok=True)
    unsafe_path.write_text("unsafe-backup-canary", encoding="utf-8")
    backup_dir = tmp_path / "backups"
    env = os.environ.copy()
    env.update({
        "PYTHON": sys.executable,
        "IMAGE_PROMPT_LIBRARY_PATH": str(library),
        "IMAGE_PROMPT_LIBRARY_AUTH_PATH": str(tmp_path / "app-state" / "auth.json"),
        "IMAGE_PROMPT_LIBRARY_CONFIG_PATH": str(tmp_path / "app-state" / "config.json"),
        "BACKUP_DIR": str(backup_dir),
        env_name: str(unsafe_path),
    })

    result = subprocess.run(
        ["bash", "scripts/backup.sh"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode != 0
    assert env_name in result.stderr
    assert "unsafe-backup-canary" not in result.stderr
    assert not list(backup_dir.glob("*.tar.gz"))


def test_backup_refuses_external_resolving_library_storage_root(tmp_path):
    library = tmp_path / "library"
    init_db(library)
    external = tmp_path / "app-state"
    external.mkdir()
    (external / "auth.json").write_text("junction-auth-canary", encoding="utf-8")
    (library / "originals").rmdir()
    try:
        (library / "originals").symlink_to(external, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"directory symlinks are unavailable: {exc}")
    backup_dir = tmp_path / "backups"
    env = os.environ.copy()
    env.update({
        "PYTHON": sys.executable,
        "IMAGE_PROMPT_LIBRARY_PATH": str(library),
        "IMAGE_PROMPT_LIBRARY_AUTH_PATH": str(external / "auth.json"),
        "IMAGE_PROMPT_LIBRARY_CONFIG_PATH": str(tmp_path / "config-state" / "config.json"),
        "BACKUP_DIR": str(backup_dir),
    })

    result = subprocess.run(
        ["bash", "scripts/backup.sh"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode != 0
    assert "originals" in result.stderr
    assert "junction-auth-canary" not in result.stderr
    assert not list(backup_dir.glob("*.tar.gz"))


def test_posix_controller_backup_verify_restore_round_trip(tmp_path):
    library = tmp_path / "library"
    init_db(library)
    for root in ("originals", "thumbs", "previews", "generation-results", "generation-references"):
        path = library / root
        path.mkdir(parents=True, exist_ok=True)
        (path / f"{root}.txt").write_text(f"{root}-before", encoding="utf-8")
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    archive = tmp_path / "portable-backup.tar.gz"
    env = {
        **os.environ,
        "PYTHON": sys.executable,
        "PYTHONUTF8": "1",
        "IMAGE_PROMPT_LIBRARY_PREFIX": str(prefix),
        "IMAGE_PROMPT_LIBRARY_PATH": str(library),
        "IMAGE_PROMPT_LIBRARY_AUTH_PATH": str(tmp_path / "state" / "auth.json"),
        "IMAGE_PROMPT_LIBRARY_CONFIG_PATH": str(tmp_path / "state" / "config.json"),
        "BACKUP_DIR": str(tmp_path / "backups"),
    }
    gc.collect()

    backup = subprocess.run(
        ["bash", "scripts/appctl.sh", "backup", "--output", str(archive)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert backup.returncode == 0, backup.stdout + backup.stderr
    verified = subprocess.run(
        ["bash", "scripts/appctl.sh", "verify-backup", str(archive)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert verified.returncode == 0, verified.stdout + verified.stderr

    (library / "originals" / "originals.txt").write_text("mutated", encoding="utf-8")
    restored = subprocess.run(
        ["bash", "scripts/appctl.sh", "restore", str(archive), "--yes"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert restored.returncode == 0, restored.stdout + restored.stderr
    assert (library / "originals" / "originals.txt").read_text(encoding="utf-8") == "originals-before"
    assert list(tmp_path.glob(".library.pre-restore-*"))


def test_installer_and_runtime_scripts_define_versioned_install_contract():
    install_script = ROOT / "scripts" / "install.sh"
    appctl_script = ROOT / "scripts" / "appctl.sh"
    setup_runtime_script = ROOT / "scripts" / "setup-runtime.sh"
    package_script = ROOT / "scripts" / "package-release.sh"

    assert install_script.exists()
    assert appctl_script.exists()
    assert "portable-backup-v1" in install_script.read_text(encoding="utf-8")
    assert setup_runtime_script.exists()
    assert package_script.exists()

    install = install_script.read_text(encoding="utf-8")
    appctl = appctl_script.read_text(encoding="utf-8")
    setup_runtime = setup_runtime_script.read_text(encoding="utf-8")
    package = package_script.read_text(encoding="utf-8")

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
    assert "api.github.com/repos/{repo}/releases?per_page=100&page={page}" in install
    assert "releases/latest" not in install
    assert "image-prompt-library-{canonical}.manifest.json" in install
    assert "image-prompt-library-{canonical}.tar.gz" in install
    assert "sha256" in install.lower()
    assert "~/.image-prompt-library" in install
    assert 'VERSIONS_DIR="$APP_DIR/versions"' in install
    assert 'CURRENT_LINK="$APP_DIR/current"' in install
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
    assert "status)" in appctl
    assert "status_app()" in appctl
    assert "Image Prompt Library status" in appctl
    assert "## App" in appctl
    assert "## Next steps" in appctl
    assert "service)" in appctl
    assert "service install" in appctl
    assert "launchctl" in appctl
    assert "LaunchAgents" in appctl
    assert "update)" in appctl
    assert "PYTHON=\"$PYTHON_BIN\" bash \"$SCRIPT_DIR/install.sh\"" in appctl
    assert "rollback)" in appctl
    assert "backup)" in appctl
    assert "verify-backup)" in appctl
    assert "restore)" in appctl
    assert "library-archive.py" in appctl
    assert "sample-data)" in appctl
    assert "uninstall)" in appctl
    assert "install-sample-data.sh" in appctl
    assert "IMAGE_PROMPT_LIBRARY_PATH" in appctl
    assert "~/ImagePromptLibrary" in appctl
    assert "uvicorn backend.main:app" in appctl
    assert "app/previous" in appctl
    assert "validate_legacy_v080_rollback_runtime" in appctl
    assert "migrate_legacy_v080_management" in appctl
    assert ".rollback-migration.json" in appctl
    assert "scripts/load-env.sh" in appctl
    assert "source_controller_version" in appctl
    assert "legacy_sha256" in appctl
    assert "os.O_NOFOLLOW" in appctl
    assert "src_dir_fd=directory" in appctl
    assert '"$target/.venv/bin"' in appctl
    assert 'marker_payload("prepared")' in appctl
    assert 'marker_payload("complete")' in appctl

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


def test_release_assets_workflow_builds_and_uploads_candidate_artifacts():
    workflow_path = ROOT / ".github" / "workflows" / "release-assets.yml"
    assert workflow_path.exists()
    workflow = workflow_path.read_text(encoding="utf-8")

    assert "tags:" not in workflow
    assert "push:" not in workflow
    assert "workflow_dispatch:" in workflow
    assert "publish as a prerelease candidate" in workflow
    assert "actions/checkout@v5" in workflow
    assert "actions/setup-python@v6" in workflow
    assert "actions/setup-node@v5" in workflow
    assert "python -m pytest -q" in workflow
    assert "npm run build" in workflow
    assert "scripts/package-release.sh" in workflow
    assert "softprops/action-gh-release" in workflow or "gh release upload" in workflow
    assert "contents: write" in workflow
    assert "draft: true" in workflow
    assert "IS_PRERELEASE=true" in workflow
    assert "MAKE_LATEST=false" in workflow
    assert 'gh api --method POST "repos/$GITHUB_REPOSITORY/git/refs"' in workflow
    assert "fail_on_unmatched_files: true" in workflow
    assert "releases/assets/$asset_id" in workflow
    assert "dist-release-readback" in workflow
    assert "scripts/verify-release-assets.py" in workflow
    assert workflow.count("--capability portable-backup-v1") == 2
    assert "draft=false" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "RESUME_PUBLISHED" in workflow
    assert "EXISTING_RELEASE_ID" in workflow


def test_readme_prefers_installer_for_users_and_keeps_source_setup_for_developers():
    readme = read("README.md")
    installation = read("docs/INSTALLATION.md")

    assert "## Quick start" in readme
    assert "scripts/install.sh" in installation
    assert "image-prompt-library start" in readme
    assert "image-prompt-library status" in readme
    assert "image-prompt-library update" in installation
    assert "image-prompt-library update --version <version>" in installation
    assert "curl -fsSL https://raw.githubusercontent.com/EddieTYP/image-prompt-library/main/scripts/install.sh | bash -s -- --version <version>" in installation
    assert "image-prompt-library rollback" in installation
    assert "image-prompt-library sample-data en" in readme
    assert "image-prompt-library uninstall" in installation
    assert "Normal release installs require" in readme
    assert "GitHub Release assets" in installation
    assert "source/development installs" in installation
    assert "git clone https://github.com/EddieTYP/image-prompt-library.git" in (
        ROOT / "docs" / "DEVELOPMENT.md"
    ).read_text(encoding="utf-8")
    assert "Node.js" in installation
    assert "Normal release installs do not require Node.js" in installation
    assert "~/ImagePromptLibrary" in installation
    assert "~/.image-prompt-library/app/versions" in installation
    assert "Add/Edit, private library management, and image generation are local-install features" in readme
    assert "image-prompt-library start --host 0.0.0.0" in installation
    assert "Binding to `0.0.0.0` can expose the app" in installation
    assert "image-prompt-library doctor" in installation
    assert "image-prompt-library status" in installation
    assert "image-prompt-library service install --host 127.0.0.1 --port 8000" in installation
    assert "image-prompt-library service install --host 0.0.0.0 --port 7500" not in readme
    assert "Use the next release tag" not in readme


def test_package_release_creates_manifest_and_excludes_private_runtime_data(tmp_path):
    release_dir = package_release(tmp_path, "v9.9.9-test")
    manifest_path = release_dir / "image-prompt-library-v9.9.9-test.manifest.json"
    tarball_path = release_dir / "image-prompt-library-v9.9.9-test.tar.gz"
    checksum_path = release_dir / "image-prompt-library-v9.9.9-test.tar.gz.sha256"

    assert manifest_path.exists()
    assert tarball_path.exists()
    assert checksum_path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["name"] == "image-prompt-library"
    assert manifest["version"] == "v9.9.9-test"
    assert manifest["artifact"] == tarball_path.name
    assert manifest["capabilities"] == ["windows-powershell-v1", "posix-shell-v1", "portable-backup-v1"]
    assert manifest["schema_version"] == 2
    assert len(manifest["source_sha"]) == 40
    assert manifest["sha256"] in checksum_path.read_text(encoding="utf-8")
    assert manifest["node_required_for_runtime"] is False
    assert manifest["built_frontend"] is True

    listing = subprocess.check_output(
        ["tar", "-tzf", str(tarball_path)], cwd=ROOT, text=True, timeout=30
    )
    assert "backend/" in listing
    assert "frontend/dist/index.html" in listing
    with tarfile.open(tarball_path, "r:gz") as archive:
        index_html = archive.extractfile("frontend/dist/index.html").read().decode("utf-8")
    assert '/image-prompt-library/assets/' not in index_html
    assert '/assets/' in index_html
    assert "frontend/dist/assets/" in listing
    assert "scripts/appctl.sh" in listing
    assert "scripts/library-archive.py" in listing
    assert "scripts/install.sh" in listing
    assert "scripts/load-env.sh" in listing
    assert "scripts/setup-runtime.sh" in listing
    assert "scripts/install-sample-data.sh" in listing
    assert "scripts/verify-release-assets.py" in listing
    for windows_script in (
        "scripts/appctl.ps1",
        "scripts/install.ps1",
        "scripts/install-sample-data.ps1",
        "scripts/setup-runtime.ps1",
    ):
        assert windows_script in listing
    with tarfile.open(tarball_path, "r:gz") as archive:
        script_members = {
            name: member
            for member in archive.getmembers()
            if member.isfile()
            for name in (member.name[2:] if member.name.startswith("./") else member.name,)
            if name.startswith("scripts/")
        }
    assert all(
        member.mode & 0o777 in ({0o644, 0o755} if name == "scripts/verify-release-assets.py" else {(0o755 if name.endswith(".sh") else 0o644)})
        for name, member in script_members.items()
    )
    for dev_script in (
        "scripts/dev.sh",
        "scripts/setup.sh",
        "scripts/start.sh",
        "scripts/smoke-test.sh",
        "scripts/backup.sh",
        "scripts/package-release.sh",
        "scripts/export-demo-data.py",
        "scripts/benchmark_generation_models.py",
        "scripts/check-codex-oauth-upstream.py",
        "scripts/codex_native_oauth_smoke.py",
    ):
        assert dev_script not in listing
    for maintenance_module in (
        "backend/services/build_awesome_gpt_image_2_sample_manifest.py",
        "backend/services/build_gpt_image_sample_manifests.py",
        "backend/services/fill_sample_manifest_translations.py",
        "backend/services/import_gpt_image_2_skill.py",
    ):
        assert maintenance_module not in listing
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


@pytest.mark.parametrize("dirty_relative", ("backend/main.py", "vite.config.ts", "tsconfig.json"))
def test_package_release_rejects_implicit_source_sha_for_dirty_packaged_input(tmp_path, dirty_relative):
    source = tmp_path / "source"
    (source / "scripts").mkdir(parents=True)
    for relative in ("scripts/package-release.sh", "scripts/verify-release-assets.py"):
        target = source / relative
        target.write_bytes((ROOT / relative).read_bytes())
    dirty_path = source / dirty_relative
    dirty_path.parent.mkdir(parents=True, exist_ok=True)
    dirty_path.write_text("clean = True\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=source, check=True, capture_output=True)
    subprocess.run(["git", "add", dirty_relative, "scripts/package-release.sh", "scripts/verify-release-assets.py"], cwd=source, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "fixture"],
        cwd=source,
        check=True,
        capture_output=True,
    )
    dirty_path.write_text("clean = False\n", encoding="utf-8")
    env = os.environ.copy()
    env.pop("IMAGE_PROMPT_LIBRARY_SOURCE_SHA", None)

    result = subprocess.run(
        ["bash", "scripts/package-release.sh", "v1.2.3", "--skip-build"],
        cwd=source,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode == 2
    assert "Packaged source inputs are dirty" in result.stderr


def test_package_release_requires_explicit_source_sha_when_skipping_build(tmp_path):
    source = tmp_path / "source"
    (source / "scripts").mkdir(parents=True)
    for relative in ("scripts/package-release.sh", "scripts/verify-release-assets.py"):
        (source / relative).write_bytes((ROOT / relative).read_bytes())
    subprocess.run(["git", "init"], cwd=source, check=True, capture_output=True)
    subprocess.run(["git", "add", "scripts/package-release.sh", "scripts/verify-release-assets.py"], cwd=source, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "fixture"],
        cwd=source,
        check=True,
        capture_output=True,
    )
    env = os.environ.copy()
    env.pop("IMAGE_PROMPT_LIBRARY_SOURCE_SHA", None)

    result = subprocess.run(
        ["bash", "scripts/package-release.sh", "v1.2.3", "--skip-build"],
        cwd=source,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode == 2
    assert "--skip-build requires IMAGE_PROMPT_LIBRARY_SOURCE_SHA" in result.stderr


def test_release_verifier_rejects_tamper_traversal_and_private_members(tmp_path):
    valid = tmp_path / "valid"
    write_synthetic_release(valid)
    assert run_release_verifier(valid).returncode == 0

    artifact = valid / "image-prompt-library-v1.2.3.tar.gz"
    artifact.write_bytes(artifact.read_bytes() + b"tampered")
    tampered = run_release_verifier(valid)
    assert tampered.returncode != 0
    assert "SHA256" in tampered.stderr

    traversal = tmp_path / "traversal"
    write_synthetic_release(traversal, extra_member=tarfile.TarInfo("../escape.txt"))
    unsafe = run_release_verifier(traversal)
    assert unsafe.returncode != 0
    assert "unsafe archive member" in unsafe.stderr

    private = tmp_path / "private"
    write_synthetic_release(private, extra_member=tarfile.TarInfo(".agents/session.txt"))
    leaked = run_release_verifier(private)
    assert leaked.returncode != 0
    assert "forbidden private/runtime" in leaked.stderr

    env_local = tmp_path / "env-local"
    write_synthetic_release(env_local, extra_member=tarfile.TarInfo("backend/.env.local"))
    leaked_env = run_release_verifier(env_local)
    assert leaked_env.returncode != 0
    assert "forbidden private/runtime" in leaked_env.stderr


def test_release_manifest_v2_requires_source_sha_but_legacy_v1_remains_readable(tmp_path):
    release_dir = tmp_path / "release"
    write_synthetic_release(release_dir)
    manifest_path = release_dir / "image-prompt-library-v1.2.3.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("source_sha")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    missing = run_release_verifier(release_dir)
    assert missing.returncode != 0
    assert "missing source_sha" in missing.stderr

    manifest["schema_version"] = 1
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    legacy = run_release_verifier(release_dir, expected_source_sha=None)
    assert legacy.returncode == 0, legacy.stdout + legacy.stderr


@pytest.mark.parametrize(
    "version",
    [
        " v1.2.3", "v1.2.3 ", "../v1.2.3", "v01.2.3", "v1.2",
        "v1.2.3-01", "v1.2.3+build.1", "v1٢.2.3", "v1.2.3\n",
    ],
)
def test_posix_installer_rejects_invalid_version_before_creating_prefix(tmp_path, version):
    prefix = tmp_path / "prefix"
    result = subprocess.run(
        ["bash", "scripts/install.sh", "--version", version, "--prefix", str(prefix), "--no-shim"],
        cwd=ROOT,
        env={**os.environ, "PYTHON": sys.executable},
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert "invalid" in result.stderr.lower()
    assert not prefix.exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink boundary is covered by the Ubuntu CI job")
def test_posix_installer_refuses_symlinked_versions_parent_without_external_cleanup(tmp_path):
    prefix = tmp_path / "prefix"
    outside = tmp_path / "outside"
    versions = prefix / "app" / "versions"
    outside.mkdir()
    versions.parent.mkdir(parents=True)
    versions.symlink_to(outside, target_is_directory=True)
    sentinel = outside / (".staging-" + "a" * 32)
    sentinel.mkdir()
    (sentinel / "keep.txt").write_text("keep", encoding="utf-8")

    result = subprocess.run(
        [
            "bash", "scripts/install.sh", "--version", "v1.2.3",
            "--prefix", str(prefix), "--library-path", str(tmp_path / "library"), "--no-shim",
        ],
        cwd=ROOT,
        env={**os.environ, "PYTHON": sys.executable},
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode != 0
    assert "symlink" in result.stderr.lower()
    assert (sentinel / "keep.txt").read_text(encoding="utf-8") == "keep"


@pytest.mark.skipif(os.name == "nt", reason="POSIX dangling symlink behavior is covered by the Ubuntu CI job")
def test_posix_installer_retains_dangling_exact_backup_symlink(tmp_path):
    version = "v1.2.3"
    prefix = tmp_path / "prefix"
    versions = prefix / "app" / "versions"
    versions.mkdir(parents=True)
    backup = versions / f"{version}.backup"
    backup.symlink_to(tmp_path / "missing-backup", target_is_directory=True)

    result = subprocess.run(
        [
            "bash", "scripts/install.sh", "--version", version,
            "--prefix", str(prefix), "--library-path", str(tmp_path / "library"), "--no-shim",
        ],
        cwd=ROOT,
        env={**os.environ, "PYTHON": sys.executable},
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode != 0
    assert "backup remnant retained" in result.stderr.lower()
    assert backup.is_symlink()


@pytest.mark.skipif(os.name == "nt", reason="POSIX private-path symlinks are covered by the Ubuntu CI job")
def test_posix_installer_rejects_symlinked_private_library_without_external_writes(tmp_path):
    prefix = tmp_path / "prefix"
    outside = tmp_path / "outside-library"
    outside.mkdir()
    sentinel = outside / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    library_alias = tmp_path / "library-alias"
    library_alias.symlink_to(outside, target_is_directory=True)

    result = subprocess.run(
        [
            "bash", "scripts/install.sh", "--version", "v1.2.3",
            "--prefix", str(prefix), "--library-path", str(library_alias), "--no-shim",
        ],
        cwd=ROOT,
        env={**os.environ, "PYTHON": sys.executable},
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode != 0
    assert "library path contains a symlink" in result.stderr.lower()
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_posix_installer_rejects_private_library_inside_install_prefix(tmp_path):
    prefix = tmp_path / "prefix"
    result = subprocess.run(
        [
            "bash", "scripts/install.sh", "--version", "v1.2.3",
            "--prefix", str(prefix), "--library-path", str(prefix / "private-library"), "--no-shim",
        ],
        cwd=ROOT,
        env={**os.environ, "PYTHON": sys.executable},
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode != 0
    assert "must not contain each other" in result.stderr.lower()
    assert not (prefix / "app").exists()


def test_installer_supports_file_release_base_and_installs_without_git(tmp_path):
    release_dir = package_release(tmp_path, "v9.9.8-test")

    prefix = tmp_path / "prefix"
    library = tmp_path / "library-data"
    env = os.environ.copy()
    env["IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL"] = release_dir.as_uri()
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
    assert current.exists()
    if current.is_symlink():
        assert current.resolve() == installed.resolve()
    else:
        assert (current / "scripts" / "appctl.sh").exists()
    assert not previous.exists() or previous.is_symlink()

    env_file = prefix / ".env"
    assert env_file.exists()
    env_text = env_file.read_text(encoding="utf-8")
    assert f"IMAGE_PROMPT_LIBRARY_PATH={git_bash_arg(library)}" in env_text
    assert f"BACKUP_DIR={git_bash_arg(prefix)}/backups" in env_text
    assert "BACKEND_PORT=8000" in env_text
    assert "IMAGE_PROMPT_LIBRARY_AUTH_PATH" not in env_text
    assert "IMAGE_PROMPT_LIBRARY_CONFIG_PATH" not in env_text
    assert str(library) not in str(installed)

    version = subprocess.check_output(
        ["bash", str(current / "scripts" / "appctl.sh"), "version"],
        text=True,
        timeout=30,
    ).strip()
    assert "v9.9.8-test" in version


def test_posix_latest_release_skips_prerelease_and_installs_stable(tmp_path):
    stable_version = "v1.2.3"
    incompatible_version = "v9.1.0"
    release_dir = package_release(tmp_path, stable_version)
    mock_python = tmp_path / "mock-python"
    mock_python.mkdir()
    stable_assets = [
        f"image-prompt-library-{stable_version}.manifest.json",
        f"image-prompt-library-{stable_version}.tar.gz",
        f"image-prompt-library-{stable_version}.tar.gz.sha256",
    ]

    def api_assets(version: str):
        return [
            {
                "name": name.replace(stable_version, version),
                "browser_download_url": (
                    "https://github.com/EddieTYP/image-prompt-library/"
                    f"releases/download/{version}/{name.replace(stable_version, version)}"
                ),
            }
            for name in stable_assets
        ]

    releases = [
        {
            "draft": False,
            "prerelease": True,
            "tag_name": "v9.0.0-rc.1",
            "assets": api_assets("v9.0.0-rc.1"),
        },
        {
            "draft": False,
            "prerelease": False,
            "tag_name": stable_version,
            "assets": api_assets(stable_version),
        },
    ]
    first_page = [
        {
            "draft": False,
            "prerelease": False,
            "tag_name": incompatible_version,
            "assets": api_assets(incompatible_version),
        },
        *({"draft": True, "prerelease": False} for _ in range(99)),
    ]
    (mock_python / "sitecustomize.py").write_text(
        "import io, json, os, pathlib, urllib.parse, urllib.request\n"
        f"FIRST_PAGE = {first_page!r}\n"
        f"RELEASES = {releases!r}\n"
        "_original = urllib.request.urlopen\n"
        "def _open(url, *args, **kwargs):\n"
        "    value = getattr(url, 'full_url', str(url))\n"
        "    if '/releases?per_page=' in value:\n"
        "        page = urllib.parse.parse_qs(urllib.parse.urlparse(value).query).get('page', ['1'])[0]\n"
        "        return io.BytesIO(json.dumps(FIRST_PAGE if page == '1' else RELEASES).encode())\n"
        "    if '/releases/download/' in value:\n"
        f"        if value.endswith('image-prompt-library-{incompatible_version}.manifest.json'):\n"
        f"            return io.BytesIO(json.dumps({{'name': 'image-prompt-library', 'version': '{incompatible_version}', 'artifact': 'image-prompt-library-{incompatible_version}.tar.gz', 'capabilities': ['windows-powershell-v1']}}).encode())\n"
        "        return open(pathlib.Path(os.environ['MOCK_RELEASE_DIR']) / value.rsplit('/', 1)[-1], 'rb')\n"
        "    return _original(url, *args, **kwargs)\n"
        "urllib.request.urlopen = _open\n",
        encoding="utf-8",
    )
    prefix = tmp_path / "prefix"
    library = tmp_path / "library"
    env = {
        **os.environ,
        "PYTHON": sys.executable,
        "PYTHONPATH": str(mock_python),
        "MOCK_RELEASE_DIR": str(release_dir),
        "IMAGE_PROMPT_LIBRARY_INSTALL_SKIP_RUNTIME_SETUP": "1",
    }
    env.pop("IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL", None)

    result = subprocess.run(
        [
            "bash", "scripts/install.sh", "--prefix", str(prefix),
            "--library-path", str(library), "--no-shim",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (prefix / "app" / "versions" / stable_version).is_dir()
    assert not (prefix / "app" / "versions" / "v9.0.0-rc.1").exists()


def test_posix_installer_reconciles_owned_remnants_and_same_version_is_safe(tmp_path):
    version = "v9.9.7-test"
    release_dir = package_release(tmp_path, version)
    prefix = tmp_path / "prefix"
    library = tmp_path / "library-data"
    env = {
        **os.environ,
        "IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL": release_dir.as_uri(),
        "IMAGE_PROMPT_LIBRARY_INSTALL_SKIP_RUNTIME_SETUP": "1",
        "PYTHON": sys.executable,
    }
    command = [
        "bash", "scripts/install.sh", "--version", version,
        "--prefix", str(prefix), "--library-path", str(library), "--no-shim",
    ]
    first = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, timeout=120)
    assert first.returncode == 0, first.stdout + first.stderr

    versions = prefix / "app" / "versions"
    installed = versions / version
    backup = versions / f"{version}.backup"
    staging = versions / (".staging-" + "a" * 32)
    staging.mkdir()
    import shutil
    shutil.copytree(installed, backup)
    (installed / "same-version-sentinel").write_text("keep", encoding="utf-8")
    previous = prefix / "app" / "previous"
    older = versions / "v9.9.6-test"
    shutil.copytree(installed, older)
    (older / "VERSION").write_text("v9.9.6-test\n", encoding="utf-8")
    if previous.exists() or previous.is_symlink():
        previous.unlink()
    try:
        previous.symlink_to(older, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Host cannot create POSIX installer symlinks: {exc}")

    second = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, timeout=120)
    assert second.returncode == 0, second.stdout + second.stderr
    assert (installed / "same-version-sentinel").read_text(encoding="utf-8") == "keep"
    assert not backup.exists()
    assert not staging.exists()
    assert previous.resolve() == older.resolve()

    lock = prefix / ".transaction.lock"
    lock.mkdir()
    (lock / "owner").write_text("99999999\n", encoding="utf-8")
    retry = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, timeout=120)
    assert retry.returncode == 0, retry.stdout + retry.stderr
    assert not lock.exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink replacement is covered by the Ubuntu CI job")
def test_posix_installer_update_swaps_existing_symlink_pointers(tmp_path):
    old_version = "v9.9.2-test"
    new_version = "v9.9.3-test"
    old_release_root = tmp_path / "old-release"
    new_release_root = tmp_path / "new-release"
    old_release_root.mkdir()
    new_release_root.mkdir()
    old_release = package_release(old_release_root, old_version)
    new_release = package_release(new_release_root, new_version)
    prefix = tmp_path / "prefix"
    library = tmp_path / "library-data"
    env = {
        **os.environ,
        "IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL": old_release.as_uri(),
        "IMAGE_PROMPT_LIBRARY_INSTALL_SKIP_RUNTIME_SETUP": "1",
        "PYTHON": sys.executable,
    }
    command = [
        "bash", "scripts/install.sh", "--prefix", str(prefix),
        "--library-path", str(library), "--no-shim",
    ]

    first = subprocess.run(
        [*command, "--version", old_version],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert first.returncode == 0, first.stdout + first.stderr

    env["IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL"] = new_release.as_uri()
    second = subprocess.run(
        [*command, "--version", new_version],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert second.returncode == 0, second.stdout + second.stderr

    versions = prefix / "app" / "versions"
    current = prefix / "app" / "current"
    previous = prefix / "app" / "previous"
    assert current.resolve() == (versions / new_version).resolve()
    assert previous.resolve() == (versions / old_version).resolve()
    assert not list((versions / old_version).glob(".*.tmp.*"))


@pytest.mark.skipif(os.name == "nt", reason="POSIX lock symlink behavior is covered by the Ubuntu CI job")
def test_posix_installer_refuses_symlinked_transaction_lock_without_external_mutation(tmp_path):
    version = "v9.9.7-test"
    release_dir = package_release(tmp_path, version)
    prefix = tmp_path / "prefix"
    outside = tmp_path / "outside-lock"
    prefix.mkdir()
    outside.mkdir()
    owner = outside / "owner"
    owner.write_text("99999999\n", encoding="utf-8")
    (prefix / ".transaction.lock").symlink_to(outside, target_is_directory=True)

    result = subprocess.run(
        [
            "bash", "scripts/install.sh", "--version", version,
            "--prefix", str(prefix), "--library-path", str(tmp_path / "library"), "--no-shim",
        ],
        cwd=ROOT,
        env={
            **os.environ,
            "IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL": release_dir.as_uri(),
            "IMAGE_PROMPT_LIBRARY_INSTALL_SKIP_RUNTIME_SETUP": "1",
            "PYTHON": sys.executable,
        },
        text=True,
        capture_output=True,
        timeout=120,
    )

    assert result.returncode != 0
    assert "managed installer path contains a symlink" in result.stderr.lower()
    assert owner.read_text(encoding="utf-8") == "99999999\n"


@pytest.mark.skipif(os.name == "nt", reason="POSIX lock symlink behavior is covered by the Ubuntu CI job")
def test_posix_rollback_refuses_symlinked_transaction_lock_without_external_mutation(tmp_path):
    prefix = tmp_path / "prefix"
    outside = tmp_path / "outside-lock"
    prefix.mkdir()
    outside.mkdir()
    owner = outside / "owner"
    owner.write_text("99999999\n", encoding="utf-8")
    (prefix / ".transaction.lock").symlink_to(outside, target_is_directory=True)

    result = subprocess.run(
        ["bash", "scripts/appctl.sh", "rollback"],
        cwd=ROOT,
        env={
            **os.environ,
            "PYTHON": sys.executable,
            "IMAGE_PROMPT_LIBRARY_PREFIX": str(prefix),
        },
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode != 0
    assert "managed path contains a symlink" in result.stderr.lower()
    assert owner.read_text(encoding="utf-8") == "99999999\n"


@pytest.mark.skipif(os.name == "nt", reason="POSIX runtime symlink behavior is covered by the Ubuntu CI job")
def test_posix_rollback_validates_runtime_and_swaps_managed_pointers(tmp_path):
    import shutil

    current_version = "v9.9.5-test"
    previous_version = "v9.9.4-test"
    release_dir = package_release(tmp_path, current_version)
    prefix = tmp_path / "prefix"
    library = tmp_path / "library-data"
    env = {
        **os.environ,
        "IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL": release_dir.as_uri(),
        "IMAGE_PROMPT_LIBRARY_INSTALL_SKIP_RUNTIME_SETUP": "1",
        "PYTHON": sys.executable,
    }
    install = subprocess.run(
        [
            "bash", "scripts/install.sh", "--version", current_version,
            "--prefix", str(prefix), "--library-path", str(library), "--no-shim",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert install.returncode == 0, install.stdout + install.stderr
    versions = prefix / "app" / "versions"
    current_target = versions / current_version
    previous_target = versions / previous_version
    shutil.copytree(current_target, previous_target)
    (previous_target / "VERSION").write_text(previous_version + "\n", encoding="utf-8")
    for target in (current_target, previous_target):
        runtime = target / ".venv" / "bin"
        runtime.mkdir(parents=True)
        (runtime / "python").symlink_to(Path(sys.executable))
    previous_link = prefix / "app" / "previous"
    previous_link.symlink_to(previous_target, target_is_directory=True)

    result = subprocess.run(
        ["bash", str(current_target / "scripts" / "appctl.sh"), "rollback"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (prefix / "app" / "current").resolve() == previous_target.resolve()
    assert previous_link.resolve() == current_target.resolve()
    assert not (prefix / ".transaction.lock").exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX v0.8.0 rollback migration is covered by the Ubuntu CI job")
def test_posix_rollback_migrates_pristine_v080_management_plane_and_records_provenance(tmp_path):
    import shutil

    current_version = "v9.9.5-test"
    release_dir = package_release(tmp_path, current_version)
    prefix = tmp_path / "prefix"
    library = tmp_path / "library-data"
    env = {
        **os.environ,
        "IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL": release_dir.as_uri(),
        "IMAGE_PROMPT_LIBRARY_INSTALL_SKIP_RUNTIME_SETUP": "1",
        "PYTHON": sys.executable,
    }
    install = subprocess.run(
        [
            "bash", "scripts/install.sh", "--version", current_version,
            "--prefix", str(prefix), "--library-path", str(library), "--no-shim",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert install.returncode == 0, install.stdout + install.stderr

    versions = prefix / "app" / "versions"
    current_target = versions / current_version
    previous_target = versions / "v0.8.0"
    shutil.copytree(current_target, previous_target)
    (previous_target / "VERSION").write_text("v0.8.0\n", encoding="utf-8")
    (previous_target / "scripts" / "load-env.sh").unlink()
    for target in (current_target, previous_target):
        runtime = target / ".venv" / "bin"
        runtime.mkdir(parents=True)
        (runtime / "python").symlink_to(Path(sys.executable))
    legacy_management = {
        relative: subprocess.check_output(
            ["git", "cat-file", "blob", f"v0.8.0:{relative}"], cwd=ROOT
        )
        for relative in ("scripts/install.sh", "scripts/install-sample-data.sh", "scripts/appctl.sh")
    }
    for relative, payload in legacy_management.items():
        path = previous_target / relative
        path.write_bytes(payload)
        path.chmod(0o755)
    (previous_target / "scripts" / "backup.sh").write_text("legacy-backup\n", encoding="utf-8")
    backup_before = (previous_target / "scripts" / "backup.sh").read_bytes()
    backend_before = (previous_target / "backend" / "main.py").read_bytes()
    frontend_before = (previous_target / "frontend" / "dist" / "index.html").read_bytes()
    version_before = (previous_target / "VERSION").read_bytes()
    runtime_before = os.readlink(previous_target / ".venv" / "bin" / "python")
    (library / "private-sentinel.txt").write_text("unchanged\n", encoding="utf-8")
    (prefix / ".env").write_text(
        "BACKEND_HOST=$(touch should-not-run)\nBACKEND_PORT=8000\n",
        encoding="utf-8",
    )
    previous_link = prefix / "app" / "previous"
    previous_link.symlink_to(previous_target, target_is_directory=True)
    exact_stale = previous_target / "scripts" / ".install.sh.rollback-migration.tmp"
    near_match = previous_target / "scripts" / ".install.sh.rollback-migration.tmp.keep"
    exact_stale.write_text("stale\n", encoding="utf-8")
    near_match.write_text("preserve\n", encoding="utf-8")

    result = subprocess.run(
        ["bash", str(current_target / "scripts" / "appctl.sh"), "rollback"],
        cwd=tmp_path,
        env={**env, "IMAGE_PROMPT_LIBRARY_PREFIX": str(prefix), "IMAGE_PROMPT_LIBRARY_PATH": str(library)},
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Migrated v0.8.0 management scripts" in result.stdout
    assert (prefix / "app" / "current").resolve() == previous_target.resolve()
    assert previous_link.resolve() == current_target.resolve()
    for relative in ("scripts/install.sh", "scripts/load-env.sh", "scripts/install-sample-data.sh", "scripts/appctl.sh"):
        assert (previous_target / relative).read_bytes() == (current_target / relative).read_bytes()
    assert (previous_target / "scripts" / "backup.sh").read_bytes() == backup_before
    assert (previous_target / "backend" / "main.py").read_bytes() == backend_before
    assert (previous_target / "frontend" / "dist" / "index.html").read_bytes() == frontend_before
    assert (previous_target / "VERSION").read_bytes() == version_before
    assert os.readlink(previous_target / ".venv" / "bin" / "python") == runtime_before
    assert (library / "private-sentinel.txt").read_text(encoding="utf-8") == "unchanged\n"
    assert not (tmp_path / "should-not-run").exists()
    marker = json.loads((previous_target / ".rollback-migration.json").read_text(encoding="utf-8"))
    assert marker["schema"] == 1
    assert marker["state"] == "complete"
    assert marker["target_version"] == "v0.8.0"
    assert marker["source_controller_version"] == current_version
    assert set(marker["files"]) == {
        "scripts/install.sh", "scripts/load-env.sh", "scripts/install-sample-data.sh", "scripts/appctl.sh",
    }
    for relative, digest in marker["files"].items():
        assert hashlib.sha256((previous_target / relative).read_bytes()).hexdigest() == digest
    assert not list((previous_target / "scripts").glob(".*.rollback-migration.tmp"))
    assert not (previous_target / ".rollback-migration.json.tmp").exists()
    assert near_match.read_text(encoding="utf-8") == "preserve\n"

    installed_appctl = prefix / "app" / "current" / "scripts" / "appctl.sh"
    post_rollback_env = {
        **env,
        "IMAGE_PROMPT_LIBRARY_PREFIX": str(prefix),
        "IMAGE_PROMPT_LIBRARY_PATH": str(library),
    }
    for command in ("version", "status", "doctor"):
        check = subprocess.run(
            ["bash", str(installed_appctl), command],
            cwd=tmp_path,
            env=post_rollback_env,
            text=True,
            capture_output=True,
            timeout=120,
        )
        assert check.returncode == 0, check.stdout + check.stderr
    assert not (tmp_path / "should-not-run").exists()
    first_marker = (previous_target / ".rollback-migration.json").read_bytes()

    repeat = subprocess.run(
        ["bash", str(current_target / "scripts" / "appctl.sh"), "rollback"],
        cwd=tmp_path,
        env={**env, "IMAGE_PROMPT_LIBRARY_PREFIX": str(prefix), "IMAGE_PROMPT_LIBRARY_PATH": str(library)},
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert repeat.returncode == 0, repeat.stdout + repeat.stderr
    assert (prefix / "app" / "current").resolve() == current_target.resolve()

    prepared = dict(marker)
    prepared["state"] = "prepared"
    (previous_target / ".rollback-migration.json").write_text(
        json.dumps(prepared, sort_keys=True) + "\n", encoding="utf-8"
    )
    (previous_target / "scripts" / "install.sh").write_bytes(legacy_management["scripts/install.sh"])
    (previous_target / "scripts" / "load-env.sh").unlink()

    migrate_again = subprocess.run(
        ["bash", str(current_target / "scripts" / "appctl.sh"), "rollback"],
        cwd=tmp_path,
        env=post_rollback_env,
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert migrate_again.returncode == 0, migrate_again.stdout + migrate_again.stderr
    assert (prefix / "app" / "current").resolve() == previous_target.resolve()
    assert (previous_target / ".rollback-migration.json").read_bytes() == first_marker

    switch_forward = subprocess.run(
        ["bash", str(current_target / "scripts" / "appctl.sh"), "rollback"],
        cwd=tmp_path,
        env=post_rollback_env,
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert switch_forward.returncode == 0, switch_forward.stdout + switch_forward.stderr
    assert (prefix / "app" / "current").resolve() == current_target.resolve()

    outside = tmp_path / "outside-migration-temp"
    outside.write_text("keep\n", encoding="utf-8")
    exact_stale.symlink_to(outside)
    management_before = {
        relative: (previous_target / relative).read_bytes()
        for relative in marker["files"]
    }
    refused = subprocess.run(
        ["bash", str(current_target / "scripts" / "appctl.sh"), "rollback"],
        cwd=tmp_path,
        env=post_rollback_env,
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert refused.returncode != 0
    assert "exact temporary is not a regular file" in refused.stderr
    assert (prefix / "app" / "current").resolve() == current_target.resolve()
    assert previous_link.resolve() == previous_target.resolve()
    assert outside.read_text(encoding="utf-8") == "keep\n"
    assert management_before == {
        relative: (previous_target / relative).read_bytes()
        for relative in marker["files"]
    }
    assert not (prefix / ".transaction.lock").exists()

    exact_stale.unlink()
    (previous_target / ".rollback-migration.json").unlink()
    (previous_target / "scripts" / "load-env.sh").unlink()
    for relative, payload in legacy_management.items():
        (previous_target / relative).write_bytes(payload)
    with (previous_target / "scripts" / "appctl.sh").open("ab") as stream:
        stream.write(b"\n# local modification\n")
    modified = subprocess.run(
        ["bash", str(current_target / "scripts" / "appctl.sh"), "rollback"],
        cwd=tmp_path,
        env=post_rollback_env,
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert modified.returncode != 0
    assert "does not match the public payload: scripts/appctl.sh" in modified.stderr
    assert (prefix / "app" / "current").resolve() == current_target.resolve()
    assert previous_link.resolve() == previous_target.resolve()
    assert not (previous_target / ".rollback-migration.json").exists()
    assert not (prefix / ".transaction.lock").exists()

    (previous_target / "scripts" / "appctl.sh").write_bytes(legacy_management["scripts/appctl.sh"])
    external_backend = tmp_path / "external-backend"
    external_backend.mkdir()
    external_code_ran = tmp_path / "external-code-ran"
    (external_backend / "main.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(external_code_ran)!r}).write_text('unsafe', encoding='utf-8')\n"
        "raise RuntimeError('external backend must not run')\n",
        encoding="utf-8",
    )
    (previous_target / "backend").rename(previous_target / "backend-preserved")
    (previous_target / "backend").symlink_to(external_backend, target_is_directory=True)
    symlinked_backend = subprocess.run(
        ["bash", str(current_target / "scripts" / "appctl.sh"), "rollback"],
        cwd=tmp_path,
        env=post_rollback_env,
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert symlinked_backend.returncode != 0
    assert "Managed path contains a symlink" in symlinked_backend.stderr
    assert not external_code_ran.exists()
    assert (prefix / "app" / "current").resolve() == current_target.resolve()
    assert previous_link.resolve() == previous_target.resolve()
    assert not (prefix / ".transaction.lock").exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX rollback migration boundaries are covered by the Ubuntu CI job")
def test_posix_rollback_non_v080_missing_load_env_fails_without_mutation(tmp_path):
    import shutil

    current_version = "v9.9.5-test"
    release_dir = package_release(tmp_path, current_version)
    prefix = tmp_path / "prefix"
    library = tmp_path / "library-data"
    env = {
        **os.environ,
        "IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL": release_dir.as_uri(),
        "IMAGE_PROMPT_LIBRARY_INSTALL_SKIP_RUNTIME_SETUP": "1",
        "PYTHON": sys.executable,
    }
    install = subprocess.run(
        [
            "bash", "scripts/install.sh", "--version", current_version,
            "--prefix", str(prefix), "--library-path", str(library), "--no-shim",
        ], cwd=ROOT, env=env, text=True, capture_output=True, timeout=120,
    )
    assert install.returncode == 0, install.stdout + install.stderr
    versions = prefix / "app" / "versions"
    current_target = versions / current_version
    previous_target = versions / "v9.9.4"
    shutil.copytree(current_target, previous_target)
    (previous_target / "VERSION").write_text("v9.9.4\n", encoding="utf-8")
    (previous_target / "scripts" / "load-env.sh").unlink()
    for target in (current_target, previous_target):
        runtime = target / ".venv" / "bin"
        runtime.mkdir(parents=True)
        (runtime / "python").symlink_to(Path(sys.executable))
    previous_link = prefix / "app" / "previous"
    previous_link.symlink_to(previous_target, target_is_directory=True)
    before = previous_target / "scripts" / "appctl.sh"
    before_bytes = before.read_bytes()
    result = subprocess.run(
        ["bash", str(current_target / "scripts" / "appctl.sh"), "rollback"],
        cwd=tmp_path,
        env={**env, "IMAGE_PROMPT_LIBRARY_PREFIX": str(prefix), "IMAGE_PROMPT_LIBRARY_PATH": str(library)},
        text=True, capture_output=True, timeout=120,
    )
    assert result.returncode != 0
    assert "Rollback target is incomplete: scripts/load-env.sh" in result.stderr
    assert before.read_bytes() == before_bytes
    assert not (previous_target / "scripts" / "load-env.sh").exists()
    assert not (previous_target / ".rollback-migration.json").exists()
    assert (prefix / "app" / "current").resolve() == current_target.resolve()
    assert previous_link.resolve() == previous_target.resolve()
    assert not (prefix / ".transaction.lock").exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX rollback symlink boundary is covered by the Ubuntu CI job")
def test_posix_rollback_refuses_symlinked_versions_parent_without_external_mutation(tmp_path):
    prefix = tmp_path / "prefix"
    outside = tmp_path / "outside-versions"
    outside.mkdir()
    sentinel = outside / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    versions = prefix / "app" / "versions"
    versions.parent.mkdir(parents=True)
    versions.symlink_to(outside, target_is_directory=True)

    result = subprocess.run(
        ["bash", "scripts/appctl.sh", "rollback"],
        cwd=ROOT,
        env={
            **os.environ,
            "PYTHON": sys.executable,
            "IMAGE_PROMPT_LIBRARY_PREFIX": str(prefix),
        },
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode != 0
    assert "managed path contains a symlink" in result.stderr.lower()
    assert sentinel.read_text(encoding="utf-8") == "keep"


@pytest.mark.skipif(os.name == "nt", reason="POSIX signal recovery is covered by the Ubuntu CI job")
def test_posix_installer_term_before_state_snapshot_preserves_existing_pointers(tmp_path):
    import shutil

    version = "v1.2.4"
    release_dir = package_release(tmp_path, version)
    prefix = tmp_path / "prefix"
    app = prefix / "app"
    versions = app / "versions"
    current_target = versions / "v1.2.2"
    previous_target = versions / "v1.2.1"
    current_target.mkdir(parents=True)
    previous_target.mkdir()
    current_link = app / "current"
    previous_link = app / "previous"
    current_link.symlink_to(current_target, target_is_directory=True)
    previous_link.symlink_to(previous_target, target_is_directory=True)

    real_mkdir = shutil.which("mkdir")
    assert real_mkdir
    wrapper_dir = tmp_path / "bin"
    wrapper_dir.mkdir()
    mkdir_wrapper = wrapper_dir / "mkdir"
    mkdir_wrapper.write_text(
        "#!/bin/sh\n"
        '"$REAL_MKDIR" "$@"\n'
        "rc=$?\n"
        'if [ "$#" -eq 2 ] && [ "$1" = "-p" ] && [ "$2" = "$SIGNAL_APP_PATH" ]; then\n'
        '  kill -TERM "$PPID"\n'
        "fi\n"
        "exit \"$rc\"\n",
        encoding="utf-8",
    )
    mkdir_wrapper.chmod(0o755)
    env = {
        **os.environ,
        "PATH": str(wrapper_dir) + os.pathsep + os.environ.get("PATH", ""),
        "REAL_MKDIR": real_mkdir,
        "SIGNAL_APP_PATH": str(app),
        "PYTHON": sys.executable,
        "IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL": release_dir.as_uri(),
        "IMAGE_PROMPT_LIBRARY_INSTALL_SKIP_RUNTIME_SETUP": "1",
    }

    result = subprocess.run(
        [
            "bash", "scripts/install.sh", "--version", version,
            "--prefix", str(prefix), "--library-path", str(tmp_path / "library"), "--no-shim",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
    )

    assert result.returncode != 0
    assert current_link.is_symlink() and current_link.resolve() == current_target.resolve()
    assert previous_link.is_symlink() and previous_link.resolve() == previous_target.resolve()
    assert not (prefix / ".transaction.lock").exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX signal recovery is covered by the Ubuntu CI job")
def test_posix_installer_term_during_setup_restores_target_and_pointer_pair(tmp_path):
    import shutil

    version = "v1.2.4"
    release_dir = package_release(tmp_path, version)
    artifact = release_dir / f"image-prompt-library-{version}.tar.gz"
    rewritten = release_dir / "rewritten.tar.gz"
    with tarfile.open(artifact, "r:gz") as source, tarfile.open(rewritten, "w:gz") as output:
        for member in source.getmembers():
            if member.isfile():
                extracted = source.extractfile(member)
                payload = extracted.read() if extracted is not None else b""
                if member.name == "scripts/setup-runtime.sh":
                    payload = b'#!/usr/bin/env bash\nkill -TERM "$PPID"\nsleep 1\nexit 1\n'
                member.size = len(payload)
                output.addfile(member, io.BytesIO(payload))
            else:
                output.addfile(member)
    rewritten.replace(artifact)
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    manifest_path = release_dir / f"image-prompt-library-{version}.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sha256"] = digest
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    (release_dir / f"image-prompt-library-{version}.tar.gz.sha256").write_text(
        f"{digest}  {artifact.name}\n", encoding="utf-8"
    )

    prefix = tmp_path / "prefix"
    versions = prefix / "app" / "versions"
    old_current = versions / "v1.2.3"
    extracted = subprocess.run(
        [
            sys.executable, "scripts/verify-release-assets.py", str(release_dir), version,
            "--source-sha", manifest["source_sha"], "--extract-to", str(old_current),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert extracted.returncode == 0, extracted.stdout + extracted.stderr
    (old_current / "VERSION").write_text("v1.2.3\n", encoding="utf-8")
    old_previous = versions / "v1.2.2"
    shutil.copytree(old_current, old_previous)
    (old_previous / "VERSION").write_text("v1.2.2\n", encoding="utf-8")
    preimage = versions / version
    shutil.copytree(old_current, preimage)
    (preimage / "VERSION").write_text(version + "\n", encoding="utf-8")
    (preimage / "preimage-sentinel").write_text("restore", encoding="utf-8")
    current_link = prefix / "app" / "current"
    previous_link = prefix / "app" / "previous"
    current_link.symlink_to(old_current, target_is_directory=True)
    previous_link.symlink_to(old_previous, target_is_directory=True)
    library = tmp_path / "library"
    env = {
        **os.environ,
        "PYTHON": sys.executable,
        "IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL": release_dir.as_uri(),
    }

    result = subprocess.run(
        [
            "bash", "scripts/install.sh", "--version", version,
            "--prefix", str(prefix), "--library-path", str(library), "--no-shim",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert result.returncode != 0
    assert (preimage / "preimage-sentinel").read_text(encoding="utf-8") == "restore"
    assert current_link.resolve() == old_current.resolve()
    assert previous_link.resolve() == old_previous.resolve()
    assert not (versions / f"{version}.backup").exists()
    assert not list(versions.glob(".staging-*"))
    assert not (prefix / ".transaction.lock").exists()


def test_installer_auto_detects_supported_python_when_python3_is_too_old(tmp_path):
    release_dir = package_release(tmp_path, "v9.9.4-test")

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
    (fake_bin / "python3.12").write_text(
        f"#!/usr/bin/env sh\nexec '{Path(sys.executable).as_posix()}' \"$@\"\n",
        encoding="utf-8",
    )
    (fake_bin / "python3.12").chmod(0o755)

    prefix = tmp_path / "prefix"
    library = tmp_path / "library-data"
    env = os.environ.copy()
    env.pop("PYTHON", None)
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL"] = release_dir.as_uri()
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
    release_dir = package_release(tmp_path, "v9.9.3-test")

    prefix = tmp_path / "prefix"
    library = tmp_path / "library-data"
    env = os.environ.copy()
    env["IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL"] = release_dir.as_uri()
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
    release_dir = package_release(tmp_path, "v9.9.2-test")

    prefix = tmp_path / "prefix"
    library = tmp_path / "library-data"
    env = os.environ.copy()
    env["IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL"] = release_dir.as_uri()
    env["IMAGE_PROMPT_LIBRARY_INSTALL_SKIP_RUNTIME_SETUP"] = "1"
    env["PYTHON"] = Path(sys.executable).as_posix()
    install = subprocess.run(
        git_bash_cmd(
            "scripts/install.sh",
            "--version",
            "v9.9.2-test",
            "--prefix",
            str(prefix),
            "--library-path",
            str(library),
            "--no-shim",
        ),
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert install.returncode == 0, install.stdout + install.stderr

    appctl = prefix / "app" / "current" / "scripts" / "appctl.sh"
    doctor = subprocess.run(
        git_bash_cmd(appctl, "doctor"),
        cwd=tmp_path,
        env={**env, "IMAGE_PROMPT_LIBRARY_PREFIX": str(prefix)},
        text=True,
        capture_output=True,
        timeout=60,
    )

    assert doctor.returncode == 0, doctor.stdout + doctor.stderr
    assert "Image Prompt Library doctor" in doctor.stdout
    assert "## App" in doctor.stdout
    assert "OK Version: v9.9.2-test" in doctor.stdout
    assert f"OK Install prefix: {prefix}" in doctor.stdout
    assert f"OK Library path: {library}" in doctor.stdout
    assert "OK Backend URL: http://127.0.0.1:8000/" in doctor.stdout
    assert "## Database" in doctor.stdout
    assert "OK Database integrity: ok" in doctor.stdout
    assert "Item count: 0" in doctor.stdout
    assert "## Generation" in doctor.stdout
    assert "openai_codex_oauth_native" in doctor.stdout
    assert "## Next steps" in doctor.stdout
    assert "image-prompt-library sample-data en" in doctor.stdout
    assert "[REDACTED]" not in doctor.stdout
    assert "app_" not in doctor.stdout


def test_installed_status_reports_short_local_summary(tmp_path):
    release_dir = package_release(tmp_path, "v9.9.3-test")

    prefix = tmp_path / "prefix"
    library = tmp_path / "library-data"
    env = os.environ.copy()
    env["IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL"] = release_dir.as_uri()
    env["IMAGE_PROMPT_LIBRARY_INSTALL_SKIP_RUNTIME_SETUP"] = "1"
    env["PYTHON"] = Path(sys.executable).as_posix()
    install = subprocess.run(
        git_bash_cmd(
            "scripts/install.sh",
            "--version",
            "v9.9.3-test",
            "--prefix",
            str(prefix),
            "--library-path",
            str(library),
            "--no-shim",
        ),
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert install.returncode == 0, install.stdout + install.stderr

    appctl = prefix / "app" / "current" / "scripts" / "appctl.sh"
    status = subprocess.run(
        git_bash_cmd(appctl, "status"),
        cwd=tmp_path,
        env={**env, "IMAGE_PROMPT_LIBRARY_PREFIX": str(prefix)},
        text=True,
        capture_output=True,
        timeout=60,
    )

    assert status.returncode == 0, status.stdout + status.stderr
    assert "Image Prompt Library status" in status.stdout
    assert "Version: v9.9.3-test" in status.stdout
    assert f"Library: {library}" in status.stdout
    assert "URL: http://127.0.0.1:8000/" in status.stdout
    assert "Items: 0" in status.stdout
    assert "Generation:" in status.stdout
    assert "Run image-prompt-library doctor for detailed diagnostics." in status.stdout
    assert "[REDACTED]" not in status.stdout
    assert "app_" not in status.stdout


def test_installed_service_commands_manage_macos_launchagent_with_fake_launchctl(tmp_path):
    release_dir = package_release(tmp_path, "v9.9.1-test")

    prefix = tmp_path / "prefix"
    library = tmp_path / "library-data"
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    calls = tmp_path / "launchctl-calls.log"
    retry_marker = tmp_path / "fail-next-bootstrap"
    service_state = tmp_path / "service-loaded"
    bash_calls = git_bash_arg(calls)
    bash_retry_marker = git_bash_arg(retry_marker)
    bash_service_state = git_bash_arg(service_state)
    (fake_bin / "launchctl").write_text(
        "#!/usr/bin/env sh\n"
        f"printf '%s ' \"$@\" >> {bash_calls}\n"
        f"printf '\\n' >> {bash_calls}\n"
        f"if [ \"$1\" = \"print\" ]; then [ -f {bash_service_state} ] && echo 'state = running' && exit 0; exit 113; fi\n"
        f"if [ \"$1\" = \"bootout\" ]; then rm -f {bash_service_state}; touch {bash_retry_marker}; exit 0; fi\n"
        f"if [ \"$1\" = \"bootstrap\" ] && [ -f {bash_retry_marker} ]; then rm -f {bash_retry_marker}; echo 'Bootstrap failed: 5: Input/output error' >&2; exit 5; fi\n"
        f"if [ \"$1\" = \"bootstrap\" ]; then touch {bash_service_state}; exit 0; fi\n"
        f"if [ \"$1\" = \"kickstart\" ]; then touch {bash_service_state}; exit 0; fi\n",
        encoding="utf-8",
    )
    (fake_bin / "launchctl").chmod(0o755)
    (fake_bin / "plutil").write_text("#!/usr/bin/env sh\necho \"$2: OK\"\n", encoding="utf-8")
    (fake_bin / "plutil").chmod(0o755)

    env = os.environ.copy()
    env["HOME"] = str(fake_home)
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL"] = release_dir.as_uri()
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
    assert git_bash_arg(appctl) in plist_text
    assert "0.0.0.0" in plist_text
    assert "7500" in plist_text
    assert git_bash_arg(prefix) in plist_text
    assert "IMAGE_PROMPT_LIBRARY_SERVICE_LABEL" in plist_text
    assert "com.example.ipl-test" in plist_text
    assert "bootstrap gui/" in calls.read_text(encoding="utf-8")
    assert "kickstart -k gui/" in calls.read_text(encoding="utf-8")

    status_default_label = subprocess.run(
        ["bash", str(appctl), "service", "status"],
        cwd=tmp_path,
        env=service_env,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert status_default_label.returncode == 0, status_default_label.stdout + status_default_label.stderr
    assert "print gui/" in calls.read_text(encoding="utf-8")
    assert "com.example.ipl-test" in calls.read_text(encoding="utf-8")

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
    release_dir = package_release(tmp_path, "v9.9.6-test")

    prefix = tmp_path / "prefix"
    library = tmp_path / "installer-library"
    env = os.environ.copy()
    env["IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL"] = release_dir.as_uri()
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
    release_dir = package_release(tmp_path, "v9.9.5-test")

    prefix = tmp_path / "prefix"
    library = tmp_path / "installer-library"
    env = os.environ.copy()
    env["IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL"] = release_dir.as_uri()
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


@pytest.mark.skipif(os.name == "nt", reason="POSIX prefix symlinks are covered by the Ubuntu CI job")
def test_posix_uninstall_refuses_symlinked_prefix_without_deleting_target(tmp_path):
    physical_prefix = tmp_path / "physical-prefix"
    physical_prefix.mkdir()
    sentinel = physical_prefix / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    prefix_alias = tmp_path / "prefix-alias"
    prefix_alias.symlink_to(physical_prefix, target_is_directory=True)

    result = subprocess.run(
        ["bash", "scripts/appctl.sh", "uninstall"],
        cwd=ROOT,
        env={
            **os.environ,
            "PYTHON": sys.executable,
            "IMAGE_PROMPT_LIBRARY_PREFIX": str(prefix_alias),
            "IMAGE_PROMPT_LIBRARY_PATH": str(tmp_path / "library"),
        },
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode != 0
    assert "symlinked install prefix" in result.stderr.lower()
    assert sentinel.read_text(encoding="utf-8") == "keep"


@pytest.mark.skipif(os.name == "nt", reason="POSIX home-ancestor paths are covered by the Ubuntu CI job")
def test_posix_installer_refuses_prefix_containing_user_home(tmp_path):
    version = "v9.9.7-test"
    release_dir = package_release(tmp_path, version)
    home = tmp_path / "home-parent" / "user"
    home.mkdir(parents=True)
    parent = home.parent

    result = subprocess.run(
        [
            "bash", "scripts/install.sh", "--version", version,
            "--prefix", str(home / ".."), "--library-path", str(tmp_path / "library"), "--no-shim",
        ],
        cwd=ROOT,
        env={
            **os.environ,
            "HOME": str(home),
            "PYTHON": sys.executable,
            "IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL": release_dir.as_uri(),
            "IMAGE_PROMPT_LIBRARY_INSTALL_SKIP_RUNTIME_SETUP": "1",
        },
        text=True,
        capture_output=True,
        timeout=120,
    )

    assert result.returncode != 0
    assert "unsafe install prefix" in result.stderr.lower()
    assert not (parent / "app").exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX home-ancestor paths are covered by the Ubuntu CI job")
def test_posix_uninstall_refuses_prefix_containing_user_home(tmp_path):
    home = tmp_path / "home-parent" / "user"
    home.mkdir(parents=True)
    sentinel = home / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")

    result = subprocess.run(
        ["bash", "scripts/appctl.sh", "uninstall", "--yes"],
        cwd=ROOT,
        env={
            **os.environ,
            "HOME": str(home),
            "PYTHON": sys.executable,
            "IMAGE_PROMPT_LIBRARY_PREFIX": str(home / ".."),
            "IMAGE_PROMPT_LIBRARY_PATH": str(tmp_path / "library"),
        },
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode != 0
    assert "unsafe install prefix" in result.stderr.lower()
    assert sentinel.read_text(encoding="utf-8") == "keep"


@pytest.mark.skipif(os.name == "nt", reason="POSIX home-ancestor paths are covered by the Ubuntu CI job")
def test_posix_uninstall_refuses_library_containing_user_home(tmp_path):
    home = tmp_path / "home-parent" / "user"
    home.mkdir(parents=True)
    prefix = tmp_path / "install-prefix"
    prefix.mkdir()
    sentinel = prefix / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")

    result = subprocess.run(
        ["bash", "scripts/appctl.sh", "uninstall", "--delete-library", "--yes"],
        cwd=ROOT,
        env={
            **os.environ,
            "HOME": str(home),
            "PYTHON": sys.executable,
            "IMAGE_PROMPT_LIBRARY_PREFIX": str(prefix),
            "IMAGE_PROMPT_LIBRARY_PATH": str(home / ".."),
        },
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode != 0
    assert "unsafe private library" in result.stderr.lower()
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_posix_appctl_treats_env_values_as_literal_data(tmp_path):
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    library = tmp_path / "library with spaces"
    marker = tmp_path / "should-not-run"
    (prefix / ".env").write_text(
        f"IMAGE_PROMPT_LIBRARY_PATH={library}\n"
        "BACKEND_HOST=$(touch should-not-run)\n"
        "BACKEND_PORT=8000\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        ["bash", str(ROOT / "scripts" / "appctl.sh"), "doctor"],
        cwd=tmp_path,
        env={
            **os.environ,
            "PYTHON": sys.executable,
            "IMAGE_PROMPT_LIBRARY_PREFIX": str(prefix),
            "IMAGE_PROMPT_LIBRARY_AUTH_PATH": str(tmp_path / "auth.json"),
            "IMAGE_PROMPT_LIBRARY_CONFIG_PATH": str(tmp_path / "config.json"),
        },
        text=True,
        capture_output=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert f"OK Library path: {library}" in result.stdout
    assert not marker.exists()


def test_posix_env_consumers_share_literal_allowlisted_parser(tmp_path):
    for relative in (
        "scripts/appctl.sh",
        "scripts/backup.sh",
        "scripts/dev.sh",
        "scripts/install-sample-data.sh",
        "scripts/start.sh",
    ):
        script = read(relative)
        assert 'source "$SCRIPT_DIR/load-env.sh"' in script
        assert "source .env" not in script
        assert 'source "$ENV_FILE"' not in script

    env_file = tmp_path / ".env"
    marker = tmp_path / "should-not-run"
    env_file.write_text(
        "IMAGE_PROMPT_LIBRARY_PATH=C:/Library With Spaces\n"
        "BACKEND_HOST=$(touch should-not-run)\n"
        "BACKEND_PORT=8123\n"
        "UNSUPPORTED=$(touch should-not-run)\n",
        encoding="utf-8",
    )
    command = (
        f"source {shlex.quote(git_bash_path(ROOT / 'scripts' / 'load-env.sh'))}; "
        f"image_prompt_library_load_env_file {shlex.quote(git_bash_path(env_file))}; "
        "printf '%s\\n' \"$IMAGE_PROMPT_LIBRARY_PATH\" \"$BACKEND_HOST\" \"$BACKEND_PORT\""
    )

    result = subprocess.run(
        [GIT_BASH, "-lc", command],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines() == [
        "C:/Library With Spaces",
        "$(touch should-not-run)",
        "8123",
    ]
    assert not marker.exists()


def test_installed_sample_data_script_imports_into_installer_library_by_default(tmp_path):
    release_dir = package_release(tmp_path, "v9.9.7-test")

    prefix = tmp_path / "prefix"
    library = tmp_path / "installer-library"
    env = os.environ.copy()
    env["IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL"] = release_dir.as_uri()
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
    assert git_bash_arg(library) in result.stdout
    assert ItemRepository(library).list_items(limit=5).total == 1
