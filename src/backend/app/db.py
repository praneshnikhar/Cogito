"""MongoDB access layer — Motor async driver, collection handles, replica-set
and mongot (search) feature detection, and index provisioning."""

from __future__ import annotations

import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from pymongo.errors import OperationFailure

from app.config import settings

log = logging.getLogger("cogito.db")

_client: AsyncIOMotorClient | None = None
_db: Any = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.effective_mongo_uri)
    return _client


def db() -> Any:
    global _db
    if _db is None:
        _db = get_client()[settings.mongodb_db]
    return _db


def col(name: str) -> AsyncIOMotorCollection:
    return db()[name]


DOCUMENTS = "documents"
CHUNKS = "chunks"
MEMORIES = "memories"
QUERY_LOGS = "query_logs"
EVAL_RESULTS = "eval_results"
FEEDBACK = "feedback"
CONVERSATIONS = "conversations"


async def is_replica_set() -> bool:
    try:
        info = await get_client().admin.command({"replSetGetStatus": 1})
        return bool(info.get("ok"))
    except Exception:
        return False


async def mongot_available() -> bool:
    """Probe for MongoDB Search (mongot) by trying to create a $search index.
    Works on the collection regardless; the index is the same one we need."""
    try:
        await col(CHUNKS).create_search_index(
            {
                "name": "cogito_text",
                "type": "search",
                "definition": {
                    "mappings": {"dynamic": False, "fields": {"text": {"type": "string"}}}
                },
            }
        )
        return True
    except OperationFailure as e:
        log.info(f"mongot not available (search index unsupported): {e}")
        return False
    except Exception as e:  # noqa: BLE001
        log.info(f"mongot probe failed: {e}")
        return False


async def _vector_index():
    """HNSW vector index required by $vectorSearch."""
    return {
        "name": "cogito_vector",
        "type": "vectorSearch",
        "definition": {
            "fields": [
                {
                    "type": "vector",
                    "path": "embedding",
                    "numDimensions": settings.embedding_dim,
                    "similarity": "cosine",
                    "quantization": "scalar",
                }
            ]
        },
    }


async def ensure_indexes() -> None:

    # Plain indexes (work regardless of mongot)
    await col(DOCUMENTS).create_index("status")
    await col(DOCUMENTS).create_index([("path", 1), ("hash", 1)])
    await col(CHUNKS).create_index([("document_id", 1)])
    await col(CHUNKS).create_index([("token_count", 1)])
    await col(QUERY_LOGS).create_index("ts")
    await col(MEMORIES).create_index([("user_id", 1), ("updated_at", -1)])

    # Text index as the lexical fallback when mongot is absent
    try:
        await col(CHUNKS).create_index({"text": "text"})
    except OperationFailure as e:
        log.warning(f"could not create text index: {e}")

    # Vector index — needs mongot/Atlas
    try:
        await col(CHUNKS).create_search_index(await _vector_index())
        log.info("vector search index ready")
    except OperationFailure as e:
        log.info(f"vector index not created (mongot absent); using cosine fallback: {e}")


async def search_mode() -> dict[str, Any]:
    """Report what retrieval capabilities are actually available."""
    rs = await is_replica_set()
    mongot = await mongot_available()
    return {
        "replica_set": rs,
        "mongot": mongot,
        "full_hybrid": rs and mongot,  # $search + $vectorSearch + $rankFusion
        "semantic_fallback": True,  # brute-force cosine always possible
        "lexical_fallback": True,  # $text index
    }


# Feature flag cached once at startup so search hot-path is cheap.
_search_features: dict[str, Any] | None = None


async def probe_search() -> dict[str, Any]:
    """Idempotent startup probe that seeds the cached feature set."""
    global _search_features
    if _search_features is None:
        _search_features = await search_mode()
    return _search_features


def search_mode_sync() -> dict[str, Any]:
    global _search_features
    if _search_features is None:
        _search_features = {
            "replica_set": True,
            "mongot": False,
            "full_hybrid": False,
            "semantic_fallback": True,
            "lexical_fallback": True,
        }
    return _search_features