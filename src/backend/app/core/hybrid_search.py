"""Hybrid search over the chunks collection.

Two modes, same output shape:
  * FULL  — mongot present: `$search` (lexical) + `$vectorSearch` (semantic)
            fused with MongoDB's native `$rankFusion`.
  * FALLBACK — mongot absent: `$text` (lexical) + brute-force cosine
            (semantic) merged with Reciprocal Rank Fusion (RRF). Identical
            result contract, runs on any replica set.

Also exposes multi-query retrieval: expand a question into several query
angles, retrieve for each, and fuse the result lists with RRF — a classic
retrieval-augmentation technique that lifts recall on hard questions.
"""

from __future__ import annotations

import logging

import numpy as np

from app import db
from app.config import settings
from app.core import embeddings
from app.telemetry import rate_limit

log = logging.getLogger("cogito.retrieval")

RRF_K = 60


async def _lexical_full(question: str, limit: int) -> list[dict]:
    """Chunks via native $search text."""
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
    """Native $rankFusion over search + vector branches.

    Correct MongoDB 8.0 `$rankFusion` shape: `input.pipelines.<name>` maps a
    name to its selection stages, and the fused RRF score is projected from
    `$scoreDetails.value`.
    """
    pipeline = [
        {
            "$rankFusion": {
                "input": {
                    "pipelines": {
                        "search": [
                            {"$search": {"index": "cogito_text",
                                         "text": {"query": question, "path": "text"}}},
                        ],
                        "vector": [
                            {"$vectorSearch": {
                                "index": "cogito_vector",
                                "path": "embedding",
                                "queryVector": query_embedding,
                                "numCandidates": settings.search_num_candidates,
                                "limit": max(settings.search_num_candidates, k * 4),
                            }},
                        ],
                    }
                },
                "scoreDetails": True,
            }
        },
        {"$limit": k},
        {"$project": {"_id": 1, "text": 1, "document_id": 1, "title": 1,
                      "page": 1, "score": "$scoreDetails.value"}},
    ]
    cur = db.col(db.CHUNKS).aggregate(pipeline)
    return [doc async for doc in cur]


# ---------------------------------------------------------------- fallback path
def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    return 0.0 if denom == 0 else float(np.dot(a, b) / denom)


def _rrf_fuse(lists: list[list[dict]], k_const: int = RRF_K) -> list[dict]:
    """Reciprocal Rank Fusion across any number of ranked lists.

    Returns a single list, ordered by descending fused score, with each doc's
    `score` set to its RRF value.
    """
    scores: dict[str, float] = {}
    order: dict[str, dict] = {}
    for lst in lists:
        for rank, doc in enumerate(lst):
            key = str(doc["_id"])
            scores[key] = scores.get(key, 0.0) + 1.0 / (k_const + rank + 1)
            order.setdefault(key, doc)
    fused = sorted(scores.items(), key=lambda kv: -kv[1])
    out = []
    for key, score in fused:
        doc = order[key]
        doc["score"] = score
        doc.pop("embedding", None)
        out.append(doc)
    return out


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

    return _rrf_fuse([lexical, semantic])[:k]


async def _retrieve_raw(
    question: str, k: int, full: bool | None = None
) -> list[dict]:
    """Embed + run lexical/semantic retrieval, returning ranked chunks before
    feedback boosting or reranking. Shared by single- and multi-query paths."""
    qv = embeddings.embed_one(question)
    mode = db.search_mode_sync()
    if (full if full is not None else mode["full_hybrid"]) and mode["mongot"]:
        return await _full_hybrid(question, qv, k)
    return await _fallback_hybrid(question, qv, k)


async def hybrid_search(
    question: str, k: int | None = None, full: bool | None = None
) -> list[dict]:
    """Returns ranked chunks {_id, text, document_id, title, page, score}."""
    k = k or settings.retrieval_top_k
    allowed, _ = await rate_limit(f"rl:search:{question[:16]}", 60, 60)
    if not allowed:
        log.warning("search rate limited")
    chunks = await _retrieve_raw(question, k, full)
    chunks = await _apply_feedback_boosts(chunks)
    from app.core.reranker import rerank

    return rerank(question, chunks)


async def multi_query_search(
    question: str, k: int | None = None, full: bool | None = None
) -> list[dict]:
    """Expand the question into multiple query angles, retrieve for each, and
    fuse the result lists with RRF. Improves recall for ambiguous/short queries.
    """
    k = k or settings.retrieval_top_k
    from app.core.query_expansion import expand_queries

    variants = await expand_queries(question)
    per_variant = [await _retrieve_raw(v, k * 3, full) for v in variants]
    chunks = _rrf_fuse(per_variant)[:k]
    chunks = await _apply_feedback_boosts(chunks)
    from app.core.reranker import rerank

    return rerank(question, chunks)


async def _apply_feedback_boosts(chunks: list[dict]) -> list[dict]:
    """Multiply scores by feedback-derived boost (a multiplier ≈ 1.0), then
    re-rank. Clamped so a down-voted chunk is suppressed, never negative."""
    try:
        from app.core.feedback import compute_boosts

        boosts = await compute_boosts([str(c["_id"]) for c in chunks])
        if boosts:
            for c in chunks:
                mult = max(0.25, min(4.0, float(boosts.get(str(c["_id"]), 1.0))))
                c["score"] = float(c.get("score", 0)) * mult
            chunks.sort(key=lambda c: -float(c.get("score", 0)))
    except Exception as e:  # noqa: BLE001
        log.debug(f"feedback boost skipped: {e}")
    return chunks
