"""Chat history + long-term memory endpoints."""

from __future__ import annotations

import time
from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel

from app import db
from app.core import memory as mem
from app.core.service import ask
from app.routers import SessionUuid, user_id

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatMessage(BaseModel):
    role: str
    content: str


@router.post("")
async def chat(body: dict, x_user_id: SessionUuid = None):
    uid = user_id(x_user_id)
    message = body.get("message", "")
    conv_id = body.get("conversation_id")
    if not conv_id:
        conv_id = str(uuid4())
        await db.col(db.CONVERSATIONS).insert_one(
            {"_id": conv_id, "user_id": uid, "messages": [], "created_at": time.time()}
        )

    # augment with recalled long-term memory
    recalled = await mem.recall(uid, message)
    recalled_text = "\n".join(f"- {r['fact']}" for r in recalled)
    augmented = f"{message}\n\n[Your known facts]\n{recalled_text}" if recalled_text else message

    answer = await ask(augmented, user_id=uid)
    memory_extract = body.get("extract_memory", True)
    if memory_extract and len(message) > 8:
        m = await _maybe_extract_fact(uid, message, answer.get("answer", ""))
        if m:
            recalled.append(m)

    await db.col(db.CONVERSATIONS).update_one(
        {"_id": conv_id},
        {"$push": {"messages": {"$each": [
            {"role": "user", "content": message, "ts": time.time()},
            {"role": "assistant", "content": answer.get("answer", ""), "answer_id": answer["answer_id"], "ts": time.time()},
        ]}}},
    )
    answer["conversation_id"] = conv_id
    answer["memory_recalled"] = recalled
    return answer


async def _maybe_extract_fact(uid: str, question: str, answer: str) -> dict | None:
    """Very light fact extraction heuristic (upgraded by real LLM when set)."""
    lowered = question.lower()
    for prefix in ("my name is", "i am", "i work at", "my favorite"):
        if prefix in lowered:
            fact = question.strip()
            mid = await mem.remember(uid, fact, importance=1.2)
            return {"memory_id": mid, "fact": fact}
    return None


@router.get("/conversations")
async def list_conversations(x_user_id: SessionUuid = None):
    cur = db.col(db.CONVERSATIONS).find({"user_id": user_id(x_user_id)}).sort("created_at", -1).limit(50)
    return [c async for c in cur]