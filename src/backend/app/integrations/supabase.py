"""Supabase integration — auth check + analytics mirror.

When SUPABASE_URL is set we route auth/analytics through the Supabase REST
(PostgREST). Otherwise we use the compatible local Postgres (via SQLAlchemy
asyncpg). This makes Cogito deployable to Vercel/edge with a real Supabase
project, or fully local with zero accounts.
"""

from __future__ import annotations

import json
import logging

from app.config import settings

log = logging.getLogger("cogito.supabase")

_pg = None
_sb = None


def _postgres():
    global _pg
    if _pg is None:
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(settings.postgres_dsn)
        _pg = {"engine": engine}
    return _pg


def _supabase():
    global _sb
    if _sb is None and settings.supabase_url:
        try:
            from supabase import create_client

            _sb = create_client(settings.supabase_url, settings.supabase_anon_key)
        except Exception as e:  # noqa: BLE001
            log.warning(f"supabase client failed: {e}")
            _sb = False
    return _sb if _sb else None


async def _pg_exec(sql: str, params: tuple | None = None) -> None:
    from sqlalchemy import text

    eng = _postgres()["engine"]
    async with eng.connect() as conn:
        await conn.execute(text(sql), params or {})
        await conn.commit()


async def record_eval(answer_id: str, result: dict) -> None:
    sb = _supabase()
    if sb:
        try:
            sb.table("eval_scores").insert(
                {
                    "answer_id": answer_id,
                    "faithfulness": result.get("faithfulness"),
                    "relevance": result.get("relevance"),
                    "judge": result.get("judge"),
                }
            ).execute()
            return
        except Exception:  # noqa: BLE001
            pass
    try:
        await _pg_exec(
            "INSERT INTO eval_scores (answer_id, faithfulness, relevance, judge) "
            "VALUES (:answer_id, :f, :r, :j)",
            {"answer_id": answer_id, "f": result.get("faithfulness"),
             "r": result.get("relevance"), "j": result.get("judge")},
        )
    except Exception as e:  # noqa: BLE001
        log.debug(f"eval mirror skipped: {e}")


async def record_feedback(answer_id: str, rating: int, comment: str | None) -> None:
    sb = _supabase()
    if sb:
        try:
            sb.table("feedback_events").insert(
                {"answer_id": answer_id, "rating": rating, "comment": comment}
            ).execute()
            return
        except Exception:  # noqa: BLE001
            pass
    try:
        await _pg_exec(
            "INSERT INTO feedback_events (answer_id, rating, comment) "
            "VALUES (:answer_id, :rating, :comment)",
            {"answer_id": answer_id, "rating": rating, "comment": comment},
        )
    except Exception as e:  # noqa: BLE001
        log.debug(f"feedback mirror skipped: {e}")


async def upsert_analytics_daily(day: str, payload: dict) -> None:
    sb = _supabase()
    if sb:
        try:
            sb.table("query_analytics_daily").upsert(
                {"day": day, **payload}
            ).execute()
            return
        except Exception:  # noqa: BLE001
            pass
    try:
        await _pg_exec(
            """
            INSERT INTO query_analytics_daily (day, total_queries, unanswered,
                avg_latency_ms, top_questions, by_source)
            VALUES (:day, :total, :unanswered, :avg, CAST(:top AS jsonb), CAST(:src AS jsonb))
            ON CONFLICT (day) DO UPDATE SET
                total_queries = EXCLUDED.total_queries,
                unanswered = EXCLUDED.unanswered,
                avg_latency_ms = EXCLUDED.avg_latency_ms,
                top_questions = EXCLUDED.top_questions,
                by_source = EXCLUDED.by_source,
                updated_at = now()
            """,
            {
                "day": day,
                "total": payload.get("total_queries", 0),
                "unanswered": payload.get("unanswered", 0),
                "avg": payload.get("avg_latency_ms", 0),
                "top": json.dumps(payload.get("top_questions", [])),
                "src": json.dumps(payload.get("by_source", [])),
            },
        )
    except Exception as e:  # noqa: BLE001
        log.debug(f"analytics mirror skipped: {e}")