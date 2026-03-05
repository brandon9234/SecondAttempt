"""Local sync state persistence helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_STATE = {
    "schema_version": 1,
    "last_run_at": None,
    "products": {},
}


@dataclass
class SyncStateStore:
    """Read/write wrapper around catalog/sync_state.json."""

    path: Path

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return json.loads(json.dumps(DEFAULT_STATE))

        with self.path.open("r", encoding="utf-8") as handle:
            parsed = json.load(handle)

        if not isinstance(parsed, dict):
            return json.loads(json.dumps(DEFAULT_STATE))

        merged = json.loads(json.dumps(DEFAULT_STATE))
        merged.update(parsed)
        if not isinstance(merged.get("products"), dict):
            merged["products"] = {}
        return merged

    def get_product(self, handle: str) -> dict[str, Any]:
        products = self.data.setdefault("products", {})
        return products.setdefault(
            handle,
            {
                "shopify_product_id": None,
                "variants_by_handle_sku": {},
                "images": {},
            },
        )

    def get_product_id(self, handle: str) -> str | None:
        return self.get_product(handle).get("shopify_product_id")

    def set_product_id(self, handle: str, product_id: str) -> None:
        self.get_product(handle)["shopify_product_id"] = product_id

    @staticmethod
    def _variant_key(handle: str, sku: str) -> str:
        return f"{handle}::{sku}"

    def _variant_map(self, handle: str) -> dict[str, Any]:
        product = self.get_product(handle)
        composite_map = product.get("variants_by_handle_sku")
        if not isinstance(composite_map, dict):
            composite_map = {}
            product["variants_by_handle_sku"] = composite_map

        # Backward compatibility migration from old state shape.
        old_map = product.get("variants_by_sku")
        if isinstance(old_map, dict):
            for sku, value in old_map.items():
                if not isinstance(sku, str):
                    continue
                composite_map.setdefault(self._variant_key(handle, sku), value)
            product.pop("variants_by_sku", None)

        return composite_map

    def get_variant_id(self, handle: str, sku: str) -> str | None:
        variants = self._variant_map(handle)
        value = variants.get(self._variant_key(handle, sku))
        if isinstance(value, dict):
            return value.get("shopify_variant_id")
        return None

    def set_variant_id(self, handle: str, sku: str, variant_id: str) -> None:
        variants = self._variant_map(handle)
        variants[self._variant_key(handle, sku)] = {"shopify_variant_id": variant_id}

    def get_images(self, handle: str) -> dict[str, Any]:
        return self.get_product(handle).setdefault("images", {})

    def set_image(
        self,
        handle: str,
        filename: str,
        *,
        last_hash: str,
        shopify_media_id: str | None,
        position: int,
        last_uploaded_at: str | None = None,
    ) -> None:
        images = self.get_images(handle)
        images[filename] = {
            "last_hash": last_hash,
            "shopify_media_id": shopify_media_id,
            "position": position,
            "last_uploaded_at": last_uploaded_at,
        }

    def remove_image(self, handle: str, filename: str) -> None:
        images = self.get_images(handle)
        images.pop(filename, None)

    def mark_last_run(self) -> None:
        self.data["last_run_at"] = datetime.now(timezone.utc).isoformat()

    def save(self) -> None:
        temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(self.data, handle, indent=2, sort_keys=True)
            handle.write("\n")
        temp_path.replace(self.path)
