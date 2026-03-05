# Security Policy

## Secrets

Never commit `.env` or API tokens.

Sensitive variables:
- `SOURCE_SHOPIFY_ADMIN_ACCESS_TOKEN`
- `TARGET_SHOPIFY_ADMIN_ACCESS_TOKEN`

## Principle of least privilege

Use separate source and target tokens with minimum required scopes.
Recommended scopes:
- products (read/write for target, read for source)
- collections (read/write for target, read for source)
- content/pages/blogs/menus/policies (read/write target, read source)
- files/media (read/write target, read source)
- themes (CLI-auth based operations)

## Rotation

- Rotate tokens regularly.
- Revoke immediately on exposure.
- Update local `.env` and CI secrets after rotation.

## CI safety

Default CI must not execute live deployment.
Live workflows should be gated and use protected environment secrets.
