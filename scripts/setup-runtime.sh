#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON_BIN=""

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

PYTHON_BIN="$(choose_python || true)"
if [ -z "$PYTHON_BIN" ]; then
  echo "Image Prompt Library requires Python 3.10 or newer." >&2
  echo "Install Python 3.10+ and rerun with PYTHON=/path/to/python3.10 image-prompt-library update." >&2
  exit 1
fi
"$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 10):
    version = ".".join(str(part) for part in sys.version_info[:3])
    raise SystemExit(
        f"Image Prompt Library requires Python 3.10 or newer; found Python {version}. "
        "Install Python 3.10+ and rerun with PYTHON=/path/to/python3.10 image-prompt-library update."
    )
PY

if [ ! -x .venv/bin/python ]; then
  "$PYTHON_BIN" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .

echo "Runtime setup complete."
