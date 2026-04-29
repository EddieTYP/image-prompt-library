#!/usr/bin/env bash
set -euo pipefail

VERSION="latest"
PREFIX="$HOME/.image-prompt-library"
LIBRARY_PATH="$HOME/ImagePromptLibrary"
CREATE_SHIM=1
REPO="EddieTYP/image-prompt-library"
RELEASE_BASE_URL="${IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL:-}"
SKIP_RUNTIME_SETUP="${IMAGE_PROMPT_LIBRARY_INSTALL_SKIP_RUNTIME_SETUP:-0}"

# Defaults shown for public docs/tests: ~/.image-prompt-library and ~/ImagePromptLibrary

usage() {
  cat <<'USAGE'
Usage: scripts/install.sh [options]

Options:
  --version <tag>        Install selected release tag; default: latest
  --prefix <path>        Install prefix; default: ~/.image-prompt-library
  --library-path <path>  Private library path; default: ~/ImagePromptLibrary
  --no-shim             Do not create ~/.local/bin/image-prompt-library
  -h, --help            Show help
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --version) VERSION="${2:-}"; shift 2 ;;
    --prefix) PREFIX="${2:-}"; shift 2 ;;
    --library-path) LIBRARY_PATH="${2:-}"; shift 2 ;;
    --no-shim) CREATE_SHIM=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [ -z "$VERSION" ] || [ -z "$PREFIX" ] || [ -z "$LIBRARY_PATH" ]; then
  echo "Missing required option value." >&2
  exit 2
fi

case "$PREFIX" in
  /|"$HOME")
    echo "Refusing unsafe install prefix: $PREFIX" >&2
    exit 2
    ;;
esac

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
  echo "Install Python 3.10+ and rerun with PYTHON=/path/to/python3.10 scripts/install.sh." >&2
  exit 1
fi
"$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 10):
    version = ".".join(str(part) for part in sys.version_info[:3])
    raise SystemExit(
        f"Image Prompt Library requires Python 3.10 or newer; found Python {version}. "
        "Install Python 3.10+ and rerun with PYTHON=/path/to/python3.10 scripts/install.sh."
    )
PY

mkdir -p "$PREFIX/app/downloads" "$PREFIX/app/versions" "$PREFIX/logs" "$LIBRARY_PATH"

python_download() {
  URL="$1"
  OUT="$2"
  "$PYTHON_BIN" - "$URL" "$OUT" <<'PY'
import pathlib
import sys
import urllib.request
url, out = sys.argv[1:]
path = pathlib.Path(out)
path.parent.mkdir(parents=True, exist_ok=True)
with urllib.request.urlopen(url) as response:
    path.write_bytes(response.read())
PY
}

resolve_latest_version() {
  "$PYTHON_BIN" - "$REPO" <<'PY'
import json
import sys
import urllib.request
repo = sys.argv[1]
url = f"https://api.github.com/repos/{repo}/releases?per_page=20"
with urllib.request.urlopen(url) as response:
    releases = json.load(response)
for release in releases:
    if release.get("draft"):
        continue
    tag = release.get("tag_name")
    asset_names = {asset.get("name") for asset in release.get("assets", [])}
    required = {
        f"image-prompt-library-{tag}.manifest.json",
        f"image-prompt-library-{tag}.tar.gz",
        f"image-prompt-library-{tag}.tar.gz.sha256",
    }
    if tag and required.issubset(asset_names):
        print(tag)
        break
else:
    raise SystemExit("Could not find a release with Image Prompt Library app installer assets.")
PY
}

if [ "$VERSION" = "latest" ]; then
  if [ -n "$RELEASE_BASE_URL" ]; then
    echo "--version is required when IMAGE_PROMPT_LIBRARY_RELEASE_BASE_URL points to a local artifact directory." >&2
    exit 2
  fi
  VERSION="$(resolve_latest_version)"
fi

ARTIFACT="image-prompt-library-$VERSION.tar.gz"
MANIFEST="image-prompt-library-$VERSION.manifest.json"
CHECKSUM_FILE="$ARTIFACT.sha256"
DOWNLOAD_DIR="$PREFIX/app/downloads/$VERSION"
INSTALL_DIR="$PREFIX/app/versions/$VERSION"
mkdir -p "$DOWNLOAD_DIR"

if [ -n "$RELEASE_BASE_URL" ]; then
  BASE="${RELEASE_BASE_URL%/}"
  MANIFEST_URL="$BASE/$MANIFEST"
  ARTIFACT_URL="$BASE/$ARTIFACT"
  CHECKSUM_URL="$BASE/$CHECKSUM_FILE"
else
  BASE="https://github.com/$REPO/releases/download/$VERSION"
  MANIFEST_URL="$BASE/$MANIFEST"
  ARTIFACT_URL="$BASE/$ARTIFACT"
  CHECKSUM_URL="$BASE/$CHECKSUM_FILE"
fi

python_download "$MANIFEST_URL" "$DOWNLOAD_DIR/$MANIFEST"
python_download "$ARTIFACT_URL" "$DOWNLOAD_DIR/$ARTIFACT"
python_download "$CHECKSUM_URL" "$DOWNLOAD_DIR/$CHECKSUM_FILE"

EXPECTED_SHA="$($PYTHON_BIN - "$DOWNLOAD_DIR/$MANIFEST" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    print(json.load(handle)["sha256"])
PY
)"
if command -v sha256sum >/dev/null 2>&1; then
  ACTUAL_SHA="$(sha256sum "$DOWNLOAD_DIR/$ARTIFACT" | awk '{print $1}')"
else
  ACTUAL_SHA="$(shasum -a 256 "$DOWNLOAD_DIR/$ARTIFACT" | awk '{print $1}')"
fi
if [ "$EXPECTED_SHA" != "$ACTUAL_SHA" ]; then
  echo "Checksum verification failed for $ARTIFACT" >&2
  exit 1
fi

rm -rf "$INSTALL_DIR.tmp"
mkdir -p "$INSTALL_DIR.tmp"
tar -xzf "$DOWNLOAD_DIR/$ARTIFACT" -C "$INSTALL_DIR.tmp"
if [ -d "$INSTALL_DIR" ]; then
  rm -rf "$INSTALL_DIR"
fi
mv "$INSTALL_DIR.tmp" "$INSTALL_DIR"

if [ "$SKIP_RUNTIME_SETUP" != "1" ]; then
  bash "$INSTALL_DIR/scripts/setup-runtime.sh"
fi

ENV_FILE="$PREFIX/.env"
if [ ! -f "$ENV_FILE" ]; then
  cat > "$ENV_FILE" <<EOF
IMAGE_PROMPT_LIBRARY_PATH=$LIBRARY_PATH
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000
BACKUP_DIR=$PREFIX/backups
EOF
fi

CURRENT_LINK="$PREFIX/app/current"
PREVIOUS_LINK="$PREFIX/app/previous"
if [ -L "$CURRENT_LINK" ]; then
  CURRENT_TARGET="$(readlink "$CURRENT_LINK")"
  if [ -n "$CURRENT_TARGET" ] && [ -d "$CURRENT_TARGET" ]; then
    ln -sfn "$CURRENT_TARGET" "$PREVIOUS_LINK"
  fi
fi
ln -sfn "$INSTALL_DIR" "$CURRENT_LINK"

if [ "$CREATE_SHIM" -eq 1 ]; then
  SHIM_DIR="$HOME/.local/bin"
  mkdir -p "$SHIM_DIR"
  cat > "$SHIM_DIR/image-prompt-library" <<EOF
#!/usr/bin/env bash
exec "$CURRENT_LINK/scripts/appctl.sh" "\$@"
EOF
  chmod 0755 "$SHIM_DIR/image-prompt-library"
fi

cat <<EOF
Image Prompt Library $VERSION installed.

Start the app:
  image-prompt-library start

Fallback command:
  $CURRENT_LINK/scripts/appctl.sh start

Local URL:
  http://127.0.0.1:8000/
EOF
