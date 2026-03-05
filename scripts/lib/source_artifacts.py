"""Helpers for reading source export artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_raw_items(root: Path, name: str) -> list[dict[str, Any]]:
    path = root / "catalog" / "import_logs" / f"source_raw_{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing source artifact: {path}")

    parsed = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(parsed, dict) and isinstance(parsed.get("items"), list):
        return [item for item in parsed["items"] if isinstance(item, dict)]

    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]

    raise ValueError(f"Unexpected source artifact shape: {path}")


def load_raw_object(root: Path, name: str) -> dict[str, Any]:
    path = root / "catalog" / "import_logs" / f"source_raw_{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing source artifact: {path}")

    parsed = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(parsed, dict) and "items" in parsed and isinstance(parsed["items"], dict):
        return parsed["items"]
    if isinstance(parsed, dict) and "items" not in parsed:
        return parsed
    raise ValueError(f"Unexpected source artifact object shape: {path}")
