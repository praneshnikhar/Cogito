"""Upstash Redis REST client — a minimal async client speaking Upstash's HTTP
API so we can rate-limit and cache in serverless contexts too."""

from __future__ import annotations

import time

import httpx


class UpstashRestClient:
    def __init__(self, url: str, token: str) -> None:
        self._base = url.rstrip("/")
        self._token = token

    async def _exec(self, *args) -> any:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._base}",
                headers={"Authorization": f"Bearer {self._token}"},
                json=args,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("error"):
                raise RuntimeError(data["error"])
            return data.get("result")

    # --- commands used by cogito ---
    async def get(self, key: str):
        return await self._exec("GET", key)

    async def set(self, key: str, value: str, ex: int | None = None):
        args = ["SET", key, value]
        if ex:
            args += ["EX", ex]
        return await self._exec(*args)

    async def sliding_window(self, key: str, limit: int, window: int):
        """Sliding log/counter rate limit. Returns (allowed, remaining)."""
        now = int(time.time() * 1000)
        member = f"{now}-{key}"
        pipe = [
            ["ZREMRANGEBYSCORE", key, 0, now - window * 1000],
            ["ZADD", key, now, member],
            ["ZCOUNT", key, now - window * 1000, now],
            ["EXPIRE", key, window],
        ]
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    self._base,
                    headers={"Authorization": f"Bearer {self._token}"},
                    json=pipe,
                )
                resp.raise_for_status()
                results = resp.json()
            count = int(results[-2]["result"])
        except Exception:  # noqa: BLE001
            return True, limit
        return count <= limit, max(0, limit - count)