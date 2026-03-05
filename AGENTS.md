# Agent Guardrails

## Non-Negotiable Rules

1. Repo is the source of truth for theme, catalog, media, content, and navigation.
2. Do not make manual product/media/content relinking edits in Shopify admin.
3. Stable identity rules:
- Product: `handle`
- Variant: `(handle, sku)` composite key
- Media: filename marker (`sync:<filename>`) within product
4. Never map product media by title.
5. Source store is read/export only; target store is deployment only.

## Required Workflow

1. Import source data/theme with source scripts.
2. Update repo files via PR.
3. Run `python scripts/validate_repo.py`.
4. Run `python scripts/catalog_build.py`.
5. Run dry-run sync for catalog and content.
6. Run live deployment only after review.

## App parity

App functionality detected in source must be tracked in `apps/app_manifest.json` and reinstalled/configured in the target store.
