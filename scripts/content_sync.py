#!/usr/bin/env python3
"""Sync repo-managed pages/blogs/policies/navigation to target Shopify store."""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.lib.catalog import CatalogValidationError, load_catalog  # noqa: E402
from scripts.lib.content import ContentValidationError, validate_content  # noqa: E402
from scripts.lib.env_utils import first_env, load_env_file, parse_bool  # noqa: E402
from scripts.lib.source_export_client import ShopifyRESTClient, ShopifyRestError  # noqa: E402

LOGGER = logging.getLogger("content_sync")


@dataclass
class ContentSyncConfig:
    store_domain: str | None
    access_token: str | None
    api_version: str
    dry_run: bool


def read_config() -> ContentSyncConfig:
    load_env_file(ROOT)
    return ContentSyncConfig(
        store_domain=first_env("TARGET_SHOPIFY_STORE_DOMAIN", "SHOPIFY_STORE_DOMAIN"),
        access_token=first_env("TARGET_SHOPIFY_ADMIN_ACCESS_TOKEN", "SHOPIFY_ADMIN_ACCESS_TOKEN"),
        api_version=first_env("TARGET_SHOPIFY_API_VERSION", "SHOPIFY_API_VERSION") or "2025-10",
        dry_run=parse_bool(first_env("DRY_RUN"), default=True),
    )


def _norm(value: Any) -> str:
    return "" if value is None else str(value)


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _page_changed(local_payload: dict[str, Any], remote_payload: dict[str, Any]) -> bool:
    checks = [
        ("title", local_payload.get("title"), remote_payload.get("title")),
        ("body_html", local_payload.get("body_html"), remote_payload.get("body_html")),
        ("handle", local_payload.get("handle"), remote_payload.get("handle")),
        ("template_suffix", local_payload.get("template_suffix"), remote_payload.get("template_suffix")),
    ]
    for _, left, right in checks:
        if _norm(left) != _norm(right):
            return True

    local_published = _to_bool(local_payload.get("published"))
    remote_published = _to_bool(remote_payload.get("published_at"))
    return local_published != remote_published


def _article_changed(local_payload: dict[str, Any], remote_payload: dict[str, Any]) -> bool:
    checks = [
        ("title", local_payload.get("title"), remote_payload.get("title")),
        ("author", local_payload.get("author"), remote_payload.get("author")),
        ("body_html", local_payload.get("body_html"), remote_payload.get("body_html")),
        ("summary_html", local_payload.get("summary_html"), remote_payload.get("summary_html")),
        ("handle", local_payload.get("article_handle"), remote_payload.get("handle")),
        (
            "template_suffix",
            local_payload.get("template_suffix"),
            remote_payload.get("template_suffix"),
        ),
        ("tags", ",".join(local_payload.get("tags", [])), _norm(remote_payload.get("tags"))),
    ]
    for _, left, right in checks:
        if _norm(left) != _norm(right):
            return True

    local_published = _to_bool(local_payload.get("published"))
    remote_published = _to_bool(remote_payload.get("published_at"))
    return local_published != remote_published


def _policy_match_key(handle: str) -> str:
    return handle.replace("-", "_").lower()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    config = read_config()

    try:
        products = load_catalog(ROOT / "products")
    except CatalogValidationError as exc:
        LOGGER.error("catalog validation failed before content sync:")
        for error in exc.errors:
            LOGGER.error("- %s", error)
        return 1

    try:
        pages, articles, policies, navigation_payload = validate_content(root=ROOT, products=products)
    except ContentValidationError as exc:
        LOGGER.error("content validation failed before sync:")
        for error in exc.errors:
            LOGGER.error("- %s", error)
        return 1

    if not config.store_domain or not config.access_token:
        if config.dry_run:
            LOGGER.info(
                "DRY_RUN=true and target credentials missing. Validation completed; "
                "skipping Shopify content mutations."
            )
            LOGGER.info(
                "Planned entities: pages=%d articles=%d policies=%d menus=%d",
                len(pages),
                len(articles),
                len(policies),
                len(navigation_payload.get("menus", [])),
            )
            return 0
        LOGGER.error(
            "Missing target Shopify credentials. Set TARGET_SHOPIFY_STORE_DOMAIN and "
            "TARGET_SHOPIFY_ADMIN_ACCESS_TOKEN in .env"
        )
        return 1

    client = ShopifyRESTClient(
        store_domain=config.store_domain,
        access_token=config.access_token,
        api_version=config.api_version,
    )

    mutation_count = 0

    try:
        remote_pages = client.list_pages()
        remote_pages_by_handle = {
            page.get("handle"): page for page in remote_pages if isinstance(page.get("handle"), str)
        }

        for page in pages:
            payload = {
                "title": page.payload.get("title"),
                "body_html": page.payload.get("body_html"),
                "handle": page.payload.get("handle"),
                "published": _to_bool(page.payload.get("published")),
                "template_suffix": page.payload.get("template_suffix"),
            }
            remote = remote_pages_by_handle.get(page.handle)
            if not remote:
                if config.dry_run:
                    LOGGER.info("DRY_RUN: would create page '%s'", page.handle)
                else:
                    client.create_page(payload)
                    mutation_count += 1
                continue

            if _page_changed(page.payload, remote):
                if config.dry_run:
                    LOGGER.info("DRY_RUN: would update page '%s'", page.handle)
                else:
                    client.update_page(remote["id"], payload)
                    mutation_count += 1

        remote_blogs = client.list_blogs()
        remote_blogs_by_handle = {
            blog.get("handle"): blog for blog in remote_blogs if isinstance(blog.get("handle"), str)
        }

        articles_by_blog: dict[str, list[Any]] = {}
        for article in articles:
            articles_by_blog.setdefault(article.blog_handle, []).append(article)

        for blog_handle, blog_articles in articles_by_blog.items():
            remote_blog = remote_blogs_by_handle.get(blog_handle)
            if not remote_blog:
                title = blog_handle.replace("-", " ").title()
                if config.dry_run:
                    LOGGER.info("DRY_RUN: would create blog '%s'", blog_handle)
                    remote_blog_id = None
                else:
                    created_blog = client.create_blog({"title": title, "handle": blog_handle}).get("blog", {})
                    remote_blog_id = created_blog.get("id")
                    mutation_count += 1
                    remote_blogs_by_handle[blog_handle] = created_blog
            else:
                remote_blog_id = remote_blog.get("id")

            if remote_blog_id is None:
                continue

            remote_articles = client.list_articles(remote_blog_id)
            remote_articles_by_handle = {
                article.get("handle"): article
                for article in remote_articles
                if isinstance(article.get("handle"), str)
            }

            for article in blog_articles:
                article_payload = {
                    "title": article.payload.get("title"),
                    "author": article.payload.get("author"),
                    "body_html": article.payload.get("body_html"),
                    "summary_html": article.payload.get("summary_html"),
                    "handle": article.payload.get("article_handle"),
                    "tags": ",".join(article.payload.get("tags", [])),
                    "published": _to_bool(article.payload.get("published")),
                    "template_suffix": article.payload.get("template_suffix"),
                }

                remote_article = remote_articles_by_handle.get(article.article_handle)
                if not remote_article:
                    if config.dry_run:
                        LOGGER.info(
                            "DRY_RUN: would create article '%s/%s'",
                            blog_handle,
                            article.article_handle,
                        )
                    else:
                        client.create_article(remote_blog_id, article_payload)
                        mutation_count += 1
                    continue

                if _article_changed(article.payload, remote_article):
                    if config.dry_run:
                        LOGGER.info(
                            "DRY_RUN: would update article '%s/%s'",
                            blog_handle,
                            article.article_handle,
                        )
                    else:
                        client.update_article(remote_blog_id, remote_article["id"], article_payload)
                        mutation_count += 1

        remote_policies = client.list_policies()
        remote_policies_by_key = {
            _policy_match_key(str(policy.get("handle") or policy.get("title") or "")): policy
            for policy in remote_policies
        }

        for policy in policies:
            policy_key = _policy_match_key(policy.handle)
            remote_policy = remote_policies_by_key.get(policy_key)
            if not remote_policy:
                LOGGER.warning(
                    "Policy '%s' not found in target store; skipping (policy creation is not supported).",
                    policy.handle,
                )
                continue

            remote_body = _norm(remote_policy.get("body"))
            if remote_body.strip() == policy.body.strip() and _norm(remote_policy.get("title")) == policy.title:
                continue

            payload = {
                "title": policy.title,
                "body": policy.body,
            }
            if config.dry_run:
                LOGGER.info("DRY_RUN: would update policy '%s'", policy.handle)
            else:
                client.update_policy(remote_policy["id"], payload)
                mutation_count += 1

        remote_menus = client.list_menus()
        remote_menus_by_handle = {
            str(menu.get("handle")): menu
            for menu in remote_menus
            if isinstance(menu, dict) and isinstance(menu.get("handle"), str)
        }

        for menu in navigation_payload.get("menus", []):
            if not isinstance(menu, dict):
                continue
            handle = menu.get("handle")
            if not isinstance(handle, str):
                continue

            payload = {
                "title": menu.get("title"),
                "handle": handle,
                "items": menu.get("items", []),
            }

            remote_menu = remote_menus_by_handle.get(handle)
            if not remote_menu:
                if config.dry_run:
                    LOGGER.info("DRY_RUN: would create menu '%s'", handle)
                else:
                    client.create_menu(payload)
                    mutation_count += 1
                continue

            remote_comparable = {
                "title": remote_menu.get("title"),
                "handle": remote_menu.get("handle"),
                "items": remote_menu.get("items", []),
            }
            if json.dumps(payload, sort_keys=True) != json.dumps(remote_comparable, sort_keys=True):
                if config.dry_run:
                    LOGGER.info("DRY_RUN: would update menu '%s'", handle)
                else:
                    client.update_menu(remote_menu.get("id"), payload)
                    mutation_count += 1

    except ShopifyRestError as exc:
        LOGGER.error("content sync failed: %s", exc)
        return 1

    if config.dry_run:
        LOGGER.info("DRY_RUN complete. Planned content mutations: %d", mutation_count)
    else:
        LOGGER.info("Content sync complete. Executed content mutations: %d", mutation_count)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
