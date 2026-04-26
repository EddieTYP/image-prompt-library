#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

INCOMING_IMAGE_PROMPT_LIBRARY_PATH="${IMAGE_PROMPT_LIBRARY_PATH-}"
INCOMING_BACKEND_HOST="${BACKEND_HOST-}"
INCOMING_BACKEND_PORT="${BACKEND_PORT-}"
INCOMING_FRONTEND_PORT="${FRONTEND_PORT-}"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [ -n "$INCOMING_IMAGE_PROMPT_LIBRARY_PATH" ]; then IMAGE_PROMPT_LIBRARY_PATH="$INCOMING_IMAGE_PROMPT_LIBRARY_PATH"; fi
if [ -n "$INCOMING_BACKEND_HOST" ]; then BACKEND_HOST="$INCOMING_BACKEND_HOST"; fi
if [ -n "$INCOMING_BACKEND_PORT" ]; then BACKEND_PORT="$INCOMING_BACKEND_PORT"; fi
if [ -n "$INCOMING_FRONTEND_PORT" ]; then FRONTEND_PORT="$INCOMING_FRONTEND_PORT"; fi

export IMAGE_PROMPT_LIBRARY_PATH="${IMAGE_PROMPT_LIBRARY_PATH:-./library}"
export BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
export BACKEND_PORT="${BACKEND_PORT:-8000}"
export FRONTEND_PORT="${FRONTEND_PORT:-5177}"

trap 'kill 0' EXIT
PYTHON="${PYTHON:-python3}"
if [ -x .venv/bin/python ]; then PYTHON=.venv/bin/python; fi
"$PYTHON" -m uvicorn backend.main:app --reload --host "$BACKEND_HOST" --port "$BACKEND_PORT" &
npm run dev -- --host 127.0.0.1 --port "$FRONTEND_PORT"
