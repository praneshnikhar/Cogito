"""Analytics dashboard — aggregation over query_logs, eval_results, feedback.
Powers both the web dashboard and the Supabase/Postgres mirror."""

from __future__ import annotations


from fastapi import APIRouter, Depends

from app import db
from app.deps import require_admin

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview")
async def overview():
    total = await db.col(db.QUERY_LOGS).count_documents({})
    from datetime import datetime, timezone

    start_of_day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today = await db.col(db.QUERY_LOGS).count_documents({"ts": {"$gte": start_of_day.timestamp()}})

    unanswered = []
    cur = db.col(db.QUERY_LOGS).aggregate(
        [{"$group": {"_id": None, "unanswered": {
            "$sum": {"$cond": [{"$eq": ["$chunks_returned", 0]}, 1, 0]}}}}]
    )
    async for r in cur:
        unanswered = r
    unanswered_count = (unanswered or {}).get("unanswered", 0) or 0

    latency = []
    cur = db.col(db.QUERY_LOGS).aggregate(
        [{"$group": {"_id": None, "avg": {"$avg": "$latency_ms"}, "max": {"$max": "$latency_ms"}}}]
    )
    async for r in cur:
        latency = r
    latency = latency or {}

    docs = await db.col(db.DOCUMENTS).count_documents({})
    chunks = await db.col(db.CHUNKS).count_documents({})
    memories = await db.col(db.MEMORIES).count_documents({})

    return {
        "total_queries": total,
        "queries_today": today,
        "unanswered": unanswered_count,
        "avg_latency_ms": round((latency.get("avg") or 0), 1),
        "max_latency_ms": round((latency.get("max") or 0), 1),
        "documents": docs,
        "chunks": chunks,
        "memories": memories,
        "rated_answers": await db.col(db.FEEDBACK).count_documents({}),
    }


@router.get("/queries")
async def top_queries(limit: int = 10):
    cur = db.col(db.QUERY_LOGS).aggregate(
        [{"$group": {"_id": "$question", "count": {"$sum": 1}}},
         {"$sort": {"count": -1}}, {"$limit": limit}]
    )
    return [{"question": r["_id"], "count": r["count"]} async for r in cur]


@router.get("/unanswered")
async def unanswered():
    cur = db.col(db.QUERY_LOGS).find({"chunks_returned": 0}).sort("ts", -1).limit(50)
    return [{"question": q["question"], "ts": q["ts"]} async for q in cur]


@router.get("/eval")
async def eval_summary():
    out = {}
    avg = db.col(db.EVAL_RESULTS).aggregate(
        [{"$group": {"_id": None, "f": {"$avg": "$faithfulness"},
                      "r": {"$avg": "$relevance"}, "n": {"$sum": 1}}}]
    )
    async for r in avg:
        out = {"avg_faithfulness": round((r.get("f") or 0), 3),
               "avg_relevance": round((r.get("r") or 0), 3), "samples": r.get("n", 0)}
    return out


@router.get("/freshness")
async def freshness():
    """Time from document drop to indexed (change-stream latency)."""
    cur = db.col(db.DOCUMENTS).aggregate(
        [{"$match": {"indexed_at": {"$exists": True}}},
         {"$project": {"_id": 1, "title": 1, "delta_s": {"$subtract": ["$indexed_at", "$created_at"]}}},
         {"$sort": {"delta_s": -1}}, {"$limit": 20}]
    )
    return [{"title": r["title"], "delta_s": round(r["delta_s"], 2)} async for r in cur]


@router.post("/rollup", dependencies=[Depends(require_admin)])
async def rollup():
    """Aggregate today's analytics into the Postgres/Supabase daily table."""
    from datetime import datetime, timezone

    from app.integrations.supabase import upsert_analytics_daily

    data = await overview()
    top = await top_queries(10)
    day = datetime.now(timezone.utc).date().isoformat()
    payload = {
        "total_queries": data["total_queries"],
        "unanswered": data["unanswered"],
        "avg_latency_ms": data["avg_latency_ms"],
        "top_questions": top,
        "by_source": data,
    }
    try:
        await upsert_analytics_daily(day, payload)
        return {"rolled_up": day, **payload}
    except Exception as e:  # noqa: BLE001
        return {"rolled_up": day, "error": str(e)}