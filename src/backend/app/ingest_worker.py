"""Change-stream ingestion worker.

Watches `documents` for new/updated entries (the event-driven write path),
chunks + embeds + stores chunk vectors, and persists its resume token so
restarts never lose events. On startup it backfills any `pending` documents
left over from a previous crash or a worker-less API run.
"""

from __future__ import annotations

import asyncio
import logging

from app import db, telemetry
from app.core.ingestion import pending_documents, process_document

log = logging.getLogger("cogito.worker")

RESUME_KEY = "cogito:resume_token"


async def backfill_pending() -> None:
    pending = await pending_documents()
    log.info(f"backfill: {len(pending)} pending document(s)")
    for doc in pending:
        try:
            doc["raw"] = bytes(doc.get("raw") or b"")
            await process_document(doc)
        except Exception as e:  # noqa: BLE001
            log.error(f"backfill failed for {doc.get('_id')}: {e}")
            await db.col(db.DOCUMENTS).update_one(
                {"_id": doc["_id"]}, {"$set": {"status": "failed", "error": str(e)}}
            )


async def _save_resume_token(token) -> None:
    try:
        await telemetry.cache_set(RESUME_KEY, repr(token), 86400 * 7)
    except Exception:  # noqa: BLE001
        log.debug("could not persist resume token")


async def watch() -> None:
    resume_token = await telemetry.cache_get(RESUME_KEY)
    opts: dict = {"full_document": "updateLookup"}
    if resume_token:
        try:
            opts["resume_after"] = eval(resume_token)  # noqa: S307 - trusted persisted repr
        except Exception:  # noqa: BLE001
            opts.pop("resume_after", None)

    coll = db.col(db.DOCUMENTS)
    change_stream = coll.watch([], **opts)
    log.info("watching documents change stream")
    async with change_stream as cs:
        async for change in cs:
            doc = change.get("fullDocument")
            if doc and doc.get("status") == "pending":
                try:
                    doc["raw"] = bytes(doc.get("raw") or b"")
                    await process_document(doc)
                except Exception as e:  # noqa: BLE001
                    log.error(f"change-stream process failed: {e}")
                    try:
                        await db.col(db.DOCUMENTS).update_one(
                            {"_id": doc["_id"]},
                            {"$set": {"status": "failed", "error": str(e)}},
                        )
                    except Exception:  # noqa: BLE001
                        pass
            token = getattr(cs, "resume_token", None)
            if token:
                await _save_resume_token(token)


async def main() -> None:
    logging.basicConfig(level=getattr(logging, "INFO"))
    log.info("cogito ingest-worker starting")
    await db.ensure_indexes()
    await db.probe_search()
    log.info(f"search mode: {db.search_mode_sync()}")
    await backfill_pending()
    while True:
        try:
            await watch()
        except Exception as e:  # noqa: BLE001
            log.error(f"change stream dropped, reconnecting: {e}")
            await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())