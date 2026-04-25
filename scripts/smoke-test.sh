#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:${BACKEND_PORT:-8000}}"

curl -fsS "$BASE_URL/api/health" >/dev/null
curl -fsS "$BASE_URL/api/items?limit=3" >/dev/null

MEDIA_STATUS="$(curl -sS -o /dev/null -w '%{http_code}' "$BASE_URL/media/db.sqlite")"
if [ "$MEDIA_STATUS" != "404" ]; then
  echo "Expected /media/db.sqlite to return 404, got $MEDIA_STATUS" >&2
  exit 1
fi

echo "Smoke test passed for $BASE_URL"
