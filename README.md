# Shopify Replica Repository

This repository is the source of truth for:
- Theme code (`theme/`)
- Product catalog and media (`products/<handle>/`)
- Storefront content (`content/`, `navigation/`)
- App dependency inventory (`apps/app_manifest.json`)

Source store: `quickclipsfloral.com` (authorized export)
Deployment target: separate Shopify store (`TARGET_SHOPIFY_STORE_DOMAIN`)

## Core Workflows

### 1. Import from source store

```bash
python scripts/source_export.py
python scripts/source_download_media.py
python scripts/source_transform_all.py
python scripts/discover_app_dependencies.py
bash scripts/theme_pull_source.sh
```

### 2. Validate and build

```bash
python scripts/validate_repo.py
python scripts/catalog_build.py
```

### 3. Deploy to target store

```bash
DRY_RUN=true python scripts/catalog_sync.py
DRY_RUN=true python scripts/content_sync.py
DRY_RUN=false python scripts/full_replicate_sync.py
```

## Repository Layout

- `theme/` pulled/published Shopify theme source
- `products/` product and media source-of-truth
- `content/pages` page documents
- `content/blogs` blog/article documents
- `content/policies` policy markdown files
- `navigation/menus.json` menu/linklist source-of-truth
- `apps/app_manifest.json` required app parity checklist
- `catalog/` generated manifests, sync state, import logs
- `scripts/` import, transform, validation, sync automation

See [docs/QUICKSTART.md](docs/QUICKSTART.md) for setup and credentials.
