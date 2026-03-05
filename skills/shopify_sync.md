# Shopify Sync Rules

- Sync is incremental, idempotent, and state-driven.
- State file: `catalog/sync_state.json`.
- Product identity: handle.
- Variant identity: `(handle, sku)` composite key.
- Media identity: filename marker `sync:<filename>`.
- Source store is for export only.
- Target store is for deployment only.
- DRY_RUN is required before live sync.
