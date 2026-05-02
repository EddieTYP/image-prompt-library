#!/usr/bin/env bash
set -euo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]}"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
APP_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VERSION_FILE="$APP_ROOT/VERSION"
APP_PREFIX="${IMAGE_PROMPT_LIBRARY_PREFIX:-}"
if [ -z "$APP_PREFIX" ]; then
  APP_PREFIX="$(cd "$APP_ROOT/../.." && pwd)"
fi
ENV_FILE="$APP_PREFIX/.env"
# Default private library path: ~/ImagePromptLibrary

load_env() {
  INCOMING_IMAGE_PROMPT_LIBRARY_PATH="${IMAGE_PROMPT_LIBRARY_PATH-}"
  INCOMING_BACKEND_HOST="${BACKEND_HOST-}"
  INCOMING_BACKEND_PORT="${BACKEND_PORT-}"
  if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
  fi
  export IMAGE_PROMPT_LIBRARY_PATH="${INCOMING_IMAGE_PROMPT_LIBRARY_PATH:-${IMAGE_PROMPT_LIBRARY_PATH:-$HOME/ImagePromptLibrary}}"
  export BACKEND_HOST="${INCOMING_BACKEND_HOST:-${BACKEND_HOST:-127.0.0.1}}"
  export BACKEND_PORT="${INCOMING_BACKEND_PORT:-${BACKEND_PORT:-8000}}"
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
print(f"Version: {version}")
print(f"Install prefix: {app_prefix}")
print(f"App root: {app_root}")
print(f"Library path: {library_path}")
print(f"Backend: {backend_host}:{backend_port}")
print(f"Platform: {platform.system()} {platform.release()}")

try:
    library_path.mkdir(parents=True, exist_ok=True)
    db_path = library_path / "db.sqlite"
    if not db_path.exists():
        from backend.db import init_db
        init_db(library_path)
    with sqlite3.connect(db_path) as conn:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        item_count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    print(f"Database path: {db_path}")
    print(f"Database integrity: {integrity}")
    print(f"Item count: {item_count}")
except Exception as exc:
    print(f"Database integrity: error ({type(exc).__name__})")

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
    print(f"Generation provider: {PROVIDER_ID} state={state} configured={configured}")
except Exception as exc:
    print(f"Generation provider: unavailable ({type(exc).__name__})")

if platform.system() == "Darwin":
    label = os.environ.get("IMAGE_PROMPT_LIBRARY_SERVICE_LABEL", "com.eddietyp.image-prompt-library")
    service_ref = f"gui/{os.getuid()}/{label}"
    try:
        result = subprocess.run(["launchctl", "print", service_ref], text=True, capture_output=True, timeout=5)
        state = "running" if "state = running" in result.stdout else "not loaded"
    except Exception:
        state = "unknown"
    print(f"macOS service: {label} {state}")
    print(f"macOS service plist: {Path.home() / 'Library' / 'LaunchAgents' / (label + '.plist')}")
    print(f"Logs: {Path.home() / 'Library' / 'Logs' / 'image-prompt-library.out.log'}")
else:
    print("macOS service: not applicable")
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

rollback_app() {
  CURRENT_LINK="$APP_PREFIX/app/current"
  PREVIOUS_LINK="$APP_PREFIX/app/previous"
  if [ ! -L "$PREVIOUS_LINK" ]; then
    echo "No previous version is available for rollback." >&2
    exit 1
  fi
  PREVIOUS_TARGET="$(readlink "$PREVIOUS_LINK")"
  if [ ! -d "$PREVIOUS_TARGET" ]; then
    echo "Previous version directory is missing: $PREVIOUS_TARGET" >&2
    exit 1
  fi
  CURRENT_TARGET=""
  if [ -L "$CURRENT_LINK" ]; then
    CURRENT_TARGET="$(readlink "$CURRENT_LINK")"
  fi
  ln -sfn "$PREVIOUS_TARGET" "$CURRENT_LINK"
  if [ -n "$CURRENT_TARGET" ] && [ -d "$CURRENT_TARGET" ]; then
    ln -sfn "$CURRENT_TARGET" "$PREVIOUS_LINK"
  fi
  echo "Rolled back to $(basename "$PREVIOUS_TARGET")."
}

sample_data() {
  load_env
  bash "$SCRIPT_DIR/install-sample-data.sh" "$@"
}

refuse_unsafe_delete_target() {
  TARGET="$1"
  LABEL="$2"
  case "$TARGET" in
    ""|"/"|"$HOME"|"$HOME/"|"."|"..")
      echo "Refusing unsafe $LABEL path: $TARGET" >&2
      exit 2
      ;;
  esac
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

  refuse_unsafe_delete_target "$APP_PREFIX" "install prefix"
  remove_default_shim_if_it_points_here
  rm -rf "$APP_PREFIX"
  echo "App files removed: $APP_PREFIX"

  if [ "$DELETE_LIBRARY" -eq 1 ]; then
    refuse_unsafe_delete_target "$LIBRARY_TO_DELETE" "private library"
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
  /usr/bin/env python3 - "$SERVICE_PLIST" "$SERVICE_LABEL" "$SCRIPT_DIR/appctl.sh" "$APP_PREFIX" "$SERVICE_HOST" "$SERVICE_PORT" "$HOME" <<'PY'
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
  service <command>     Manage the macOS launchd user service
  version               Print installed app version
  update [--version V]  Install latest or selected release version
  rollback              Switch current app symlink back to app/previous
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
  service) service_app "$@" ;;
  version) print_version ;;
  update) update_app "$@" ;;
  rollback) rollback_app "$@" ;;
  sample-data) sample_data "$@" ;;
  uninstall) uninstall_app "$@" ;;
  -h|--help|help|"") usage ;;
  *) echo "Unknown command: $COMMAND" >&2; usage >&2; exit 2 ;;
esac
