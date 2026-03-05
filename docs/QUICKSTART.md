# Quickstart

## 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Configure environment

```bash
cp .env.example .env
```

Required source credentials:
- `SOURCE_SHOPIFY_STORE_DOMAIN`
- `SOURCE_SHOPIFY_ADMIN_ACCESS_TOKEN`

Required target credentials:
- `TARGET_SHOPIFY_STORE_DOMAIN`
- `TARGET_SHOPIFY_ADMIN_ACCESS_TOKEN`

## 3. Pull source data and theme

```bash
python scripts/source_export.py
python scripts/source_download_media.py
python scripts/source_transform_all.py
python scripts/discover_app_dependencies.py
bash scripts/theme_pull_source.sh
```

## 4. Validate and build

```bash
python scripts/validate_repo.py
python scripts/catalog_build.py
```

## 5. Dry-run sync to target store

```bash
DRY_RUN=true python scripts/catalog_sync.py
DRY_RUN=true python scripts/content_sync.py
```

## 6. Live deployment to target store

```bash
DRY_RUN=false python scripts/full_replicate_sync.py
```
