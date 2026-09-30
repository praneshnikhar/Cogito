"""Memory + feedback + evaluation endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app import db
from app.core import memory as mem
from app.core.feedback import record_feedback
from app.integrations.supabase import record_feedback as sb_feedback
from app.routers import SessionUuid, user_id
from app.deps import require_admin

router = APIRouter(tags=["memory"])


@router.post("/memories", dependencies=[Depends(require_admin)])
async def add_memory(body: dict, x_user_id: SessionUuid = None):
    fact = body.get("fact", "").strip()
    if not fact:
        raise HTTPException(400, "fact is required")
    mid = await mem.remember(user_id(x_user_id), fact, importance=body.get("importance", 1.0))
    return {"memory_id": mid}


@router.get("/memories")
async def get_memories(x_user_id: SessionUuid = None):
    return await mem.list_memories(user_id(x_user_id))


@router.post("/memories/recall", dependencies=[Depends(require_admin)])
async def recall_memories(body: dict, x_user_id: SessionUuid = None):
    return await mem.recall(user_id(x_user_id), body.get("query", ""))


@router.post("/feedback", dependencies=[Depends(require_admin)])
async def feedback(body: dict):
    rating = int(body.get("rating", 0))
    if rating not in (-1, 0, 1):
        raise HTTPException(400, "rating must be -1, 0, or 1")
    out = await record_feedback(body.get("answer_id", ""), rating, body.get("comment"))
    try:
        await sb_feedback(body.get("answer_id", ""), rating, body.get("comment"))
    except Exception:  # noqa: BLE001
        pass
    return out


@router.get("/eval")
async def list_evals(limit: int = 100):
    cur = db.col(db.EVAL_RESULTS).find().sort("ts", -1).limit(limit)
    return [e async for e in cur]