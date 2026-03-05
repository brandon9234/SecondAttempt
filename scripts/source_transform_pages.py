#!/usr/bin/env python3
"""Transform exported source pages into content/pages/*.json."""

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

LOGGER = logging.getLogger("source_transform_pages")


def normalize_page(raw: dict[str, Any]) -> dict[str, Any] | None:
    handle = raw.get("handle")
    title = raw.get("title")
    body_html = raw.get("body_html")

    if not isinstance(handle, str) or not handle.strip():
        return None
    if not isinstance(title, str):
        title = handle.replace("-", " ").title()
    if not isinstance(body_html, str):
        body_html = ""

    return {
        "handle": handle.strip(),
        "title": title,
        "body_html": body_html,
        "published": bool(raw.get("published_at")),
        "published_at": raw.get("published_at"),
        "template_suffix": raw.get("template_suffix"),
        "source_id": raw.get("id"),
        "updated_at": raw.get("updated_at"),
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    try:
        pages = load_raw_items(ROOT, "pages")
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("Unable to load source pages artifact: %s", exc)
        return 1

    pages_root = ROOT / "content" / "pages"
    pages_root.mkdir(parents=True, exist_ok=True)

    count = 0
    for raw in pages:
        payload = normalize_page(raw)
        if not payload:
            continue
        write_json(pages_root / f"{payload['handle']}.json", payload)
        count += 1

    LOGGER.info("Transformed %d pages", count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
