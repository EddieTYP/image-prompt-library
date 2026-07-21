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

PYTHON_BIN="${PYTHON:-}"

if [ -z "$PYTHON_BIN" ]; then
  if [ -x .venv/bin/python ]; then
    PYTHON_BIN=.venv/bin/python
  else
    PYTHON_BIN=python3
  fi
fi

exec "$PYTHON_BIN" "$SCRIPT_DIR/library-archive.py" backup "$@"
