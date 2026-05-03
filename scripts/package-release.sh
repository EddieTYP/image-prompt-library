#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:-}"
SKIP_BUILD=0
if [ -z "$VERSION" ]; then
  echo "Usage: scripts/package-release.sh <version> [--skip-build]" >&2
  exit 2
fi
shift || true
while [ "$#" -gt 0 ]; do
  case "$1" in
    --skip-build) SKIP_BUILD=1; shift ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

cd "$(dirname "$0")/.."

if [ "$SKIP_BUILD" -eq 0 ]; then
  VITE_APP_VERSION="$VERSION" npm run build
elif [ ! -f frontend/dist/index.html ]; then
  mkdir -p frontend/dist/assets
  printf '<!doctype html><html><body><div id="root"></div><script type="module" src="/assets/test.js"></script></body></html>\n' > frontend/dist/index.html
elif grep -q '/image-prompt-library/assets/' frontend/dist/index.html; then
  echo "Existing frontend/dist is a GitHub Pages demo build; rebuilding local app assets for release." >&2
  VITE_APP_VERSION="$VERSION" npm run build
fi

RELEASE_DIR="dist-release"
STAGING_ROOT="$RELEASE_DIR/staging"
STAGING="$STAGING_ROOT/image-prompt-library-$VERSION"
ARTIFACT="image-prompt-library-$VERSION.tar.gz"
MANIFEST="image-prompt-library-$VERSION.manifest.json"
CHECKSUM_FILE="$ARTIFACT.sha256"

rm -rf "$STAGING_ROOT"
mkdir -p "$STAGING"
mkdir -p "$RELEASE_DIR"

copy_path() {
  SRC="$1"
  DEST="$STAGING/$1"
  if [ -d "$SRC" ]; then
    mkdir -p "$(dirname "$DEST")"
    cp -R "$SRC" "$DEST"
  elif [ -f "$SRC" ]; then
    mkdir -p "$(dirname "$DEST")"
    cp "$SRC" "$DEST"
  fi
}

for path in \
  backend \
  scripts/appctl.sh \
  scripts/install.sh \
  scripts/install-sample-data.sh \
  scripts/setup-runtime.sh \
  sample-data/manifests \
  pyproject.toml \
  README.md \
  LICENSE \
  NOTICE \
  SECURITY.md; do
  copy_path "$path"
done

mkdir -p "$STAGING/frontend"
cp -R frontend/dist "$STAGING/frontend/dist"

printf '%s\n' "$VERSION" > "$STAGING/VERSION"

# Explicitly keep private/runtime/generated paths out of release artifacts:
# .env .local-work library node_modules .venv backups
find "$STAGING" \( \
  -name '.env' -o \
  -name '.local-work' -o \
  -name 'library' -o \
  -name 'node_modules' -o \
  -name '.venv' -o \
  -name 'backups' -o \
  -name '__pycache__' \
\) -prune -exec rm -rf {} +
find "$STAGING" -name '*.pyc' -type f -delete

(
  cd "$STAGING"
  find . -type f -exec chmod 0644 {} +
  find . -type d -exec chmod 0755 {} +
  chmod 0755 scripts/*.sh
)

rm -f "$RELEASE_DIR/$ARTIFACT" "$RELEASE_DIR/$CHECKSUM_FILE" "$RELEASE_DIR/$MANIFEST"
(
  cd "$STAGING"
  tar -czf "../../$ARTIFACT" .
)

if command -v sha256sum >/dev/null 2>&1; then
  SHA256="$(sha256sum "$RELEASE_DIR/$ARTIFACT" | awk '{print $1}')"
else
  SHA256="$(shasum -a 256 "$RELEASE_DIR/$ARTIFACT" | awk '{print $1}')"
fi
printf '%s  %s\n' "$SHA256" "$ARTIFACT" > "$RELEASE_DIR/$CHECKSUM_FILE"

python3 - "$VERSION" "$ARTIFACT" "$SHA256" "$RELEASE_DIR/$MANIFEST" <<'PY'
import json
import sys
from datetime import datetime, timezone
version, artifact, sha256, manifest_path = sys.argv[1:]
manifest = {
    "name": "image-prompt-library",
    "version": version,
    "schema_version": 1,
    "artifact": artifact,
    "sha256": sha256,
    "python": ">=3.10",
    "node_required_for_runtime": False,
    "built_frontend": True,
    "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
}
with open(manifest_path, "w", encoding="utf-8") as handle:
    json.dump(manifest, handle, indent=2)
    handle.write("\n")
PY

rm -rf "$STAGING_ROOT"
echo "Created $RELEASE_DIR/$ARTIFACT"
echo "Created $RELEASE_DIR/$CHECKSUM_FILE"
echo "Created $RELEASE_DIR/$MANIFEST"
