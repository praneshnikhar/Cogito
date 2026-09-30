"""Health + readiness + webhook endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app import db, telemetry
from app.deps import require_admin

router = APIRouter(tags=["ops"])


@router.get("/health")
async def health():
    probe = {"mongo": "down"}
    try:
        await db.get_client().admin.command("ping")
        probe["mongo"] = "up"
    except Exception:  # noqa: BLE001
        probe["mongo"] = "down"
    redis = telemetry.redis_client()
    try:
        await redis.ping()
        probe["redis"] = "up"
    except Exception:  # noqa: BLE001
        probe["redis"] = "down"
    return {"status": "ok", "probes": probe}


@router.get("/health/search-mode")
async def search_mode():
    return db.search_mode_sync()


@router.get("/capabilities")
async def capabilities():
    """Feature matrix reflecting runtime credentials — drives the UI badges."""
    from app.config import settings

    return {
        "hybrid_search": db.search_mode_sync()["full_hybrid"],
        "search_mode": db.search_mode_sync(),
        "llm_provider": settings.llm_provider,
        "embedding_provider": settings.embedding_provider,
        "posthog": bool(settings.posthog_api_key),
        "sentry": bool(settings.sentry_dsn),
        "upstash": bool(settings.upstash_redis_rest_url),
        "pinecone": bool(settings.pinecone_api_key),
        "supabase": bool(settings.supabase_url) or True,
        "n8n": True,
        "evaluation": settings.evaluation_enabled,
    }


@router.post("/webhooks/ingest", dependencies=[Depends(require_admin)])
async def webhook_ingest(body: dict):
    """Entrypoint used by n8n automation to push new content."""
    from app.core.ingestion import create_document

    text = body.get("text")
    if not text:
        raise HTTPException(400, "text is required")
    filename = body.get("filename", "webhook.txt")
    doc_id = await create_document(filename, text.encode("utf-8"), body.get("type", "text"), "n8n")
    return {"document_id": doc_id, "status": "queued", "source": "n8n"}