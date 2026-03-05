"""Content model helpers for pages/blogs/policies/navigation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ContentValidationError(Exception):
    """Raised when repository content files fail validation."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("Content validation failed")
        self.errors = errors


@dataclass
class PageContent:
    handle: str
    path: Path
    payload: dict[str, Any]


@dataclass
class BlogArticleContent:
    blog_handle: str
    article_handle: str
    path: Path
    payload: dict[str, Any]


@dataclass
class PolicyContent:
    handle: str
    title: str
    body: str
    metadata: dict[str, str]
    path: Path


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_pages(content_root: Path) -> list[PageContent]:
    pages_root = content_root / "pages"
    if not pages_root.exists():
        return []

    pages: list[PageContent] = []
    for path in sorted(pages_root.glob("*.json")):
        payload = load_json(path)
        if not isinstance(payload, dict):
            continue
        handle = payload.get("handle")
        if isinstance(handle, str) and handle.strip():
            pages.append(PageContent(handle=handle.strip(), path=path, payload=payload))
    return pages


def load_blog_articles(content_root: Path) -> list[BlogArticleContent]:
    blogs_root = content_root / "blogs"
    if not blogs_root.exists():
        return []

    results: list[BlogArticleContent] = []
    for blog_dir in sorted(path for path in blogs_root.iterdir() if path.is_dir()):
        blog_handle = blog_dir.name
        for path in sorted(blog_dir.glob("*.json")):
            payload = load_json(path)
            if not isinstance(payload, dict):
                continue
            article_handle = payload.get("article_handle") or payload.get("handle")
            if isinstance(article_handle, str) and article_handle.strip():
                results.append(
                    BlogArticleContent(
                        blog_handle=blog_handle,
                        article_handle=article_handle.strip(),
                        path=path,
                        payload=payload,
                    )
                )
    return results


def parse_policy_markdown(path: Path) -> PolicyContent:
    text = path.read_text(encoding="utf-8")
    metadata: dict[str, str] = {}
    body = text
    if text.startswith("---\n"):
        parts = text.split("\n---\n", 1)
        if len(parts) == 2:
            frontmatter = parts[0][4:]
            body = parts[1]
            for line in frontmatter.splitlines():
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                metadata[key.strip()] = value.strip()
    handle = metadata.get("handle") or path.stem
    title = metadata.get("title") or handle.replace("-", " ").title()
    return PolicyContent(
        handle=handle,
        title=title,
        body=body,
        metadata=metadata,
        path=path,
    )


def load_policies(content_root: Path) -> list[PolicyContent]:
    policies_root = content_root / "policies"
    if not policies_root.exists():
        return []
    return [parse_policy_markdown(path) for path in sorted(policies_root.glob("*.md"))]


def load_navigation(navigation_root: Path) -> dict[str, Any]:
    menus_path = navigation_root / "menus.json"
    if not menus_path.exists():
        return {"generated_at": None, "menus": []}

    parsed = load_json(menus_path)
    if not isinstance(parsed, dict):
        return {"generated_at": None, "menus": []}
    if not isinstance(parsed.get("menus"), list):
        parsed["menus"] = []
    return parsed


def _validate_page_payload(page: PageContent, errors: list[str]) -> None:
    required = {
        "handle": str,
        "title": str,
        "body_html": str,
    }
    for key, expected_type in required.items():
        value = page.payload.get(key)
        if not isinstance(value, expected_type):
            errors.append(f"{page.path}: '{key}' must be {expected_type.__name__}")


def _validate_article_payload(article: BlogArticleContent, errors: list[str]) -> None:
    required = {
        "blog_handle": str,
        "article_handle": str,
        "title": str,
        "body_html": str,
    }
    for key, expected_type in required.items():
        value = article.payload.get(key)
        if not isinstance(value, expected_type):
            errors.append(f"{article.path}: '{key}' must be {expected_type.__name__}")

    tags = article.payload.get("tags", [])
    if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
        errors.append(f"{article.path}: 'tags' must be a list of strings")


def _collect_known_collection_handles(products: list[Any]) -> set[str]:
    known: set[str] = set()
    for product in products:
        for handle in product.collections:
            known.add(handle)
    return known


def _validate_navigation(
    navigation_payload: dict[str, Any],
    *,
    pages: list[PageContent],
    articles: list[BlogArticleContent],
    products: list[Any],
    navigation_path: Path,
    errors: list[str],
) -> None:
    menus = navigation_payload.get("menus")
    if not isinstance(menus, list):
        errors.append(f"{navigation_path}: 'menus' must be a list")
        return

    page_handles = {page.handle for page in pages}
    article_lookup = {(article.blog_handle, article.article_handle) for article in articles}
    collection_handles = _collect_known_collection_handles(products)
    product_handles = {product.handle for product in products}

    def iter_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        flattened: list[dict[str, Any]] = []
        stack = list(items)
        while stack:
            item = stack.pop(0)
            flattened.append(item)
            nested = item.get("items", [])
            if isinstance(nested, list):
                stack.extend([child for child in nested if isinstance(child, dict)])
        return flattened

    for menu_index, menu in enumerate(menus):
        if not isinstance(menu, dict):
            errors.append(f"{navigation_path}: menu[{menu_index}] must be an object")
            continue
        if not isinstance(menu.get("handle"), str):
            errors.append(f"{navigation_path}: menu[{menu_index}].handle must be a string")
        items = menu.get("items", [])
        if not isinstance(items, list):
            errors.append(f"{navigation_path}: menu[{menu_index}].items must be a list")
            continue

        for item in iter_items([entry for entry in items if isinstance(entry, dict)]):
            url = item.get("url")
            if not isinstance(url, str) or not url.strip():
                continue

            normalized_url = url.strip()
            if normalized_url.startswith("http://") or normalized_url.startswith("https://"):
                continue

            page_match = re.match(r"^/pages/([a-z0-9\-]+)$", normalized_url)
            article_match = re.match(r"^/blogs/([a-z0-9\-]+)/([a-z0-9\-]+)$", normalized_url)
            collection_match = re.match(r"^/collections/([a-z0-9\-]+)$", normalized_url)
            product_match = re.match(r"^/products/([a-z0-9\-]+)$", normalized_url)

            if page_match and page_match.group(1) not in page_handles:
                errors.append(
                    f"{navigation_path}: menu link '{normalized_url}' references unknown page handle"
                )
            if article_match and (article_match.group(1), article_match.group(2)) not in article_lookup:
                errors.append(
                    f"{navigation_path}: menu link '{normalized_url}' references unknown blog/article"
                )
            if collection_match and collection_match.group(1) not in collection_handles:
                errors.append(
                    f"{navigation_path}: menu link '{normalized_url}' references unknown collection handle"
                )
            if product_match and product_match.group(1) not in product_handles:
                errors.append(
                    f"{navigation_path}: menu link '{normalized_url}' references unknown product handle"
                )


def validate_content(
    *,
    root: Path,
    products: list[Any],
) -> tuple[list[PageContent], list[BlogArticleContent], list[PolicyContent], dict[str, Any]]:
    content_root = root / "content"
    navigation_root = root / "navigation"
    errors: list[str] = []

    pages = load_pages(content_root)
    for page in pages:
        _validate_page_payload(page, errors)

    articles = load_blog_articles(content_root)
    for article in articles:
        _validate_article_payload(article, errors)

    policies = load_policies(content_root)
    for policy in policies:
        if not policy.body.strip():
            errors.append(f"{policy.path}: policy body must not be empty")
        if not policy.handle.strip():
            errors.append(f"{policy.path}: policy handle must not be empty")

    navigation_payload = load_navigation(navigation_root)
    _validate_navigation(
        navigation_payload,
        pages=pages,
        articles=articles,
        products=products,
        navigation_path=navigation_root / "menus.json",
        errors=errors,
    )

    if errors:
        raise ContentValidationError(errors)

    return pages, articles, policies, navigation_payload
