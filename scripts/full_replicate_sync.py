#!/usr/bin/env python3
"""Run full deployment pipeline for repo-managed Shopify replica."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
LOGGER = logging.getLogger("full_replicate_sync")


def run_step(name: str, command: list[str], env: dict[str, str]) -> None:
    LOGGER.info("Running step: %s", name)
    completed = subprocess.run(command, cwd=ROOT, env=env, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"Step failed: {name} (exit code {completed.returncode})")


def main() -> int:
    env = os.environ.copy()
    dry_run = env.get("DRY_RUN", "true").strip().lower() in {"1", "true", "yes", "y", "on"}

    try:
        run_step("Validate repo", [sys.executable, "scripts/validate_repo.py"], env)
        run_step("Build manifests", [sys.executable, "scripts/catalog_build.py"], env)
        run_step("Sync catalog", [sys.executable, "scripts/catalog_sync.py"], env)
        run_step("Sync content", [sys.executable, "scripts/content_sync.py"], env)

        if dry_run:
            LOGGER.info("DRY_RUN=true; skipping theme push step.")
        else:
            run_step("Theme push", ["bash", "scripts/theme_push.sh"], env)

    except RuntimeError as exc:
        LOGGER.error("Full replicate sync failed: %s", exc)
        return 1

    LOGGER.info("Full replicate sync completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
