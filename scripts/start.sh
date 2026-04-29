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

choose_python() {
  if [ -n "${PYTHON:-}" ]; then
    printf '%s\n' "$PYTHON"
    return 0
  fi
  for candidate in python3.13 python3.12 python3.11 python3.10 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
    then
      command -v "$candidate"
      return 0
    fi
  done
  return 1
}

PYTHON_BIN="${PYTHON:-}"
if [ -x .venv/bin/python ]; then
  PYTHON_BIN=.venv/bin/python
elif [ -z "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(choose_python || true)"
fi

if [ -z "$PYTHON_BIN" ]; then
  echo "Image Prompt Library requires Python 3.10 or newer." >&2
  echo "Install Python 3.10+ and run ./scripts/setup.sh before ./scripts/start.sh." >&2
  exit 1
fi
"$PYTHON_BIN" - <<'PY'
import importlib.util
import sys

if sys.version_info < (3, 10):
    version = ".".join(str(part) for part in sys.version_info[:3])
    raise SystemExit(
        f"Image Prompt Library requires Python 3.10 or newer; found Python {version}. "
        "Install Python 3.10+ and run ./scripts/setup.sh before ./scripts/start.sh."
    )
if importlib.util.find_spec("uvicorn") is None:
    raise SystemExit(
        "Missing Python dependencies. Run ./scripts/setup.sh before ./scripts/start.sh."
    )
PY

npm run build
exec "$PYTHON_BIN" -m uvicorn backend.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT"
