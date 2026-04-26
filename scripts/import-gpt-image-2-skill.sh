#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [ "$#" -lt 1 ]; then
  cat >&2 <<'USAGE'
Usage: ./scripts/import-gpt-image-2-skill.sh /path/to/gpt_image_2_skill [library_path]

Import the optional public sample/demo source wuyoscar/gpt_image_2_skill into a
local Image Prompt Library data directory. Clone the source yourself first, e.g.:

  git clone https://github.com/wuyoscar/gpt_image_2_skill.git .local-work/gpt_image_2_skill
  IMAGE_PROMPT_LIBRARY_PATH=.local-work/demo-library \
    ./scripts/import-gpt-image-2-skill.sh .local-work/gpt_image_2_skill

Imported data remains local runtime data and should not be committed.
USAGE
  exit 2
fi

SOURCE_PATH="$1"
LIBRARY_PATH="${2:-${IMAGE_PROMPT_LIBRARY_PATH:-./library}}"

PYTHON_BIN="${PYTHON:-python3}"
if [ -x .venv/bin/python ]; then
  PYTHON_BIN=.venv/bin/python
fi

exec "$PYTHON_BIN" -m backend.services.import_gpt_image_2_skill \
  --source "$SOURCE_PATH" \
  --library "$LIBRARY_PATH"
