#!/usr/bin/env bash
set -euo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]}"
SCRIPT_DIR="$(cd -P "$(dirname "$SCRIPT_PATH")" && pwd -P)"
APP_ROOT="$(cd -P "$SCRIPT_DIR/.." && pwd -P)"
VERSION_FILE="$APP_ROOT/VERSION"
APP_PREFIX="${IMAGE_PROMPT_LIBRARY_PREFIX:-}"
APP_PREFIX_USED_ALIAS=0
if [ -z "$APP_PREFIX" ]; then
  if [ "$(basename "$(dirname "$APP_ROOT")")" = "versions" ] && [ "$(basename "$(dirname "$(dirname "$APP_ROOT")")")" = "app" ]; then
    APP_PREFIX="$(cd -P "$APP_ROOT/../../.." && pwd -P)"
  elif [ "$(basename "$APP_ROOT")" = "current" ] && [ "$(basename "$(dirname "$APP_ROOT")")" = "app" ]; then
    APP_PREFIX="$(cd -P "$APP_ROOT/../.." && pwd -P)"
  else
    APP_PREFIX="$HOME/.image-prompt-library"
  fi
fi
if [ -d "$APP_PREFIX" ]; then
  APP_PREFIX_LOGICAL="$(cd -L "$APP_PREFIX" && pwd -L)"
  APP_PREFIX_PHYSICAL="$(cd -P "$APP_PREFIX" && pwd -P)"
  if [ -L "$APP_PREFIX" ] || [ "$APP_PREFIX_LOGICAL" != "$APP_PREFIX_PHYSICAL" ]; then
    APP_PREFIX_USED_ALIAS=1
  fi
  APP_PREFIX="$APP_PREFIX_PHYSICAL"
fi
ENV_FILE="$APP_PREFIX/.env"
source "$SCRIPT_DIR/load-env.sh"
# Default private library path: ~/ImagePromptLibrary

load_env() {
  local INCOMING_IMAGE_PROMPT_LIBRARY_PATH="${IMAGE_PROMPT_LIBRARY_PATH-}"
  local INCOMING_IMAGE_PROMPT_LIBRARY_AUTH_PATH="${IMAGE_PROMPT_LIBRARY_AUTH_PATH-}"
  local INCOMING_IMAGE_PROMPT_LIBRARY_CONFIG_PATH="${IMAGE_PROMPT_LIBRARY_CONFIG_PATH-}"
  local INCOMING_BACKEND_HOST="${BACKEND_HOST-}"
  local INCOMING_BACKEND_PORT="${BACKEND_PORT-}"
  local INCOMING_BACKUP_DIR="${BACKUP_DIR-}"
  image_prompt_library_load_env_file "$ENV_FILE"
  export IMAGE_PROMPT_LIBRARY_PATH="${INCOMING_IMAGE_PROMPT_LIBRARY_PATH:-${IMAGE_PROMPT_LIBRARY_PATH:-$HOME/ImagePromptLibrary}}"
  if [ -n "$INCOMING_IMAGE_PROMPT_LIBRARY_AUTH_PATH" ]; then export IMAGE_PROMPT_LIBRARY_AUTH_PATH="$INCOMING_IMAGE_PROMPT_LIBRARY_AUTH_PATH"; fi
  if [ -n "$INCOMING_IMAGE_PROMPT_LIBRARY_CONFIG_PATH" ]; then export IMAGE_PROMPT_LIBRARY_CONFIG_PATH="$INCOMING_IMAGE_PROMPT_LIBRARY_CONFIG_PATH"; fi
  export BACKEND_HOST="${INCOMING_BACKEND_HOST:-${BACKEND_HOST:-127.0.0.1}}"
  export BACKEND_PORT="${INCOMING_BACKEND_PORT:-${BACKEND_PORT:-8000}}"
  export BACKUP_DIR="${INCOMING_BACKUP_DIR:-${BACKUP_DIR:-$APP_PREFIX/backups}}"
}

is_wsl() {
  grep -qiE '(microsoft|wsl)' /proc/version 2>/dev/null
}

python_bin() {
  if [ -n "${PYTHON:-}" ]; then
    printf '%s\n' "$PYTHON"
  elif [ -x "$APP_ROOT/.venv/bin/python" ]; then
    printf '%s\n' "$APP_ROOT/.venv/bin/python"
  else
    printf '%s\n' "python3"
  fi
}

print_version() {
  if [ -f "$VERSION_FILE" ]; then
    printf '%s\n' "$(tr -d '\n\r' < "$VERSION_FILE")"
  else
    basename "$APP_ROOT"
  fi
}

start_app() {
  START_HOST=""
  START_PORT=""
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --host)
        if [ "$#" -lt 2 ] || [ -z "${2:-}" ]; then
          echo "Missing value for --host" >&2
          echo "Usage: image-prompt-library start [--host HOST] [--port PORT]" >&2
          exit 2
        fi
        START_HOST="$2"
        shift 2
        ;;
      --port)
        if [ "$#" -lt 2 ] || [ -z "${2:-}" ]; then
          echo "Missing value for --port" >&2
          echo "Usage: image-prompt-library start [--host HOST] [--port PORT]" >&2
          exit 2
        fi
        START_PORT="$2"
        shift 2
        ;;
      *)
        echo "Unknown start option: $1" >&2
        echo "Usage: image-prompt-library start [--host HOST] [--port PORT]" >&2
        exit 2
        ;;
    esac
  done
  load_env
  if [ -n "$START_HOST" ]; then
    BACKEND_HOST="$START_HOST"
  fi
  if [ -n "$START_PORT" ]; then
    BACKEND_PORT="$START_PORT"
  fi
  export BACKEND_HOST BACKEND_PORT
  if is_wsl && [ "$BACKEND_HOST" = "127.0.0.1" ]; then
    cat >&2 <<WSL_HINT
WSL detected. If your Windows browser cannot open http://127.0.0.1:$BACKEND_PORT/, stop this server with Ctrl-C and run:
  image-prompt-library start --host 0.0.0.0 --port $BACKEND_PORT
Then open http://localhost:$BACKEND_PORT/ from Windows. Binding to 0.0.0.0 may expose the app beyond WSL; use only on a trusted machine/network.
WSL_HINT
  fi
  PYTHON_BIN="$(python_bin)"
  cd "$APP_ROOT"
  exec "$PYTHON_BIN" -m uvicorn backend.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT"
}

doctor_app() {
  load_env
  PYTHON_BIN="$(python_bin)"
  cd "$APP_ROOT"
  "$PYTHON_BIN" - "$APP_ROOT" "$APP_PREFIX" "$IMAGE_PROMPT_LIBRARY_PATH" "$BACKEND_HOST" "$BACKEND_PORT" "$(print_version)" <<'PY'
from __future__ import annotations

import os
import platform
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

app_root = Path(sys.argv[1])
app_prefix = Path(sys.argv[2])
library_path = Path(sys.argv[3]).expanduser()
backend_host = sys.argv[4]
backend_port = sys.argv[5]
version = sys.argv[6]
sys.path.insert(0, str(app_root))

print("Image Prompt Library doctor")
print()
print("## App")
print(f"OK Version: {version}")
print(f"OK Install prefix: {app_prefix}")
print(f"OK App root: {app_root}")
print(f"OK Backend URL: http://{backend_host}:{backend_port}/")
print(f"OK Platform: {platform.system()} {platform.release()}")
print()
print("## Library")
print(f"OK Library path: {library_path}")

item_count = None
try:
    library_path.mkdir(parents=True, exist_ok=True)
    db_path = library_path / "db.sqlite"
    if not db_path.exists():
        from backend.db import init_db
        init_db(library_path)
    with sqlite3.connect(db_path) as conn:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        item_count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    print()
    print("## Database")
    print(f"OK Database path: {db_path}")
    print(f"OK Database integrity: {integrity}")
    print(f"OK Item count: {item_count}")
except Exception as exc:
    print()
    print("## Database")
    print(f"ERROR Database integrity: {type(exc).__name__}")
    item_count = None

generation_optional = True
try:
    from backend.services.openai_codex_native import CodexNativeAuthStore, PROVIDER_ID, configured_client_id
    store = CodexNativeAuthStore()
    configured = bool(configured_client_id())
    saved_auth_present = store.path.is_file()
    if not configured:
        state = "not_configured"
    elif saved_auth_present:
        state = "saved_auth_present"
    else:
        state = "not_connected"
    severity = "OK" if state == "saved_auth_present" else "WARN"
    print()
    print("## Generation")
    print(f"{severity} Generation provider: {PROVIDER_ID} state={state} configured={configured}")
except Exception as exc:
    print()
    print("## Generation")
    print(f"WARN Generation provider: unavailable ({type(exc).__name__})")

print()
print("## Updates / Service")

versions_dir = app_prefix / "app" / "versions"
if versions_dir.is_dir():
    backup_pattern = re.compile(r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?\.backup$")
    entries = list(versions_dir.iterdir())
    backups = sorted(path.name for path in entries if backup_pattern.fullmatch(path.name))
    staging = sorted(path.name for path in entries if re.fullmatch(r"\.staging-[0-9a-fA-F]{32}", path.name))
    if backups:
        print(f"WARN Installer backup remnants: {', '.join(backups)}; retry update or inspect before manual cleanup")
    if staging:
        print(f"WARN Installer staging remnants: {', '.join(staging)}; retry update to reconcile")
lock_dir = app_prefix / ".transaction.lock"
if lock_dir.exists() or lock_dir.is_symlink():
    print("WARN Update transaction lock is present; wait for the active operation or retry after it exits")

if platform.system() == "Darwin":
    label = os.environ.get("IMAGE_PROMPT_LIBRARY_SERVICE_LABEL", "com.eddietyp.image-prompt-library")
    service_ref = f"gui/{os.getuid()}/{label}"
    try:
        result = subprocess.run(["launchctl", "print", service_ref], text=True, capture_output=True, timeout=5)
        state = "running" if "state = running" in result.stdout else "not loaded"
    except Exception:
        state = "unknown"
    print(f"OK macOS service: {label} {state}")
    print(f"OK macOS service plist: {Path.home() / 'Library' / 'LaunchAgents' / (label + '.plist')}")
    print(f"OK Logs: {Path.home() / 'Library' / 'Logs' / 'image-prompt-library.out.log'}")
else:
    print("WARN macOS service: not applicable")

print()
print("## Next steps")
if item_count == 0:
    print("WARN Empty library: add a prompt in the app, or run image-prompt-library sample-data en")
else:
    print("OK Library has saved references.")
if generation_optional:
    print("OK Generation is optional. Connect ChatGPT / Codex OAuth in Config only if you want local generation.")
print("OK For a shorter summary, run image-prompt-library status")
PY
}

status_app() {
  load_env
  PYTHON_BIN="$(python_bin)"
  cd "$APP_ROOT"
  "$PYTHON_BIN" - "$APP_ROOT" "$IMAGE_PROMPT_LIBRARY_PATH" "$BACKEND_HOST" "$BACKEND_PORT" "$(print_version)" <<'PY'
from __future__ import annotations

import platform
import sqlite3
import sys
from pathlib import Path

app_root = Path(sys.argv[1])
library_path = Path(sys.argv[2]).expanduser()
backend_host = sys.argv[3]
backend_port = sys.argv[4]
version = sys.argv[5]
sys.path.insert(0, str(app_root))

print("Image Prompt Library status")
print(f"Version: {version}")
print(f"Library: {library_path}")
print(f"URL: http://{backend_host}:{backend_port}/")

try:
    db_path = library_path / "db.sqlite"
    if not db_path.exists():
        from backend.db import init_db
        init_db(library_path)
    with sqlite3.connect(db_path) as conn:
        item_count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    print(f"Items: {item_count}")
except Exception as exc:
    print(f"Items: unavailable ({type(exc).__name__})")

try:
    from backend.services.openai_codex_native import CodexNativeAuthStore, PROVIDER_ID, configured_client_id
    store = CodexNativeAuthStore()
    configured = bool(configured_client_id())
    saved_auth_present = store.path.is_file()
    if not configured:
        state = "not configured"
    elif saved_auth_present:
        state = "connected"
    else:
        state = "not connected"
    print(f"Generation: {PROVIDER_ID} {state}")
except Exception as exc:
    print(f"Generation: unavailable ({type(exc).__name__})")

if platform.system() == "Darwin":
    print("Service: macOS launchd available; run image-prompt-library service status for details.")
else:
    print("Service: not applicable")

print("Run image-prompt-library doctor for detailed diagnostics.")
PY
}

update_app() {
  VERSION_ARG="latest"
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --version)
        VERSION_ARG="${2:-}"
        shift 2
        ;;
      *)
        echo "Unknown update option: $1" >&2
        exit 2
        ;;
    esac
  done
  PYTHON_BIN="$(python_bin)"
  PYTHON="$PYTHON_BIN" bash "$SCRIPT_DIR/install.sh" --prefix "$APP_PREFIX" --version "$VERSION_ARG" --no-shim
}

library_archive_app() {
  load_env
  local PYTHON_BIN status=0
  PYTHON_BIN="$(python_bin)"
  if [ ! -f "$SCRIPT_DIR/library-archive.py" ]; then
    echo "Portable backup support is missing from this installed version." >&2
    exit 1
  fi
  lock_update_transaction
  trap 'unlock_update_transaction' EXIT
  trap 'exit 130' HUP INT TERM
  cd "$APP_ROOT"
  "$PYTHON_BIN" "$SCRIPT_DIR/library-archive.py" "$@" || status=$?
  trap - EXIT HUP INT TERM
  unlock_update_transaction
  return "$status"
}

ROLLBACK_LOCK_HELD=0
ROLLBACK_HEALTH_DIR=""
ROLLBACK_MUTATED=0
ROLLBACK_COMMITTED=0
ROLLBACK_OLD_CURRENT=""
ROLLBACK_OLD_PREVIOUS=""

lock_update_transaction() {
  local lock_dir="$APP_PREFIX/.transaction.lock" pid
  assert_physical_managed_path "$lock_dir"
  if mkdir "$lock_dir" 2>/dev/null; then
    ROLLBACK_LOCK_HELD=1
    printf '%s\n' "$$" > "$lock_dir/owner"
    return
  fi
  if [ -f "$lock_dir/owner" ]; then
    read -r pid < "$lock_dir/owner" || true
    if [[ "$pid" =~ ^[0-9]+$ ]] && ! kill -0 "$pid" 2>/dev/null; then
      rm -f "$lock_dir/owner"
      if rmdir "$lock_dir" 2>/dev/null && mkdir "$lock_dir" 2>/dev/null; then
        ROLLBACK_LOCK_HELD=1
        printf '%s\n' "$$" > "$lock_dir/owner"
        return
      fi
    fi
  elif [ -d "$lock_dir" ] && "$(python_bin)" - "$lock_dir" <<'PY'
import pathlib
import sys
import time
path = pathlib.Path(sys.argv[1])
raise SystemExit(0 if time.time() - path.stat().st_mtime >= 30 else 1)
PY
  then
    if rmdir "$lock_dir" 2>/dev/null && mkdir "$lock_dir" 2>/dev/null; then
      ROLLBACK_LOCK_HELD=1
      printf '%s\n' "$$" > "$lock_dir/owner"
      return
    fi
  fi
  echo "Another Image Prompt Library managed operation is already running; retry later." >&2
  exit 1
}

unlock_update_transaction() {
  local lock_dir="$APP_PREFIX/.transaction.lock"
  assert_physical_managed_path "$lock_dir"
  if [ "$ROLLBACK_LOCK_HELD" -eq 1 ] && [ -f "$lock_dir/owner" ] && [ "$(cat "$lock_dir/owner")" = "$$" ]; then
    rm -f "$lock_dir/owner"
    rmdir "$lock_dir" 2>/dev/null || true
  fi
  ROLLBACK_LOCK_HELD=0
}

atomic_installed_pointer() {
  local link="$1" target="$2" temporary
  if [ -e "$link" ] && [ ! -L "$link" ]; then
    echo "Refusing to replace non-symlink pointer: $link" >&2
    return 1
  fi
  temporary="$(dirname "$link")/.$(basename "$link").tmp.$$"
  rm -f "$temporary"
  ln -s "$target" "$temporary"
  "$(python_bin)" - "$temporary" "$link" <<'PY'
import os
import sys

os.replace(sys.argv[1], sys.argv[2])
PY
}

resolve_installed_pointer() {
  local link="$1" versions_dir="$2" runtime_python
  runtime_python="$(python_bin)"
  "$runtime_python" - "$link" "$versions_dir" <<'PY'
import pathlib
import os
import stat
import sys

link = pathlib.Path(sys.argv[1])
versions = pathlib.Path(os.path.abspath(sys.argv[2]))
versions_mode = os.lstat(versions).st_mode
if stat.S_ISLNK(versions_mode) or not stat.S_ISDIR(versions_mode):
    raise SystemExit(f"Managed versions path is not a physical directory: {versions}")
if not link.is_symlink():
    raise SystemExit(f"Installed pointer is not a symlink: {link}")
raw = pathlib.Path(os.readlink(link))
candidate = raw if raw.is_absolute() else link.parent / raw
candidate = pathlib.Path(os.path.abspath(candidate))
if candidate.parent != versions:
    raise SystemExit(f"Installed pointer resolves outside the managed versions directory: {link}")
mode = os.lstat(candidate).st_mode
if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
    raise SystemExit(f"Installed pointer target is not a physical version directory: {link}")
print(candidate.resolve(strict=True))
PY
}

assert_physical_managed_path() {
  "$(python_bin)" - "$1" "$APP_PREFIX" <<'PY'
import os
import pathlib
import stat
import sys

target = pathlib.Path(os.path.abspath(sys.argv[1]))
root = pathlib.Path(sys.argv[2]).resolve(strict=True)
try:
    relative = target.relative_to(root)
except ValueError:
    raise SystemExit(f"Managed path is outside the install prefix: {target}")
cursor = root
for part in relative.parts:
    cursor = cursor / part
    try:
        mode = os.lstat(cursor).st_mode
    except FileNotFoundError:
        break
    if stat.S_ISLNK(mode):
        raise SystemExit(f"Managed path contains a symlink: {cursor}")
    if not stat.S_ISDIR(mode):
        raise SystemExit(f"Managed path contains a non-directory: {cursor}")
PY
}

validate_rollback_runtime() {
  local target="$1" expected runtime_python
  expected="$(basename "$target")"
  runtime_python="$(python_bin)"
  "$runtime_python" - "$target" "$expected" <<'PY'
import os
import pathlib
import re
import sys

root = pathlib.Path(sys.argv[1]).resolve(strict=True)
expected = sys.argv[2]
pattern = re.compile(r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?")
match = pattern.fullmatch(expected)
if not match or any(part.isdigit() and len(part) > 1 and part.startswith("0") for part in (match.group(4) or "").split(".") if part):
    raise SystemExit("Rollback target directory is not a strict SemVer tag.")
required = (
    "VERSION", "pyproject.toml", "backend/main.py", "frontend/dist/index.html",
    "scripts/appctl.sh", "scripts/install.sh", "scripts/load-env.sh", "scripts/install-sample-data.sh", "scripts/setup-runtime.sh",
)
for relative in required:
    if not (root / relative).is_file():
        raise SystemExit(f"Rollback target is incomplete: {relative}")
if (root / "VERSION").read_text(encoding="utf-8").strip() != expected:
    raise SystemExit("Rollback target VERSION does not match its directory.")
python = root / ".venv" / "bin" / "python"
if not python.is_file() or not os.access(python, os.X_OK):
    raise SystemExit("Rollback target runtime is missing; reinstall that version before rollback.")
PY
}

validate_legacy_v080_rollback_runtime() {
  local target="$1" runtime_python directory
  runtime_python="$(python_bin)"
  for directory in \
    "$target/backend" \
    "$target/frontend" \
    "$target/frontend/dist" \
    "$target/scripts" \
    "$target/.venv" \
    "$target/.venv/bin"; do
    assert_physical_managed_path "$directory"
  done
  "$runtime_python" - "$target" <<'PY'
import os
import pathlib
import stat
import sys

root = pathlib.Path(sys.argv[1]).resolve(strict=True)
if root.name != "v0.8.0":
    raise SystemExit("Legacy rollback migration target is not v0.8.0.")
required = (
    "VERSION", "pyproject.toml", "backend/main.py", "frontend/dist/index.html",
    "scripts/appctl.sh", "scripts/install.sh", "scripts/install-sample-data.sh", "scripts/setup-runtime.sh",
)
for relative in required:
    path = root / relative
    try:
        mode = os.lstat(path).st_mode
    except FileNotFoundError:
        raise SystemExit(f"Legacy v0.8.0 rollback target is incomplete: {relative}")
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise SystemExit(f"Legacy v0.8.0 rollback payload is not a regular file: {relative}")
if (root / "VERSION").read_text(encoding="utf-8").strip() != "v0.8.0":
    raise SystemExit("Legacy v0.8.0 rollback target VERSION does not match its directory.")
python = root / ".venv" / "bin" / "python"
if not python.is_file() or not os.access(python, os.X_OK):
    raise SystemExit("Legacy v0.8.0 rollback target runtime is missing; reinstall that version before rollback.")
PY
}

migrate_legacy_v080_management() {
  local target="$1" source_dir="$SCRIPT_DIR" source_root runtime_python
  source_root="$(cd -P "$source_dir/.." && pwd -P)"
  runtime_python="$(python_bin)"
  assert_physical_managed_path "$source_dir"
  assert_physical_managed_path "$target"
  assert_physical_managed_path "$target/scripts"
  "$runtime_python" - "$source_dir" "$source_root" "$target" "$APP_PREFIX" <<'PY'
import hashlib
import json
import os
import pathlib
import stat
import sys

source_dir, source_root, target, prefix = map(pathlib.Path, sys.argv[1:])
source_dir = source_dir.resolve(strict=True)
source_root = source_root.resolve(strict=True)
target = target.resolve(strict=True)
prefix = prefix.resolve(strict=True)

def assert_in_prefix(path: pathlib.Path, label: str) -> pathlib.Path:
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(prefix)
    except ValueError:
        raise SystemExit(f"Legacy rollback migration {label} is outside the install prefix: {resolved}")
    return resolved

assert_in_prefix(source_dir, "source scripts directory")
assert_in_prefix(source_root, "source root")
assert_in_prefix(target, "target")
assert_in_prefix(target / "scripts", "target scripts directory")

management = (
    "scripts/install.sh",
    "scripts/load-env.sh",
    "scripts/install-sample-data.sh",
    "scripts/appctl.sh",
)
legacy_sha256 = {
    "scripts/install.sh": "baa71e8f21eb314ad56fd7d70d43ccd5965168020c0ef9c26216c76342ad8bae",
    "scripts/install-sample-data.sh": "476b44b8ae677420407d25325e6fd9a73f6571f1c07cdc31220fac317633f662",
    "scripts/appctl.sh": "df7db6025605e503696134dc26f2915db813793ffa4b502e3bcb147d4a46e76b",
}

if not hasattr(os, "O_NOFOLLOW") or any(
    function not in os.supports_dir_fd for function in (os.open, os.stat, os.unlink, os.rename)
):
    raise SystemExit("Legacy rollback migration requires confined POSIX directory operations.")

def identity(details: os.stat_result) -> tuple[int, int]:
    return details.st_dev, details.st_ino

def open_directory(path: pathlib.Path, label: str) -> int:
    before = os.stat(path, follow_symlinks=False)
    if not stat.S_ISDIR(before.st_mode):
        raise SystemExit(f"Legacy rollback migration {label} is not a physical directory.")
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    opened = os.fstat(descriptor)
    current = os.stat(path, follow_symlinks=False)
    if not stat.S_ISDIR(opened.st_mode) or identity(before) != identity(opened) or identity(opened) != identity(current):
        os.close(descriptor)
        raise SystemExit(f"Legacy rollback migration {label} changed during validation.")
    return descriptor

def read_regular(directory: int, name: str, label: str, *, optional: bool = False) -> tuple[bytes, int] | None:
    try:
        before = os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        if optional:
            return None
        raise SystemExit(f"Legacy rollback migration {label} is missing: {name}")
    if not stat.S_ISREG(before.st_mode):
        raise SystemExit(f"Legacy rollback migration {label} is not a regular file: {name}")
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or identity(before) != identity(opened):
            raise SystemExit(f"Legacy rollback migration {label} changed during validation: {name}")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            return stream.read(), stat.S_IMODE(opened.st_mode)
    finally:
        if descriptor != -1:
            os.close(descriptor)

def require_same_directory(parent: int, name: str, child: int, label: str) -> None:
    details = os.stat(name, dir_fd=parent, follow_symlinks=False)
    if not stat.S_ISDIR(details.st_mode) or identity(details) != identity(os.fstat(child)):
        raise SystemExit(f"Legacy rollback migration {label} is not anchored to its validated parent.")

def remove_exact_temporary(directory: int, name: str) -> None:
    try:
        details = os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        return
    if not stat.S_ISREG(details.st_mode):
        raise SystemExit(f"Legacy rollback migration exact temporary is not a regular file: {name}")
    os.unlink(name, dir_fd=directory)
    os.fsync(directory)

def atomic_write(directory: int, name: str, temporary: str, payload: bytes, mode: int) -> None:
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        mode,
        dir_fd=directory,
    )
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    finally:
        if descriptor != -1:
            os.close(descriptor)
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass

source_root_fd = open_directory(source_root, "source root")
source_scripts_fd = open_directory(source_dir, "source scripts directory")
target_root_fd = open_directory(target, "target")
target_scripts_fd = open_directory(target / "scripts", "target scripts directory")
try:
    require_same_directory(source_root_fd, "scripts", source_scripts_fd, "source scripts directory")
    require_same_directory(target_root_fd, "scripts", target_scripts_fd, "target scripts directory")

    source_payloads: dict[str, tuple[bytes, int]] = {}
    for relative in management:
        basename = pathlib.Path(relative).name
        value = read_regular(source_scripts_fd, basename, "source")
        assert value is not None
        source_payloads[relative] = value
    version_value = read_regular(source_root_fd, "VERSION", "source VERSION")
    assert version_value is not None
    source_controller_version = version_value[0].decode("utf-8").strip()
    if not source_controller_version:
        raise SystemExit("Legacy rollback migration source VERSION is empty.")

    for relative in (
        "VERSION", "pyproject.toml", "backend/main.py", "frontend/dist/index.html",
        "scripts/appctl.sh", "scripts/install.sh", "scripts/install-sample-data.sh", "scripts/setup-runtime.sh",
    ):
        value = read_regular(target_root_fd, relative, "target")
        assert value is not None

    desired_sha256 = {
        relative: hashlib.sha256(payload).hexdigest()
        for relative, (payload, _) in source_payloads.items()
    }
    marker_value = read_regular(
        target_root_fd, ".rollback-migration.json", "provenance marker", optional=True
    )
    existing: dict[str, bytes | None] = {}
    for relative in management:
        basename = pathlib.Path(relative).name
        value = read_regular(
            target_scripts_fd, basename, "target", optional=relative == "scripts/load-env.sh"
        )
        existing[relative] = None if value is None else value[0]

    if marker_value is None:
        if existing["scripts/load-env.sh"] is not None:
            raise SystemExit("Legacy v0.8.0 rollback target has an unprovenanced scripts/load-env.sh.")
        for relative, expected in legacy_sha256.items():
            payload = existing[relative]
            if payload is None or hashlib.sha256(payload).hexdigest() != expected:
                raise SystemExit(f"Legacy v0.8.0 rollback target does not match the public payload: {relative}")
        marker_state = "new"
    else:
        try:
            marker_data = json.loads(marker_value[0].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SystemExit(f"Legacy rollback migration provenance marker is invalid: {exc}")
        if (
            not isinstance(marker_data, dict)
            or marker_data.get("schema") != 1
            or marker_data.get("target_version") != "v0.8.0"
            or marker_data.get("source_controller_version") != source_controller_version
            or marker_data.get("files") != desired_sha256
            or marker_data.get("state") not in {"prepared", "complete"}
        ):
            raise SystemExit("Legacy rollback migration provenance marker does not match this controller.")
        marker_state = marker_data["state"]
        for relative, payload in existing.items():
            if payload is None:
                if marker_state == "prepared" and relative == "scripts/load-env.sh":
                    continue
                raise SystemExit(f"Legacy rollback migration marked target is incomplete: {relative}")
            actual = hashlib.sha256(payload).hexdigest()
            allowed = {desired_sha256[relative]}
            if marker_state == "prepared" and relative in legacy_sha256:
                allowed.add(legacy_sha256[relative])
            if actual not in allowed:
                raise SystemExit(f"Legacy rollback migration marked target was modified: {relative}")

    for relative in management:
        basename = pathlib.Path(relative).name
        remove_exact_temporary(target_scripts_fd, f".{basename}.rollback-migration.tmp")
    remove_exact_temporary(target_root_fd, ".rollback-migration.json.tmp")

    def marker_payload(state: str) -> bytes:
        return (json.dumps({
            "schema": 1,
            "state": state,
            "target_version": "v0.8.0",
            "source_controller_version": source_controller_version,
            "files": desired_sha256,
        }, sort_keys=True) + "\n").encode("utf-8")

    if marker_state == "new":
        atomic_write(
            target_root_fd,
            ".rollback-migration.json",
            ".rollback-migration.json.tmp",
            marker_payload("prepared"),
            0o644,
        )

    for relative in management:
        basename = pathlib.Path(relative).name
        payload, mode = source_payloads[relative]
        atomic_write(
            target_scripts_fd,
            basename,
            f".{basename}.rollback-migration.tmp",
            payload,
            mode,
        )
    atomic_write(
        target_root_fd,
        ".rollback-migration.json",
        ".rollback-migration.json.tmp",
        marker_payload("complete"),
        0o644,
    )
finally:
    os.close(target_scripts_fd)
    os.close(target_root_fd)
    os.close(source_scripts_fd)
    os.close(source_root_fd)
PY
  echo "Migrated v0.8.0 management scripts for rollback (backend, frontend, data, and pointers unchanged)."
}

remove_rollback_health() {
  local target="$1"
  "$(python_bin)" - "$target" "$APP_PREFIX" <<'PY'
import os
import pathlib
import re
import shutil
import stat
import sys

target = pathlib.Path(sys.argv[1])
prefix = pathlib.Path(sys.argv[2]).resolve(strict=True)
if target.parent.resolve(strict=True) != prefix or not re.fullmatch(r"\.rollback-health-[0-9a-fA-F]{32}", target.name):
    raise SystemExit("Refusing unsafe rollback health cleanup.")
try:
    mode = os.lstat(target).st_mode
except FileNotFoundError:
    raise SystemExit(0)
if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
    raise SystemExit("Refusing unsafe rollback health cleanup.")
shutil.rmtree(target)
PY
}

health_check_rollback_runtime() {
  local target="$1" expected nonce
  expected="$(basename "$target")"
  nonce="$("$(python_bin)" -c 'import uuid; print(uuid.uuid4().hex)')"
  ROLLBACK_HEALTH_DIR="$APP_PREFIX/.rollback-health-$nonce"
  mkdir "$ROLLBACK_HEALTH_DIR"
  IMAGE_PROMPT_LIBRARY_PATH="$ROLLBACK_HEALTH_DIR/library" \
  IMAGE_PROMPT_LIBRARY_AUTH_PATH="$ROLLBACK_HEALTH_DIR/auth.json" \
  IMAGE_PROMPT_LIBRARY_CONFIG_PATH="$ROLLBACK_HEALTH_DIR/config.json" \
  "$target/.venv/bin/python" - "$target" "$expected" <<'PY'
import os
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
os.chdir(root)
sys.path.insert(0, str(root))
from backend.main import app
if app.version != sys.argv[2] or "/api/health" not in {getattr(route, "path", None) for route in app.routes}:
    raise SystemExit("Rollback target failed its offline health check.")
PY
  remove_rollback_health "$ROLLBACK_HEALTH_DIR"
  ROLLBACK_HEALTH_DIR=""
}

rollback_cleanup() {
  local rc=$? current_link="$APP_PREFIX/app/current" previous_link="$APP_PREFIX/app/previous" recovery_failed=0
  trap - EXIT HUP INT TERM
  set +e
  if [ "$rc" -ne 0 ] && [ "$ROLLBACK_MUTATED" -eq 1 ] && [ "$ROLLBACK_COMMITTED" -eq 0 ]; then
    atomic_installed_pointer "$current_link" "$ROLLBACK_OLD_CURRENT" || recovery_failed=1
    atomic_installed_pointer "$previous_link" "$ROLLBACK_OLD_PREVIOUS" || recovery_failed=1
    if [ "$recovery_failed" -ne 0 ]; then
      echo "Rollback failed and pointer recovery was incomplete; run doctor before retrying." >&2
    fi
  fi
  if [ -n "$ROLLBACK_HEALTH_DIR" ] && [ -d "$ROLLBACK_HEALTH_DIR" ]; then
    remove_rollback_health "$ROLLBACK_HEALTH_DIR" || true
  fi
  unlock_update_transaction
  exit "$rc"
}

rollback_app() {
  if [ "$#" -ne 0 ]; then
    echo "Usage: image-prompt-library rollback" >&2
    exit 2
  fi
  local current_link="$APP_PREFIX/app/current" previous_link="$APP_PREFIX/app/previous" versions_dir="$APP_PREFIX/app/versions"
  local current_target previous_target
  lock_update_transaction
  trap 'exit 130' HUP INT TERM
  trap rollback_cleanup EXIT
  assert_physical_managed_path "$versions_dir"
  mkdir -p "$versions_dir"
  assert_physical_managed_path "$versions_dir"
  if [ ! -L "$previous_link" ]; then
    echo "No previous version is available for rollback." >&2
    exit 1
  fi
  if [ ! -L "$current_link" ]; then
    echo "Current version pointer is unavailable; run doctor before rollback." >&2
    exit 1
  fi
  current_target="$(resolve_installed_pointer "$current_link" "$versions_dir")"
  previous_target="$(resolve_installed_pointer "$previous_link" "$versions_dir")"
  if [ "$current_target" = "$previous_target" ]; then
    echo "Current and previous point to the same version; refusing a no-op rollback." >&2
    exit 1
  fi
  if [ "$(basename "$previous_target")" = "v0.8.0" ]; then
    validate_legacy_v080_rollback_runtime "$previous_target"
    health_check_rollback_runtime "$previous_target"
    migrate_legacy_v080_management "$previous_target"
  fi
  validate_rollback_runtime "$previous_target"
  health_check_rollback_runtime "$previous_target"
  ROLLBACK_OLD_CURRENT="$(readlink "$current_link")"
  ROLLBACK_OLD_PREVIOUS="$(readlink "$previous_link")"
  ROLLBACK_MUTATED=1
  atomic_installed_pointer "$previous_link" "$current_target"
  atomic_installed_pointer "$current_link" "$previous_target"
  ROLLBACK_COMMITTED=1
  trap - EXIT HUP INT TERM
  unlock_update_transaction
  echo "Rolled back to $(basename "$previous_target")."
}

sample_data() {
  load_env
  bash "$SCRIPT_DIR/install-sample-data.sh" "$@"
}

refuse_unsafe_delete_target() {
  local TARGET="$1" LABEL="$2"
  case "$TARGET" in
    ""|"/"|"$HOME"|"$HOME/"|"."|"..")
      echo "Refusing unsafe $LABEL path: $TARGET" >&2
      exit 2
      ;;
  esac
  local PY_TARGET="$TARGET" PY_HOME="$HOME"
  case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*)
      PY_TARGET="$(cygpath -m "$PY_TARGET")"
      PY_HOME="$(cygpath -m "$PY_HOME")"
      ;;
  esac
  "$(python_bin)" - "$PY_TARGET" "$PY_HOME" "$LABEL" <<'PY'
import os
import pathlib
import sys

target_path = pathlib.Path(os.path.abspath(sys.argv[1]))
home_path = pathlib.Path(os.path.abspath(sys.argv[2]))
try:
    target = target_path.resolve(strict=False)
except OSError:
    target = target_path
try:
    home = home_path.resolve(strict=True)
except OSError:
    home = home_path
label = sys.argv[3]

try:
    contains_home = os.path.normcase(os.path.commonpath((str(target), str(home)))) == os.path.normcase(str(target))
except ValueError:
    contains_home = False

if target == pathlib.Path(target.anchor) or contains_home:
    raise SystemExit(f"Refusing unsafe {label} path: {target}")
PY
}

assert_disjoint_uninstall_paths() {
  "$(python_bin)" - "$1" "$2" <<'PY'
import os
import pathlib
import sys

prefix = pathlib.Path(sys.argv[1]).resolve(strict=False)
library = pathlib.Path(sys.argv[2]).resolve(strict=False)

def contains(parent: pathlib.Path, child: pathlib.Path) -> bool:
    try:
        return os.path.commonpath((str(parent), str(child))) == str(parent)
    except ValueError:
        return False

if contains(prefix, library) or contains(library, prefix):
    raise SystemExit("Private library and install prefix must not contain each other; move the library before uninstalling.")
PY
}

assert_physical_delete_path() {
  "$(python_bin)" - "$1" "$2" <<'PY'
import os
import pathlib
import stat
import sys

target = pathlib.Path(os.path.abspath(sys.argv[1]))
label = sys.argv[2]
cursor = pathlib.Path(target.anchor)
for part in target.parts[1:]:
    cursor = cursor / part
    try:
        mode = os.lstat(cursor).st_mode
    except FileNotFoundError:
        break
    if stat.S_ISLNK(mode):
        raise SystemExit(f"Refusing {label} through a symlinked path: {cursor}")
    if not stat.S_ISDIR(mode):
        raise SystemExit(f"Refusing non-directory {label}: {cursor}")
PY
}

remove_default_shim_if_it_points_here() {
  SHIM_PATH="$HOME/.local/bin/image-prompt-library"
  if [ -f "$SHIM_PATH" ] && grep -F "$APP_PREFIX/app/current" "$SHIM_PATH" >/dev/null 2>&1; then
    rm -f "$SHIM_PATH"
    echo "Removed command shim: $SHIM_PATH"
  fi
}

uninstall_app() {
  DELETE_LIBRARY=0
  ASSUME_YES=0
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --delete-library)
        DELETE_LIBRARY=1
        shift
        ;;
      --yes)
        ASSUME_YES=1
        shift
        ;;
      *)
        echo "Unknown uninstall option: $1" >&2
        exit 2
        ;;
    esac
  done

  load_env
  LIBRARY_TO_DELETE="$IMAGE_PROMPT_LIBRARY_PATH"

  if [ "$APP_PREFIX_USED_ALIAS" -eq 1 ]; then
    echo "Refusing uninstall through a symlinked install prefix; use the physical install path." >&2
    exit 2
  fi
  if [ ! -d "$APP_PREFIX" ]; then
    echo "Refusing uninstall from a missing install prefix: $APP_PREFIX" >&2
    exit 2
  fi
  refuse_unsafe_delete_target "$APP_PREFIX" "install prefix"
  assert_physical_delete_path "$APP_PREFIX" "install prefix"
  assert_disjoint_uninstall_paths "$APP_PREFIX" "$LIBRARY_TO_DELETE"
  if [ "$DELETE_LIBRARY" -eq 1 ]; then
    refuse_unsafe_delete_target "$LIBRARY_TO_DELETE" "private library"
    assert_physical_delete_path "$LIBRARY_TO_DELETE" "private library"
  fi

  if [ "$DELETE_LIBRARY" -eq 1 ] && [ "$ASSUME_YES" -ne 1 ]; then
    if [ -t 0 ]; then
      printf 'This will delete your private library at %s. Type DELETE to continue: ' "$LIBRARY_TO_DELETE" >&2
      read -r CONFIRMATION
      if [ "$CONFIRMATION" != "DELETE" ]; then
        echo "Uninstall cancelled." >&2
        exit 1
      fi
    else
      echo "Refusing to delete the private library without --yes in a non-interactive shell." >&2
      exit 2
    fi
  fi

  remove_default_shim_if_it_points_here
  rm -rf "$APP_PREFIX"
  echo "App files removed: $APP_PREFIX"

  if [ "$DELETE_LIBRARY" -eq 1 ]; then
    rm -rf "$LIBRARY_TO_DELETE"
    echo "Private library deleted: $LIBRARY_TO_DELETE"
  else
    echo "Private library kept: $LIBRARY_TO_DELETE"
  fi
}

service_usage() {
  cat <<'USAGE'
Usage: image-prompt-library service <command>

Commands:
  install [--host H] [--port P] [--label L] [--replace]
  status [--label L]
  start [--label L]
  stop [--label L]
  restart [--label L]
  uninstall [--label L]
USAGE
}

service_label_default() {
  if [ -n "${IMAGE_PROMPT_LIBRARY_SERVICE_LABEL:-}" ]; then
    printf '%s\n' "$IMAGE_PROMPT_LIBRARY_SERVICE_LABEL"
    return
  fi

  /usr/bin/env python3 - "$APP_PREFIX" "com.eddietyp.image-prompt-library" <<'PY'
import os
import plistlib
import sys
from pathlib import Path

app_prefix = str(Path(sys.argv[1]).expanduser())
default_label = sys.argv[2]
home = Path(os.environ.get("HOME", str(Path.home()))).expanduser()
launch_agents = home / "Library" / "LaunchAgents"
needle = f"{app_prefix}/app/current/scripts/appctl.sh"
candidates = []
fallback_candidates = []
if launch_agents.is_dir():
    for plist_path in launch_agents.glob("*image-prompt-library*.plist"):
        try:
            payload = plistlib.loads(plist_path.read_bytes())
        except Exception:
            continue
        label = str(payload.get("Label") or "")
        if not label:
            continue
        env = payload.get("EnvironmentVariables") or {}
        args = "\n".join(str(arg) for arg in (payload.get("ProgramArguments") or []))
        mtime = plist_path.stat().st_mtime
        matches_prefix = str(env.get("IMAGE_PROMPT_LIBRARY_PREFIX") or "") == app_prefix
        matches_program = needle in args
        if matches_prefix or matches_program:
            candidates.append((mtime, label))
        else:
            fallback_candidates.append((mtime, label))
if candidates:
    candidates.sort(reverse=True)
    print(candidates[0][1])
elif len(fallback_candidates) == 1:
    print(fallback_candidates[0][1])
else:
    print(default_label)
PY
}

service_domain() {
  printf 'gui/%s\n' "$(id -u)"
}

require_macos_service_tools() {
  if ! command -v launchctl >/dev/null 2>&1; then
    echo "macOS launchctl is required for image-prompt-library service commands." >&2
    exit 2
  fi
}

parse_label_option() {
  SERVICE_LABEL="$(service_label_default)"
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --label)
        if [ "$#" -lt 2 ] || [ -z "${2:-}" ]; then
          echo "Missing value for --label" >&2
          exit 2
        fi
        SERVICE_LABEL="$2"
        shift 2
        ;;
      *)
        echo "Unknown service option: $1" >&2
        service_usage >&2
        exit 2
        ;;
    esac
  done
}

service_plist_path() {
  LABEL="$1"
  printf '%s\n' "${IMAGE_PROMPT_LIBRARY_SERVICE_PLIST:-$HOME/Library/LaunchAgents/$LABEL.plist}"
}

service_wait_unloaded() {
  DOMAIN="$1"
  LABEL="$2"
  ATTEMPT=0
  while [ "$ATTEMPT" -lt 20 ]; do
    if ! launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
      return 0
    fi
    ATTEMPT=$((ATTEMPT + 1))
    sleep 0.25
  done
}

service_bootstrap() {
  DOMAIN="$1"
  LABEL="$2"
  PLIST="$3"
  if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
    return 0
  fi
  ATTEMPT=0
  while [ "$ATTEMPT" -lt 20 ]; do
    if launchctl bootstrap "$DOMAIN" "$PLIST" >/dev/null 2>&1; then
      return 0
    fi
    if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
      return 0
    fi
    ATTEMPT=$((ATTEMPT + 1))
    sleep 0.5
  done
  launchctl bootstrap "$DOMAIN" "$PLIST"
}

service_install() {
  SERVICE_HOST="127.0.0.1"
  SERVICE_PORT="8000"
  SERVICE_LABEL="$(service_label_default)"
  SERVICE_REPLACE=0
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --host)
        if [ "$#" -lt 2 ] || [ -z "${2:-}" ]; then
          echo "Missing value for --host" >&2
          exit 2
        fi
        SERVICE_HOST="$2"
        shift 2
        ;;
      --port)
        if [ "$#" -lt 2 ] || [ -z "${2:-}" ]; then
          echo "Missing value for --port" >&2
          exit 2
        fi
        SERVICE_PORT="$2"
        shift 2
        ;;
      --label)
        if [ "$#" -lt 2 ] || [ -z "${2:-}" ]; then
          echo "Missing value for --label" >&2
          exit 2
        fi
        SERVICE_LABEL="$2"
        shift 2
        ;;
      --replace)
        SERVICE_REPLACE=1
        shift
        ;;
      *)
        echo "Unknown service install option: $1" >&2
        service_usage >&2
        exit 2
        ;;
    esac
  done
  require_macos_service_tools
  SERVICE_PLIST="$(service_plist_path "$SERVICE_LABEL")"
  if [ -e "$SERVICE_PLIST" ] && [ "$SERVICE_REPLACE" -ne 1 ]; then
    echo "Service plist already exists: $SERVICE_PLIST" >&2
    echo "Use --replace to overwrite and restart this launchd service." >&2
    exit 2
  fi
  mkdir -p "$(dirname "$SERVICE_PLIST")" "$HOME/Library/Logs"
  /usr/bin/env python3 - "$SERVICE_PLIST" "$SERVICE_LABEL" "$APP_PREFIX/app/current/scripts/appctl.sh" "$APP_PREFIX" "$SERVICE_HOST" "$SERVICE_PORT" "$HOME" <<'PY'
import plistlib
import sys
from pathlib import Path

plist_path = Path(sys.argv[1])
label = sys.argv[2]
appctl = sys.argv[3]
prefix = sys.argv[4]
host = sys.argv[5]
port = sys.argv[6]
home = sys.argv[7]
payload = {
    "Label": label,
    "ProgramArguments": [appctl, "start", "--host", host, "--port", port],
    "EnvironmentVariables": {
        "HOME": home,
        "IMAGE_PROMPT_LIBRARY_PREFIX": prefix,
        "IMAGE_PROMPT_LIBRARY_SERVICE_LABEL": label,
    },
    "WorkingDirectory": home,
    "RunAtLoad": True,
    "KeepAlive": True,
    "StandardOutPath": str(Path(home) / "Library" / "Logs" / "image-prompt-library.out.log"),
    "StandardErrorPath": str(Path(home) / "Library" / "Logs" / "image-prompt-library.err.log"),
}
plist_path.write_bytes(plistlib.dumps(payload))
PY
  if command -v plutil >/dev/null 2>&1; then
    plutil -lint "$SERVICE_PLIST" >/dev/null
  fi
  DOMAIN="$(service_domain)"
  if [ "$SERVICE_REPLACE" -eq 1 ]; then
    launchctl bootout "$DOMAIN/$SERVICE_LABEL" >/dev/null 2>&1 || true
    service_wait_unloaded "$DOMAIN" "$SERVICE_LABEL"
  fi
  service_bootstrap "$DOMAIN" "$SERVICE_LABEL" "$SERVICE_PLIST"
  launchctl enable "$DOMAIN/$SERVICE_LABEL"
  launchctl kickstart -k "$DOMAIN/$SERVICE_LABEL"
  echo "Installed service: $SERVICE_LABEL"
  echo "Plist: $SERVICE_PLIST"
  echo "URL: http://127.0.0.1:$SERVICE_PORT/"
}

service_status() {
  parse_label_option "$@"
  require_macos_service_tools
  launchctl print "$(service_domain)/$SERVICE_LABEL"
}

service_start() {
  parse_label_option "$@"
  require_macos_service_tools
  SERVICE_PLIST="$(service_plist_path "$SERVICE_LABEL")"
  if [ ! -f "$SERVICE_PLIST" ]; then
    echo "Service plist not found: $SERVICE_PLIST" >&2
    echo "Run image-prompt-library service install first." >&2
    exit 1
  fi
  DOMAIN="$(service_domain)"
  service_bootstrap "$DOMAIN" "$SERVICE_LABEL" "$SERVICE_PLIST"
  launchctl enable "$DOMAIN/$SERVICE_LABEL"
  launchctl kickstart -k "$DOMAIN/$SERVICE_LABEL"
}

service_stop() {
  parse_label_option "$@"
  require_macos_service_tools
  launchctl bootout "$(service_domain)/$SERVICE_LABEL"
}

service_restart() {
  parse_label_option "$@"
  require_macos_service_tools
  SERVICE_PLIST="$(service_plist_path "$SERVICE_LABEL")"
  if [ ! -f "$SERVICE_PLIST" ]; then
    echo "Service plist not found: $SERVICE_PLIST" >&2
    echo "Run image-prompt-library service install first." >&2
    exit 1
  fi
  DOMAIN="$(service_domain)"
  launchctl bootout "$DOMAIN/$SERVICE_LABEL" >/dev/null 2>&1 || true
  service_wait_unloaded "$DOMAIN" "$SERVICE_LABEL"
  service_bootstrap "$DOMAIN" "$SERVICE_LABEL" "$SERVICE_PLIST"
  launchctl enable "$DOMAIN/$SERVICE_LABEL"
  launchctl kickstart -k "$DOMAIN/$SERVICE_LABEL"
}

service_uninstall() {
  parse_label_option "$@"
  require_macos_service_tools
  launchctl bootout "$(service_domain)/$SERVICE_LABEL" >/dev/null 2>&1 || true
  SERVICE_PLIST="$(service_plist_path "$SERVICE_LABEL")"
  rm -f "$SERVICE_PLIST"
  echo "Removed service: $SERVICE_LABEL"
}

service_app() {
  SUBCOMMAND="${1:-}"
  if [ -n "$SUBCOMMAND" ]; then shift; fi
  case "$SUBCOMMAND" in
    install) service_install "$@" ;;
    status) service_status "$@" ;;
    start) service_start "$@" ;;
    stop) service_stop "$@" ;;
    restart) service_restart "$@" ;;
    uninstall) service_uninstall "$@" ;;
    -h|--help|help|"") service_usage ;;
    *) echo "Unknown service command: $SUBCOMMAND" >&2; service_usage >&2; exit 2 ;;
  esac
}

usage() {
  cat <<'USAGE'
Usage: image-prompt-library <command>

Commands:
  start [--host H] [--port P]
                        Start the local app server
  doctor                Print local diagnostics with private values omitted
  status                Print short local app status
  service <command>     Manage the macOS launchd user service
  version               Print installed app version
  update [--version V]  Install latest or selected release version
  rollback              Switch current app symlink back to app/previous
  backup [options]      Create a validated portable backup while the app is stopped
  verify-backup ARCHIVE Validate a portable backup without changing the library
  restore ARCHIVE       Restore a validated backup; preserves the old library
  sample-data LANG [PKG] Import optional sample data into the private library
  uninstall [--delete-library] [--yes]
                        Remove installed app files; keeps private library by default
USAGE
}

COMMAND="${1:-}"
if [ -n "$COMMAND" ]; then shift; fi
case "$COMMAND" in
  start) start_app "$@" ;;
  doctor) doctor_app "$@" ;;
  status) status_app "$@" ;;
  service) service_app "$@" ;;
  version) print_version ;;
  update) update_app "$@" ;;
  rollback) rollback_app "$@" ;;
  backup) library_archive_app backup "$@" ;;
  verify-backup) library_archive_app verify-backup "$@" ;;
  restore) library_archive_app restore "$@" ;;
  sample-data) sample_data "$@" ;;
  uninstall) uninstall_app "$@" ;;
  -h|--help|help|"") usage ;;
  *) echo "Unknown command: $COMMAND" >&2; usage >&2; exit 2 ;;
esac
