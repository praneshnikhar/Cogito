"""Answer orchestration: search → grounded answer → LLM-judge eval → telemetry.
This is the read path backbone used by the API, MCP server, and agent."""

from __future__ import annotations

import logging
import time
from uuid import uuid4

from app import db, telemetry
from app.config import settings
from app.core.hybrid_search import hybrid_search
from app.core.llm import generate_cited_answer

log = logging.getLogger("cogito.service")


async def log_query(
    question: str,
    chunks: list[dict],
    latency_ms: int,
    answer_id: str | None,
    user_id: str | None = None,
) -> None:
    await db.col(db.QUERY_LOGS).insert_one(
        {
            "question": question,
            "chunks_returned": len(chunks),
            "chunk_ids": [str(c["_id"]) for c in chunks],
            "top_documents": [str(c["document_id"]) for c in chunks[:5]],
            "latency_ms": latency_ms,
            "answer_id": answer_id,
            "user_id": user_id,
            "ts": time.time(),
        }
    )


async def ask(
    question: str,
    k: int | None = None,
    user_id: str | None = None,
    full: bool | None = None,
) -> dict:
    chunks = await hybrid_search(question, k=k, full=full)
    return await ask_from_chunks(question, chunks, user_id)


async def ask_from_chunks(
    question: str, chunks: list[dict], user_id: str | None = None
) -> dict:
    """Generate a grounded, cited answer from pre-retrieved chunks, then log and
    evaluate it. Shared by the single-pass, agent, and multi-query paths."""
    start = time.time()
    answer = generate_cited_answer(question, chunks)
    answer["chunks"] = chunks
    answer["query"] = question
    latency = int((time.time() - start) * 1000)
    answer["latency_ms"] = latency

    answer_id = str(uuid4())
    await log_query(question, chunks, latency, answer_id, user_id)
    answer["answer_id"] = answer_id

    telemetry.capture("question_asked", {"answer_id": answer_id, "latency_ms": latency,
                                          "chunks": len(chunks)})

    if settings.evaluation_enabled:
        answer["eval"] = await evaluate(question, answer.get("answer", ""), chunks, answer_id)
    if telemetry.redis_client():
        await telemetry.cache_set(f"answer:{answer_id}", answer_id, 3600)
    return answer


async def evaluate(
    question: str, answer: str, chunks: list[dict], answer_id: str
) -> dict:
    """LLM-judge faithfulness + relevance scoring."""
    from app.core.evaluator import evaluate_answer

    try:
        result = evaluate_answer(question, answer, chunks)
        await db.col(db.EVAL_RESULTS).insert_one(
            {
                "answer_id": answer_id,
                "question": question,
                "faithfulness": result["faithfulness"],
                "relevance": result["relevance"],
                "judge": result.get("judge", settings.llm_provider),
                "ts": time.time(),
            }
        )
        # mirror to Postgres/Supabase analytics
        try:
            from app.integrations.supabase import record_eval

            await record_eval(answer_id, result)
        except Exception:  # noqa: BLE001
            pass
        return result
    except Exception as e:  # noqa: BLE001
        log.warning(f"eval failed: {e}")
        return {"faithfulness": None, "relevance": None, "error": str(e)}