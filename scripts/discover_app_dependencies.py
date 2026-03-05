#!/usr/bin/env python3
"""Discover third-party app dependencies from storefront and pulled theme files."""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.lib.content import write_json  # noqa: E402
from scripts.lib.env_utils import first_env, load_env_file  # noqa: E402

LOGGER = logging.getLogger("discover_app_dependencies")


def fetch_url(url: str, timeout_seconds: int = 20) -> str:
    response = requests.get(url, timeout=timeout_seconds)
    response.raise_for_status()
    return response.text


def sitemap_urls(base_url: str) -> list[str]:
    try:
        xml = fetch_url(f"{base_url.rstrip('/')}/sitemap.xml")
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Unable to fetch sitemap.xml: %s", exc)
        return [base_url.rstrip("/") + "/"]

    child_sitemaps = re.findall(r"<loc>(.*?)</loc>", xml)
    urls: list[str] = []
    for sitemap in child_sitemaps:
        sitemap = sitemap.replace("&amp;", "&")
        if "/es/" in sitemap:
            continue
        try:
            child_xml = fetch_url(sitemap)
        except Exception:
            continue
        urls.extend(
            [
                unquote(url).replace("&amp;", "&")
                for url in re.findall(r"<loc>(.*?)</loc>", child_xml)
                if "/es/" not in url
            ]
        )

    if not urls:
        urls = [base_url.rstrip("/") + "/"]
    return sorted(set(urls))


def find_scripts_in_html(html: str) -> set[str]:
    scripts = set(re.findall(r"<script[^>]+src=[\"']([^\"']+)[\"']", html, flags=re.IGNORECASE))
    normalized: set[str] = set()
    for script in scripts:
        if script.startswith("//"):
            normalized.add("https:" + script)
        else:
            normalized.add(script)
    return normalized


def infer_app_name(script_url: str) -> str | None:
    lowered = script_url.lower()
    if "judgeme" in lowered:
        return "Judge.me"
    if "mailchimp" in lowered or "chimpstatic" in lowered:
        return "Mailchimp"
    if "multivariants" in lowered:
        return "MultiVariants"
    if "dealeasy" in lowered:
        return "Dealeasy"
    if "formbuilder" in lowered or "globo" in lowered:
        return "Globo Form Builder"
    if "wholesale-lock-hide-price" in lowered:
        return "Wholesale Lock / Hide Price"
    if "checkout-validation" in lowered:
        return "Checkout Validation"
    if "/extensions/" in lowered:
        return "Shopify App Extension"
    return None


def scan_theme_files(theme_root: Path) -> dict[str, list[str]]:
    if not theme_root.exists():
        return {"matches": []}

    patterns = [
        "judgeme",
        "mailchimp",
        "multivariants",
        "dealeasy",
        "globo",
        "shopify.extension",
        "review",
    ]

    matches: list[str] = []
    for path in theme_root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".liquid", ".js", ".json", ".css", ".scss"}:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            continue
        lowered = content.lower()
        for pattern in patterns:
            if pattern in lowered:
                matches.append(f"{path.relative_to(ROOT)}:{pattern}")

    return {"matches": sorted(set(matches))}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    load_env_file(ROOT)

    source_domain = first_env("SOURCE_SHOPIFY_STORE_DOMAIN") or "quickclipsfloral.com"
    if not source_domain.startswith("http://") and not source_domain.startswith("https://"):
        base_url = f"https://{source_domain}"
    else:
        base_url = source_domain

    urls = sitemap_urls(base_url)
    # Sample first 25 pages to keep runtime practical.
    sample_urls = urls[:25]

    script_urls: set[str] = set()
    for url in sample_urls:
        try:
            html = fetch_url(url)
        except Exception:
            continue
        script_urls.update(find_scripts_in_html(html))

    external_scripts = sorted(
        script
        for script in script_urls
        if "/shopifycloud/" not in script
        and "/cdn/shop/t/" not in script
        and "checkouts/internal/preloads.js" not in script
    )

    inferred_apps = sorted({name for script in external_scripts if (name := infer_app_name(script))})
    theme_scan = scan_theme_files(ROOT / "theme")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_store": source_domain,
        "pages_scanned": len(sample_urls),
        "inferred_apps": inferred_apps,
        "external_script_references": external_scripts,
        "theme_matches": theme_scan["matches"],
        "manual_install_checklist": [
            "Install each required app in target store.",
            "Reconfigure app embeds/blocks and app-level settings.",
            "Recreate app-specific metafields and automation rules if required.",
            "Validate storefront behavior for reviews, forms, pricing locks, and bundle widgets.",
        ],
    }

    write_json(ROOT / "apps" / "app_manifest.json", payload)
    LOGGER.info("Wrote apps/app_manifest.json with %d inferred apps", len(inferred_apps))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
