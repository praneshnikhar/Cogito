"""Shared application errors."""

from __future__ import annotations


class RateLimitExceeded(Exception):
    """Raised when the per-question search budget is exhausted."""

    def __init__(self, retry_after: int = 60) -> None:
        self.retry_after = retry_after
        super().__init__("rate limit exceeded")
