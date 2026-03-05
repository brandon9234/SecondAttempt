# Architecture

## Source-of-Truth Model

Repo-managed state includes:
- `theme/`: Liquid, templates, sections, assets
- `products/`: product definitions and ordered media files
- `content/`: pages, blog articles, policies
- `navigation/menus.json`: menus/linklists
- `apps/app_manifest.json`: required app dependency parity

Shopify is a deployment target only.

## Identity Model

- Product identity: `handle`
- Variant identity: composite `(handle, sku)`
- Media identity: filename marker `sync:<filename>` attached to product media alt text

Image matching by title is prohibited.

## Import Pipeline (Source -> Repo)

1. `source_export.py`
- Exports products (all statuses), variants, collections, pages, blogs/articles, policies, menus, shop metadata.
- Writes `catalog/import_logs/source_raw_*.json` and `catalog/source_snapshot.json`.

2. `source_download_media.py`
- Downloads product images from exported source URLs.
- Writes deterministic filenames to each `products/<handle>/` folder (`main.*`, `02.*`, `03.*`, ...).
- Emits `catalog/import_logs/media_map.json` with hashes.

3. `source_transform_all.py`
- Converts raw exports into repo contracts (`products`, `content`, `navigation`).

4. `theme_pull_source.sh`
- Pulls source theme into `theme/` using Shopify CLI.

## Deployment Pipeline (Repo -> Target)

- `catalog_sync.py`: incremental product + media sync via Admin API.
- `content_sync.py`: upsert pages/blogs/articles/policies/menus.
- `theme_push.sh`: pushes `theme/` to target store.
- `full_replicate_sync.py`: validate -> build -> catalog sync -> content sync -> theme push.

## Incremental and Idempotent Behavior

- Media SHA256 hashes and Shopify IDs are tracked in `catalog/sync_state.json`.
- State keys variant IDs by `"<handle>::<sku>"`.
- Re-running sync with no repo changes should produce zero target mutations.
