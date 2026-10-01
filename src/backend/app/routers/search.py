"""Search + answer endpoints — the read path."""

from __future__ import annotations

from fastapi import APIRouter

from app import telemetry
from app.core.agent import run_agent
from app.core.hybrid_search import hybrid_search, multi_query_search
from app.core.service import ask, ask_from_chunks
from app.integrations.pinecone import search as pinecone_search
from app.routers import SessionUuid, user_id

router = APIRouter(tags=["read-path"])


@router.post("/search")
async def search(query: str, k: int = 5):
    chunks = await hybrid_search(query, k=k)
    return {"query": query, "chunks": chunks, "count": len(chunks)}


@router.post("/search/multi")
async def search_multi(query: str, k: int = 5):
    chunks = await multi_query_search(query, k=k)
    return {"query": query, "chunks": chunks, "count": len(chunks), "mode": "multi-query"}


@router.post("/ask")
async def ask_question(body: dict, x_user_id: SessionUuid = None):
    question = body.get("question", "")
    k = body.get("k") or 5
    resp = await ask(question, k=k, user_id=user_id(x_user_id))
    return resp


@router.post("/ask/agent")
async def ask_agent(body: dict, x_user_id: SessionUuid = None):
    question = body.get("question", "")
    resp = await run_agent(question, user_id(x_user_id))
    telemetry.capture("agent_query", {"iterations": resp["iterations"],
                                       "confidence": resp["confidence"]})
    return resp


@router.post("/ask/multi")
async def ask_multi(body: dict, x_user_id: SessionUuid = None):
    """Grounded, cited answer using multi-query (expanded) retrieval."""
    question = body.get("question", "")
    k = body.get("k") or 5
    chunks = await multi_query_search(question, k=k)
    return await ask_from_chunks(question, chunks, user_id(x_user_id))


@router.post("/compare/store")
async def compare_stores(body: dict):
    """Cross-store retrieval comparison (Mongo vs Pinecone)."""
    text = body.get("text", "")

    mongo = await hybrid_search(text, k=5)
    pinecone = await pinecone_search(text, 5)
    return {
        "query": text,
        "mongo": mongo,
        "pinecone": pinecone,
        "counts": {"mongo": len(mongo), "pinecone": len(pinecone)},
    }