"""Long-term memory (MongoDB 'agent memory' pattern): extracted facts stored
with embeddings and recalled via vector search."""

from __future__ import annotations

import logging
import time
from uuid import uuid4

import numpy as np

from app import db
from app.core import embeddings

log = logging.getLogger("cogito.memory")


async def remember(user_id: str, fact: str, importance: float = 1.0) -> str:
    mem_id = str(uuid4())
    await db.col(db.MEMORIES).insert_one(
        {
            "_id": mem_id,
            "user_id": user_id,
            "fact": fact,
            "embedding": embeddings.embed_one(fact),
            "importance": importance,
            "created_at": time.time(),
            "updated_at": time.time(),
        }
    )
    return mem_id


async def recall(user_id: str, query: str, limit: int = 3) -> list[dict]:
    """Recover the most relevant memories by cosine similarity."""
    qv = np.asarray(embeddings.embed_one(query), dtype=np.float32)
    out = []
    cur = db.col(db.MEMORIES).find({"user_id": user_id}) \
        if user_id else db.col(db.MEMORIES).find({})
    async for m in cur:
        v = m.get("embedding")
        if not v:
            continue
        a = np.asarray(v, dtype=np.float32)
        denom = float(np.linalg.norm(a) * np.linalg.norm(qv))
        score = 0.0 if denom == 0 else float(np.dot(a, qv) / denom)
        out.append((score, m))
    out.sort(key=lambda x: -x[0])
    return [{"memory_id": m["_id"], "fact": m["fact"], "importance": m.get("importance"),
             "score": round(s, 3)} for s, m in out[:limit]]


async def list_memories(user_id: str | None = None) -> list[dict]:
    cur = db.col(db.MEMORIES).find({"user_id": user_id} if user_id else {}).sort("updated_at", -1)
    return [m async for m in cur]