"""Pinecone integration — a secondary vector store that mirrors the Mongo
chunks, enabling cross-store retrieval comparison and a serverless-query
path. All methods no-op cleanly without a PINECONE_API_KEY."""

from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.core import embeddings

log = logging.getLogger("cogito.pinecone")


def _enabled() -> bool:
    return bool(settings.pinecone_api_key and settings.pinecone_index)


class PineconeStore:
    """Minimal REST client speaking Pinecone's Namespace API (vector/upsert &
    query). Avoids the heavy gRPC dependency at import time."""

    def __init__(self) -> None:
        self.base = f"https://{settings.pinecone_index}-{settings.pinecone_env}.pinecone.io"

    def _headers(self) -> dict:
        return {"Api-Key": settings.pinecone_api_key, "Content-Type": "application/json"}

    async def upsert(self, chunk_id: str, vector: list[float], metadata: dict) -> bool:
        if not _enabled():
            return False
        async with httpx.AsyncClient() as c:
            r = await c.post(
                f"{self.base}/vectors/upsert",
                headers=self._headers(),
                json={"vectors": [{"id": chunk_id, "values": vector, "metadata": metadata}]},
            )
        r.raise_for_status()
        return True

    async def query(self, vector: list[float], top_k: int = 5):
        if not _enabled():
            return []
        async with httpx.AsyncClient() as c:
            r = await c.post(
                f"{self.base}/query",
                headers=self._headers(),
                json={"vector": vector, "topK": top_k, "includeMetadata": True},
            )
        r.raise_for_status()
        return r.json().get("matches", [])

    async def search(self, text: str, top_k: int = 5):
        return await self.query(embeddings.embed_one(text), top_k)


_store = PineconeStore()


async def mirror_chunk(chunk: dict) -> bool:
    """Mirror a Mongo chunk into Pinecone for cross-store comparison."""
    try:
        return await _store.upsert(
            str(chunk["_id"]),
            chunk.get("embedding", []),
            {"text": chunk.get("text", ""), "document_id": chunk.get("document_id", "")},
        )
    except Exception as e:  # noqa: BLE001
        log.debug(f"pinecone mirror skipped: {e}")
        return False


async def search(text: str, top_k: int = 5) -> list[dict]:
    try:
        return await _store.search(text, top_k)
    except Exception as e:  # noqa: BLE001
        log.debug(f"pinecone search skipped: {e}")
        return []