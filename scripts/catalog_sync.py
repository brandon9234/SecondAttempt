#!/usr/bin/env python3
"""Incremental catalog sync engine for Shopify Admin API."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.lib.catalog import CatalogValidationError, CatalogProduct, load_catalog  # noqa: E402
from scripts.lib.diff import diff_collections, diff_media, product_needs_update  # noqa: E402
from scripts.lib.env_utils import first_env, load_env_file, parse_bool  # noqa: E402
from scripts.lib.hashing import sha256_file  # noqa: E402
from scripts.lib.state_store import SyncStateStore  # noqa: E402

LOGGER = logging.getLogger("catalog_sync")

@dataclass
class SyncConfig:
    shop_domain: str | None
    admin_token: str | None
    api_version: str
    dry_run: bool
    enable_direct_upload: bool
    cdn_base_url: str | None
    allow_deletes: bool
    log_level: str

def read_config() -> SyncConfig:
    load_env_file(ROOT)
    return SyncConfig(
        shop_domain=first_env("TARGET_SHOPIFY_STORE_DOMAIN", "SHOPIFY_STORE_DOMAIN"),
        admin_token=first_env("TARGET_SHOPIFY_ADMIN_ACCESS_TOKEN", "SHOPIFY_ADMIN_ACCESS_TOKEN"),
        api_version=first_env("TARGET_SHOPIFY_API_VERSION", "SHOPIFY_API_VERSION") or "2025-10",
        dry_run=parse_bool(first_env("DRY_RUN"), default=True),
        enable_direct_upload=parse_bool(first_env("ENABLE_DIRECT_UPLOAD"), default=True),
        cdn_base_url=first_env("CDN_BASE_URL"),
        allow_deletes=parse_bool(first_env("ALLOW_DELETES"), default=False),
        log_level=(first_env("LOG_LEVEL") or "INFO").upper(),
    )


def configure_logging(log_level: str) -> None:
    logging.basicConfig(level=getattr(logging, log_level, logging.INFO), format="%(levelname)s: %(message)s")


def has_credentials(config: SyncConfig) -> bool:
    return bool(config.shop_domain and config.admin_token)


def build_desired_product_payload(
    product: CatalogProduct,
    variant_id_by_sku: dict[str, str],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "handle": product.handle,
        "title": product.title,
        "descriptionHtml": product.description_html,
        "vendor": product.vendor,
        "productType": product.product_type,
        "tags": product.tags,
    }

    variants_payload: list[dict[str, Any]] = []
    option_count = 0
    for variant in product.variants:
        option_count = max(option_count, len(variant.get("option_values", [])))

    use_options = len(product.variants) > 1 or option_count > 0
    option_values_by_index: list[list[str]] = [[] for _ in range(option_count)]

    for position, variant in enumerate(product.variants, start=1):
        variant_payload: dict[str, Any] = {
            "sku": variant["sku"],
            "price": variant["price"],
            "position": position,
        }

        if variant.get("compare_at_price"):
            variant_payload["compareAtPrice"] = variant["compare_at_price"]
        if variant.get("barcode"):
            variant_payload["barcode"] = variant["barcode"]

        existing_variant_id = variant_id_by_sku.get(variant["sku"])
        if existing_variant_id:
            variant_payload["id"] = existing_variant_id

        if use_options and option_count:
            option_values = variant.get("option_values", [])
            variant_payload["optionValues"] = []
            for index in range(option_count):
                value = option_values[index]
                option_values_by_index[index].append(value)
                variant_payload["optionValues"].append(
                    {
                        "optionName": f"Option {index + 1}",
                        "name": value,
                    }
                )

        variants_payload.append(variant_payload)

    payload["variants"] = variants_payload

    if use_options and option_count:
        payload["productOptions"] = []
        for index, values in enumerate(option_values_by_index, start=1):
            unique_values = []
            seen = set()
            for value in values:
                if value not in seen:
                    seen.add(value)
                    unique_values.append(value)
            payload["productOptions"].append(
                {
                    "name": f"Option {index}",
                    "position": index,
                    "values": [{"name": value} for value in unique_values],
                }
            )

    return payload


def build_desired_media(product: CatalogProduct) -> list[dict[str, Any]]:
    desired_media: list[dict[str, Any]] = []
    for image in product.images:
        desired_media.append(
            {
                "filename": image["filename"],
                "path": image["path"],
                "position": image["position"],
                "mime_type": image["mime_type"],
                "sha256": sha256_file(image["path"]),
            }
        )
    return desired_media


def build_cdn_url(cdn_base_url: str, handle: str, filename: str) -> str:
    return f"{cdn_base_url.rstrip('/')}/{handle}/{filename}"


def update_variant_state(
    state: SyncStateStore,
    handle: str,
    remote_variants: list[dict[str, Any]],
) -> None:
    for variant in remote_variants:
        sku = variant.get("sku")
        variant_id = variant.get("id")
        if sku and variant_id:
            state.set_variant_id(handle, sku, variant_id)


def main() -> int:
    config = read_config()
    configure_logging(config.log_level)

    products_root = ROOT / "products"
    state_path = ROOT / "catalog" / "sync_state.json"

    try:
        products = load_catalog(products_root)
    except CatalogValidationError as exc:
        LOGGER.error("catalog_sync aborted due to validation errors:")
        for error in exc.errors:
            LOGGER.error("- %s", error)
        return 1

    if not products:
        LOGGER.info("No products found under %s; nothing to sync.", products_root)
        return 0

    if not config.enable_direct_upload and not config.cdn_base_url:
        LOGGER.error("ENABLE_DIRECT_UPLOAD=false requires CDN_BASE_URL to be set.")
        return 1

    creds_available = has_credentials(config)
    if not creds_available and config.dry_run:
        print(
            "DRY_RUN=true and Shopify credentials are missing. "
            "Catalog parsed successfully; skipping Shopify API calls."
        )
        print(f"Products discovered: {len(products)}")
        return 0

    if not creds_available:
        LOGGER.error(
            "Missing target Shopify credentials. Set TARGET_SHOPIFY_STORE_DOMAIN and "
            "TARGET_SHOPIFY_ADMIN_ACCESS_TOKEN in .env"
        )
        return 1

    from scripts.lib.shopify_client import ShopifyAPIError, ShopifyClient  # noqa: WPS433,E402

    client = ShopifyClient(
        store_domain=config.shop_domain or "",
        access_token=config.admin_token or "",
        api_version=config.api_version,
    )

    state = SyncStateStore(state_path)

    total_mutations = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    for product in products:
        LOGGER.info("Syncing product handle='%s'", product.handle)

        remote_product = client.query_product_by_handle(product.handle)
        remote_variant_ids = {
            variant["sku"]: variant["id"]
            for variant in (remote_product or {}).get("variants", [])
            if variant.get("sku") and variant.get("id")
        }

        state_variant_ids = {}
        for variant in product.variants:
            sku = variant["sku"]
            state_variant_id = state.get_variant_id(product.handle, sku)
            if state_variant_id:
                state_variant_ids[sku] = state_variant_id

        variant_id_by_sku = {**state_variant_ids, **remote_variant_ids}

        desired_product_view = {
            "title": product.title,
            "description_html": product.description_html,
            "vendor": product.vendor,
            "product_type": product.product_type,
            "tags": product.tags,
            "variants": product.variants,
        }

        needs_product_upsert = product_needs_update(desired_product_view, remote_product)
        product_id: str | None = (remote_product or {}).get("id") or state.get_product_id(product.handle)

        if needs_product_upsert:
            payload = build_desired_product_payload(product, variant_id_by_sku)
            if config.dry_run:
                LOGGER.info("DRY_RUN: would upsert product '%s'", product.handle)
            else:
                try:
                    upserted = client.product_set_upsert(product.handle, payload)
                except ShopifyAPIError as exc:
                    LOGGER.error("Failed product upsert for '%s': %s", product.handle, exc)
                    return 1
                remote_product = upserted
                product_id = upserted.get("id")
                total_mutations += 1
        else:
            LOGGER.info("No product core/variant changes for '%s'", product.handle)

        if not product_id:
            LOGGER.error("Unable to resolve Shopify product id for '%s'", product.handle)
            return 1

        if not config.dry_run:
            state.set_product_id(product.handle, product_id)
            update_variant_state(state, product.handle, (remote_product or {}).get("variants", []))

        desired_collection_handles = product.collections
        desired_collection_ids: set[str] = set()
        if config.dry_run:
            # Dry run never mutates collections; resolve known IDs where possible.
            for collection_handle in desired_collection_handles:
                existing = client.get_collection_by_handle(collection_handle)
                if existing:
                    desired_collection_ids.add(existing["id"])
                else:
                    LOGGER.info(
                        "DRY_RUN: would create missing custom collection '%s'",
                        collection_handle,
                    )

            current_collection_ids = {
                collection.get("id")
                for collection in (remote_product or {}).get("collections", [])
                if collection.get("id")
            }
            to_add, to_remove = diff_collections(desired_collection_ids, current_collection_ids)
            if to_add:
                LOGGER.info(
                    "DRY_RUN: would add product '%s' to %d collection(s)",
                    product.handle,
                    len(to_add),
                )
            if to_remove:
                if config.allow_deletes:
                    LOGGER.info(
                        "DRY_RUN: would remove product '%s' from %d collection(s)",
                        product.handle,
                        len(to_remove),
                    )
                else:
                    LOGGER.warning(
                        "DRY_RUN: collection removals for '%s' skipped because ALLOW_DELETES=false",
                        product.handle,
                    )
        else:
            for collection_handle in desired_collection_handles:
                try:
                    collection_id = client.resolve_or_create_custom_collection_by_handle(collection_handle)
                except ShopifyAPIError as exc:
                    LOGGER.error(
                        "Collection resolve/create failed for handle='%s' product='%s': %s",
                        collection_handle,
                        product.handle,
                        exc,
                    )
                    return 1
                desired_collection_ids.add(collection_id)

            try:
                collection_actions = client.sync_product_collections(
                    product_id=product_id,
                    desired_collection_ids=desired_collection_ids,
                    allow_deletes=config.allow_deletes,
                )
            except ShopifyAPIError as exc:
                LOGGER.error("Failed syncing collections for '%s': %s", product.handle, exc)
                return 1

            if collection_actions["added"]:
                total_mutations += len(collection_actions["added"])
            if collection_actions["removed"]:
                total_mutations += len(collection_actions["removed"])
            if collection_actions["skipped_removals"]:
                LOGGER.warning(
                    "Collection removals skipped for '%s' due to ALLOW_DELETES=false: %s",
                    product.handle,
                    ", ".join(collection_actions["skipped_removals"]),
                )

        desired_media = build_desired_media(product)

        remote_media = client.list_product_media(product_id)
        remote_by_filename = {
            media["filename"]: media for media in remote_media if media.get("filename")
        }

        state_images = state.get_images(product.handle)
        media_changes = diff_media(desired_media, state_images, remote_by_filename)
        to_upload = media_changes["to_upload"]
        to_delete = media_changes["to_delete"]

        if config.dry_run:
            if to_upload:
                LOGGER.info(
                    "DRY_RUN: would upload/replace %d media file(s) for '%s'",
                    len(to_upload),
                    product.handle,
                )
            if to_delete:
                if config.allow_deletes:
                    LOGGER.info(
                        "DRY_RUN: would delete %d removed media file(s) for '%s'",
                        len(to_delete),
                        product.handle,
                    )
                else:
                    LOGGER.warning(
                        "DRY_RUN: %d media file(s) removed locally for '%s' but ALLOW_DELETES=false",
                        len(to_delete),
                        product.handle,
                    )
        else:
            if config.allow_deletes:
                delete_ids = [item["remote_id"] for item in to_delete if item.get("remote_id")]
                if delete_ids:
                    try:
                        client.product_delete_media(product_id, delete_ids)
                    except ShopifyAPIError as exc:
                        LOGGER.error("Failed deleting media for '%s': %s", product.handle, exc)
                        return 1
                    total_mutations += len(delete_ids)
                for item in to_delete:
                    state.remove_image(product.handle, item["filename"])
            elif to_delete:
                LOGGER.warning(
                    "%d media file(s) removed locally for '%s' but ALLOW_DELETES=false",
                    len(to_delete),
                    product.handle,
                )

            for media in to_upload:
                filename = media["filename"]
                file_path: Path = media["path"]
                existing_media = remote_by_filename.get(filename)

                if existing_media and existing_media.get("id"):
                    try:
                        client.product_delete_media(product_id, [existing_media["id"]])
                    except ShopifyAPIError as exc:
                        LOGGER.error(
                            "Failed replacing existing media '%s' for '%s': %s",
                            filename,
                            product.handle,
                            exc,
                        )
                        return 1
                    total_mutations += 1

                if config.enable_direct_upload:
                    staged = client.staged_uploads_create(
                        filename=filename,
                        mime_type=media["mime_type"],
                        file_size=file_path.stat().st_size,
                    )
                    file_bytes = file_path.read_bytes()
                    client.upload_to_staged_target(
                        url=staged["url"],
                        form_fields=staged["parameters"],
                        bytes_payload=file_bytes,
                    )
                    original_source = staged["resource_url"]
                else:
                    original_source = build_cdn_url(config.cdn_base_url or "", product.handle, filename)

                created_media = client.product_create_media(
                    product_id,
                    [
                        {
                            "alt": client.make_media_alt(filename),
                            "mediaContentType": "IMAGE",
                            "originalSource": original_source,
                        }
                    ],
                )
                created_media_id = created_media[0]["id"] if created_media else None

                state.set_image(
                    product.handle,
                    filename,
                    last_hash=media["sha256"],
                    shopify_media_id=created_media_id,
                    position=media["position"],
                    last_uploaded_at=now_iso,
                )
                total_mutations += 1

            refreshed_media = client.list_product_media(product_id)
            refreshed_by_filename = {
                item["filename"]: item for item in refreshed_media if item.get("filename")
            }

            moves: list[dict[str, Any]] = []
            for media in desired_media:
                filename = media["filename"]
                remote_entry = refreshed_by_filename.get(filename)
                if not remote_entry or not remote_entry.get("id"):
                    continue
                desired_position = media["position"]
                current_position = int(remote_entry.get("position") or 0)
                if current_position != desired_position:
                    moves.append(
                        {
                            "id": remote_entry["id"],
                            "newPosition": str(desired_position - 1),
                        }
                    )

                existing_state_entry = state_images.get(filename, {})
                state.set_image(
                    product.handle,
                    filename,
                    last_hash=media["sha256"],
                    shopify_media_id=remote_entry["id"],
                    position=desired_position,
                    last_uploaded_at=existing_state_entry.get("last_uploaded_at"),
                )

            if moves:
                try:
                    client.product_reorder_media(product_id, moves)
                except ShopifyAPIError as exc:
                    LOGGER.error("Failed reordering media for '%s': %s", product.handle, exc)
                    return 1
                total_mutations += 1

            latest_product = client.query_product_by_handle(product.handle)
            if latest_product:
                update_variant_state(state, product.handle, latest_product.get("variants", []))
                state.set_product_id(product.handle, latest_product["id"])

    if config.dry_run:
        LOGGER.info("DRY_RUN complete. Planned mutation count estimate: %d", total_mutations)
        return 0

    state.mark_last_run()
    state.save()
    LOGGER.info("Sync complete. Executed mutation calls: %d", total_mutations)
    LOGGER.info("Updated sync state at %s", state_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
