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

echo "Pushing theme from $ROOT_DIR/theme"
if [[ -n "${TARGET_SHOPIFY_STORE_DOMAIN:-}" ]]; then
  shopify theme push --store "$TARGET_SHOPIFY_STORE_DOMAIN" --path theme
else
  shopify theme push --path theme
fi
