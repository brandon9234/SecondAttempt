#!/usr/bin/env python3
"""Transform exported menus into navigation/menus.json."""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.lib.content import write_json  # noqa: E402
from scripts.lib.source_artifacts import load_raw_items  # noqa: E402

LOGGER = logging.getLogger("source_transform_navigation")


def normalize_items(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []

    normalized: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        normalized_item = {
            "title": str(item.get("title") or ""),
            "type": str(item.get("type") or ""),
            "url": str(item.get("url") or ""),
            "resource_id": item.get("resource_id") or item.get("resourceId"),
            "items": normalize_items(item.get("items") or []),
        }
        normalized.append(normalized_item)

    return normalized


def normalize_menu(raw: dict[str, Any]) -> dict[str, Any] | None:
    handle = raw.get("handle")
    title = raw.get("title")
    if not isinstance(handle, str) or not handle.strip():
        return None
    if not isinstance(title, str):
        title = handle

    return {
        "handle": handle.strip(),
        "title": title,
        "source_id": raw.get("id"),
        "updated_at": raw.get("updated_at"),
        "items": normalize_items(raw.get("items") or []),
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    try:
        menus = load_raw_items(ROOT, "menus")
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("Unable to load source menus artifact: %s", exc)
        return 1

    normalized_menus: list[dict[str, Any]] = []
    for menu in menus:
        normalized = normalize_menu(menu)
        if normalized:
            normalized_menus.append(normalized)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "menus": sorted(normalized_menus, key=lambda menu: menu["handle"]),
    }
    write_json(ROOT / "navigation" / "menus.json", payload)

    LOGGER.info("Transformed %d menus", len(normalized_menus))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
