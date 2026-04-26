#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

INCOMING_IMAGE_PROMPT_LIBRARY_PATH="${IMAGE_PROMPT_LIBRARY_PATH-}"
INCOMING_BACKEND_HOST="${BACKEND_HOST-}"
INCOMING_BACKEND_PORT="${BACKEND_PORT-}"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [ -n "$INCOMING_IMAGE_PROMPT_LIBRARY_PATH" ]; then IMAGE_PROMPT_LIBRARY_PATH="$INCOMING_IMAGE_PROMPT_LIBRARY_PATH"; fi
if [ -n "$INCOMING_BACKEND_HOST" ]; then BACKEND_HOST="$INCOMING_BACKEND_HOST"; fi
if [ -n "$INCOMING_BACKEND_PORT" ]; then BACKEND_PORT="$INCOMING_BACKEND_PORT"; fi

export IMAGE_PROMPT_LIBRARY_PATH="${IMAGE_PROMPT_LIBRARY_PATH:-./library}"
export BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
export BACKEND_PORT="${BACKEND_PORT:-8000}"

PYTHON_BIN="${PYTHON:-python3}"
if [ -x .venv/bin/python ]; then
  PYTHON_BIN=.venv/bin/python
fi

npm run build
exec "$PYTHON_BIN" -m uvicorn backend.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT"
