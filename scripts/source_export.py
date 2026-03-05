#!/usr/bin/env python3
"""Export source Shopify store data into normalized raw artifacts."""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.lib.content import write_json  # noqa: E402
from scripts.lib.env_utils import first_env, load_env_file  # noqa: E402
from scripts.lib.source_export_client import ShopifyRESTClient, ShopifyRestError  # noqa: E402

LOGGER = logging.getLogger("source_export")


@dataclass
class ExportConfig:
    store_domain: str | None
    access_token: str | None
    api_version: str


def read_config() -> ExportConfig:
    load_env_file(ROOT)
    return ExportConfig(
        store_domain=first_env("SOURCE_SHOPIFY_STORE_DOMAIN"),
        access_token=first_env("SOURCE_SHOPIFY_ADMIN_ACCESS_TOKEN"),
        api_version=first_env("SOURCE_SHOPIFY_API_VERSION") or "2025-10",
    )


def _sort_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def _key(item: dict[str, Any]) -> tuple:
        return (
            str(item.get("id", "")),
            str(item.get("handle", "")),
            str(item.get("title", "")),
        )

    return sorted(items, key=_key)


def _save_raw(name: str, payload: Any) -> None:
    path = ROOT / "catalog" / "import_logs" / f"source_raw_{name}.json"
    if isinstance(payload, dict):
        write_json(path, payload)
        return

    wrapped = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "items": payload,
    }
    write_json(path, wrapped)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    config = read_config()

    if not config.store_domain or not config.access_token:
        LOGGER.error(
            "Missing source Shopify credentials. Set SOURCE_SHOPIFY_STORE_DOMAIN and "
            "SOURCE_SHOPIFY_ADMIN_ACCESS_TOKEN in .env"
        )
        return 1

    client = ShopifyRESTClient(
        store_domain=config.store_domain,
        access_token=config.access_token,
        api_version=config.api_version,
    )

    try:
        products = _sort_items(client.export_products())
        custom_collections = _sort_items(client.export_custom_collections())
        smart_collections = _sort_items(client.export_smart_collections())
        collects = _sort_items(client.export_collects())
        pages = _sort_items(client.export_pages())
        blogs = _sort_items(client.export_blogs())

        articles: list[dict[str, Any]] = []
        for blog in blogs:
            blog_id = blog.get("id")
            if blog_id is None:
                continue
            for article in client.export_articles_for_blog(blog_id):
                if isinstance(article, dict):
                    article = dict(article)
                    article["blog_id"] = blog_id
                    article["blog_handle"] = blog.get("handle")
                    articles.append(article)
        articles = _sort_items(articles)

        policies = _sort_items(client.export_policies())
        menus = _sort_items(client.export_menus())
        shop = client.export_shop()
    except ShopifyRestError as exc:
        LOGGER.error("Source export failed: %s", exc)
        return 1

    _save_raw("products", products)
    _save_raw("custom_collections", custom_collections)
    _save_raw("smart_collections", smart_collections)
    _save_raw("collects", collects)
    _save_raw("pages", pages)
    _save_raw("blogs", blogs)
    _save_raw("articles", articles)
    _save_raw("policies", policies)
    _save_raw("menus", menus)
    _save_raw("shop", shop)

    snapshot = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "source_store": config.store_domain,
        "api_version": config.api_version,
        "counts": {
            "products": len(products),
            "custom_collections": len(custom_collections),
            "smart_collections": len(smart_collections),
            "collects": len(collects),
            "pages": len(pages),
            "blogs": len(blogs),
            "articles": len(articles),
            "policies": len(policies),
            "menus": len(menus),
        },
    }
    write_json(ROOT / "catalog" / "source_snapshot.json", snapshot)

    LOGGER.info("Source export complete. Snapshot written to catalog/source_snapshot.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
