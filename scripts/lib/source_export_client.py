"""Shopify Admin REST client for source export and content sync flows."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests

from scripts.lib.retry import with_retry


class ShopifyRestError(RuntimeError):
    """Raised when Shopify REST returns a non-retryable error."""


@dataclass
class RetryableHTTPError(Exception):
    status_code: int
    message: str

    def __str__(self) -> str:
        return f"HTTP {self.status_code}: {self.message}"


class ShopifyRESTClient:
    """Thin Shopify REST wrapper with pagination and retries."""

    def __init__(
        self,
        *,
        store_domain: str,
        access_token: str,
        api_version: str,
        timeout_seconds: int = 60,
    ) -> None:
        self.store_domain = store_domain
        self.access_token = access_token
        self.api_version = api_version
        self.timeout_seconds = timeout_seconds
        self.base_rest_url = f"https://{store_domain}/admin/api/{api_version}"
        self.base_graphql_url = f"{self.base_rest_url}/graphql.json"

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": self.access_token,
        }

    @staticmethod
    def _is_retryable_exception(exc: BaseException) -> bool:
        if isinstance(exc, RetryableHTTPError):
            return exc.status_code == 429 or exc.status_code >= 500
        if isinstance(exc, requests.RequestException):
            return True
        return False

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        absolute_url: str | None = None,
        expected_statuses: set[int] | None = None,
    ) -> requests.Response:
        url = absolute_url or f"{self.base_rest_url}{path}"
        accepted = expected_statuses or {200}

        def _call() -> requests.Response:
            response = requests.request(
                method=method,
                url=url,
                headers=self._headers(),
                params=params,
                data=json.dumps(payload) if payload is not None else None,
                timeout=self.timeout_seconds,
            )

            if response.status_code == 429 or response.status_code >= 500:
                raise RetryableHTTPError(response.status_code, response.text)
            if response.status_code not in accepted:
                raise ShopifyRestError(
                    f"{method} {url} failed ({response.status_code}): {response.text}"
                )
            return response

        return with_retry(_call, self._is_retryable_exception)

    def get_json(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self._request("GET", path, params=params, expected_statuses={200})
        return response.json()

    def post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._request("POST", path, payload=payload, expected_statuses={200, 201})
        return response.json()

    def put_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._request("PUT", path, payload=payload, expected_statuses={200})
        return response.json()

    def delete(self, path: str) -> None:
        self._request("DELETE", path, expected_statuses={200})

    @staticmethod
    def _extract_next_link(response: requests.Response) -> str | None:
        link_header = response.headers.get("Link")
        if not link_header:
            return None
        parts = [part.strip() for part in link_header.split(",")]
        for part in parts:
            if 'rel="next"' not in part:
                continue
            if part.startswith("<") and ">" in part:
                return part[1 : part.index(">")]
        return None

    def get_paginated(self, path: str, key: str, *, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        next_url: str | None = None
        query_params = dict(params or {})
        if "limit" not in query_params:
            query_params["limit"] = 250

        while True:
            if next_url:
                parsed = urlparse(next_url)
                next_params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
                response = self._request(
                    "GET",
                    path="",
                    absolute_url=f"{parsed.scheme}://{parsed.netloc}{parsed.path}",
                    params=next_params,
                    expected_statuses={200},
                )
            else:
                response = self._request("GET", path, params=query_params, expected_statuses={200})

            parsed_json = response.json()
            chunk = parsed_json.get(key)
            if isinstance(chunk, list):
                merged.extend([item for item in chunk if isinstance(item, dict)])

            next_url = self._extract_next_link(response)
            if not next_url:
                break

        return merged

    def graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {"query": query, "variables": variables or {}}

        def _call() -> dict[str, Any]:
            response = requests.post(
                self.base_graphql_url,
                headers=self._headers(),
                data=json.dumps(payload),
                timeout=self.timeout_seconds,
            )
            if response.status_code == 429 or response.status_code >= 500:
                raise RetryableHTTPError(response.status_code, response.text)
            if response.status_code >= 400:
                raise ShopifyRestError(
                    f"GraphQL failed ({response.status_code}): {response.text}"
                )
            parsed = response.json()
            if parsed.get("errors"):
                raise ShopifyRestError(f"GraphQL errors: {parsed['errors']}")
            return parsed.get("data", {})

        return with_retry(_call, self._is_retryable_exception)

    def export_products(self) -> list[dict[str, Any]]:
        return self.get_paginated("/products.json", "products", params={"status": "any", "limit": 250})

    def export_custom_collections(self) -> list[dict[str, Any]]:
        return self.get_paginated("/custom_collections.json", "custom_collections")

    def export_smart_collections(self) -> list[dict[str, Any]]:
        return self.get_paginated("/smart_collections.json", "smart_collections")

    def export_collects(self) -> list[dict[str, Any]]:
        return self.get_paginated("/collects.json", "collects")

    def export_pages(self) -> list[dict[str, Any]]:
        return self.get_paginated("/pages.json", "pages")

    def export_blogs(self) -> list[dict[str, Any]]:
        return self.get_paginated("/blogs.json", "blogs")

    def export_articles_for_blog(self, blog_id: int | str) -> list[dict[str, Any]]:
        return self.get_paginated(f"/blogs/{blog_id}/articles.json", "articles")

    def export_policies(self) -> list[dict[str, Any]]:
        try:
            data = self.get_json("/policies.json")
        except ShopifyRestError:
            return []
        policies = data.get("policies")
        if isinstance(policies, list):
            return [policy for policy in policies if isinstance(policy, dict)]
        return []

    def export_menus(self) -> list[dict[str, Any]]:
        # REST-first; fallback to GraphQL when menus endpoint is unavailable.
        try:
            data = self.get_json("/menus.json")
            menus = data.get("menus")
            if isinstance(menus, list):
                return [menu for menu in menus if isinstance(menu, dict)]
        except ShopifyRestError:
            pass

        query = """
        query ExportMenus($cursor: String) {
          menus(first: 50, after: $cursor) {
            pageInfo {
              hasNextPage
              endCursor
            }
            nodes {
              id
              handle
              title
              items {
                id
                title
                type
                url
                resourceId
                items {
                  id
                  title
                  type
                  url
                  resourceId
                }
              }
            }
          }
        }
        """

        menus: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            data = self.graphql(query, {"cursor": cursor})
            payload = data.get("menus") or {}
            for node in payload.get("nodes", []):
                if isinstance(node, dict):
                    menus.append(node)
            page_info = payload.get("pageInfo") or {}
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")
            if not cursor:
                break

        return menus

    def export_shop(self) -> dict[str, Any]:
        data = self.get_json("/shop.json")
        shop = data.get("shop")
        return shop if isinstance(shop, dict) else {}

    def list_pages(self) -> list[dict[str, Any]]:
        return self.get_paginated("/pages.json", "pages")

    def create_page(self, page: dict[str, Any]) -> dict[str, Any]:
        return self.post_json("/pages.json", {"page": page})

    def update_page(self, page_id: int | str, page: dict[str, Any]) -> dict[str, Any]:
        return self.put_json(f"/pages/{page_id}.json", {"page": page})

    def list_blogs(self) -> list[dict[str, Any]]:
        return self.get_paginated("/blogs.json", "blogs")

    def create_blog(self, blog: dict[str, Any]) -> dict[str, Any]:
        return self.post_json("/blogs.json", {"blog": blog})

    def update_blog(self, blog_id: int | str, blog: dict[str, Any]) -> dict[str, Any]:
        return self.put_json(f"/blogs/{blog_id}.json", {"blog": blog})

    def list_articles(self, blog_id: int | str) -> list[dict[str, Any]]:
        return self.get_paginated(f"/blogs/{blog_id}/articles.json", "articles")

    def create_article(self, blog_id: int | str, article: dict[str, Any]) -> dict[str, Any]:
        return self.post_json(f"/blogs/{blog_id}/articles.json", {"article": article})

    def update_article(self, blog_id: int | str, article_id: int | str, article: dict[str, Any]) -> dict[str, Any]:
        return self.put_json(f"/blogs/{blog_id}/articles/{article_id}.json", {"article": article})

    def list_menus(self) -> list[dict[str, Any]]:
        return self.export_menus()

    def create_menu(self, menu: dict[str, Any]) -> dict[str, Any]:
        return self.post_json("/menus.json", {"menu": menu})

    def update_menu(self, menu_id: int | str, menu: dict[str, Any]) -> dict[str, Any]:
        return self.put_json(f"/menus/{menu_id}.json", {"menu": menu})

    def list_policies(self) -> list[dict[str, Any]]:
        return self.export_policies()

    def update_policy(self, policy_id: int | str, policy: dict[str, Any]) -> dict[str, Any]:
        return self.put_json(f"/policies/{policy_id}.json", {"policy": policy})
