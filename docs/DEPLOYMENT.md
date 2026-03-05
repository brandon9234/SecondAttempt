# Deployment

## Source import workflow

```bash
python scripts/source_export.py
python scripts/source_download_media.py
python scripts/source_transform_all.py
python scripts/discover_app_dependencies.py
bash scripts/theme_pull_source.sh
```

## Target deployment workflow

```bash
python scripts/validate_repo.py
python scripts/catalog_build.py
DRY_RUN=true python scripts/catalog_sync.py
DRY_RUN=true python scripts/content_sync.py
DRY_RUN=false python scripts/full_replicate_sync.py
```

## Theme deployment alternatives

- CLI path (default): `bash scripts/theme_push.sh`
- Shopify GitHub theme integration can be used, but this repo remains the authoring source.

## CI behavior

Default CI validates repository shape and builds manifests only.
Live sync/deploy steps remain commented and require protected secrets.
