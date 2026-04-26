#!/usr/bin/env bash
set -euo pipefail

LANGUAGE="${1:-}"
if [[ -z "$LANGUAGE" ]]; then
  echo "Usage: $0 <en|zh_hans|zh_hant>" >&2
  exit 2
fi
case "$LANGUAGE" in
  en|zh_hans|zh_hant) ;;
  *) echo "Unsupported sample language: $LANGUAGE" >&2; exit 2 ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LIBRARY_PATH="${IMAGE_PROMPT_LIBRARY_PATH:-$REPO_ROOT/library}"
MANIFEST_PATH="${SAMPLE_DATA_MANIFEST:-$REPO_ROOT/sample-data/manifests/$LANGUAGE.json}"
WORK_DIR="${SAMPLE_DATA_WORK_DIR:-$REPO_ROOT/.local-work/sample-data-installer}"
ASSET_DIR="${SAMPLE_DATA_IMAGE_DIR:-}"
IMAGE_ZIP="${SAMPLE_DATA_IMAGE_ZIP:-}"
RELEASE_BASE_URL="${SAMPLE_DATA_RELEASE_BASE_URL:-https://github.com/EddieTYP/image-prompt-library/releases/download/sample-data-v1}"
RELEASE_ASSET_NAME="${SAMPLE_DATA_RELEASE_ASSET_NAME:-image-prompt-library-sample-images-v1.zip}"

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
    unzip -q "$IMAGE_ZIP" -d "$ASSET_DIR"
  else
    IMAGE_ZIP="$WORK_DIR/$RELEASE_ASSET_NAME"
    echo "Downloading sample images from $RELEASE_BASE_URL/$RELEASE_ASSET_NAME"
    curl -fL "$RELEASE_BASE_URL/$RELEASE_ASSET_NAME" -o "$IMAGE_ZIP"
    unzip -q "$IMAGE_ZIP" -d "$ASSET_DIR"
  fi
fi

PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="${PYTHON:-python3}"
fi

RESULT_JSON="$($PYTHON_BIN -m backend.services.import_sample_bundle \
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
