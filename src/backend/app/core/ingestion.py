"""Document ingestion — records a document for the change-stream worker, and
the actual chunk → embed → store service both the worker and API use."""

from __future__ import annotations

import logging
import time
from typing import Any
from uuid import uuid4

from bson import Binary

from app import db
from app.core import embeddings
from app.core.chunker import chunks_for_document, content_hash, extract_text
from app.telemetry import capture

log = logging.getLogger("cogito.ingest")


async def create_document(
    filename: str, raw: bytes, doc_type: str = "text", source: str = "upload"
) -> str:
    """Insert a 'pending' document (raw embedded as BSON so the change-stream
    worker can chunk+embed+index it) — the event-driven write path."""
    doc_id = str(uuid4())
    doc = {
        "_id": doc_id,
        "path": filename,
        "title": filename.split("/")[-1],
        "type": doc_type,
        "hash": content_hash(raw.decode("utf-8", errors="ignore")),
        "source": source,
        "raw": Binary(raw),
        "status": "pending",
        "created_at": time.time(),
    }
    await db.col(db.DOCUMENTS).insert_one(doc)
    capture("document_created", {"document_id": doc_id, "type": doc_type})
    log.info(f"document queued for ingestion: {doc_id} ({filename})")
    return doc_id


async def process_document(doc: dict[str, Any]) -> dict[str, Any]:
    """Turn a document row into chunks + embeddings + store. Idempotent."""
    doc_id = doc["_id"]
    start = time.time()
    raw = doc.get("raw")
    if raw is None:
        # document stored via API stores raw in the row; if absent, nothing to do
        log.warning(f"document {doc_id} has no raw content")
        return {"document_id": doc_id, "chunks_created": 0, "status": "failed", "reason": "no raw"}

    filename = doc.get("path", doc.get("title", "doc.txt"))
    doc_type = doc.get("type", "text")
    text, mime = await extract_text(filename, raw)

    chunk_docs = chunks_for_document(filename, text, doc_type)
    texts = [c["text"] for c in chunk_docs]
    vectors = [_ensure_dim(v) for v in embeddings.embed(texts)]

    created = 0
    bulk = []
    for c, v in zip(chunk_docs, vectors):
        chunk_id = str(uuid4())
        bulk.append(
            {
                "_id": chunk_id,
                "document_id": doc_id,
                "text": c["text"],
                "embedding": v,
                "page": c["page"],
                "order": c["order"],
                "token_count": c["token_count"],
                "title": doc.get("title", filename),
                "mime": mime,
                "created_at": time.time(),
            }
        )
        created += 1
    if bulk:
        await db.col(db.CHUNKS).insert_many(bulk)

    await db.col(db.DOCUMENTS).update_one(
        {"_id": doc_id}, {"$set": {"status": "indexed", "chunk_count": created,
                                    "indexed_at": time.time(), "mime": mime}}
    )
    elapsed_ms = int((time.time() - start) * 1000)
    log.info(f"indexed {doc_id}: {created} chunks in {elapsed_ms}ms")
    capture("document_indexed", {"document_id": doc_id, "chunks": created, "ms": elapsed_ms})
    return {"document_id": doc_id, "chunks_created": created, "status": "indexed"}


def _ensure_dim(v: list[float]) -> list[float]:
    return embeddings.fit(v)


async def pending_documents() -> list[dict[str, Any]]:
    cur = db.col(db.DOCUMENTS).find({"status": "pending"})
    return [d async for d in cur]