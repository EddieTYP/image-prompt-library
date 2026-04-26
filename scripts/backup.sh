#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

INCOMING_IMAGE_PROMPT_LIBRARY_PATH="${IMAGE_PROMPT_LIBRARY_PATH-}"
INCOMING_BACKUP_DIR="${BACKUP_DIR-}"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [ -n "$INCOMING_IMAGE_PROMPT_LIBRARY_PATH" ]; then IMAGE_PROMPT_LIBRARY_PATH="$INCOMING_IMAGE_PROMPT_LIBRARY_PATH"; fi
if [ -n "$INCOMING_BACKUP_DIR" ]; then BACKUP_DIR="$INCOMING_BACKUP_DIR"; fi

LIBRARY_PATH="${IMAGE_PROMPT_LIBRARY_PATH:-./library}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
ARCHIVE="${BACKUP_DIR%/}/image-prompt-library-${TIMESTAMP}.tar.gz"

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
