# Troubleshooting

## Missing source credentials

`source_export.py` requires:
- `SOURCE_SHOPIFY_STORE_DOMAIN`
- `SOURCE_SHOPIFY_ADMIN_ACCESS_TOKEN`

## Missing target credentials

Live sync scripts require:
- `TARGET_SHOPIFY_STORE_DOMAIN`
- `TARGET_SHOPIFY_ADMIN_ACCESS_TOKEN`

With `DRY_RUN=true`, sync scripts validate local data and exit without target mutations.

## Duplicate SKU validation confusion

Global duplicate SKUs are allowed.
Only duplicates within the same product are invalid.

## Media ordering errors

If validation reports media gaps:
- Ensure `main.*` exists
- Ensure secondary files are `02.*`, `03.*`, ... with no gaps

## Policy/menu API limitations

Some Shopify plans or API versions can restrict policy/menu write operations.
If policy/menu writes fail, sync logs will report actionable API errors.

## App feature mismatch after deploy

Run:

```bash
python scripts/discover_app_dependencies.py
```

Then use `apps/app_manifest.json` and `docs/APPS_PARITY.md` to reinstall and reconfigure required apps in target store.
