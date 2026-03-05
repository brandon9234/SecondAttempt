#!/usr/bin/env python3
"""Transform exported blogs and articles into content/blogs structure."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.lib.content import write_json  # noqa: E402
from scripts.lib.source_artifacts import load_raw_items  # noqa: E402

LOGGER = logging.getLogger("source_transform_blogs")


def _parse_tags(raw_tags: Any) -> list[str]:
    if isinstance(raw_tags, list):
        return [str(tag).strip() for tag in raw_tags if str(tag).strip()]
    if isinstance(raw_tags, str):
        return [tag.strip() for tag in raw_tags.split(",") if tag.strip()]
    return []


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    try:
        blogs = load_raw_items(ROOT, "blogs")
        articles = load_raw_items(ROOT, "articles")
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("Unable to load source blog artifacts: %s", exc)
        return 1

    blog_id_to_handle: dict[int, str] = {}
    for blog in blogs:
        blog_id = blog.get("id")
        handle = blog.get("handle")
        try:
            blog_id_int = int(blog_id)
        except (TypeError, ValueError):
            continue
        if isinstance(handle, str) and handle.strip():
            blog_id_to_handle[blog_id_int] = handle.strip()

    transformed = 0
    for article in articles:
        blog_id = article.get("blog_id")
        article_handle = article.get("handle")
        if not isinstance(article_handle, str) or not article_handle.strip():
            continue

        try:
            blog_id_int = int(blog_id)
        except (TypeError, ValueError):
            continue

        blog_handle = blog_id_to_handle.get(blog_id_int)
        if not blog_handle:
            continue

        blog_dir = ROOT / "content" / "blogs" / blog_handle
        blog_dir.mkdir(parents=True, exist_ok=True)

        payload = {
            "blog_handle": blog_handle,
            "article_handle": article_handle.strip(),
            "title": str(article.get("title") or article_handle),
            "author": str(article.get("author") or ""),
            "body_html": str(article.get("body_html") or ""),
            "summary_html": str(article.get("summary_html") or ""),
            "tags": _parse_tags(article.get("tags")),
            "published": bool(article.get("published_at")),
            "published_at": article.get("published_at"),
            "template_suffix": article.get("template_suffix"),
            "source_id": article.get("id"),
            "updated_at": article.get("updated_at"),
        }

        write_json(blog_dir / f"{payload['article_handle']}.json", payload)
        transformed += 1

    LOGGER.info("Transformed %d blog articles", transformed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
