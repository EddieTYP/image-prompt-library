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
  if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
  fi
  export IMAGE_PROMPT_LIBRARY_PATH="${IMAGE_PROMPT_LIBRARY_PATH:-$HOME/ImagePromptLibrary}"
  export BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
  export BACKEND_PORT="${BACKEND_PORT:-8000}"
}

print_version() {
  if [ -f "$VERSION_FILE" ]; then
    printf '%s\n' "$(tr -d '\n\r' < "$VERSION_FILE")"
  else
    basename "$APP_ROOT"
  fi
}

start_app() {
  load_env
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

usage() {
  cat <<'USAGE'
Usage: image-prompt-library <command>

Commands:
  start                 Start the local app server
  version               Print installed app version
  update [--version V]  Install latest or selected release version
  rollback              Switch current app symlink back to app/previous
  sample-data LANG [PKG] Import optional sample data into the private library
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
  -h|--help|help|"") usage ;;
  *) echo "Unknown command: $COMMAND" >&2; usage >&2; exit 2 ;;
esac
