# Products As Code

## Folder layout

```text
products/<handle>/
  product.json
  main.jpg|main.png|main.jpeg|main.webp
  02.jpg
  03.jpg
  ...
```

Rules:
- Folder name must equal `product.json.handle`.
- `main.*` is always position 1.
- Secondary images are `02.*`, `03.*`, ... with no gaps.

## `product.json` contract

Required keys:
- `handle`
- `title`
- `description_html`
- `vendor`
- `product_type`
- `tags` (array)
- `collections` (array of collection handles)

Variant keys:
- Use `variants` array for imported catalogs.
- Each variant requires:
- `sku`
- `price`
- `option_values` (empty list allowed only for single-variant products)
- Optional: `compare_at_price`, `barcode`, `inventory_quantity`

Metadata keys used by import workflow:
- `source_status`
- `source_product_id`

## SKU identity rule

SKUs are validated for uniqueness **within each product only**.
Global duplicate SKUs are allowed, and variant identity is tracked by `(handle, sku)`.
