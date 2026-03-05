# Catalog Rules

- Product folder must equal `product.json.handle`.
- Required schema fields must be present and typed correctly.
- SKUs must be unique within a product (global duplicates allowed).
- Image order must be `main.*`, then `02.*`, `03.*` with no gaps.
- `python scripts/validate_repo.py` must pass before sync.
