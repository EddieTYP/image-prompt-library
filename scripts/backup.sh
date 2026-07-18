#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$SCRIPT_DIR/.."
source "$SCRIPT_DIR/load-env.sh"

INCOMING_IMAGE_PROMPT_LIBRARY_PATH="${IMAGE_PROMPT_LIBRARY_PATH-}"
INCOMING_BACKUP_DIR="${BACKUP_DIR-}"

image_prompt_library_load_env_file .env

if [ -n "$INCOMING_IMAGE_PROMPT_LIBRARY_PATH" ]; then IMAGE_PROMPT_LIBRARY_PATH="$INCOMING_IMAGE_PROMPT_LIBRARY_PATH"; fi
if [ -n "$INCOMING_BACKUP_DIR" ]; then BACKUP_DIR="$INCOMING_BACKUP_DIR"; fi

LIBRARY_PATH="${IMAGE_PROMPT_LIBRARY_PATH:-./library}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
ARCHIVE="${BACKUP_DIR%/}/image-prompt-library-${TIMESTAMP}.tar.gz"
PYTHON_BIN="${PYTHON:-}"

if [ -z "$PYTHON_BIN" ]; then
  if [ -x .venv/bin/python ]; then
    PYTHON_BIN=.venv/bin/python
  else
    PYTHON_BIN=python3
  fi
fi

"$PYTHON_BIN" - "$LIBRARY_PATH" <<'PY'
import sys

from backend.config import validate_app_owned_paths

try:
    validate_app_owned_paths(sys.argv[1])
except ValueError as exc:
    print(exc, file=sys.stderr)
    raise SystemExit(2)
PY

if [ ! -f "$LIBRARY_PATH/db.sqlite" ]; then
  echo "No database found at $LIBRARY_PATH/db.sqlite. Start the app once before backing up." >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"
# The default backup payload is library/db.sqlite, library/originals, library/thumbs, and library/previews.
tar -czf "$ARCHIVE" \
  "$LIBRARY_PATH/db.sqlite" \
  "$LIBRARY_PATH/originals" \
  "$LIBRARY_PATH/thumbs" \
  "$LIBRARY_PATH/previews"

echo "Backup written to $ARCHIVE"
