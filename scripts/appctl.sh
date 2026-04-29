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
  PYTHON_BIN="${PYTHON:-python3}"
  if [ -x "$APP_ROOT/.venv/bin/python" ]; then
    PYTHON_BIN="$APP_ROOT/.venv/bin/python"
  fi
  cd "$APP_ROOT"
  exec "$PYTHON_BIN" -m uvicorn backend.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT"
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
  bash "$SCRIPT_DIR/install.sh" --prefix "$APP_PREFIX" --version "$VERSION_ARG" --no-shim
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

usage() {
  cat <<'USAGE'
Usage: image-prompt-library <command>

Commands:
  start [--host H] [--port P]
                        Start the local app server
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
  version) print_version ;;
  update) update_app "$@" ;;
  rollback) rollback_app "$@" ;;
  sample-data) sample_data "$@" ;;
  uninstall) uninstall_app "$@" ;;
  -h|--help|help|"") usage ;;
  *) echo "Unknown command: $COMMAND" >&2; usage >&2; exit 2 ;;
esac
