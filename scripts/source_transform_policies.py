#!/usr/bin/env python3
"""Transform exported policies into content/policies/*.md."""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.lib.source_artifacts import load_raw_items  # noqa: E402

LOGGER = logging.getLogger("source_transform_policies")


def slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return normalized or "policy"


def to_markdown(policy: dict[str, Any]) -> tuple[str, str]:
    title = str(policy.get("title") or "Policy")
    handle_raw = policy.get("handle")
    if isinstance(handle_raw, str) and handle_raw.strip():
        handle = handle_raw.strip()
    else:
        handle = slugify(title)

    body = str(policy.get("body") or "")
    frontmatter = [
        "---",
        f"handle: {handle}",
        f"title: {title}",
        f"source_id: {policy.get('id')}",
        f"updated_at: {policy.get('updated_at')}",
        "---",
        "",
    ]
    return handle, "\n".join(frontmatter) + body + "\n"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    try:
        policies = load_raw_items(ROOT, "policies")
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("Unable to load source policies artifact: %s", exc)
        return 1

    policies_root = ROOT / "content" / "policies"
    policies_root.mkdir(parents=True, exist_ok=True)

    count = 0
    for policy in policies:
        handle, markdown = to_markdown(policy)
        (policies_root / f"{handle}.md").write_text(markdown, encoding="utf-8")
        count += 1

    LOGGER.info("Transformed %d policies", count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
