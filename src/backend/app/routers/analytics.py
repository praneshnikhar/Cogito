"""Analytics dashboard — MongoDB aggregation over query_logs, eval_results,
feedback. Powers both the web dashboard and the Supabase/Postgres mirror.

The overview endpoint deliberately showcases `$facet` (many metrics in one
pass), `$bucketAuto` (latency histogram), and `$dateToString` + `$group`
(query volume over time) — the same operators you would use in a production
MongoDB analytics pipeline.
"""

from __future__ import annotations


from fastapi import APIRouter, Depends

from app import db
from app.deps import require_admin

router = APIRouter(prefix="/analytics", tags=["analytics"])


async def _query_log_facets() -> dict:
    """One $facet pass computing totals, unanswered, latency, and daily volume."""
    facet_pipeline = [
        {
            "$facet": {
                "totals": [{"$count": "n"}],
                "unanswered": [
                    {"$match": {"chunks_returned": 0}},
                    {"$count": "n"},
                ],
                "latency": [
                    {"$group": {
                        "_id": None,
                        "avg": {"$avg": "$latency_ms"},
                        "max": {"$max": "$latency_ms"},
                        "p50": {"$avg": "$latency_ms"},  # placeholder; use $percentile on Atlas
                    }},
                ],
                "by_day": [
                    {"$group": {
                        "_id": {
                            "$dateToString": {
                                "format": "%Y-%m-%d",
                                "date": {"$toDate": {"$multiply": ["$ts", 1000]}},
                            }
                        },
                        "count": {"$sum": 1},
                    }},
                    {"$sort": {"_id": 1}},
                ],
            }
        }
    ]
    result: dict = {}
    async for r in db.col(db.QUERY_LOGS).aggregate(facet_pipeline):
        result = r
    return result


async def _latency_histogram() -> list[dict]:
    """$bucketAuto latency distribution over 8 adaptive buckets."""
    pipeline = [
        {"$match": {"latency_ms": {"$exists": True}}},
        {"$bucketAuto": {"groupBy": "$latency_ms", "buckets": 8}},
    ]
    out = []
    async for r in db.col(db.QUERY_LOGS).aggregate(pipeline):
        lo = round(r["_id"]["min"], 0)
        hi = round(r["_id"]["max"], 0)
        out.append({"bucket": f"{lo}-{hi}ms", "count": r["count"]})
    return out


@router.get("/overview")
async def overview():
    facets = await _query_log_facets()

    def _num(path: list[str], key: str, default=0):
        node = facets
        for p in path:
            node = (node or {}).get(p) or {}
            if node is None:
                return default
        return node.get(key) or default

    total = _num(["totals"], "n")
    unanswered = _num(["unanswered"], "n")
    latency = facets.get("latency") or {}
    by_day = facets.get("by_day") or []

    from datetime import datetime, timezone

    start_of_day = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    queries_today = await db.col(db.QUERY_LOGS).count_documents(
        {"ts": {"$gte": start_of_day.timestamp()}}
    )

    docs = await db.col(db.DOCUMENTS).count_documents({})
    chunks = await db.col(db.CHUNKS).count_documents({})
    memories = await db.col(db.MEMORIES).count_documents({})

    return {
        "total_queries": total,
        "queries_today": queries_today,
        "unanswered": unanswered,
        "avg_latency_ms": round((latency.get("avg") or 0), 1),
        "max_latency_ms": round((latency.get("max") or 0), 1),
        "queries_by_day": by_day,
        "documents": docs,
        "chunks": chunks,
        "memories": memories,
        "rated_answers": await db.col(db.FEEDBACK).count_documents({}),
    }


@router.get("/histogram")
async def histogram():
    """Latency distribution via $bucketAuto."""
    return {"buckets": await _latency_histogram()}


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
