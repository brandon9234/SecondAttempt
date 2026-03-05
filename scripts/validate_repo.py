#!/usr/bin/env python3
"""Validate catalog repository structure and product contracts."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.lib.catalog import CatalogValidationError, load_catalog  # noqa: E402
from scripts.lib.content import ContentValidationError, validate_content  # noqa: E402


def validate_required_directories(root: Path) -> list[str]:
    required_dirs = [
        "theme",
        "products",
        "catalog",
        "catalog/import_logs",
        "scripts",
        "docs",
        "skills",
        "content",
        "content/pages",
        "content/blogs",
        "content/policies",
        "navigation",
        "apps",
        ".vscode",
        ".github/workflows",
    ]
    errors: list[str] = []
    for rel_path in required_dirs:
        directory = root / rel_path
        if not directory.exists() or not directory.is_dir():
            errors.append(f"Missing required directory: {directory}")
    return errors


def validate_required_files(root: Path) -> list[str]:
    required_files = [
        ".env.example",
        "README.md",
        "AGENTS.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "pyproject.toml",
        ".gitignore",
        ".gitattributes",
        "navigation/menus.json",
        "apps/app_manifest.json",
    ]
    errors: list[str] = []
    for rel_path in required_files:
        file_path = root / rel_path
        if not file_path.exists() or not file_path.is_file():
            errors.append(f"Missing required file: {file_path}")
    return errors


def main() -> int:
    root = ROOT
    errors: list[str] = []

    errors.extend(validate_required_directories(root))
    errors.extend(validate_required_files(root))

    products_root = root / "products"
    try:
        products = load_catalog(products_root)
        if not products:
            errors.append("No product folders found under products/")
    except CatalogValidationError as exc:
        errors.extend(exc.errors)
        products = []

    if products:
        try:
            validate_content(root=root, products=products)
        except ContentValidationError as exc:
            errors.extend(exc.errors)

    if errors:
        print("Repository validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Repository validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
