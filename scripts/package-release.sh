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

VERSION="$(python3 - "$VERSION" <<'PY'
import runpy
import sys
module = runpy.run_path("scripts/verify-release-assets.py")
try:
    print(module["normalize_version"](sys.argv[1]))
except module["VerificationError"] as exc:
    raise SystemExit(str(exc))
PY
)"
SOURCE_SHA="${IMAGE_PROMPT_LIBRARY_SOURCE_SHA:-}"
if [ -z "$SOURCE_SHA" ]; then
  if ! git rev-parse --verify HEAD >/dev/null 2>&1; then
    echo "Set IMAGE_PROMPT_LIBRARY_SOURCE_SHA for a controlled source snapshot." >&2
    exit 2
  fi
  DIRTY_SOURCE="$(git status --porcelain --untracked-files=normal -- \
    backend frontend package.json package-lock.json pyproject.toml vite.config.ts tsconfig.json \
    sample-data/manifests scripts README.md LICENSE NOTICE SECURITY.md)"
  if [ -n "$DIRTY_SOURCE" ]; then
    echo "Packaged source inputs are dirty; commit them or set IMAGE_PROMPT_LIBRARY_SOURCE_SHA only for a controlled source snapshot." >&2
    exit 2
  fi
  if [ "$SKIP_BUILD" -eq 1 ]; then
    echo "--skip-build requires IMAGE_PROMPT_LIBRARY_SOURCE_SHA for a controlled source snapshot." >&2
    exit 2
  fi
  SOURCE_SHA="$(git rev-parse HEAD)"
fi
if ! [[ "$SOURCE_SHA" =~ ^[0-9a-fA-F]{40}$ ]]; then
  echo "Release source SHA must be the exact 40-character commit id." >&2
  exit 2
fi

if [ "$SKIP_BUILD" -eq 0 ]; then
  VITE_APP_VERSION="$VERSION" npm run build
elif [ ! -f frontend/dist/index.html ]; then
  echo "frontend/dist is missing; building local app assets before packaging." >&2
  VITE_APP_VERSION="$VERSION" npm run build
elif grep -q '/image-prompt-library/assets/' frontend/dist/index.html; then
  echo "Existing frontend/dist is a GitHub Pages demo build; rebuilding local app assets for release." >&2
  VITE_APP_VERSION="$VERSION" npm run build
fi

RELEASE_DIR="${IMAGE_PROMPT_LIBRARY_RELEASE_DIR:-dist-release}"
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
  scripts/load-env.sh \
  scripts/verify-release-assets.py \
  scripts/install-sample-data.sh \
  scripts/setup-runtime.sh \
  scripts/appctl.ps1 \
  scripts/install.ps1 \
  scripts/install-sample-data.ps1 \
  scripts/setup-runtime.ps1 \
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
# .env* .codex* .qa-* and other local/private runtime paths
find "$STAGING" \( \
  -name '.env*' -o \
  -name '.agents' -o \
  -name '.codebase-memory' -o \
  -name '.codex*' -o \
  -name '.local-work' -o \
  -name '.qa-*' -o \
  -name '.superpowers' -o \
  -name 'library' -o \
  -name 'node_modules' -o \
  -name '.venv' -o \
  -name 'backups' -o \
  -name '__pycache__' \
\) -prune -exec rm -rf {} +
find "$STAGING" -name '*.pyc' -type f -delete

# Keep release artifacts focused on normal user runtime only. These helper modules are
# source/developer maintenance tools for building sample manifests or importing upstream
# authoring repos; the installed app and sample-data wrapper do not need them.
rm -f \
  "$STAGING/backend/services/build_awesome_gpt_image_2_sample_manifest.py" \
  "$STAGING/backend/services/build_gpt_image_sample_manifests.py" \
  "$STAGING/backend/services/fill_sample_manifest_translations.py" \
  "$STAGING/backend/services/import_gpt_image_2_skill.py"

(
  cd "$STAGING"
  find . -type f -exec chmod 0644 {} +
  find . -type d -exec chmod 0755 {} +
  chmod 0755 scripts/*.sh
)

rm -f "$RELEASE_DIR/$ARTIFACT" "$RELEASE_DIR/$CHECKSUM_FILE" "$RELEASE_DIR/$MANIFEST"
(
  cd "$STAGING"
  tar -czf "../../$ARTIFACT" \
    VERSION \
    backend \
    frontend \
    LICENSE \
    NOTICE \
    pyproject.toml \
    README.md \
    sample-data \
    scripts \
    SECURITY.md
)

if command -v sha256sum >/dev/null 2>&1; then
  SHA256="$(sha256sum "$RELEASE_DIR/$ARTIFACT" | awk '{print $1}')"
else
  SHA256="$(shasum -a 256 "$RELEASE_DIR/$ARTIFACT" | awk '{print $1}')"
fi
printf '%s  %s\n' "$SHA256" "$ARTIFACT" > "$RELEASE_DIR/$CHECKSUM_FILE"

python3 - "$VERSION" "$ARTIFACT" "$SHA256" "$SOURCE_SHA" "$RELEASE_DIR/$MANIFEST" <<'PY'
import json
import sys
from datetime import datetime, timezone
version, artifact, sha256, source_sha, manifest_path = sys.argv[1:]
manifest = {
    "name": "image-prompt-library",
    "version": version,
    "schema_version": 2,
    "capabilities": ["windows-powershell-v1", "posix-shell-v1"],
    "artifact": artifact,
    "sha256": sha256,
    "source_sha": source_sha,
    "python": ">=3.10",
    "node_required_for_runtime": False,
    "built_frontend": True,
    "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
}
with open(manifest_path, "w", encoding="utf-8") as handle:
    json.dump(manifest, handle, indent=2)
    handle.write("\n")
PY

python3 scripts/verify-release-assets.py "$RELEASE_DIR" "$VERSION" --source-sha "$SOURCE_SHA" --capability posix-shell-v1

rm -rf "$STAGING_ROOT"
echo "Created $RELEASE_DIR/$ARTIFACT"
echo "Created $RELEASE_DIR/$CHECKSUM_FILE"
echo "Created $RELEASE_DIR/$MANIFEST"
