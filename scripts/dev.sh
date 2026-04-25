#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
trap 'kill 0' EXIT
PYTHON="${PYTHON:-python3}"
if [ -x .venv/bin/python ]; then PYTHON=.venv/bin/python; fi
"$PYTHON" -m uvicorn backend.main:app --reload --port 8787 &
npm run dev -- --host 127.0.0.1 --port 5177
