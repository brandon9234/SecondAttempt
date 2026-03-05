#!/usr/bin/env python3
"""Download source product media into repo product folders."""

from __future__ import annotations

import argparse
import hashlib
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.lib.content import write_json  # noqa: E402
from scripts.lib.source_artifacts import load_raw_items  # noqa: E402

LOGGER = logging.getLogger("source_download_media")
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def _sha256_bytes(payload: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(payload)
    return digest.hexdigest()


def _parse_extension(url: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in SUPPORTED_EXTENSIONS:
        return suffix
    return ".jpg"


def _image_sort_key(image: dict[str, Any]) -> tuple[int, int]:
    position = image.get("position")
    image_id = image.get("id")
    try:
        pos = int(position)
    except (TypeError, ValueError):
        pos = 9999
    try:
        image_num = int(image_id)
    except (TypeError, ValueError):
        image_num = 0
    return pos, image_num


def _candidate_image_files(product_dir: Path) -> list[Path]:
    candidates: list[Path] = []
    pattern = re.compile(r"^(main|\d{2,})\.[a-zA-Z0-9]+$")
    for path in product_dir.iterdir():
        if path.is_file() and pattern.match(path.name):
            candidates.append(path)
    return candidates


def download_file(url: str, timeout_seconds: int = 120) -> bytes:
    response = requests.get(url, timeout=timeout_seconds)
    if response.status_code >= 400:
        raise RuntimeError(f"Failed downloading {url}: HTTP {response.status_code}")
    return response.content


def build_media_filename(index: int, extension: str) -> str:
    if index == 1:
        return f"main{extension}"
    return f"{index:02d}{extension}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Download source media into products folders")
    parser.add_argument(
        "--prune-local-images",
        action="store_true",
        help="Delete local numbered/main image files not present in source mapping",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    try:
        products = load_raw_items(ROOT, "products")
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("Unable to load source products artifact: %s", exc)
        return 1

    media_map: list[dict[str, Any]] = []

    for product in products:
        handle = product.get("handle")
        if not isinstance(handle, str) or not handle.strip():
            continue
        handle = handle.strip()

        images = product.get("images")
        if not isinstance(images, list):
            images = []

        ordered_images = sorted(
            [image for image in images if isinstance(image, dict)],
            key=_image_sort_key,
        )

        product_dir = ROOT / "products" / handle
        product_dir.mkdir(parents=True, exist_ok=True)

        desired_files: set[str] = set()

        for index, image in enumerate(ordered_images, start=1):
            source_url = image.get("src")
            if not isinstance(source_url, str) or not source_url.strip():
                continue
            source_url = source_url.strip()
            extension = _parse_extension(source_url)
            local_name = build_media_filename(index, extension)
            desired_files.add(local_name)
            local_path = product_dir / local_name

            try:
                payload = download_file(source_url)
            except Exception as exc:  # noqa: BLE001
                LOGGER.error("Download failed for %s (%s): %s", handle, source_url, exc)
                return 1

            incoming_hash = _sha256_bytes(payload)
            action = "downloaded"
            if local_path.exists():
                existing_hash = _sha256_bytes(local_path.read_bytes())
                if existing_hash == incoming_hash:
                    action = "reused"
                else:
                    local_path.write_bytes(payload)
                    action = "updated"
            else:
                local_path.write_bytes(payload)

            media_map.append(
                {
                    "handle": handle,
                    "source_product_id": product.get("id"),
                    "source_image_id": image.get("id"),
                    "source_url": source_url,
                    "local_file": str(local_path.relative_to(ROOT)),
                    "position": index,
                    "sha256": incoming_hash,
                    "action": action,
                }
            )

        if args.prune_local_images:
            for existing in _candidate_image_files(product_dir):
                if existing.name not in desired_files:
                    existing.unlink()
                    LOGGER.info("Pruned stale local image: %s", existing)

    write_json(
        ROOT / "catalog" / "import_logs" / "media_map.json",
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "items": media_map,
        },
    )

    LOGGER.info("Downloaded/reused %d media entries", len(media_map))
    LOGGER.info("Wrote catalog/import_logs/media_map.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
