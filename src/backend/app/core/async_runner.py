"""Sync-over-async bridge for provider SDK calls.

The ingestion worker and the FastAPI handlers are asyncio-based, while the
provider facade (LLM / embeddings) is synchronous. Calling `asyncio.run`
inside a live event loop raises, and opening a fresh loop per call orphans the
SDK client's connection pool, so every provider call is dispatched onto one
long-lived background loop instead.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from typing import Any, TypeVar

T = TypeVar("T")


class AsyncRunner:
    def __init__(self, name: str = "cogito-providers") -> None:
        self._name = name
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()

    def _loop_or_start(self) -> asyncio.AbstractEventLoop:
        if self._loop is None:
            with self._lock:
                if self._loop is None:
                    loop = asyncio.new_event_loop()
                    threading.Thread(
                        target=loop.run_forever, name=self._name, daemon=True
                    ).start()
                    self._loop = loop
        return self._loop

    def run(self, coro: Coroutine[Any, Any, T], timeout: float = 120.0) -> T:
        """Block until `coro` completes, from sync or async calling code."""
        return asyncio.run_coroutine_threadsafe(
            coro, self._loop_or_start()
        ).result(timeout)


runner = AsyncRunner()
