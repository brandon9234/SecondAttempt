#!/usr/bin/env python3
"""Run all source artifact -> repo transform scripts."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_step(script: str) -> None:
    result = subprocess.run([sys.executable, script], cwd=ROOT, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"Transform step failed: {script}")


def main() -> int:
    try:
        run_step("scripts/source_transform_products.py")
        run_step("scripts/source_transform_pages.py")
        run_step("scripts/source_transform_blogs.py")
        run_step("scripts/source_transform_policies.py")
        run_step("scripts/source_transform_navigation.py")
    except RuntimeError as exc:
        print(exc)
        return 1

    print("Source transform complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
