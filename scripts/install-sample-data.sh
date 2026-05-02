#!/usr/bin/env bash
set -euo pipefail

LANGUAGE="${1:-}"
PACKAGE="${2:-gpt-image-2-skill}"
if [[ -z "$LANGUAGE" ]]; then
  echo "Usage: $0 <en|zh_hans|zh_hant> [gpt-image-2-skill|awesome-gpt-image-2]" >&2
  exit 2
fi
case "$LANGUAGE" in
  en|zh_hans|zh_hant) ;;
  *) echo "Unsupported sample language: $LANGUAGE" >&2; exit 2 ;;
esac
case "$PACKAGE" in
  gpt-image-2-skill|awesome-gpt-image-2) ;;
  *) echo "Unsupported sample package: $PACKAGE" >&2; exit 2 ;;
esac
if [[ "$PACKAGE" == "awesome-gpt-image-2" && "$LANGUAGE" != "zh_hant" ]]; then
  echo "awesome-gpt-image-2 sample package currently ships zh_hant manifests only" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
if [[ -z "${IMAGE_PROMPT_LIBRARY_PATH:-}" && -f "$REPO_ROOT/VERSION" ]]; then
  INSTALL_PREFIX="$(cd "$REPO_ROOT/../../.." && pwd -P)"
  ENV_FILE="$INSTALL_PREFIX/.env"
  if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
  fi
fi
LIBRARY_PATH="${IMAGE_PROMPT_LIBRARY_PATH:-$REPO_ROOT/library}"
if [[ -n "${SAMPLE_DATA_MANIFEST:-}" ]]; then
  MANIFEST_PATH="$SAMPLE_DATA_MANIFEST"
elif [[ "$PACKAGE" == "awesome-gpt-image-2" ]]; then
  MANIFEST_PATH="$REPO_ROOT/sample-data/manifests/awesome-gpt-image-2/$LANGUAGE.json"
else
  MANIFEST_PATH="$REPO_ROOT/sample-data/manifests/$LANGUAGE.json"
fi
WORK_DIR="${SAMPLE_DATA_WORK_DIR:-$REPO_ROOT/.local-work/sample-data-installer/$PACKAGE}"
ASSET_DIR="${SAMPLE_DATA_IMAGE_DIR:-}"
IMAGE_ZIP="${SAMPLE_DATA_IMAGE_ZIP:-}"
if [[ "$PACKAGE" == "awesome-gpt-image-2" ]]; then
  DEFAULT_RELEASE_TAG="sample-data-awesome-gpt-image-2-v1"
  DEFAULT_RELEASE_ASSET="image-prompt-library-awesome-gpt-image-2-sample-images-v1.zip"
  DEFAULT_SHA256="153714b7611524d7b98b4b0452baa86c8d05053477bb670b731953e8d26a8c9c"
else
  DEFAULT_RELEASE_TAG="sample-data-v1"
  DEFAULT_RELEASE_ASSET="image-prompt-library-sample-images-v1.zip"
  DEFAULT_SHA256="8a458f6c8c96079f40fbc46c689e7de0bd2eb464ee7f800f94f3ca60131d5035"
fi
RELEASE_BASE_URL="${SAMPLE_DATA_RELEASE_BASE_URL:-https://github.com/EddieTYP/image-prompt-library/releases/download/$DEFAULT_RELEASE_TAG}"
RELEASE_ASSET_NAME="${SAMPLE_DATA_RELEASE_ASSET_NAME:-$DEFAULT_RELEASE_ASSET}"
EXPECTED_SHA256="${SAMPLE_DATA_IMAGE_ZIP_SHA256:-$DEFAULT_SHA256}"

PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="${PYTHON:-python3}"
fi

sha256_file() {
  local file="$1"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$file" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$file" | awk '{print $1}'
  else
    echo "Neither sha256sum nor shasum is available for checksum verification" >&2
    return 1
  fi
}

verify_zip_checksum() {
  local file="$1"
  local expected="$2"
  if [[ -z "$expected" ]]; then
    return 0
  fi
  local actual
  actual="$(sha256_file "$file")"
  if [[ "$actual" != "$expected" ]]; then
    echo "Sample image ZIP checksum mismatch: $file" >&2
    echo "Expected: $expected" >&2
    echo "Actual:   $actual" >&2
    exit 1
  fi
}

extract_zip() {
  local file="$1"
  local destination="$2"
  "$PYTHON_BIN" - "$file" "$destination" <<'PY'
import sys
import zipfile
from pathlib import Path

zip_path = Path(sys.argv[1])
destination = Path(sys.argv[2]).resolve()
destination.mkdir(parents=True, exist_ok=True)

with zipfile.ZipFile(zip_path) as archive:
    for member in archive.infolist():
        member_path = Path(member.filename)
        if member.filename.startswith(("/", "\\")) or ".." in member_path.parts:
            raise SystemExit(f"Refusing unsafe ZIP member path: {member.filename}")
        target = (destination / member_path).resolve()
        try:
            target.relative_to(destination)
        except ValueError as exc:
            raise SystemExit(f"Refusing unsafe ZIP member path: {member.filename}") from exc
    archive.extractall(destination)
PY
}

if [[ ! -f "$MANIFEST_PATH" ]]; then
  echo "Sample manifest not found: $MANIFEST_PATH" >&2
  exit 1
fi

mkdir -p "$WORK_DIR"
if [[ -z "$ASSET_DIR" ]]; then
  ASSET_DIR="$WORK_DIR/images"
  rm -rf "$ASSET_DIR"
  mkdir -p "$ASSET_DIR"
  if [[ -n "$IMAGE_ZIP" ]]; then
    if [[ ! -f "$IMAGE_ZIP" ]]; then
      echo "Sample image ZIP not found: $IMAGE_ZIP" >&2
      exit 1
    fi
    if [[ -n "${SAMPLE_DATA_IMAGE_ZIP_SHA256:-}" ]]; then
      verify_zip_checksum "$IMAGE_ZIP" "$EXPECTED_SHA256"
    fi
    extract_zip "$IMAGE_ZIP" "$ASSET_DIR"
  else
    IMAGE_ZIP="$WORK_DIR/$RELEASE_ASSET_NAME"
    echo "Downloading sample images from $RELEASE_BASE_URL/$RELEASE_ASSET_NAME"
    curl -fL "$RELEASE_BASE_URL/$RELEASE_ASSET_NAME" -o "$IMAGE_ZIP"
    verify_zip_checksum "$IMAGE_ZIP" "$EXPECTED_SHA256"
    extract_zip "$IMAGE_ZIP" "$ASSET_DIR"
  fi
fi

RESULT_JSON="$(cd "$REPO_ROOT" && "$PYTHON_BIN" -m backend.services.import_sample_bundle \
  --manifest "$MANIFEST_PATH" \
  --assets "$ASSET_DIR" \
  --library "$LIBRARY_PATH")"

ITEMS="$($PYTHON_BIN -c 'import json,sys; print(json.load(sys.stdin)["item_count"])' <<<"$RESULT_JSON")"
IMAGES="$($PYTHON_BIN -c 'import json,sys; print(json.load(sys.stdin)["image_count"])' <<<"$RESULT_JSON")"
LOG="$($PYTHON_BIN -c 'import json,sys; print(json.load(sys.stdin).get("log", ""))' <<<"$RESULT_JSON")"

echo "Imported $ITEMS items and $IMAGES images into $LIBRARY_PATH"
if [[ -n "$LOG" ]]; then
  echo "$LOG"
fi
