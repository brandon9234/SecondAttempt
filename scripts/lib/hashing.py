"""Hashing helpers for incremental media sync."""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Return SHA256 hash for a file using a streaming read."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def build_media_manifest_entry(handle: str, ordered_file_paths: list[Path]) -> dict:
    """Build media manifest entry for a single product handle."""
    return {
        "handle": handle,
        "media": [
            {
                "filename": path.name,
                "sha256": sha256_file(path),
            }
            for path in ordered_file_paths
        ],
    }
