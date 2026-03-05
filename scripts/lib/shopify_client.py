"""Shopify Admin GraphQL client for catalog sync."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from scripts.lib.diff import diff_collections
from scripts.lib.retry import with_retry

LOGGER = logging.getLogger(__name__)


class ShopifyAPIError(RuntimeError):
    """Raised for non-retryable Shopify API errors."""


@dataclass
class RetryableHTTPError(Exception):
    status_code: int
    message: str

    def __str__(self) -> str:
        return f"HTTP {self.status_code}: {self.message}"


class ShopifyClient:
    def __init__(
        self,
        store_domain: str,
        access_token: str,
        api_version: str,
        timeout_seconds: int = 60,
    ) -> None:
        self.store_domain = store_domain
        self.access_token = access_token
        self.api_version = api_version
        self.timeout_seconds = timeout_seconds
        self.endpoint = (
            f"https://{self.store_domain}/admin/api/{self.api_version}/graphql.json"
        )

    def _is_retryable_exception(self, exc: BaseException) -> bool:
        if isinstance(exc, RetryableHTTPError):
            return exc.status_code == 429 or exc.status_code >= 500
        if isinstance(exc, requests.RequestException):
            return True
        return False

    def _graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {"query": query, "variables": variables or {}}
        headers = {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": self.access_token,
        }

        def _call() -> dict[str, Any]:
            response = requests.post(
                self.endpoint,
                headers=headers,
                data=json.dumps(payload),
                timeout=self.timeout_seconds,
            )
            if response.status_code == 429 or response.status_code >= 500:
                raise RetryableHTTPError(response.status_code, response.text)
            if response.status_code >= 400:
                raise ShopifyAPIError(
                    f"Shopify GraphQL request failed ({response.status_code}): {response.text}"
                )

            parsed = response.json()
            if parsed.get("errors"):
                raise ShopifyAPIError(f"Shopify GraphQL errors: {parsed['errors']}")
            return parsed

        parsed = with_retry(_call, self._is_retryable_exception)
        return parsed.get("data", {})

    def _normalize_product_node(self, node: dict[str, Any]) -> dict[str, Any]:
        variants: list[dict[str, Any]] = []
        for variant in (node.get("variants") or {}).get("nodes", []):
            variants.append(
                {
                    "id": variant.get("id"),
                    "sku": variant.get("sku"),
                    "price": variant.get("price"),
                    "compare_at_price": variant.get("compareAtPrice"),
                    "barcode": variant.get("barcode"),
                    "selected_options": variant.get("selectedOptions", []),
                }
            )

        collections = (node.get("collections") or {}).get("nodes", [])

        media_nodes = (node.get("media") or {}).get("nodes", [])
        media: list[dict[str, Any]] = []
        for index, media_node in enumerate(media_nodes, start=1):
            alt = media_node.get("alt") or ""
            filename = self.filename_from_alt(alt)
            media.append(
                {
                    "id": media_node.get("id"),
                    "alt": alt,
                    "filename": filename,
                    "position": index,
                    "status": media_node.get("status"),
                }
            )

        return {
            "id": node.get("id"),
            "handle": node.get("handle"),
            "title": node.get("title"),
            "description_html": node.get("descriptionHtml"),
            "vendor": node.get("vendor"),
            "product_type": node.get("productType"),
            "tags": node.get("tags", []),
            "variants": variants,
            "collections": collections,
            "media": media,
        }

    def query_product_by_handle(self, handle: str) -> dict[str, Any] | None:
        query = """
        query ProductByHandle($handle: String!) {
          productByHandle(handle: $handle) {
            id
            handle
            title
            descriptionHtml
            vendor
            productType
            tags
            variants(first: 250) {
              nodes {
                id
                sku
                price
                compareAtPrice
                barcode
                selectedOptions {
                  name
                  value
                }
              }
            }
            collections(first: 250) {
              nodes {
                id
                handle
              }
            }
            media(first: 250) {
              nodes {
                id
                alt
                status
                ... on MediaImage {
                  image {
                    url
                  }
                }
              }
            }
          }
        }
        """

        try:
            data = self._graphql(query, {"handle": handle})
            node = data.get("productByHandle")
            if not node:
                return None
            return self._normalize_product_node(node)
        except ShopifyAPIError as exc:
            # Fallback for shops/APIs where productByHandle is unavailable.
            if "productByHandle" not in str(exc):
                raise

        fallback_query = """
        query ProductBySearch($search: String!) {
          products(first: 1, query: $search) {
            nodes {
              id
              handle
              title
              descriptionHtml
              vendor
              productType
              tags
              variants(first: 250) {
                nodes {
                  id
                  sku
                  price
                  compareAtPrice
                  barcode
                  selectedOptions {
                    name
                    value
                  }
                }
              }
              collections(first: 250) {
                nodes {
                  id
                  handle
                }
              }
              media(first: 250) {
                nodes {
                  id
                  alt
                  status
                  ... on MediaImage {
                    image {
                      url
                    }
                  }
                }
              }
            }
          }
        }
        """
        data = self._graphql(fallback_query, {"search": f"handle:{handle}"})
        nodes = (data.get("products") or {}).get("nodes", [])
        if not nodes:
            return None
        return self._normalize_product_node(nodes[0])

    def product_set_upsert(self, identifier_handle: str, product_input: dict[str, Any]) -> dict[str, Any]:
        mutation = """
        mutation ProductSetUpsert($identifier: ProductSetIdentifiers!, $input: ProductSetInput!) {
          productSet(identifier: $identifier, input: $input) {
            product {
              id
              handle
              title
              descriptionHtml
              vendor
              productType
              tags
              variants(first: 250) {
                nodes {
                  id
                  sku
                  price
                  compareAtPrice
                  barcode
                }
              }
            }
            userErrors {
              field
              message
            }
          }
        }
        """

        variables = {
            "identifier": {"handle": identifier_handle},
            "input": product_input,
        }
        data = self._graphql(mutation, variables)
        payload = data.get("productSet") or {}
        user_errors = payload.get("userErrors") or []
        if user_errors:
            raise ShopifyAPIError(f"productSet userErrors: {user_errors}")

        product = payload.get("product")
        if not product:
            raise ShopifyAPIError("productSet returned no product payload")

        return self._normalize_product_node(product)

    def list_product_media(self, product_id: str) -> list[dict[str, Any]]:
        query = """
        query ProductMedia($id: ID!) {
          product(id: $id) {
            media(first: 250) {
              nodes {
                id
                alt
                status
                ... on MediaImage {
                  image {
                    url
                  }
                }
              }
            }
          }
        }
        """

        data = self._graphql(query, {"id": product_id})
        product = data.get("product") or {}
        media_nodes = (product.get("media") or {}).get("nodes", [])
        media: list[dict[str, Any]] = []
        for index, node in enumerate(media_nodes, start=1):
            alt = node.get("alt") or ""
            media.append(
                {
                    "id": node.get("id"),
                    "alt": alt,
                    "filename": self.filename_from_alt(alt),
                    "position": index,
                    "status": node.get("status"),
                }
            )
        return media

    def staged_uploads_create(self, filename: str, mime_type: str, file_size: int) -> dict[str, Any]:
        mutation = """
        mutation CreateStagedUpload($input: [StagedUploadInput!]!) {
          stagedUploadsCreate(input: $input) {
            stagedTargets {
              url
              resourceUrl
              parameters {
                name
                value
              }
            }
            userErrors {
              field
              message
            }
          }
        }
        """

        variables = {
            "input": [
                {
                    "filename": filename,
                    "mimeType": mime_type,
                    "resource": "IMAGE",
                    "httpMethod": "POST",
                    "fileSize": str(file_size),
                }
            ]
        }
        data = self._graphql(mutation, variables)
        payload = data.get("stagedUploadsCreate") or {}
        user_errors = payload.get("userErrors") or []
        if user_errors:
            raise ShopifyAPIError(f"stagedUploadsCreate userErrors: {user_errors}")

        targets = payload.get("stagedTargets") or []
        if not targets:
            raise ShopifyAPIError("stagedUploadsCreate returned no staged targets")

        target = targets[0]
        params = {item["name"]: item["value"] for item in target.get("parameters", [])}
        return {
            "url": target.get("url"),
            "resource_url": target.get("resourceUrl"),
            "parameters": params,
        }

    def upload_to_staged_target(
        self,
        *,
        url: str,
        form_fields: dict[str, str],
        bytes_payload: bytes,
    ) -> None:
        def _call() -> None:
            files = {"file": ("upload", bytes_payload)}
            response = requests.post(
                url,
                data=form_fields,
                files=files,
                timeout=self.timeout_seconds,
            )
            if response.status_code == 429 or response.status_code >= 500:
                raise RetryableHTTPError(response.status_code, response.text)
            if response.status_code >= 400:
                raise ShopifyAPIError(
                    f"Upload to staged target failed ({response.status_code}): {response.text}"
                )

        with_retry(_call, self._is_retryable_exception)

    def product_create_media(self, product_id: str, media_inputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        mutation = """
        mutation CreateMedia($productId: ID!, $media: [CreateMediaInput!]!) {
          productCreateMedia(productId: $productId, media: $media) {
            media {
              ... on MediaImage {
                id
                alt
                status
              }
            }
            mediaUserErrors {
              field
              message
            }
          }
        }
        """

        data = self._graphql(mutation, {"productId": product_id, "media": media_inputs})
        payload = data.get("productCreateMedia") or {}
        user_errors = payload.get("mediaUserErrors") or []
        if user_errors:
            raise ShopifyAPIError(f"productCreateMedia userErrors: {user_errors}")

        created_media = payload.get("media") or []
        return [
            {
                "id": item.get("id"),
                "alt": item.get("alt"),
                "status": item.get("status"),
            }
            for item in created_media
            if isinstance(item, dict)
        ]

    def product_delete_media(self, product_id: str, media_ids: list[str]) -> list[str]:
        if not media_ids:
            return []

        mutation = """
        mutation DeleteMedia($productId: ID!, $mediaIds: [ID!]!) {
          productDeleteMedia(productId: $productId, mediaIds: $mediaIds) {
            deletedMediaIds
            mediaUserErrors {
              field
              message
            }
          }
        }
        """

        data = self._graphql(mutation, {"productId": product_id, "mediaIds": media_ids})
        payload = data.get("productDeleteMedia") or {}
        user_errors = payload.get("mediaUserErrors") or []
        if user_errors:
            raise ShopifyAPIError(f"productDeleteMedia userErrors: {user_errors}")

        return payload.get("deletedMediaIds") or []

    def product_reorder_media(self, product_id: str, moves: list[dict[str, Any]]) -> None:
        if not moves:
            return

        mutation = """
        mutation ReorderMedia($id: ID!, $moves: [MoveInput!]!) {
          productReorderMedia(id: $id, moves: $moves) {
            job {
              id
              done
            }
            mediaUserErrors {
              field
              message
            }
          }
        }
        """

        data = self._graphql(mutation, {"id": product_id, "moves": moves})
        payload = data.get("productReorderMedia") or {}
        user_errors = payload.get("mediaUserErrors") or []
        if user_errors:
            raise ShopifyAPIError(f"productReorderMedia userErrors: {user_errors}")

    def _query_collection_by_handle(self, handle: str) -> dict[str, Any] | None:
        query = """
        query CollectionByHandle($query: String!) {
          collections(first: 1, query: $query) {
            nodes {
              id
              handle
              title
              ruleSet {
                appliedDisjunctively
              }
            }
          }
        }
        """
        data = self._graphql(query, {"query": f"handle:{handle}"})
        nodes = (data.get("collections") or {}).get("nodes", [])
        if not nodes:
            return None
        return nodes[0]

    def get_collection_by_handle(self, handle: str) -> dict[str, Any] | None:
        """Return collection node by handle without creating it."""
        return self._query_collection_by_handle(handle)

    @staticmethod
    def _titleize_handle(handle: str) -> str:
        words = [word for word in re.split(r"[-_]+", handle) if word]
        if not words:
            return handle
        return " ".join(word[:1].upper() + word[1:] for word in words)

    def resolve_or_create_custom_collection_by_handle(self, handle: str) -> str:
        existing = self._query_collection_by_handle(handle)
        if existing:
            return existing["id"]

        mutation = """
        mutation CreateCollection($input: CollectionInput!) {
          collectionCreate(input: $input) {
            collection {
              id
              handle
            }
            userErrors {
              field
              message
            }
          }
        }
        """
        input_payload = {
            "title": self._titleize_handle(handle),
            "handle": handle,
        }
        data = self._graphql(mutation, {"input": input_payload})
        payload = data.get("collectionCreate") or {}
        user_errors = payload.get("userErrors") or []
        if user_errors:
            raise ShopifyAPIError(f"collectionCreate userErrors: {user_errors}")

        collection = payload.get("collection")
        if not collection:
            raise ShopifyAPIError(f"Failed to create collection for handle '{handle}'")
        return collection["id"]

    def _get_product_collection_ids(self, product_id: str) -> set[str]:
        query = """
        query ProductCollections($id: ID!) {
          product(id: $id) {
            collections(first: 250) {
              nodes {
                id
              }
            }
          }
        }
        """
        data = self._graphql(query, {"id": product_id})
        nodes = ((data.get("product") or {}).get("collections") or {}).get("nodes", [])
        return {node["id"] for node in nodes if node.get("id")}

    def _collection_add_products(self, collection_id: str, product_ids: list[str]) -> None:
        mutation = """
        mutation CollectionAddProducts($id: ID!, $productIds: [ID!]!) {
          collectionAddProductsV2(id: $id, productIds: $productIds) {
            job {
              id
            }
            userErrors {
              field
              message
            }
          }
        }
        """
        data = self._graphql(mutation, {"id": collection_id, "productIds": product_ids})
        payload = data.get("collectionAddProductsV2") or {}
        user_errors = payload.get("userErrors") or []
        if user_errors:
            raise ShopifyAPIError(f"collectionAddProductsV2 userErrors: {user_errors}")

    def _collection_remove_products(self, collection_id: str, product_ids: list[str]) -> None:
        mutation = """
        mutation CollectionRemoveProducts($id: ID!, $productIds: [ID!]!) {
          collectionRemoveProducts(id: $id, productIds: $productIds) {
            job {
              id
            }
            userErrors {
              field
              message
            }
          }
        }
        """
        data = self._graphql(mutation, {"id": collection_id, "productIds": product_ids})
        payload = data.get("collectionRemoveProducts") or {}
        user_errors = payload.get("userErrors") or []
        if user_errors:
            raise ShopifyAPIError(f"collectionRemoveProducts userErrors: {user_errors}")

    def sync_product_collections(
        self,
        product_id: str,
        desired_collection_ids: set[str],
        allow_deletes: bool,
    ) -> dict[str, list[str]]:
        current_collection_ids = self._get_product_collection_ids(product_id)
        to_add, to_remove = diff_collections(desired_collection_ids, current_collection_ids)

        for collection_id in sorted(to_add):
            self._collection_add_products(collection_id, [product_id])

        removed: list[str] = []
        skipped: list[str] = []
        for collection_id in sorted(to_remove):
            if allow_deletes:
                self._collection_remove_products(collection_id, [product_id])
                removed.append(collection_id)
            else:
                skipped.append(collection_id)

        return {
            "added": sorted(to_add),
            "removed": removed,
            "skipped_removals": skipped,
        }

    @staticmethod
    def make_media_alt(filename: str) -> str:
        return f"sync:{filename}"

    @staticmethod
    def filename_from_alt(alt_text: str | None) -> str | None:
        if not alt_text:
            return None
        prefix = "sync:"
        if not alt_text.startswith(prefix):
            return None
        filename = alt_text[len(prefix) :].strip()
        return filename or None

    @staticmethod
    def read_file_bytes(path: Path) -> bytes:
        return path.read_bytes()
