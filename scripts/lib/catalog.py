"""Catalog loading and validation helpers shared by scripts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
REQUIRED_PRODUCT_FIELDS: dict[str, type] = {
    "handle": str,
    "title": str,
    "description_html": str,
    "vendor": str,
    "product_type": str,
    "tags": list,
    "collections": list,
}


class CatalogValidationError(Exception):
    """Raised when catalog data fails validation."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("Catalog validation failed")
        self.errors = errors


@dataclass
class CatalogProduct:
    folder_name: str
    folder_path: Path
    product_json_path: Path
    handle: str
    title: str
    description_html: str
    vendor: str
    product_type: str
    tags: list[str]
    collections: list[str]
    variants: list[dict[str, Any]]
    images: list[dict[str, Any]]
    source_status: str | None = None

    def to_manifest_dict(self) -> dict[str, Any]:
        return {
            "handle": self.handle,
            "title": self.title,
            "description_html": self.description_html,
            "vendor": self.vendor,
            "product_type": self.product_type,
            "tags": self.tags,
            "collections": self.collections,
            "variants": self.variants,
            "media_filenames": [image["filename"] for image in self.images],
            "source_status": self.source_status,
        }


def normalize_price(value: Any, field_name: str, errors: list[str], context: str) -> str | None:
    try:
        normalized = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        errors.append(f"{context}: '{field_name}' must be a numeric value")
        return None
    return format(normalized, "f")


def list_product_directories(products_root: Path) -> list[Path]:
    if not products_root.exists():
        return []
    return sorted([path for path in products_root.iterdir() if path.is_dir() and not path.name.startswith(".")])


def _validate_string_list(value: Any, field_name: str, errors: list[str], context: str) -> list[str] | None:
    if not isinstance(value, list):
        errors.append(f"{context}: '{field_name}' must be a list of strings")
        return None
    typed: list[str] = []
    for idx, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{context}: '{field_name}[{idx}]' must be a non-empty string")
            continue
        typed.append(item.strip())
    return typed


def _collect_images(product_dir: Path, errors: list[str]) -> list[dict[str, Any]]:
    context = str(product_dir)
    media_files = [
        path
        for path in product_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
    ]

    main_files = [path for path in media_files if path.stem == "main"]
    if len(main_files) != 1:
        errors.append(f"{context}: expected exactly one main image named 'main.*' (found {len(main_files)})")

    secondary_files: list[tuple[int, Path]] = []
    seen_secondary_numbers: set[int] = set()
    secondary_pattern = re.compile(r"^(\d{2,})$")

    for path in media_files:
        if path.stem == "main":
            continue
        match = secondary_pattern.match(path.stem)
        if not match:
            errors.append(
                f"{context}: secondary media '{path.name}' must use numeric filenames like 02.jpg, 03.png"
            )
            continue
        number = int(match.group(1))
        if number < 2:
            errors.append(f"{context}: secondary media numbering must start at 02 (found {path.name})")
            continue
        if number in seen_secondary_numbers:
            errors.append(f"{context}: duplicate secondary media position number {number:02d}")
            continue
        seen_secondary_numbers.add(number)
        secondary_files.append((number, path))

    secondary_numbers = sorted(number for number, _ in secondary_files)
    if secondary_numbers:
        expected = list(range(2, 2 + len(secondary_numbers)))
        if secondary_numbers != expected:
            missing = sorted(set(expected) - set(secondary_numbers))
            missing_text = ", ".join(f"{number:02d}" for number in missing)
            errors.append(
                f"{context}: secondary media numbering has gaps; missing position(s): {missing_text}"
            )

    ordered_images: list[dict[str, Any]] = []
    if main_files:
        ordered_images.append(
            {
                "filename": main_files[0].name,
                "path": main_files[0],
                "position": 1,
                "mime_type": _mime_type_for_path(main_files[0]),
            }
        )

    for index, (_, path) in enumerate(sorted(secondary_files, key=lambda item: item[0]), start=2):
        ordered_images.append(
            {
                "filename": path.name,
                "path": path,
                "position": index,
                "mime_type": _mime_type_for_path(path),
            }
        )

    return ordered_images


def _mime_type_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    if suffix == ".webp":
        return "image/webp"
    return "application/octet-stream"


def _normalize_variants(data: dict[str, Any], errors: list[str], context: str) -> list[dict[str, Any]]:
    variants_input = data.get("variants")
    normalized_variants: list[dict[str, Any]] = []

    if variants_input is None:
        if "sku" not in data or "price" not in data:
            errors.append(f"{context}: either provide top-level 'sku' + 'price' or a 'variants' array")
            return []
        sku = data.get("sku")
        if not isinstance(sku, str) or not sku.strip():
            errors.append(f"{context}: 'sku' must be a non-empty string")
            return []
        price = normalize_price(data.get("price"), "price", errors, context)
        compare_at_price = data.get("compare_at_price")
        normalized: dict[str, Any] = {
            "sku": sku.strip(),
            "price": price,
        }
        if compare_at_price is not None:
            normalized_compare = normalize_price(compare_at_price, "compare_at_price", errors, context)
            normalized["compare_at_price"] = normalized_compare
        if data.get("barcode") is not None:
            if not isinstance(data.get("barcode"), str):
                errors.append(f"{context}: 'barcode' must be a string when provided")
            else:
                normalized["barcode"] = data.get("barcode")
        if data.get("inventory_quantity") is not None:
            if not isinstance(data.get("inventory_quantity"), int):
                errors.append(f"{context}: 'inventory_quantity' must be an integer when provided")
            else:
                normalized["inventory_quantity"] = data.get("inventory_quantity")
        normalized["option_values"] = []
        normalized_variants.append(normalized)
        return normalized_variants

    if not isinstance(variants_input, list) or not variants_input:
        errors.append(f"{context}: 'variants' must be a non-empty list")
        return []

    option_value_count: int | None = None
    for index, variant in enumerate(variants_input):
        variant_ctx = f"{context} variants[{index}]"
        if not isinstance(variant, dict):
            errors.append(f"{variant_ctx}: variant entry must be an object")
            continue

        sku = variant.get("sku")
        if not isinstance(sku, str) or not sku.strip():
            errors.append(f"{variant_ctx}: 'sku' must be a non-empty string")
            continue

        price = normalize_price(variant.get("price"), "price", errors, variant_ctx)

        normalized_variant: dict[str, Any] = {
            "sku": sku.strip(),
            "price": price,
        }

        if variant.get("compare_at_price") is not None:
            normalized_variant["compare_at_price"] = normalize_price(
                variant.get("compare_at_price"),
                "compare_at_price",
                errors,
                variant_ctx,
            )

        if variant.get("barcode") is not None:
            if not isinstance(variant.get("barcode"), str):
                errors.append(f"{variant_ctx}: 'barcode' must be a string when provided")
            else:
                normalized_variant["barcode"] = variant.get("barcode")

        if variant.get("inventory_quantity") is not None:
            if not isinstance(variant.get("inventory_quantity"), int):
                errors.append(f"{variant_ctx}: 'inventory_quantity' must be an integer when provided")
            else:
                normalized_variant["inventory_quantity"] = variant.get("inventory_quantity")

        option_values = variant.get("option_values", [])
        if option_values is None:
            option_values = []
        if not isinstance(option_values, list) or any(not isinstance(item, str) or not item.strip() for item in option_values):
            errors.append(f"{variant_ctx}: 'option_values' must be a list of non-empty strings")
            continue

        stripped_option_values = [item.strip() for item in option_values]
        if option_value_count is None:
            option_value_count = len(stripped_option_values)
        elif option_value_count != len(stripped_option_values):
            errors.append(
                f"{variant_ctx}: all variants must have the same number of 'option_values' entries"
            )

        normalized_variant["option_values"] = stripped_option_values
        normalized_variants.append(normalized_variant)

    # If there are multiple variants, force option values so Shopify can differentiate them.
    if len(normalized_variants) > 1 and any(not variant["option_values"] for variant in normalized_variants):
        errors.append(
            f"{context}: when using multiple variants, each variant must include non-empty 'option_values'"
        )

    return normalized_variants


def load_catalog(products_root: Path) -> list[CatalogProduct]:
    errors: list[str] = []
    products: list[CatalogProduct] = []
    seen_handles: set[str] = set()

    for product_dir in list_product_directories(products_root):
        folder_name = product_dir.name
        context = str(product_dir)
        product_json_path = product_dir / "product.json"
        if not product_json_path.exists():
            errors.append(f"{context}: missing required file product.json")
            continue

        try:
            raw_data = json.loads(product_json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{product_json_path}: invalid JSON ({exc})")
            continue

        if not isinstance(raw_data, dict):
            errors.append(f"{product_json_path}: product.json root must be an object")
            continue

        for field_name, expected_type in REQUIRED_PRODUCT_FIELDS.items():
            if field_name not in raw_data:
                errors.append(f"{product_json_path}: missing required field '{field_name}'")
                continue
            if not isinstance(raw_data[field_name], expected_type):
                errors.append(
                    f"{product_json_path}: field '{field_name}' must be of type {expected_type.__name__}"
                )

        handle = raw_data.get("handle")
        if isinstance(handle, str):
            handle = handle.strip()

        if not handle:
            errors.append(f"{product_json_path}: 'handle' must be a non-empty string")
            continue

        if handle != folder_name:
            errors.append(
                f"{product_json_path}: handle '{handle}' must match folder name '{folder_name}'"
            )

        if handle in seen_handles:
            errors.append(f"{product_json_path}: duplicate handle '{handle}'")
        seen_handles.add(handle)

        tags = _validate_string_list(raw_data.get("tags"), "tags", errors, str(product_json_path))
        collections = _validate_string_list(
            raw_data.get("collections"),
            "collections",
            errors,
            str(product_json_path),
        )

        variants = _normalize_variants(raw_data, errors, str(product_json_path))

        local_seen_skus: set[str] = set()
        for variant in variants:
            sku = variant.get("sku")
            if not sku:
                continue
            if sku in local_seen_skus:
                errors.append(f"{product_json_path}: duplicate sku '{sku}' within product")
            local_seen_skus.add(sku)

        images = _collect_images(product_dir, errors)

        title = raw_data.get("title")
        description_html = raw_data.get("description_html")
        vendor = raw_data.get("vendor")
        product_type = raw_data.get("product_type")

        if not isinstance(title, str) or not title.strip():
            errors.append(f"{product_json_path}: 'title' must be a non-empty string")
        if not isinstance(description_html, str):
            errors.append(f"{product_json_path}: 'description_html' must be a string")
        if not isinstance(vendor, str) or not vendor.strip():
            errors.append(f"{product_json_path}: 'vendor' must be a non-empty string")
        if not isinstance(product_type, str) or not product_type.strip():
            errors.append(f"{product_json_path}: 'product_type' must be a non-empty string")

        products.append(
            CatalogProduct(
                folder_name=folder_name,
                folder_path=product_dir,
                product_json_path=product_json_path,
                handle=handle,
                title=title.strip() if isinstance(title, str) else "",
                description_html=description_html if isinstance(description_html, str) else "",
                vendor=vendor.strip() if isinstance(vendor, str) else "",
                product_type=product_type.strip() if isinstance(product_type, str) else "",
                tags=tags or [],
                collections=collections or [],
                variants=variants,
                images=images,
                source_status=raw_data.get("source_status")
                if isinstance(raw_data.get("source_status"), str)
                else None,
            )
        )

    if errors:
        raise CatalogValidationError(errors)

    return sorted(products, key=lambda product: product.handle)
