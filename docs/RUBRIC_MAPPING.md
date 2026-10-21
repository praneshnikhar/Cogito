# Cogito — Rubric Mapping

The evaluation rubric is capability-based, not tied to one fixed application.
Cogito is a real-world document assistant built on MongoDB, so it satisfies the
rubric while remaining a genuinely useful system. This file maps every criterion
to concrete evidence you can open during the viva.

| # | Criterion | How Cogito satisfies it | Evidence |
|---|---|---|---|
| 1 | Problem identification and real-world relevance | Teams need answers from contracts, policies, and notices; keyword-only search misses paraphrases, vector-only search misses clause numbers, and most tools return answers without sources. Cogito indexes documents automatically and answers with citations. | `docs/PROJECT_REPORT.md` §1–2; `/documents`, `/chat` UI |
| 2 | NoSQL selection and justification | MongoDB stores each chunk, its vector, and its metadata as one document; the same deployment provides keyword search, vector search, change streams, transactions, and aggregation. A relational design would need joins, a separate search engine, and a separate vector store. | `docs/PROJECT_REPORT.md` §3; `docs/DATABASE.md`; `docs/VIVA_PREP.md` Q1 |
| 3 | Database design and data modeling | Seven collections; embedded chunk vectors; optional fields; denormalized chunk title for citations; indexes derived from access patterns; HNSW vector index; compound indexes. | `src/backend/app/db.py`; `docs/PROJECT_REPORT.md` §3; slide “Data model” |
| 4 | NoSQL implementation and CRUD | Full create/read/update/delete on documents, plus memory CRUD. Text edits mark a document `pending`, and the change stream rebuilds chunks; deletes remove the document and all chunks in one transaction. | `src/backend/app/routers/ingest.py`, `memory.py`; UI at `/documents`; slide “CRUD” |
| 5 | Advanced features and query optimization | Change streams, multi-document transactions, `$search`, `$vectorSearch`, `$rankFusion`, `$text` + cosine fallback, RRF, `$facet`, `$bucketAuto`, `$group`, `$dateToString`, text/HNSW indexes, 20× candidate over-request, reranking. | `core/ingest_worker.py`, `core/ingestion.py`, `core/hybrid_search.py`, `routers/analytics.py`; `docs/DATABASE.md` |
| 6 | Application integration and functionality | Next.js 15 UI (documents, chat, dashboard), FastAPI REST API, MCP server for AI clients, Gemini chat + embeddings, server-side admin-token proxy, friendly error handling. | `web/`; `src/mcp_cogito/server.py`; slides “Application integration” and “Demo” |
| 7 | Testing, security, and validation | 17 unit tests, Ruff + Next build in CI, MCP smoke test, and manual/Playwright end-to-end CRUD/search verification. Pydantic request validation, 10 MB upload cap, type whitelist, admin-token auth on writes, rate limiting with 429 + `Retry-After`. | `src/backend/tests/`; `.github/workflows/`; `docs/TEST_REPORT.md` |
| 8 | Live demonstration, viva, and documentation | Seeded demo is not required; documents are added live. Deck, report, feature map, viva sheet, demo script, and test report are present. **The institutional plagiarism report must be attached separately before submission.** | `docs/Cogito_Presentation.pptx`, `PROJECT_REPORT.md`, `DATABASE.md`, `VIVA_PREP.md`, `DEMO_SCRIPT.md`, `TEST_REPORT.md` |

## Deliberate scope note

The original proposal described a document assistant; the delivered project is a
more complete version of the same idea. The rubric does not require a specific
domain — it requires demonstrated NoSQL competence. The table above shows where
each required capability is implemented and where it is demonstrated live.

## What to bring to the viva

1. Working stack (`docker compose ps` all healthy).
2. Empty knowledge base at the start; upload a document during the demo.
3. This mapping, the report, and the plagiarism report.
4. A one-page demo script (`DEMO_SCRIPT.md`).
