#!/usr/bin/env python3
"""Generate catalog manifests for inspection and debugging."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.lib.catalog import CatalogValidationError, load_catalog  # noqa: E402
from scripts.lib.content import ContentValidationError, validate_content  # noqa: E402
from scripts.lib.hashing import sha256_file  # noqa: E402


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main() -> int:
    products_root = ROOT / "products"
    catalog_root = ROOT / "catalog"

    try:
        products = load_catalog(products_root)
    except CatalogValidationError as exc:
        print("catalog_build failed due to validation errors:")
        for error in exc.errors:
            print(f"- {error}")
        return 1

    try:
        pages, articles, policies, navigation_payload = validate_content(root=ROOT, products=products)
    except ContentValidationError as exc:
        print("catalog_build failed due to content validation errors:")
        for error in exc.errors:
            print(f"- {error}")
        return 1

    generated_at = datetime.now(timezone.utc).isoformat()

    media_manifest = {
        "generated_at": generated_at,
        "products": {},
    }
    products_manifest = {
        "generated_at": generated_at,
        "products": {},
    }
    pages_manifest = {
        "generated_at": generated_at,
        "pages": {},
    }
    blog_manifest = {
        "generated_at": generated_at,
        "blogs": {},
        "policies": {},
    }
    navigation_manifest = {
        "generated_at": generated_at,
        "menus": navigation_payload.get("menus", []),
    }

    for product in products:
        media_entries = []
        for image in product.images:
            media_entries.append(
                {
                    "filename": image["filename"],
                    "position": image["position"],
                    "sha256": sha256_file(image["path"]),
                }
            )

        media_manifest["products"][product.handle] = media_entries
        products_manifest["products"][product.handle] = product.to_manifest_dict()

    for page in pages:
        pages_manifest["pages"][page.handle] = {
            "title": page.payload.get("title"),
            "updated_at": page.payload.get("updated_at"),
            "source_id": page.payload.get("source_id"),
        }

    for article in articles:
        blog_entry = blog_manifest["blogs"].setdefault(
            article.blog_handle,
            {
                "article_count": 0,
                "articles": {},
            },
        )
        blog_entry["article_count"] += 1
        blog_entry["articles"][article.article_handle] = {
            "title": article.payload.get("title"),
            "updated_at": article.payload.get("updated_at"),
            "source_id": article.payload.get("source_id"),
        }

    for policy in policies:
        blog_manifest["policies"][policy.handle] = {
            "title": policy.title,
            "updated_at": policy.metadata.get("updated_at"),
            "source_id": policy.metadata.get("source_id"),
        }

    write_json(catalog_root / "media_manifest.json", media_manifest)
    write_json(catalog_root / "products_manifest.json", products_manifest)
    write_json(catalog_root / "pages_manifest.json", pages_manifest)
    write_json(catalog_root / "blog_manifest.json", blog_manifest)
    write_json(catalog_root / "navigation_manifest.json", navigation_manifest)

    print(f"Wrote {catalog_root / 'media_manifest.json'}")
    print(f"Wrote {catalog_root / 'products_manifest.json'}")
    print(f"Wrote {catalog_root / 'pages_manifest.json'}")
    print(f"Wrote {catalog_root / 'blog_manifest.json'}")
    print(f"Wrote {catalog_root / 'navigation_manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
