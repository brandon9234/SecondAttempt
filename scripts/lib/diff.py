"""Diff helpers used by catalog_sync."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


def _normalize_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_price(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        return format(Decimal(str(value)).quantize(Decimal("0.01")), "f")
    except (InvalidOperation, ValueError):
        return str(value)


def _normalize_tags(tags: list[str]) -> list[str]:
    return sorted({tag.strip() for tag in tags if tag.strip()})


def product_needs_update(desired: dict[str, Any], remote: dict[str, Any] | None) -> bool:
    """Return True when product/variant fields differ from remote state."""
    if remote is None:
        return True

    if _normalize_string(desired.get("title")) != _normalize_string(remote.get("title")):
        return True
    if _normalize_string(desired.get("description_html")) != _normalize_string(remote.get("description_html")):
        return True
    if _normalize_string(desired.get("vendor")) != _normalize_string(remote.get("vendor")):
        return True
    if _normalize_string(desired.get("product_type")) != _normalize_string(remote.get("product_type")):
        return True

    if _normalize_tags(desired.get("tags", [])) != _normalize_tags(remote.get("tags", [])):
        return True

    desired_variants = {variant["sku"]: variant for variant in desired.get("variants", []) if variant.get("sku")}
    remote_variants = {variant["sku"]: variant for variant in remote.get("variants", []) if variant.get("sku")}

    if set(desired_variants.keys()) != set(remote_variants.keys()):
        return True

    for sku, desired_variant in desired_variants.items():
        remote_variant = remote_variants[sku]
        if _normalize_price(desired_variant.get("price")) != _normalize_price(remote_variant.get("price")):
            return True
        if _normalize_price(desired_variant.get("compare_at_price")) != _normalize_price(
            remote_variant.get("compare_at_price")
        ):
            return True
        if _normalize_string(desired_variant.get("barcode")) != _normalize_string(remote_variant.get("barcode")):
            return True

    return False


def diff_collections(desired_ids: set[str], current_ids: set[str]) -> tuple[set[str], set[str]]:
    to_add = desired_ids - current_ids
    to_remove = current_ids - desired_ids
    return to_add, to_remove


def diff_media(
    desired_media: list[dict[str, Any]],
    state_images: dict[str, Any],
    remote_by_filename: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    desired_names = {item["filename"] for item in desired_media}
    upload: list[dict[str, Any]] = []
    unchanged: list[dict[str, Any]] = []

    for item in desired_media:
        filename = item["filename"]
        expected_hash = item["sha256"]
        state_entry = state_images.get(filename, {}) if isinstance(state_images, dict) else {}
        remote_entry = remote_by_filename.get(filename)

        hash_matches = state_entry.get("last_hash") == expected_hash
        remote_exists = bool(remote_entry and remote_entry.get("id"))

        if hash_matches and remote_exists:
            unchanged.append(item)
        else:
            upload.append(item)

    known_remote_names = set(remote_by_filename.keys())
    known_state_names = set(state_images.keys()) if isinstance(state_images, dict) else set()
    delete_candidates = (known_remote_names | known_state_names) - desired_names

    to_delete: list[dict[str, Any]] = []
    for filename in sorted(delete_candidates):
        remote_entry = remote_by_filename.get(filename, {})
        state_entry = state_images.get(filename, {}) if isinstance(state_images, dict) else {}
        to_delete.append(
            {
                "filename": filename,
                "remote_id": remote_entry.get("id") or state_entry.get("shopify_media_id"),
            }
        )

    return {
        "to_upload": upload,
        "unchanged": unchanged,
        "to_delete": to_delete,
    }
