#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-python3}"
if [ -x .venv/bin/python ]; then PYTHON=.venv/bin/python; fi

if [ $# -lt 1 ]; then
  cat >&2 <<'USAGE'
Usage: ./scripts/import-opennana.sh /path/to/gallery.json [library-path]

OpenNana import is an optional adapter for a local OpenNana gallery JSON export.
It is not a universal webpage scraper and it does not download from opennana.com directly.
USAGE
  exit 2
fi

SOURCE_PATH="$1"
LIBRARY_PATH="${2:-${IMAGE_PROMPT_LIBRARY_PATH:-./library}}"

"$PYTHON" -m backend.services.import_opennana --source "$SOURCE_PATH" --library "$LIBRARY_PATH"
