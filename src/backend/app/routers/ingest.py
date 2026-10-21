"""Ingestion endpoints — the write path (full CRUD for documents)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from bson import Binary
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app import db
from app.core.chunker import content_hash
from app.core.ingestion import create_document
from app.deps import require_admin

router = APIRouter(prefix="/ingest", tags=["ingest"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_TEXT_CHARS = 2_000_000
DOC_TYPES = {"text", "contract", "markdown", "html", "csv", "json", "pdf", "docx", "image"}
TEXT_EXTENSIONS = (".txt", ".md", ".markdown", ".csv", ".json", ".html", ".htm")
TEXT_MIMES = ("text/", "application/json")


class IngestResult(BaseModel):
    document_id: str
    status: str = "queued"


class RawIngestRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    filename: str = Field(default="raw.txt", min_length=1, max_length=255)
    type: str = Field(default="text", max_length=32)


class DocumentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    type: str | None = Field(default=None, max_length=32)
    text: str | None = Field(default=None, max_length=MAX_TEXT_CHARS)


def _clean_filename(name: str) -> str:
    cleaned = Path(name or "doc.txt").name.strip()
    return cleaned or "doc.txt"


def _validate_type(doc_type: str) -> str:
    normalized = (doc_type or "text").strip().lower()
    if normalized not in DOC_TYPES:
        raise HTTPException(422, f"type must be one of: {', '.join(sorted(DOC_TYPES))}")
    return normalized


def _is_text_doc(doc: dict[str, Any]) -> bool:
    path = str(doc.get("path") or doc.get("title") or "").lower()
    mime = str(doc.get("mime") or "").lower()
    doc_type = str(doc.get("type") or "").lower()
    return (
        path.endswith(TEXT_EXTENSIONS)
        or mime.startswith(TEXT_MIMES)
        or doc_type in {"text", "contract", "markdown", "html", "csv", "json"}
    )


def _serialize(doc: dict[str, Any], include_text: bool = False) -> dict[str, Any]:
    out = {k: v for k, v in doc.items() if k != "raw"}
    out["editable"] = _is_text_doc(doc)
    if include_text and out["editable"]:
        raw = doc.get("raw")
        payload = bytes(raw) if isinstance(raw, (bytes, Binary)) else b""
        out["text"] = payload.decode("utf-8", errors="ignore")
    return out


@router.post("", response_model=IngestResult, dependencies=[Depends(require_admin)])
async def ingest_file(
    file: UploadFile = File(...),  # noqa: B008
    doc_type: str = Form("text"),
    source: str = Form("upload"),
) -> IngestResult:
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "file is empty")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "file too large (max 10 MB)")
    doc_id = await create_document(
        _clean_filename(file.filename or "doc.txt"),
        raw,
        _validate_type(doc_type),
        source[:64],
    )
    return IngestResult(document_id=doc_id)


@router.post("/raw", dependencies=[Depends(require_admin)])
async def ingest_raw(body: RawIngestRequest) -> IngestResult:
    doc_id = await create_document(
        _clean_filename(body.filename), body.text.encode("utf-8"),
        _validate_type(body.type), "raw",
    )
    return IngestResult(document_id=doc_id)


@router.get("/documents")
async def list_documents(status: str | None = None, limit: int = 100):
    q = {"status": status} if status else {}
    limit = max(1, min(limit, 200))
    cur = db.col(db.DOCUMENTS).find(q, {"raw": 0}).sort("created_at", -1).limit(limit)
    return [d async for d in cur]


@router.get("/documents/{doc_id}")
async def get_document(doc_id: str, include_text: bool = False):
    doc = await db.col(db.DOCUMENTS).find_one({"_id": doc_id})
    if not doc:
        raise HTTPException(404, "document not found")
    return _serialize(doc, include_text=include_text)


@router.get("/documents/{doc_id}/chunks")
async def get_document_chunks(doc_id: str, limit: int = 50):
    exists = await db.col(db.DOCUMENTS).find_one({"_id": doc_id}, {"_id": 1})
    if not exists:
        raise HTTPException(404, "document not found")
    limit = max(1, min(limit, 200))
    cur = (
        db.col(db.CHUNKS)
        .find({"document_id": doc_id}, {"embedding": 0})
        .sort("order", 1)
        .limit(limit)
    )
    return [c async for c in cur]


@router.patch("/documents/{doc_id}", dependencies=[Depends(require_admin)])
async def update_document(doc_id: str, body: DocumentUpdate):
    doc = await db.col(db.DOCUMENTS).find_one({"_id": doc_id})
    if not doc:
        raise HTTPException(404, "document not found")

    fields: dict[str, Any] = {}
    if body.title is not None:
        fields["title"] = body.title.strip()
    if body.type is not None:
        fields["type"] = _validate_type(body.type)
    if body.text is not None:
        if not _is_text_doc(doc):
            raise HTTPException(422, "content of this file type cannot be edited as text")
        if not body.text.strip():
            raise HTTPException(400, "text cannot be empty")
        fields.update(
            {
                "raw": Binary(body.text.encode("utf-8")),
                "hash": content_hash(body.text),
                "status": "pending",
                "updated_at": time.time(),
            }
        )

    if not fields:
        raise HTTPException(400, "nothing to update")

    update: dict[str, Any] = {"$set": fields}
    if body.text is not None:
        update["$unset"] = {"error": ""}
    await db.col(db.DOCUMENTS).update_one({"_id": doc_id}, update)
    if body.title is not None:
        # The title is denormalized onto chunks for citations; keep them in sync.
        await db.col(db.CHUNKS).update_many(
            {"document_id": doc_id}, {"$set": {"title": fields["title"]}}
        )

    updated = await db.col(db.DOCUMENTS).find_one({"_id": doc_id})
    return _serialize(updated or {}, include_text=True)


@router.post("/documents/{doc_id}/reindex", dependencies=[Depends(require_admin)])
async def reindex_document(doc_id: str):
    doc = await db.col(db.DOCUMENTS).find_one({"_id": doc_id}, {"_id": 1})
    if not doc:
        raise HTTPException(404, "document not found")
    await db.col(db.DOCUMENTS).update_one(
        {"_id": doc_id},
        {"$set": {"status": "pending", "updated_at": time.time()}, "$unset": {"error": ""}},
    )
    return {"document_id": doc_id, "status": "pending"}


@router.delete("/documents/{doc_id}", dependencies=[Depends(require_admin)])
async def delete_document(doc_id: str):
    doc = await db.col(db.DOCUMENTS).find_one({"_id": doc_id}, {"_id": 1})
    if not doc:
        raise HTTPException(404, "document not found")

    deleted_chunks = await _delete_document_and_chunks(doc_id)
    return {"deleted": True, "document_id": doc_id, "chunks_deleted": deleted_chunks}


async def _delete_document_and_chunks(doc_id: str) -> int:
    """Delete the document and every chunk atomically when possible."""
    chunks = db.col(db.CHUNKS)
    documents = db.col(db.DOCUMENTS)
    client = db.get_client()
    try:
        async with await client.start_session() as session, session.start_transaction():
            result = await chunks.delete_many({"document_id": doc_id}, session=session)
            await documents.delete_one({"_id": doc_id}, session=session)
        return int(result.deleted_count)
    except Exception:  # noqa: BLE001
        result = await chunks.delete_many({"document_id": doc_id})
        await documents.delete_one({"_id": doc_id})
        return int(result.deleted_count)
