# App Parity Guide

`apps/app_manifest.json` is generated from storefront/theme analysis and lists inferred app dependencies.

## Migration checklist

1. Install each required app in the target store.
2. Re-enable theme app embeds and app blocks.
3. Recreate app-side settings/configuration not stored in theme files.
4. Reconnect app data sources (forms, review widgets, bundle rules, lock rules).
5. Validate pages where app scripts were detected.

## Verification targets

- Product page review blocks/widgets
- Any lock/hide-price behavior
- Bundle/variant app interactions
- Form builder pages
- Promotional/cart widgets

## Notes

App configuration is typically not fully exportable through theme source.
Treat app install/config as a required manual post-import step.
