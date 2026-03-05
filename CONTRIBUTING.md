# Contributing

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Source import workflow

```bash
python scripts/source_export.py
python scripts/source_download_media.py
python scripts/source_transform_all.py
python scripts/discover_app_dependencies.py
```

## Validation and build

```bash
python scripts/validate_repo.py
python scripts/catalog_build.py
```

## Deploy workflow

```bash
DRY_RUN=true python scripts/catalog_sync.py
DRY_RUN=true python scripts/content_sync.py
DRY_RUN=false python scripts/full_replicate_sync.py
```

## PR checklist

- [ ] Repo source-of-truth rules are respected.
- [ ] No manual Shopify relinking edits were used for product/media/content data.
- [ ] Product media naming/order rules pass validation.
- [ ] `python scripts/validate_repo.py` passes.
- [ ] `python scripts/catalog_build.py` passes.
- [ ] Dry-run sync outputs reviewed.
- [ ] `apps/app_manifest.json` updated when app dependencies change.
- [ ] No secrets committed.
