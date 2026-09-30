"""Hybrid search over the chunks collection.

Two modes, same output shape:
  * FULL  — mongot present: `$search` (lexical) + `$vectorSearch` (semantic)
            fused with MongoDB's native `$rankFusion`.
  * FALLBACK — mongot absent: `$text` (lexical) + brute-force cosine
            (semantic) merged with Reciprocal Rank Fusion (RRF). Identical
            result contract, runs on any replica set.
"""

from __future__ import annotations

import logging

import numpy as np

from app import db
from app.config import settings
from app.core import embeddings
from app.telemetry import rate_limit

log = logging.getLogger("cogito.retrieval")


async def _lexical_full(question: str, limit: int) -> list[int]:
    """Document-ids via native $search text."""
    pipeline = [
        {
            "$search": {
                "index": "cogito_text",
                "text": {"query": question, "path": "text"},
            }
        },
        {"$limit": limit},
        {"$project": {"_id": 1, "score": {"$meta": "searchScore"}, "text": 1,
                      "document_id": 1, "title": 1, "page": 1}},
    ]
    cur = db.col(db.CHUNKS).aggregate(pipeline)
    return [doc async for doc in cur]


async def _vector_full(query_embedding: list[float], limit: int) -> list[dict]:
    pipeline = [
        {
            "$vectorSearch": {
                "index": "cogito_vector",
                "path": "embedding",
                "queryVector": query_embedding,
                "numCandidates": settings.search_num_candidates,
                "limit": limit,
            }
        },
        {"$project": {"_id": 1, "score": {"$meta": "vectorSearchScore"}, "text": 1,
                      "document_id": 1, "title": 1, "page": 1}},
    ]
    cur = db.col(db.CHUNKS).aggregate(pipeline)
    return [doc async for doc in cur]


async def _full_hybrid(question: str, query_embedding: list[float], k: int) -> list[dict]:
    """Native $rankFusion over search + vector branches."""
    pipeline = [
        {
            "$rankFusion": {
                "input": {
                    "pipeline": [
                        {"$search": {"index": "cogito_text",
                                     "text": {"query": question, "path": "text"}}},
                    ],
                    "output": "searchRank",
                },
                "input2": {
                    "pipeline": [
                        {"$vectorSearch": {
                            "index": "cogito_vector",
                            "path": "embedding",
                            "queryVector": query_embedding,
                            "numCandidates": settings.search_num_candidates,
                            "limit": max(settings.search_num_candidates, k * 4),
                        }},
                    ],
                    "output": "vectorRank",
                },
            }
        },
        {"$set": {"rank": {"$add": ["$searchRank", "$vectorRank"]}}},
        {"$sort": {"rank": 1}},
        {"$limit": k},
        {"$project": {"_id": 1, "text": 1, "document_id": 1, "title": 1,
                      "page": 1, "searchRank": 1, "vectorRank": 1, "rank": 1}},
    ]
    cur = db.col(db.CHUNKS).aggregate(pipeline)
    chunks = [doc async for doc in cur]
    for c in chunks:
        c["score"] = 1.0 / (1.0 + c.get("rank", 1))
        c.pop("rank", None)
    return chunks


# ---------------------------------------------------------------- fallback path
def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    return 0.0 if denom == 0 else float(np.dot(a, b) / denom)


async def _fallback_hybrid(
    question: str, query_embedding: list[float], k: int
) -> list[dict]:
    """$text lexical + brute-force cosine semantic, merged with RRF."""
    lexical: list[dict] = []
    try:
        cur = db.col(db.CHUNKS).find(
            {"$text": {"$search": question}}, {"score": {"$meta": "textScore"}, "text": 1,
                                                  "document_id": 1, "title": 1, "page": 1}
        ).sort([("score", {"$meta": "textScore"})]).limit(k * 4)
        lexical = [d async for d in cur]
    except Exception as e:  # noqa: BLE001
        log.debug(f"$text fallback skipped: {e}")

    semantic: list[dict] = []
    try:
        cur = db.col(db.CHUNKS).find({}, {"embedding": 1, "text": 1, "document_id": 1,
                                            "title": 1, "page": 1})
        q = np.asarray(query_embedding, dtype=np.float32)
        scored = []
        async for d in cur:
            v = d.get("embedding")
            if not v:
                continue
            scored.append((_cosine(q, np.asarray(v, dtype=np.float32)), d))
        scored.sort(key=lambda x: -x[0])
        semantic = [d for _, d in scored[: k * 4]]
    except Exception as e:  # noqa: BLE001
        log.warning(f"semantic fallback failed: {e}")

    def rrf_lists(lists: list[list[dict]], k_const: int = 60) -> dict[str, float]:
        scores: dict[str, float] = {}
        order: dict[str, dict] = {}
        for lst, mult in zip(lists, [1.0, 1.0]):
            for rank, doc in enumerate(lst):
                key = str(doc["_id"])
                scores[key] = scores.get(key, 0.0) + mult / (k_const + rank + 1)
                order.setdefault(key, doc)
        return {k: (scores[k], order[k]) for k in scores}

    fused = rrf_lists([lexical, semantic])
    ranked = sorted(fused.items(), key=lambda kv: -kv[1][0])[:k]
    out = []
    for key, (score, doc) in ranked:
        doc["score"] = score
        doc.pop("embedding", None)
        out.append(doc)
    return out


async def hybrid_search(
    question: str, k: int | None = None, full: bool | None = None
) -> list[dict]:
    """Returns ranked chunks {_id, text, document_id, title, page, score}."""
    k = k or settings.retrieval_top_k
    allowed, _ = await rate_limit(f"rl:search:{question[:16]}", 60, 60)
    if not allowed:
        log.warning("search rate limited")
    qv = embeddings.embed_one(question)
    mode = db.search_mode_sync()
    if (full if full is not None else mode["full_hybrid"]) and mode["mongot"]:
        chunks = await _full_hybrid(question, qv, k)
    else:
        chunks = await _fallback_hybrid(question, qv, k)
    chunks = await _apply_feedback_boosts(chunks)
    from app.core.reranker import rerank

    return rerank(question, chunks)


async def _apply_feedback_boosts(chunks: list[dict]) -> list[dict]:
    """Multiply scores by feedback-derived boost, then re-rank."""
    try:
        from app.core.feedback import compute_boosts

        boosts = await compute_boosts([str(c["_id"]) for c in chunks])
        if boosts:
            for c in chunks:
                c["score"] = float(c.get("score", 0)) * boosts.get(str(c["_id"]), 1.0)
            chunks.sort(key=lambda c: -float(c.get("score", 0)))
    except Exception as e:  # noqa: BLE001
        log.debug(f"feedback boost skipped: {e}")
    return chunks