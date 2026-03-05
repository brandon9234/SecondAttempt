"""Retry helpers for transient HTTP/API failures."""

from __future__ import annotations

import random
import time
from typing import Callable, TypeVar

T = TypeVar("T")


class RetryError(RuntimeError):
    """Raised when retry attempts are exhausted."""


def with_retry(
    func: Callable[[], T],
    is_retryable: Callable[[BaseException], bool],
    max_attempts: int = 5,
    base_delay: float = 1.0,
    jitter: float = 0.25,
) -> T:
    """Execute ``func`` with exponential backoff for retryable errors."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    attempt = 0
    while True:
        attempt += 1
        try:
            return func()
        except BaseException as exc:  # noqa: BLE001
            if attempt >= max_attempts or not is_retryable(exc):
                raise RetryError(f"Operation failed after {attempt} attempt(s): {exc}") from exc

            sleep_seconds = base_delay * (2 ** (attempt - 1))
            sleep_seconds += random.uniform(0, jitter)
            time.sleep(sleep_seconds)
