#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON_BIN="${PYTHON:-python3}"
"$PYTHON_BIN" - <<'PY'
import sys

if sys.version_info < (3, 10):
    version = ".".join(str(part) for part in sys.version_info[:3])
    raise SystemExit(
        f"Image Prompt Library requires Python 3.10 or newer; found Python {version}. "
        "Install Python 3.10+ and rerun with PYTHON=/path/to/python3.10 ./scripts/setup.sh."
    )
PY

if [ ! -x .venv/bin/python ]; then
  # Default equivalent: python3 -m venv .venv
  "$PYTHON_BIN" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
npm install

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

echo "Setup complete. Run ./scripts/dev.sh for development or ./scripts/start.sh for single-service local mode."
