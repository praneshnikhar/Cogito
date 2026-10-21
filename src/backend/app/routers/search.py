"""Search + answer endpoints — the read path."""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app import telemetry
from app.core.agent import run_agent
from app.core.hybrid_search import hybrid_search, multi_query_search
from app.core.service import ask, ask_from_chunks
from app.integrations.pinecone import search as pinecone_search
from app.routers import SessionUuid, user_id

router = APIRouter(tags=["read-path"])


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    k: int = Field(default=5, ge=1, le=20)


class CompareRequest(BaseModel):
    text: str = Field(min_length=1, max_length=10_000)


@router.post("/search")
async def search(
    query: str = Query(min_length=1, max_length=2000),
    k: int = Query(default=5, ge=1, le=20),
):
    chunks = await hybrid_search(query, k=k)
    return {"query": query, "chunks": chunks, "count": len(chunks)}


@router.post("/search/multi")
async def search_multi(
    query: str = Query(min_length=1, max_length=2000),
    k: int = Query(default=5, ge=1, le=20),
):
    chunks = await multi_query_search(query, k=k)
    return {"query": query, "chunks": chunks, "count": len(chunks), "mode": "multi-query"}


@router.post("/ask")
async def ask_question(body: AskRequest, x_user_id: SessionUuid = None):
    resp = await ask(body.question, k=body.k, user_id=user_id(x_user_id))
    return resp


@router.post("/ask/agent")
async def ask_agent(body: AskRequest, x_user_id: SessionUuid = None):
    resp = await run_agent(body.question, user_id(x_user_id))
    telemetry.capture("agent_query", {"iterations": resp["iterations"],
                                       "confidence": resp["confidence"]})
    return resp


@router.post("/ask/multi")
async def ask_multi(body: AskRequest, x_user_id: SessionUuid = None):
    """Grounded, cited answer using multi-query (expanded) retrieval."""
    chunks = await multi_query_search(body.question, k=body.k)
    return await ask_from_chunks(body.question, chunks, user_id=user_id(x_user_id))


@router.post("/compare/store")
async def compare_stores(body: CompareRequest):
    """Cross-store retrieval comparison (Mongo vs Pinecone)."""
    mongo = await hybrid_search(body.text, k=5)
    pinecone = await pinecone_search(body.text, 5)
    return {
        "query": body.text,
        "mongo": mongo,
        "pinecone": pinecone,
        "counts": {"mongo": len(mongo), "pinecone": len(pinecone)},
    }
