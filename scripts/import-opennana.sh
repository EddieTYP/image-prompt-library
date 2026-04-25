#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-python3}"
if [ -x .venv/bin/python ]; then PYTHON=.venv/bin/python; fi
"$PYTHON" -m backend.services.import_opennana --source /Users/edwardtsoi/hermes-agent/.local-work/data/opennana-chatgpt-gallery/data/gallery.json --library ./library
