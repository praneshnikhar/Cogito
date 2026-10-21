"""Memory + feedback + evaluation endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import db
from app.core import memory as mem
from app.core.feedback import record_feedback
from app.deps import require_admin
from app.integrations.supabase import record_feedback as sb_feedback
from app.routers import SessionUuid, user_id

router = APIRouter(tags=["memory"])


class MemoryCreate(BaseModel):
    fact: str = Field(min_length=1, max_length=5000)
    importance: float = Field(default=1.0, ge=0, le=10)


class MemoryUpdate(BaseModel):
    fact: str | None = Field(default=None, min_length=1, max_length=5000)
    importance: float | None = Field(default=None, ge=0, le=10)


class RecallRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)


@router.post("/memories", dependencies=[Depends(require_admin)])
async def add_memory(body: MemoryCreate, x_user_id: SessionUuid = None):
    fact = body.fact.strip()
    if not fact:
        raise HTTPException(400, "fact is required")
    mid = await mem.remember(user_id(x_user_id), fact, importance=body.importance)
    return {"memory_id": mid}


@router.get("/memories")
async def get_memories(x_user_id: SessionUuid = None):
    return await mem.list_memories(user_id(x_user_id))


@router.patch("/memories/{memory_id}", dependencies=[Depends(require_admin)])
async def edit_memory(memory_id: str, body: MemoryUpdate, x_user_id: SessionUuid = None):
    if body.fact is None and body.importance is None:
        raise HTTPException(400, "nothing to update")
    updated = await mem.update_memory(
        user_id(x_user_id), memory_id, fact=body.fact, importance=body.importance
    )
    if not updated:
        raise HTTPException(404, "memory not found")
    updated["_id"] = str(updated["_id"])
    updated.pop("embedding", None)
    return updated


@router.delete("/memories/{memory_id}", dependencies=[Depends(require_admin)])
async def remove_memory(memory_id: str, x_user_id: SessionUuid = None):
    if not await mem.delete_memory(user_id(x_user_id), memory_id):
        raise HTTPException(404, "memory not found")
    return {"deleted": True, "memory_id": memory_id}


@router.post("/memories/recall", dependencies=[Depends(require_admin)])
async def recall_memories(body: RecallRequest, x_user_id: SessionUuid = None):
    return await mem.recall(user_id(x_user_id), body.query)


@router.post("/feedback", dependencies=[Depends(require_admin)])
async def feedback(body: dict):
    rating = int(body.get("rating", 0))
    if rating not in (-1, 0, 1):
        raise HTTPException(400, "rating must be -1, 0, or 1")
    out = await record_feedback(body.get("answer_id", ""), rating, body.get("comment"))
    try:
        await sb_feedback(body.get("answer_id", ""), rating, body.get("comment"))
    except Exception:  # noqa: BLE001, S110
        pass
    return out


@router.get("/eval")
async def list_evals(limit: int = 100):
    cur = db.col(db.EVAL_RESULTS).find().sort("ts", -1).limit(limit)
    # _id is a Mongo ObjectId here; stringify so FastAPI can serialize it
    return [{**e, "_id": str(e.get("_id"))} async for e in cur]