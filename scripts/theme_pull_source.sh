#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v shopify >/dev/null 2>&1; then
  echo "Shopify CLI is required. Install from https://shopify.dev/docs/apps/tools/cli" >&2
  exit 1
fi

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

SOURCE_STORE="${SOURCE_SHOPIFY_STORE_DOMAIN:-}"
SOURCE_THEME_ID="${SOURCE_THEME_ID:-}"

if [[ -z "$SOURCE_STORE" ]]; then
  echo "SOURCE_SHOPIFY_STORE_DOMAIN is required in .env" >&2
  exit 1
fi

mkdir -p catalog/import_logs

PULL_MODE="live"
if [[ -n "$SOURCE_THEME_ID" ]]; then
  PULL_MODE="theme_id"
  echo "Pulling source theme id $SOURCE_THEME_ID from $SOURCE_STORE into theme/"
  shopify theme pull --store "$SOURCE_STORE" --theme "$SOURCE_THEME_ID" --path theme
else
  echo "Pulling live source theme from $SOURCE_STORE into theme/"
  shopify theme pull --store "$SOURCE_STORE" --live --path theme
fi

python - <<'PY'
import json
from datetime import datetime, timezone
from pathlib import Path
import os

payload = {
    "pulled_at": datetime.now(timezone.utc).isoformat(),
    "source_store": os.getenv("SOURCE_SHOPIFY_STORE_DOMAIN"),
    "source_theme_id": os.getenv("SOURCE_THEME_ID") or None,
    "pull_mode": "theme_id" if os.getenv("SOURCE_THEME_ID") else "live",
    "path": "theme",
}
path = Path("catalog/import_logs/theme_pull.json")
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(f"Wrote {path}")
PY
