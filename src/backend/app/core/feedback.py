"""Feedback loop — thumbs up/down feed back into retrieval ranking.

Each chunk carries a `boost` multiplier (default 1.0). A positive rating bumps
the referenced chunks up (increase multiplier); a negative rating suppresses
them (decrease multiplier). The multiplier is applied during hybrid retrieval.
"""

from __future__ import annotations

import logging
import time
from uuid import uuid4

from app import db, telemetry

log = logging.getLogger("cogito.feedback")

BOOST_UP = 0.5
BOOST_DOWN = -0.25
BOOST_FLOOR = 0.25
BOOST_CEIL = 4.0


async def record_feedback(
    answer_id: str, rating: int, comment: str | None = None
) -> dict:
    """rating: 1 = up, -1 = down, 0 = neutral."""
    fb_id = str(uuid4())
    await db.col(db.FEEDBACK).insert_one(
        {
            "_id": fb_id,
            "answer_id": answer_id,
            "rating": rating,
            "comment": comment,
            "ts": time.time(),
        }
    )
    telemetry.capture("feedback_rating", {"answer_id": answer_id, "rating": rating})
    # apply boost/suppress to the chunks that produced this answer
    log_row = await db.col(db.QUERY_LOGS).find_one({"answer_id": answer_id})
    chunk_ids = (log_row or {}).get("chunk_ids", [])
    delta = BOOST_UP if rating > 0 else (BOOST_DOWN if rating < 0 else 0.0)
    if delta and chunk_ids:
        # bump the multiplier, then clamp into a safe band
        await db.col(db.CHUNKS).update_many(
            {"_id": {"$in": chunk_ids}}, {"$inc": {"boost": delta}}
        )
        await db.col(db.CHUNKS).update_many(
            {"_id": {"$in": chunk_ids}, "boost": {"$lt": BOOST_FLOOR}},
            {"$set": {"boost": BOOST_FLOOR}},
        )
        await db.col(db.CHUNKS).update_many(
            {"_id": {"$in": chunk_ids}, "boost": {"$gt": BOOST_CEIL}},
            {"$set": {"boost": BOOST_CEIL}},
        )
        log.info(f"applied feedback delta {delta} to {len(chunk_ids)} chunks")
    return {"feedback_id": fb_id, "applied": bool(delta and chunk_ids)}


async def compute_boosts(chunk_ids: list[str]) -> dict[str, float]:
    """Read boost multipliers for a set of chunk ids (used by retrieval)."""
    if not chunk_ids:
        return {}
    cursor = db.col(db.CHUNKS).find({"_id": {"$in": chunk_ids}}, {"boost": 1, "_id": 1})
    out = {}
    async for c in cursor:
        b = c.get("boost")
        if b is not None:
            out[str(c["_id"])] = float(b)
    return out
