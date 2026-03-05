#!/usr/bin/env python3
"""Transform exported source products into repository product.json files."""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.lib.content import write_json  # noqa: E402
from scripts.lib.source_artifacts import load_raw_items  # noqa: E402

LOGGER = logging.getLogger("source_transform_products")


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return normalized or "untitled"


def _parse_tags(raw_tags: Any) -> list[str]:
    if isinstance(raw_tags, list):
        return sorted({str(tag).strip() for tag in raw_tags if str(tag).strip()})
    if isinstance(raw_tags, str):
        return sorted({tag.strip() for tag in raw_tags.split(",") if tag.strip()})
    return []


def _normalize_option_values(variant: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("option1", "option2", "option3"):
        value = variant.get(key)
        if value is None:
            continue
        value_text = str(value).strip()
        if not value_text or value_text.lower() == "default title":
            continue
        values.append(value_text)
    return values


def _variant_sku(handle: str, variant: dict[str, Any]) -> tuple[str, str | None]:
    sku = variant.get("sku")
    if isinstance(sku, str) and sku.strip():
        return sku.strip(), None

    variant_id = variant.get("id")
    fallback = f"NO-SKU-{handle.upper()}-{variant_id if variant_id is not None else 'UNKNOWN'}"
    return fallback, "missing_sku_replaced"


def _collection_map(
    custom_collections: list[dict[str, Any]],
    smart_collections: list[dict[str, Any]],
) -> dict[int, str]:
    mapping: dict[int, str] = {}
    for collection in custom_collections + smart_collections:
        handle = collection.get("handle")
        collection_id = collection.get("id")
        if not isinstance(handle, str) or not handle.strip():
            continue
        try:
            collection_id_int = int(collection_id)
        except (TypeError, ValueError):
            continue
        mapping[collection_id_int] = handle.strip()
    return mapping


def _product_collections(
    product_id: int,
    collects: list[dict[str, Any]],
    collection_id_to_handle: dict[int, str],
) -> list[str]:
    handles: set[str] = set()
    for collect in collects:
        collect_product_id = collect.get("product_id")
        collect_collection_id = collect.get("collection_id")
        try:
            if int(collect_product_id) != product_id:
                continue
            collection_handle = collection_id_to_handle.get(int(collect_collection_id))
        except (TypeError, ValueError):
            continue
        if collection_handle:
            handles.add(collection_handle)
    return sorted(handles)


def _normalize_product_type(value: Any, handle: str, notes: list[dict[str, Any]]) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()

    notes.append(
        {
            "handle": handle,
            "note": "blank_product_type_normalized",
            "normalized_to": "Uncategorized",
        }
    )
    return "Uncategorized"


def transform_product(
    raw: dict[str, Any],
    *,
    collects: list[dict[str, Any]],
    collection_id_to_handle: dict[int, str],
    notes: list[dict[str, Any]],
) -> tuple[str, dict[str, Any]] | None:
    handle_raw = raw.get("handle")
    if not isinstance(handle_raw, str) or not handle_raw.strip():
        title = raw.get("title")
        handle_raw = _slugify(str(title)) if title else None

    if not handle_raw:
        return None

    handle = handle_raw.strip()

    title = raw.get("title")
    if not isinstance(title, str) or not title.strip():
        title = handle.replace("-", " ").title()

    product_id = raw.get("id")
    product_id_int: int | None = None
    try:
        product_id_int = int(product_id)
    except (TypeError, ValueError):
        pass

    variants_payload: list[dict[str, Any]] = []
    variants = raw.get("variants") if isinstance(raw.get("variants"), list) else []
    for variant in variants:
        if not isinstance(variant, dict):
            continue
        sku, sku_note = _variant_sku(handle, variant)
        if sku_note:
            notes.append(
                {
                    "handle": handle,
                    "variant_id": variant.get("id"),
                    "note": sku_note,
                    "generated_sku": sku,
                }
            )

        variant_payload: dict[str, Any] = {
            "sku": sku,
            "price": str(variant.get("price") if variant.get("price") is not None else "0.00"),
            "option_values": _normalize_option_values(variant),
        }

        if variant.get("compare_at_price") is not None:
            variant_payload["compare_at_price"] = str(variant.get("compare_at_price"))
        if variant.get("barcode") is not None:
            variant_payload["barcode"] = str(variant.get("barcode"))

        inventory_quantity = variant.get("inventory_quantity")
        if isinstance(inventory_quantity, int):
            variant_payload["inventory_quantity"] = inventory_quantity

        variants_payload.append(variant_payload)

    if not variants_payload:
        fallback_sku = f"NO-VARIANT-{handle.upper()}"
        notes.append(
            {
                "handle": handle,
                "note": "missing_variants_replaced",
                "generated_sku": fallback_sku,
            }
        )
        variants_payload.append(
            {
                "sku": fallback_sku,
                "price": "0.00",
                "option_values": [],
            }
        )

    output: dict[str, Any] = {
        "handle": handle,
        "title": title.strip(),
        "description_html": str(raw.get("body_html") or ""),
        "vendor": str(raw.get("vendor") or "Unknown Vendor").strip() or "Unknown Vendor",
        "product_type": _normalize_product_type(raw.get("product_type"), handle, notes),
        "tags": _parse_tags(raw.get("tags")),
        "collections": _product_collections(
            product_id_int or -1,
            collects,
            collection_id_to_handle,
        ),
        "variants": variants_payload,
        "source_status": str(raw.get("status") or "unknown"),
        "source_product_id": raw.get("id"),
    }
    return handle, output


def prune_product_folders(expected_handles: set[str]) -> None:
    products_root = ROOT / "products"
    for path in products_root.iterdir():
        if not path.is_dir():
            continue
        if path.name.startswith("."):
            continue
        if path.name not in expected_handles:
            for child in path.iterdir():
                if child.is_file():
                    child.unlink()
            path.rmdir()
            LOGGER.info("Pruned stale product folder: %s", path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Transform source raw products into repo product.json files")
    parser.add_argument(
        "--prune-product-folders",
        action="store_true",
        help="Remove local product folders that are not in source export",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    try:
        products = load_raw_items(ROOT, "products")
        custom_collections = load_raw_items(ROOT, "custom_collections")
        smart_collections = load_raw_items(ROOT, "smart_collections")
        collects = load_raw_items(ROOT, "collects")
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("Missing source artifacts for product transform: %s", exc)
        return 1

    collection_id_to_handle = _collection_map(custom_collections, smart_collections)
    notes: list[dict[str, Any]] = []

    expected_handles: set[str] = set()
    transformed = 0
    for raw in products:
        transformed_product = transform_product(
            raw,
            collects=collects,
            collection_id_to_handle=collection_id_to_handle,
            notes=notes,
        )
        if not transformed_product:
            continue
        handle, payload = transformed_product

        product_dir = ROOT / "products" / handle
        product_dir.mkdir(parents=True, exist_ok=True)
        write_json(product_dir / "product.json", payload)
        expected_handles.add(handle)
        transformed += 1

    if args.prune_product_folders:
        prune_product_folders(expected_handles)

    write_json(
        ROOT / "catalog" / "import_logs" / "product_transform_notes.json",
        {
            "items": notes,
            "transformed_products": transformed,
        },
    )

    LOGGER.info("Transformed %d products", transformed)
    LOGGER.info("Wrote catalog/import_logs/product_transform_notes.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
