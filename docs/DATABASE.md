# Cogito: MongoDB and AI Feature Map

This document is a reference, not a narrative. It lists every MongoDB and AI feature the project uses, the code that implements it, and the documentation page for it. All paths are relative to `src/backend/app` unless stated otherwise. Function and file names are stable and can be used to navigate the source during the viva.

---

## 1. Collections

| Collection | Stores | Key fields |
|---|---|---|
| `documents` | source files and metadata | `_id`, `path`, `title`, `type`, `hash`, `status`, `raw` (BSON binary), `summary`, `keywords`, `chunk_count` |
| `chunks` | text passages and vectors | `_id`, `document_id`, `text`, `embedding`, `page`, `order`, `token_count`, `boost` |
| `conversations` | chat history | `_id`, `user_id`, `messages[]` |
| `memories` | long-term facts | `_id`, `user_id`, `fact`, `embedding`, `importance` |
| `query_logs` | one record per question | `_id`, `question`, `chunks_returned`, `chunk_ids[]`, `latency_ms`, `answer_id`, `ts` |
| `eval_results` | judge scores per answer | `_id`, `answer_id`, `faithfulness`, `relevance`, `judge`, `ts` |
| `feedback` | ratings | `_id`, `answer_id`, `rating`, `comment`, `ts` |

Collection handles are defined in `db.py` as constants (`DOCUMENTS`, `CHUNKS`, `MEMORIES`, and so on).

### CRUD surface

| Operation | Route | Code |
|---|---|---|
| Create (file) | `POST /ingest` | `routers/ingest.py`: `ingest_file` → `core/ingestion.py`: `create_document` |
| Create (text) | `POST /ingest/raw` | `routers/ingest.py`: `ingest_raw` |
| Read (list) | `GET /ingest/documents` | `routers/ingest.py`: `list_documents` |
| Read (one) | `GET /ingest/documents/{id}?include_text=true` | `routers/ingest.py`: `get_document` |
| Read (chunks) | `GET /ingest/documents/{id}/chunks` | `routers/ingest.py`: `get_document_chunks` |
| Update (metadata/text) | `PATCH /ingest/documents/{id}` | `routers/ingest.py`: `update_document` (text edits set `status: pending`; the change stream re-indexes) |
| Update (re-index) | `POST /ingest/documents/{id}/reindex` | `routers/ingest.py`: `reindex_document` |
| Delete | `DELETE /ingest/documents/{id}` | `routers/ingest.py`: `delete_document` + `_delete_document_and_chunks` (multi-document transaction) |
| Memory update | `PATCH /memories/{id}` | `routers/memory.py`: `edit_memory` (re-embeds the fact) |
| Memory delete | `DELETE /memories/{id}` | `routers/memory.py`: `remove_memory` |

The web UI at `/documents` exercises every one of these routes: upload or paste,
list, open (read + chunks), rename/edit text, re-index, delete, and hybrid
search.

---

## 2. MongoDB features and operators

| Feature | Code | Documentation |
|---|---|---|
| Change streams | `ingest_worker.py`: `watch`, `backfill_pending`, `_save_resume_token` | [MongoDB: Change Streams](https://www.mongodb.com/docs/manual/changeStreams/) |
| Multi-document transaction | `core/ingestion.py`: `_commit_document` (delete chunks, insert new chunks, flip status, with a non-transactional fallback) | [MongoDB: Transactions](https://www.mongodb.com/docs/manual/core/transactions/) |
| `$search` | `core/hybrid_search.py`: `_full_hybrid`, `_lexical_full` | [MongoDB Search: $search](https://www.mongodb.com/docs/search/query/aggregation-stages/search/) |
| `$vectorSearch` | `core/hybrid_search.py`: `_full_hybrid`, `_vector_full` | [$vectorSearch](https://www.mongodb.com/docs/vector-search/query/aggregation-stages/vector-search-stage/) |
| `$rankFusion` | `core/hybrid_search.py`: `_full_hybrid` | [$rankFusion](https://www.mongodb.com/docs/manual/reference/operator/aggregation/rankFusion/) |
| RRF in Python (fallback fusion) | `core/hybrid_search.py`: `_rrf_fuse` | [Cormack et al., SIGIR 2009](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf) |
| `$text` and `textScore` (fallback lexical) | `core/hybrid_search.py`: `_fallback_hybrid` | [MongoDB: $text](https://www.mongodb.com/docs/manual/reference/operator/query/text/) |
| Cosine similarity (fallback semantic) | `core/hybrid_search.py`: `_fallback_hybrid`, `_cosine` | self-implemented |
| `$facet` | `routers/analytics.py`: `_query_log_facets` | [Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/) |
| `$bucketAuto` | `routers/analytics.py`: `_latency_histogram` | [Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/) |
| `$dateToString`, `$toDate` | `routers/analytics.py`: `_query_log_facets` (`by_day`) | [Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/) |
| `$group`, `$sort`, `$limit` | `routers/analytics.py`: `top_queries` | [Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/) |
| `$inc` with clamped `$set` (boost) | `core/feedback.py`: `record_feedback` | [MongoDB: $inc](https://www.mongodb.com/docs/manual/reference/operator/update/inc/) |
| `$in` (bulk chunk lookups) | `core/feedback.py`: `compute_boosts`, `core/memory.py`: `recall` | [MongoDB: $in](https://www.mongodb.com/docs/manual/reference/operator/query/in/) |
| Text index | `db.py`: `ensure_indexes` (on `chunks.text`) | [MongoDB: Text Indexes](https://www.mongodb.com/docs/manual/core/index-text/) |
| HNSW vector index (cosine) | `db.py`: `_vector_index` (on `chunks.embedding`) | [Vector Search index type](https://www.mongodb.com/docs/vector-search/indexes/vector-search-type/) |
| Search probe | `db.py`: `mongot_available`, `search_mode`, `probe_search` | detects whether `$search` and `$vectorSearch` are available |
| Replica set bootstrap | `docker/mongodb/init.js`, `docker-compose.yml` (`replSetInitiate`) | [MongoDB: Replication](https://www.mongodb.com/docs/manual/replication/) |
| Duplicate detection | `core/ingestion.py`: `create_document` compares an sha1 content hash; index on (`path`, `hash`) | [MongoDB: Indexes](https://www.mongodb.com/docs/manual/indexes/) |

---

## 3. Search modes at a glance

| Condition | Path | Operators |
|---|---|---|
| MongoDB Search available | `core/hybrid_search.py`: `_full_hybrid` | `$search` + `$vectorSearch` fused by `$rankFusion` |
| Plain `mongod` | `core/hybrid_search.py`: `_fallback_hybrid` | `$text` + cosine fused by `_rrf_fuse` |

Both modes return the same fields: `_id`, `text`, `document_id`, `title`, `page`, `score`. Feature detection runs once at startup (`db.probe_search`) and is read from the cached `db.search_mode_sync()` on the hot path.

---

## 4. AI features

| Feature | Code | Notes |
|---|---|---|
| Embeddings | `core/embeddings.py`: `LocalHashEmbedder` (default), `OpenAIEmbedder`, `OpenRouterEmbedder`, `GeminiEmbedder`, `OllamaEmbedder`; `fit()` | local embedder is key-free, 384 dimensions; Gemini through its OpenAI-compatible endpoint ([docs](https://ai.google.dev/gemini-api/docs/openai)); every provider output is normalized to `EMBEDDING_DIM` |
| Chunking | `core/chunker.py`: `split_by_type`, `extract_text`, `content_hash` | recursive splitting (800/120 characters, 500 for contracts), PDF page markers, DOCX and HTML extraction, OCR when Tesseract is available |
| Enrichment | `core/enrich.py`: `enrich` (extractive), `enrich_llm` (abstractive, keyed), `enrich_document` | stores summary and keywords on the document |
| Query expansion | `core/query_expansion.py`: `_deterministic`, `_llm_expand`, `expand_queries` | deterministic offline; LLM rewrites when a key is set |
| Reranking | `core/reranker.py`: `rerank`, `_lexical_rerank` | cross-encoder `cross-encoder/ms-marco-MiniLM-L-6-v2` when `sentence-transformers` is installed; lexical boost otherwise |
| Cited answers | `core/llm.py`: `SYSTEM_PROMPT`, `generate_cited_answer`, `LocalTemplateLLM` | answer and citations returned as JSON; the local template keeps the pipeline runnable offline |
| Provider clients | `core/llm.py`: `_OpenAICompatLLM`, `GeminiLLM`, `OpenAILLM`, `OpenRouterLLM`; `core/async_runner.py` | all provider calls run on one background event loop so blocking calls do not stall asyncio handlers |
| Agent loop | `core/agent.py`: `build_graph` (LangGraph `StateGraph`), `retrieve`, `should_refine`, `refine`, `generate` | retrieve, confidence check, refine and re-retrieve when weak, then answer |
| Memory | `core/memory.py`: `remember`, `recall`, `list_memories` | facts stored with embeddings, recalled by cosine similarity |
| Evaluation | `core/evaluator.py`: `evaluate_answer` (LLM judge or `_LocalJudge`); `core/service.py`: `evaluate` | faithfulness and relevance per answer, stored in `eval_results` |
| Feedback loop | `core/feedback.py`: `record_feedback`, `compute_boosts`; `core/hybrid_search.py`: `_apply_feedback_boosts` | ratings change chunk boosts, which retrieval applies |
| MCP server | `src/mcp_cogito/server.py`: seven tools | `list_sources`, `search_knowledge`, `search_multi`, `ask_question`, `add_document`, `remember`, `recall` ([MCP](https://modelcontextprotocol.io/)) |

---

## 5. Quick verification commands

The commands assume the Docker stack is running (`docker compose up -d --build`).

```bash
# seed the knowledge base
docker exec cogito-backend python -m app.scripts.seed

# cited answer with hybrid retrieval
curl -s -XPOST localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"question":"What are the penalty clauses for late delivery?"}'

# capabilities (shows which search path is active)
curl -s localhost:8000/capabilities

# analytics with live aggregation output
curl -s localhost:8000/analytics/overview

# tests and lint
cd src/backend && pytest tests/ -q
cd src/backend && ruff check app

# web UI
open http://localhost:3000/chat
open http://localhost:3000/dashboard
```
