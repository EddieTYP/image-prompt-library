#!/usr/bin/env bash
set -euo pipefail

VERSION_INPUT="latest"
PREFIX="$HOME/.image-prompt-library"
LIBRARY_PATH="$HOME/ImagePromptLibrary"
CREATE_SHIM=1
REPO="EddieTYP/image-prompt-library"
RELEASE_BASE_URL="${IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL:-}"
SKIP_RUNTIME_SETUP="${IMAGE_PROMPT_LIBRARY_INSTALL_SKIP_RUNTIME_SETUP:-0}"

usage() {
  cat <<'USAGE'
Usage: scripts/install.sh [options]

Options:
  --version <tag>        Install selected release tag; default: latest
  --prefix <path>        Install prefix; default: ~/.image-prompt-library
  --library-path <path>  Private library path; default: ~/ImagePromptLibrary
  --no-shim             Do not create ~/.local/bin/image-prompt-library
  -h, --help            Show help
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --version) VERSION_INPUT="${2:-}"; shift 2 ;;
    --prefix) PREFIX="${2:-}"; shift 2 ;;
    --library-path) LIBRARY_PATH="${2:-}"; shift 2 ;;
    --no-shim) CREATE_SHIM=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [ -z "$VERSION_INPUT" ] || [ -z "$PREFIX" ] || [ -z "$LIBRARY_PATH" ]; then
  echo "Missing required option value." >&2
  exit 2
fi
case "$PREFIX" in
  /|"$HOME"|"$HOME/")
    echo "Refusing unsafe install prefix: $PREFIX" >&2
    exit 2
    ;;
esac

PYTHON_BIN=""

choose_python() {
  if [ -n "${PYTHON:-}" ]; then
    printf '%s\n' "$PYTHON"
    return 0
  fi
  for candidate in python3.13 python3.12 python3.11 python3.10 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
    then
      command -v "$candidate"
      return 0
    fi
  done
  return 1
}

PYTHON_BIN="$(choose_python || true)"
if [ -z "$PYTHON_BIN" ]; then
  echo "Image Prompt Library requires Python 3.10 or newer." >&2
  echo "Install Python 3.10+ and rerun with PYTHON=/path/to/python3.10 scripts/install.sh." >&2
  exit 1
fi

normalize_version() {
  "$PYTHON_BIN" - "$1" <<'PY'
import re
import sys
value = sys.argv[1]
if value != value.strip():
    raise SystemExit(f"Release version is invalid: {value}")
pattern = re.compile(r"^v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?")
match = pattern.fullmatch(value)
if not match or any(part.isdigit() and len(part) > 1 and part.startswith("0") for part in (match.group(4) or "").split(".") if part):
    raise SystemExit(f"Release version is invalid: {value}")
print("v" + value.lstrip("v"))
PY
}

version_is_valid() {
  normalize_version "$1" >/dev/null
}

python_download() {
  local url="$1" out="$2" temporary
  temporary="$out.download-$$"
  "$PYTHON_BIN" - "$url" "$temporary" <<'PY'
import pathlib
import sys
import urllib.request
url, out = sys.argv[1:]
path = pathlib.Path(out)
path.parent.mkdir(parents=True, exist_ok=True)
with urllib.request.urlopen(url) as response:
    path.write_bytes(response.read())
PY
  mv -f "$temporary" "$out"
}

prepare_release_verifier() {
  local manifest="$1" artifact="$2" checksum="$3" version="$4" output="$5" temporary
  temporary="$output.tmp.$$"
  "$PYTHON_BIN" - "$manifest" "$artifact" "$checksum" "$version" "$temporary" <<'PY'
import hashlib
import json
import pathlib
import re
import sys
import tarfile

manifest_path, artifact_path, checksum_path, version, output_path = map(pathlib.Path, sys.argv[1:])
version = str(version)
artifact_name = f"image-prompt-library-{version}.tar.gz"
try:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as exc:
    raise SystemExit(f"Release manifest is invalid: {exc}")
if not isinstance(manifest, dict) or (
    manifest.get("name") != "image-prompt-library"
    or manifest.get("version") != version
    or manifest.get("artifact") != artifact_name
):
    raise SystemExit("Release manifest identity does not match the selected release.")
expected = manifest.get("sha256")
source_sha = manifest.get("source_sha")
schema_version = manifest.get("schema_version", 1)
capabilities = manifest.get("capabilities")
if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected):
    raise SystemExit("Release manifest SHA256 is invalid.")
if not isinstance(schema_version, int) or isinstance(schema_version, bool) or schema_version not in {1, 2}:
    raise SystemExit("Release manifest schema_version is unsupported.")
if schema_version >= 2 and source_sha is None:
    raise SystemExit("Release manifest is missing source_sha.")
if source_sha is not None and (not isinstance(source_sha, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", source_sha)):
    raise SystemExit("Release manifest source_sha is invalid.")
if not isinstance(capabilities, list) or "posix-shell-v1" not in capabilities:
    raise SystemExit("Release does not advertise POSIX installer support.")
lines = [line.strip() for line in checksum_path.read_text(encoding="utf-8").splitlines() if line.strip()]
match = re.fullmatch(r"([0-9a-fA-F]{64})\s+\*?([^\s]+)", lines[0]) if len(lines) == 1 else None
if not match or match.group(2) != artifact_name or match.group(1).lower() != expected.lower():
    raise SystemExit("Release checksum sidecar does not match the manifest.")
digest = hashlib.sha256()
with artifact_path.open("rb") as handle:
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
if digest.hexdigest().lower() != expected.lower():
    raise SystemExit("Release artifact SHA256 does not match the manifest.")
with tarfile.open(artifact_path, "r:gz") as archive:
    members = [member for member in archive.getmembers() if member.name == "scripts/verify-release-assets.py"]
    if len(members) != 1 or not members[0].isfile() or members[0].issym() or members[0].islnk():
        raise SystemExit("Release archive is missing its regular verifier payload.")
    source = archive.extractfile(members[0])
    payload = source.read() if source is not None else b""
if not payload:
    raise SystemExit("Release verifier payload is empty.")
pathlib.Path(output_path).write_bytes(payload)
PY
  mv -f "$temporary" "$output"
}

resolve_latest_version() {
  "$PYTHON_BIN" - "$REPO" <<'PY'
import json
import re
import sys
import urllib.request
repo = sys.argv[1]
pattern = re.compile(r"^v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?")
page = 1
while True:
    url = f"https://api.github.com/repos/{repo}/releases?per_page=100&page={page}"
    with urllib.request.urlopen(url) as response:
        releases = json.load(response)
    if not isinstance(releases, list):
        raise SystemExit("GitHub release listing returned an invalid response.")
    for release in releases:
        if not isinstance(release, dict):
            continue
        if release.get("draft") or release.get("prerelease"):
            continue
        tag = release.get("tag_name")
        match = pattern.fullmatch(tag) if isinstance(tag, str) else None
        if not match or any(part.isdigit() and len(part) > 1 and part.startswith("0") for part in (match.group(4) or "").split(".") if part):
            continue
        canonical = "v" + tag.lstrip("v")
        assets = {
            asset.get("name"): asset
            for asset in (release.get("assets") or [])
            if isinstance(asset, dict) and isinstance(asset.get("name"), str)
        }
        required = {
            f"image-prompt-library-{canonical}.manifest.json",
            f"image-prompt-library-{canonical}.tar.gz",
            f"image-prompt-library-{canonical}.tar.gz.sha256",
        }
        if not required.issubset(assets):
            continue
        manifest_name = f"image-prompt-library-{canonical}.manifest.json"
        manifest_url = assets[manifest_name].get("browser_download_url")
        if not isinstance(manifest_url, str):
            continue
        try:
            with urllib.request.urlopen(manifest_url) as response:
                manifest = json.load(response)
        except Exception:
            continue
        if not isinstance(manifest, dict):
            continue
        capabilities = manifest.get("capabilities")
        if (
            manifest.get("name") != "image-prompt-library"
            or manifest.get("version") != canonical
            or manifest.get("artifact") != f"image-prompt-library-{canonical}.tar.gz"
            or not isinstance(capabilities, list)
            or "posix-shell-v1" not in capabilities
        ):
            continue
        print(canonical)
        raise SystemExit(0)
    if len(releases) < 100:
        break
    page += 1
raise SystemExit("Could not find a stable release with Image Prompt Library installer assets.")
PY
}

validate_private_library_path() {
  "$PYTHON_BIN" - "$1" "$2" <<'PY'
import os
import pathlib
import stat
import sys

if any(character in sys.argv[1] + sys.argv[2] for character in "\r\n"):
    raise SystemExit("Private library and install prefix must not contain line breaks.")
target = pathlib.Path(os.path.abspath(sys.argv[1]))
prefix = pathlib.Path(sys.argv[2]).resolve(strict=True)

def contains(parent: pathlib.Path, child: pathlib.Path) -> bool:
    try:
        return os.path.commonpath((str(parent), str(child))) == str(parent)
    except ValueError:
        return False

resolved_target = target.resolve(strict=False)
if contains(prefix, resolved_target) or contains(resolved_target, prefix):
    raise SystemExit("Private library and install prefix must not contain each other.")

cursor = pathlib.Path(target.anchor)
for index, part in enumerate(target.parts[1:]):
    cursor = cursor / part
    try:
        mode = os.lstat(cursor).st_mode
    except FileNotFoundError:
        break
    if stat.S_ISLNK(mode):
        raise SystemExit(f"Private library path contains a symlink: {cursor}")
    if not stat.S_ISDIR(mode):
        raise SystemExit(f"Private library path contains a non-directory: {cursor}")
PY
}

validate_safe_install_prefix() {
  local target="$1" home="$HOME"
  case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*)
      target="$(cygpath -m "$target")"
      home="$(cygpath -m "$home")"
      ;;
  esac
  "$PYTHON_BIN" - "$target" "$home" <<'PY'
import os
import pathlib
import stat
import sys

target = pathlib.Path(os.path.abspath(sys.argv[1]))
home_path = pathlib.Path(os.path.abspath(sys.argv[2]))
try:
    home = home_path.resolve(strict=True)
except OSError:
    home = home_path
try:
    resolved_target = target.resolve(strict=False)
except OSError:
    resolved_target = target

def same_or_contains(parent: pathlib.Path, child: pathlib.Path) -> bool:
    try:
        common = os.path.commonpath((str(parent), str(child)))
    except ValueError:
        return False
    return os.path.normcase(common) == os.path.normcase(str(parent))

if resolved_target == pathlib.Path(resolved_target.anchor) or same_or_contains(resolved_target, home):
    raise SystemExit(f"Refusing unsafe install prefix: {resolved_target}")

cursor = pathlib.Path(target.anchor)
for part in target.parts[1:]:
    cursor = cursor / part
    try:
        mode = os.lstat(cursor).st_mode
    except FileNotFoundError:
        break
    if stat.S_ISLNK(mode):
        raise SystemExit(f"Install prefix contains a symlink: {cursor}")
    if not stat.S_ISDIR(mode):
        raise SystemExit(f"Install prefix contains a non-directory: {cursor}")
PY
}

# Normalize the explicit value before constructing any version-derived path or URL.
if [ "$VERSION_INPUT" = "latest" ]; then
  if [ -n "$RELEASE_BASE_URL" ]; then
    echo "--version is required when IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL points to a local artifact directory." >&2
    exit 2
  fi
  VERSION="$(resolve_latest_version)"
else
  VERSION="$(normalize_version "$VERSION_INPUT")"
fi
version_is_valid "$VERSION"

# Resolve the physical prefix before creating version-derived directories.  This
# also keeps a current-symlink invocation and a direct version invocation on the
# same lock and transaction paths.
validate_safe_install_prefix "$PREFIX"
mkdir -p "$PREFIX"
PREFIX="$(cd "$PREFIX" && pwd -P)"
validate_safe_install_prefix "$PREFIX"
validate_private_library_path "$LIBRARY_PATH" "$PREFIX"
mkdir -p "$LIBRARY_PATH"
validate_private_library_path "$LIBRARY_PATH" "$PREFIX"
PHYSICAL_LIBRARY_PATH="$(cd "$LIBRARY_PATH" && pwd -P)"
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)
    LIBRARY_PATH="$(cygpath -m "$PHYSICAL_LIBRARY_PATH")"
    ENV_PREFIX="$(cygpath -m "$PREFIX")"
    ;;
  *)
    LIBRARY_PATH="$PHYSICAL_LIBRARY_PATH"
    ENV_PREFIX="$PREFIX"
    ;;
esac
APP_DIR="$PREFIX/app"
VERSIONS_DIR="$APP_DIR/versions"
DOWNLOADS_DIR="$APP_DIR/downloads"
DOWNLOAD_DIR="$DOWNLOADS_DIR/$VERSION"
INSTALL_DIR="$VERSIONS_DIR/$VERSION"
BACKUP_DIR="$VERSIONS_DIR/$VERSION.backup"
CURRENT_LINK="$APP_DIR/current"
PREVIOUS_LINK="$APP_DIR/previous"
ENV_FILE="$PREFIX/.env"
SHIM_PATH="$HOME/.local/bin/image-prompt-library"
LOCK_DIR="$PREFIX/.transaction.lock"
LOCK_HELD=0
STAGING_DIR=""
HEALTH_DIR=""
TARGET_PUBLISHED=0
BACKUP_CREATED=0
COMMITTED=0
OLD_CURRENT_TARGET=""
OLD_CURRENT_RESOLVED=""
OLD_PREVIOUS_TARGET=""
OLD_CURRENT_PRESENT=0
OLD_PREVIOUS_PRESENT=0
STATE_SAVED=0
ENV_CREATED=0
SHIM_BACKUP=""
SHIM_CREATED=0
REQUIRE_RUNTIME=1
if [ "$SKIP_RUNTIME_SETUP" = "1" ]; then REQUIRE_RUNTIME=0; fi

assert_managed_directory_path() {
  local target="$1" root="$2"
  "$PYTHON_BIN" - "$target" "$root" <<'PY'
import os
import pathlib
import stat
import sys

target = pathlib.Path(os.path.abspath(sys.argv[1]))
root = pathlib.Path(sys.argv[2]).resolve(strict=True)
try:
    relative = target.relative_to(root)
except ValueError:
    raise SystemExit(f"managed installer path is outside the install prefix: {target}")
cursor = root
for part in relative.parts:
    cursor = cursor / part
    try:
        mode = os.lstat(cursor).st_mode
    except FileNotFoundError:
        break
    if stat.S_ISLNK(mode):
        raise SystemExit(f"managed installer path contains a symlink: {cursor}")
    if not stat.S_ISDIR(mode):
        raise SystemExit(f"managed installer path contains a non-directory: {cursor}")
PY
}

lock_prefix() {
  mkdir -p "$PREFIX"
  assert_managed_directory_path "$LOCK_DIR" "$PREFIX"
  if mkdir "$LOCK_DIR" 2>/dev/null; then
    LOCK_HELD=1
    printf '%s\n' "$$" > "$LOCK_DIR/owner"
    return
  fi
  if [ -f "$LOCK_DIR/owner" ]; then
    local pid
    read -r pid < "$LOCK_DIR/owner" || true
    if [[ "$pid" =~ ^[0-9]+$ ]] && ! kill -0 "$pid" 2>/dev/null; then
      rm -f "$LOCK_DIR/owner"
      if rmdir "$LOCK_DIR" 2>/dev/null && mkdir "$LOCK_DIR" 2>/dev/null; then
        LOCK_HELD=1
        printf '%s\n' "$$" > "$LOCK_DIR/owner"
        return
      fi
    fi
  elif [ -d "$LOCK_DIR" ] && "$PYTHON_BIN" - "$LOCK_DIR" <<'PY'
import pathlib
import sys
import time
path = pathlib.Path(sys.argv[1])
raise SystemExit(0 if time.time() - path.stat().st_mtime >= 30 else 1)
PY
  then
    if rmdir "$LOCK_DIR" 2>/dev/null && mkdir "$LOCK_DIR" 2>/dev/null; then
      LOCK_HELD=1
      printf '%s\n' "$$" > "$LOCK_DIR/owner"
      return
    fi
  fi
  echo "Another Image Prompt Library transaction is already running for this prefix; retry later." >&2
  exit 1
}

unlock_prefix() {
  if [ "$LOCK_HELD" -eq 1 ]; then
    assert_managed_directory_path "$LOCK_DIR" "$PREFIX"
    if [ -f "$LOCK_DIR/owner" ] && [ "$(cat "$LOCK_DIR/owner")" = "$$" ]; then
      rm -f "$LOCK_DIR/owner"
      rmdir "$LOCK_DIR" 2>/dev/null || true
    fi
    LOCK_HELD=0
  fi
}

remove_owned_tree() {
  local target="$1" expected_parent="$2" expected_name="$3"
  "$PYTHON_BIN" - "$target" "$expected_parent" "$expected_name" <<'PY'
import os
import pathlib
import shutil
import stat
import sys

target, parent, expected_name = map(pathlib.Path, sys.argv[1:])
parent_mode = os.lstat(parent).st_mode
if stat.S_ISLNK(parent_mode) or not stat.S_ISDIR(parent_mode):
    raise SystemExit("refusing cleanup through a symlinked installer parent")
if (
    target.name != str(expected_name)
    or pathlib.Path(os.path.abspath(target.parent)) != pathlib.Path(os.path.abspath(parent))
    or target.parent.resolve(strict=True) != parent.resolve(strict=True)
):
    raise SystemExit("refusing to remove a path outside the installer-owned boundary")
try:
    mode = os.lstat(target).st_mode
except FileNotFoundError:
    raise SystemExit(0)
if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
    raise SystemExit("refusing to remove a non-directory or symlink remnant")
shutil.rmtree(target)
PY
}

reconcile_owned_remnants() {
  local path leaf current_resolved
  for path in "$VERSIONS_DIR"/.staging-*; do
    [ -e "$path" ] || [ -L "$path" ] || continue
    leaf="$(basename "$path")"
    if [[ "$leaf" =~ ^\.staging-[0-9a-fA-F]{32}$ ]] && [ -d "$path" ] && [ ! -L "$path" ]; then
      remove_owned_tree "$path" "$VERSIONS_DIR" "$leaf"
    else
      echo "Ambiguous installer staging remnant retained: $path" >&2
      exit 1
    fi
  done
  for path in "$PREFIX"/.health-*; do
    [ -e "$path" ] || [ -L "$path" ] || continue
    leaf="$(basename "$path")"
    if [[ "$leaf" =~ ^\.health-[0-9a-fA-F]{32}$ ]] && [ -d "$path" ] && [ ! -L "$path" ]; then
      remove_owned_tree "$path" "$PREFIX" "$leaf"
    fi
  done
  [ -e "$BACKUP_DIR" ] || [ -L "$BACKUP_DIR" ] || return 0
  if [ -L "$BACKUP_DIR" ] || [ ! -d "$BACKUP_DIR" ]; then
    echo "Ambiguous installer backup remnant retained: $BACKUP_DIR" >&2
    exit 1
  fi
  validate_target "$BACKUP_DIR" "$VERSION" "$REQUIRE_RUNTIME"
  current_resolved=""
  if [ "$OLD_CURRENT_PRESENT" -eq 1 ]; then
    current_resolved="$(resolve_link_target "$CURRENT_LINK" || true)"
    if [ -z "$current_resolved" ]; then
      echo "Current pointer target could not be resolved; backup was retained." >&2
      exit 1
    fi
  fi
  if [ ! -e "$INSTALL_DIR" ] && [ ! -L "$INSTALL_DIR" ]; then
    mv -f "$BACKUP_DIR" "$INSTALL_DIR"
  elif [ -L "$INSTALL_DIR" ] || [ ! -d "$INSTALL_DIR" ]; then
    echo "Ambiguous version target retained beside installer backup: $INSTALL_DIR" >&2
    exit 1
  elif [ "$current_resolved" = "$INSTALL_DIR" ]; then
    validate_target "$INSTALL_DIR" "$VERSION" "$REQUIRE_RUNTIME"
    remove_owned_tree "$BACKUP_DIR" "$VERSIONS_DIR" "$VERSION.backup"
  else
    remove_owned_tree "$INSTALL_DIR" "$VERSIONS_DIR" "$VERSION"
    mv -f "$BACKUP_DIR" "$INSTALL_DIR"
  fi
}

resolve_link_target() {
  local link="$1" raw resolved
  [ -L "$link" ] || return 1
  raw="$(readlink "$link")"
  [ -n "$raw" ] || return 1
  if [[ "$raw" = /* ]]; then resolved="$raw"; else resolved="$(dirname "$link")/$raw"; fi
  (cd "$resolved" 2>/dev/null && pwd -P)
}

validate_target() {
  local target="$1" expected="$2" require_runtime="${3:-0}"
  "$PYTHON_BIN" - "$target" "$expected" "$require_runtime" <<'PY'
import os
import pathlib
import sys
root = pathlib.Path(sys.argv[1]).resolve()
version = sys.argv[2]
require_runtime = sys.argv[3] == "1"
required = (
    "VERSION", "pyproject.toml", "backend/main.py", "frontend/dist/index.html",
    "scripts/appctl.sh", "scripts/install.sh", "scripts/load-env.sh", "scripts/install-sample-data.sh", "scripts/setup-runtime.sh",
)
for relative in required:
    path = root / relative
    if not path.is_file():
        raise SystemExit(f"installed payload is incomplete: {relative}")
if (root / "VERSION").read_text(encoding="utf-8").strip() != version:
    raise SystemExit("installed payload VERSION does not match its directory")
runtime = root / ".venv" / "bin" / "python"
if require_runtime and not (runtime.is_file() and os.access(runtime, os.X_OK)):
    raise SystemExit("installed payload is missing its version-local Python runtime")
PY
}

offline_health_check() {
  local target="$1" expected="$2" nonce
  nonce="$($PYTHON_BIN -c 'import uuid; print(uuid.uuid4().hex)')"
  HEALTH_DIR="$PREFIX/.health-$nonce"
  mkdir "$HEALTH_DIR"
  IMAGE_PROMPT_LIBRARY_PATH="$HEALTH_DIR/library" \
  IMAGE_PROMPT_LIBRARY_AUTH_PATH="$HEALTH_DIR/auth.json" \
  IMAGE_PROMPT_LIBRARY_CONFIG_PATH="$HEALTH_DIR/config.json" \
  "$target/.venv/bin/python" - "$target" "$expected" <<'PY'
import os
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
expected = sys.argv[2]
os.chdir(root)
sys.path.insert(0, str(root))
from backend.main import app

paths = {getattr(route, "path", None) for route in app.routes}
if app.version != expected or "/api/health" not in paths:
    raise SystemExit("candidate runtime health check failed")
PY
  remove_owned_tree "$HEALTH_DIR" "$PREFIX" "$(basename "$HEALTH_DIR")"
  HEALTH_DIR=""
}

atomic_symlink() {
  local link="$1" target="$2" temporary
  if [ -e "$link" ] && [ ! -L "$link" ]; then
    echo "Refusing to replace non-symlink pointer: $link" >&2
    return 1
  fi
  temporary="$(dirname "$link")/.$(basename "$link").tmp.$$"
  rm -f "$temporary"
  ln -s "$target" "$temporary"
  "$PYTHON_BIN" - "$temporary" "$link" <<'PY'
import os
import sys

os.replace(sys.argv[1], sys.argv[2])
PY
}

remove_pointer() {
  local link="$1"
  if [ -L "$link" ]; then rm -f "$link"; elif [ -e "$link" ]; then return 1; fi
}

save_state() {
  if [ -L "$CURRENT_LINK" ]; then OLD_CURRENT_PRESENT=1; OLD_CURRENT_TARGET="$(readlink "$CURRENT_LINK")"; fi
  if [ -L "$PREVIOUS_LINK" ]; then OLD_PREVIOUS_PRESENT=1; OLD_PREVIOUS_TARGET="$(readlink "$PREVIOUS_LINK")"; fi
  if [ -e "$CURRENT_LINK" ] && [ "$OLD_CURRENT_PRESENT" -eq 0 ]; then echo "Refusing non-symlink current pointer." >&2; exit 1; fi
  if [ -e "$PREVIOUS_LINK" ] && [ "$OLD_PREVIOUS_PRESENT" -eq 0 ]; then echo "Refusing non-symlink previous pointer." >&2; exit 1; fi
  STATE_SAVED=1
}

restore_state() {
  local failed=0
  set +e
  if [ "$OLD_CURRENT_PRESENT" -eq 1 ]; then atomic_symlink "$CURRENT_LINK" "$OLD_CURRENT_TARGET" || failed=1; else remove_pointer "$CURRENT_LINK" || failed=1; fi
  if [ "$OLD_PREVIOUS_PRESENT" -eq 1 ]; then atomic_symlink "$PREVIOUS_LINK" "$OLD_PREVIOUS_TARGET" || failed=1; else remove_pointer "$PREVIOUS_LINK" || failed=1; fi
  if [ "$TARGET_PUBLISHED" -eq 1 ]; then remove_owned_tree "$INSTALL_DIR" "$VERSIONS_DIR" "$VERSION" || failed=1; fi
  if [ "$BACKUP_CREATED" -eq 1 ] && [ -d "$BACKUP_DIR" ] && [ ! -e "$INSTALL_DIR" ] && [ ! -L "$INSTALL_DIR" ]; then mv -f "$BACKUP_DIR" "$INSTALL_DIR" || failed=1; fi
  if [ "$ENV_CREATED" -eq 1 ] && [ -f "$ENV_FILE" ]; then rm -f "$ENV_FILE" || failed=1; fi
  if [ -n "$SHIM_BACKUP" ] && [ -f "$SHIM_BACKUP" ]; then mv -f "$SHIM_BACKUP" "$SHIM_PATH" || failed=1; elif [ "$SHIM_CREATED" -eq 1 ]; then rm -f "$SHIM_PATH" || failed=1; fi
  set -e
  return "$failed"
}

cleanup_exit() {
  local rc=$?
  trap - EXIT HUP INT TERM
  if [ "$rc" -ne 0 ] && [ "$COMMITTED" -eq 0 ] && [ "$LOCK_HELD" -eq 1 ] && [ "$STATE_SAVED" -eq 1 ]; then
    echo "Install failed; restoring the prior version and pointers." >&2
    restore_state || echo "Automatic recovery was incomplete; inspect $PREFIX and retry." >&2
  fi
  if [ -n "$STAGING_DIR" ] && [ -d "$STAGING_DIR" ]; then remove_owned_tree "$STAGING_DIR" "$VERSIONS_DIR" "$(basename "$STAGING_DIR")" || true; fi
  if [ -n "$HEALTH_DIR" ] && [ -d "$HEALTH_DIR" ]; then remove_owned_tree "$HEALTH_DIR" "$PREFIX" "$(basename "$HEALTH_DIR")" || true; fi
  unlock_prefix
  exit "$rc"
}
trap 'exit 130' HUP INT TERM
trap cleanup_exit EXIT

lock_prefix
assert_managed_directory_path "$APP_DIR" "$PREFIX"
mkdir -p "$APP_DIR"
assert_managed_directory_path "$VERSIONS_DIR" "$PREFIX"
mkdir -p "$VERSIONS_DIR"
assert_managed_directory_path "$DOWNLOADS_DIR" "$PREFIX"
mkdir -p "$DOWNLOADS_DIR"
assert_managed_directory_path "$DOWNLOAD_DIR" "$PREFIX"
assert_managed_directory_path "$PREFIX/logs" "$PREFIX"
mkdir -p "$DOWNLOAD_DIR" "$PREFIX/logs" "$LIBRARY_PATH"
save_state
reconcile_owned_remnants

ARTIFACT="image-prompt-library-$VERSION.tar.gz"
MANIFEST="image-prompt-library-$VERSION.manifest.json"
CHECKSUM_FILE="$ARTIFACT.sha256"
if [ -n "$RELEASE_BASE_URL" ]; then
  BASE="${RELEASE_BASE_URL%/}"
else
  BASE="https://github.com/$REPO/releases/download/$VERSION"
fi
MANIFEST_URL="$BASE/$MANIFEST"
ARTIFACT_URL="$BASE/$ARTIFACT"
CHECKSUM_URL="$BASE/$CHECKSUM_FILE"
MANIFEST_PATH="$DOWNLOAD_DIR/$MANIFEST"
ARTIFACT_PATH="$DOWNLOAD_DIR/$ARTIFACT"
CHECKSUM_PATH="$DOWNLOAD_DIR/$CHECKSUM_FILE"
VERIFY_SCRIPT="$DOWNLOAD_DIR/verify-release-assets-$VERSION.py"

# A valid selected version is safe to reuse without replacing its target or
# disturbing the true previous pointer.
if [ "$OLD_CURRENT_PRESENT" -eq 1 ]; then
  CURRENT_RESOLVED="$(resolve_link_target "$CURRENT_LINK" || true)"
  case "$CURRENT_RESOLVED" in
    "$VERSIONS_DIR"/*)
      if [ "$(basename "$CURRENT_RESOLVED")" = "$VERSION" ] && [ -d "$CURRENT_RESOLVED" ]; then
        validate_target "$CURRENT_RESOLVED" "$VERSION" "$REQUIRE_RUNTIME"
        COMMITTED=1
        echo "Image Prompt Library $VERSION is already installed."
        exit 0
      fi
      OLD_CURRENT_RESOLVED="$CURRENT_RESOLVED"
      ;;
    "") echo "Current pointer target could not be resolved." >&2; exit 1 ;;
    *) echo "Current pointer resolves outside the install prefix." >&2; exit 1 ;;
  esac
fi

python_download "$MANIFEST_URL" "$MANIFEST_PATH"
python_download "$ARTIFACT_URL" "$ARTIFACT_PATH"
python_download "$CHECKSUM_URL" "$CHECKSUM_PATH"
prepare_release_verifier "$MANIFEST_PATH" "$ARTIFACT_PATH" "$CHECKSUM_PATH" "$VERSION" "$VERIFY_SCRIPT"
STAGING_DIR="$VERSIONS_DIR/.staging-$($PYTHON_BIN -c 'import uuid; print(uuid.uuid4().hex)')"
"$PYTHON_BIN" "$VERIFY_SCRIPT" --version "$VERSION" --manifest "$MANIFEST_PATH" --artifact "$ARTIFACT_PATH" --checksum "$CHECKSUM_PATH" --capability posix-shell-v1 --extract-to "$STAGING_DIR"
validate_target "$STAGING_DIR" "$VERSION"

if [ -e "$INSTALL_DIR" ] || [ -L "$INSTALL_DIR" ]; then
  if [ -L "$INSTALL_DIR" ]; then echo "Refusing symlink at version target: $INSTALL_DIR" >&2; exit 1; fi
  if [ -e "$BACKUP_DIR" ] || [ -L "$BACKUP_DIR" ]; then echo "Installer backup remnant exists at $BACKUP_DIR; inspect it and retry." >&2; exit 1; fi
  mv -f "$INSTALL_DIR" "$BACKUP_DIR"
  BACKUP_CREATED=1
fi
mv -f "$STAGING_DIR" "$INSTALL_DIR"
STAGING_DIR=""
TARGET_PUBLISHED=1

if [ "$SKIP_RUNTIME_SETUP" != "1" ]; then
  bash "$INSTALL_DIR/scripts/setup-runtime.sh"
  offline_health_check "$INSTALL_DIR" "$VERSION"
fi

mkdir -p "$LIBRARY_PATH" "$PREFIX/logs"
if [ ! -f "$ENV_FILE" ]; then
  temporary="$ENV_FILE.tmp.$$"
  cat > "$temporary" <<EOF
IMAGE_PROMPT_LIBRARY_PATH=$LIBRARY_PATH
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000
BACKUP_DIR=$ENV_PREFIX/backups
EOF
  mv -f "$temporary" "$ENV_FILE"
  ENV_CREATED=1
fi

if [ "$CREATE_SHIM" -eq 1 ]; then
  mkdir -p "$(dirname "$SHIM_PATH")"
  if [ -e "$SHIM_PATH" ] && [ ! -f "$SHIM_PATH" ]; then echo "Refusing non-file command shim: $SHIM_PATH" >&2; exit 1; fi
  if [ -f "$SHIM_PATH" ]; then
    SHIM_BACKUP="$SHIM_PATH.rollback.$$"
    cp -p "$SHIM_PATH" "$SHIM_BACKUP"
  else
    SHIM_CREATED=1
  fi
  temporary="$SHIM_PATH.tmp.$$"
  cat > "$temporary" <<EOF
#!/usr/bin/env bash
exec "$CURRENT_LINK/scripts/appctl.sh" "\$@"
EOF
  chmod 0755 "$temporary"
  mv -f "$temporary" "$SHIM_PATH"
fi

if [ "$OLD_CURRENT_PRESENT" -eq 1 ]; then
  atomic_symlink "$PREVIOUS_LINK" "$OLD_CURRENT_RESOLVED"
elif [ "$OLD_PREVIOUS_PRESENT" -eq 0 ]; then
  remove_pointer "$PREVIOUS_LINK"
fi
atomic_symlink "$CURRENT_LINK" "$INSTALL_DIR"

COMMITTED=1
if [ "$BACKUP_CREATED" -eq 1 ] && [ -d "$BACKUP_DIR" ]; then
  remove_owned_tree "$BACKUP_DIR" "$VERSIONS_DIR" "$VERSION.backup" || echo "Installed successfully; retained backup for retry reconciliation: $BACKUP_DIR" >&2
fi
if [ -n "$SHIM_BACKUP" ] && [ -f "$SHIM_BACKUP" ]; then rm -f "$SHIM_BACKUP"; fi
echo "Installed Image Prompt Library $VERSION."
echo
echo "Start the app:"
echo "  image-prompt-library start"
echo
echo "Fallback command:"
echo "  $CURRENT_LINK/scripts/appctl.sh start"
