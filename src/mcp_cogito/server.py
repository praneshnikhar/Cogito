"""Cogito as an MCP server — exposes the knowledge base as tools so any MCP
client (Claude Desktop, Cursor, Gemini CLI, Codex) can query it.

Tools:
  * list_sources        — enumerate indexed documents
  * search_knowledge    — hybrid search, return ranked chunks
  * ask_question        — grounded, cited answer
  * add_document        — ingest + index a local file
  * remember / recall   — long-term memory
"""

from __future__ import annotations

import asyncio
import logging
import sys

from mcp.server.fastmcp import FastMCP

from app import db
from app.core.hybrid_search import hybrid_search
from app.core.ingestion import create_document, process_document
from app.core.service import ask

# MCP stdio protocol uses stdout for JSON-RPC only — log to stderr.
logging.basicConfig(level=logging.INFO, stream=sys.stderr)

mcp = FastMCP(
    "Cogito",
    instructions="MongoDB-native RAG knowledge assistant. Ground answers in retrieved chunks.",
)


@mcp.tool()
async def list_sources() -> list[dict]:
    """List every indexed knowledge source."""
    cur = db.col(db.DOCUMENTS).find({"status": "indexed"}, {"raw": 0}).sort("created_at", -1).limit(200)
    return [
        {"document_id": str(d["_id"]), "title": d.get("title"), "type": d.get("type"),
         "chunks": d.get("chunk_count", 0)} async for d in cur
    ]


@mcp.tool()
async def search_knowledge(query: str, k: int = 5) -> list[dict]:
    """Hybrid (keyword + semantic) search over the knowledge base."""
    chunks = await hybrid_search(query, k=k)
    return [
        {"text": c.get("text"), "source": c.get("title"), "page": c.get("page"),
         "score": round(float(c.get("score", 0)), 3)} for c in chunks
    ]


@mcp.tool()
async def ask_question(question: str) -> dict:
    """Answer a question, grounded in retrieved chunks with citations."""
    result = await ask(question)
    return {
        "answer": result.get("answer", ""),
        "citations": result.get("citations", []),
        "eval": result.get("eval"),
    }


@mcp.tool()
async def add_document(path: str, doc_type: str = "text") -> dict:
    """Read a local file and index it (chunk + embed + store)."""
    import pathlib

    p = pathlib.Path(path).expanduser().resolve()
    if not p.exists():
        return {"ok": False, "error": f"not found: {p}"}
    raw = p.read_bytes()
    doc_id = await create_document(str(p), raw, doc_type, "mcp")
    # process inline so the MCP caller sees it indexed immediately
    doc = await db.col(db.DOCUMENTS).find_one({"_id": doc_id})
    doc["raw"] = bytes(doc.get("raw") or b"")
    return await process_document(doc)


@mcp.tool()
async def remember(fact: str) -> str:
    """Store a long-term fact for future recall."""
    from app.core.memory import remember as _remember
    mid = await _remember("mcp", fact)
    return f"Remembered ({mid})."


@mcp.tool()
async def recall(query: str, limit: int = 3) -> list[dict]:
    """Recall long-term facts relevant to a query."""
    from app.core.memory import recall as _recall
    return await _recall("mcp", query, limit)


if __name__ == "__main__":
    async def _bootstrap() -> None:
        await db.ensure_indexes()
        await db.probe_search()

    asyncio.run(_bootstrap())
    mcp.run()