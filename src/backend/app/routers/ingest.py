"""Ingestion endpoints — the write path."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel

from app import db
from app.core.ingestion import create_document
from app.deps import require_admin

router = APIRouter(prefix="/ingest", tags=["ingest"])


class IngestResult(BaseModel):
    document_id: str
    status: str = "queued"


@router.post("", response_model=IngestResult, dependencies=[Depends(require_admin)])
async def ingest_file(
    file: UploadFile = File(...),
    doc_type: str = Form("text"),
    source: str = Form("upload"),
) -> IngestResult:
    raw = await file.read()
    doc_id = await create_document(file.filename or "doc.txt", raw, doc_type, source)
    return IngestResult(document_id=doc_id)


@router.post("/raw", dependencies=[Depends(require_admin)])
async def ingest_raw(body: dict) -> IngestResult:
    text = body.get("text", "")
    filename = body.get("filename", "raw.txt")
    doc_type = body.get("type", "text")
    doc_id = await create_document(filename, text.encode("utf-8"), doc_type, "raw")
    return IngestResult(document_id=doc_id)


@router.get("/documents")
async def list_documents(status: str | None = None):
    q = {"status": status} if status else {}
    cur = db.col(db.DOCUMENTS).find(q, {"raw": 0}).sort("created_at", -1).limit(200)
    return [d async for d in cur]