# How Cogito Uses MongoDB & Its AI Features

This document is a complete map of **every MongoDB feature** and **every AI
feature** Cogito uses, with pointers to the exact code. It is written to be the
"explain your database + AI choices" section of a NoSQL class submission.

---

## 1. Why MongoDB (the one-minute pitch)

Cogito stores **documents, their text chunks, the chunk vectors, conversation
history, long-term facts, query logs, evaluation scores, and feedback** — all in
one MongoDB deployment. There is no separate vector database, no separate
search engine, and no sync layer between them. That is the whole argument for a
document database here:

- The unit of retrieval is a **chunk** (a paragraph of text + its embedding +
  metadata). That is naturally one document, not one row across three SQL
  tables.
- **Vector search and full-text search run natively** (`$vectorSearch`,
  `$search`, `$text`), so retrieval and storage live in the same place.
- **Change streams** make ingestion *event-driven* instead of batch — drop a
  document and it indexes itself.

Everything — documents, chunks, vectors, memory, logs — is a document in a
collection (see `src/backend/app/db.py`).

---

## 2. Data model (document-oriented schema)

Each collection is a set of self-describing documents; fields appear only when
relevant. This is the flexible-schema payoff: a `chunk` carries `page` only for
PDFs, `boost` only after feedback, and a `document` carries `summary`/`keywords`
only after enrichment.

| Collection | Stores | Key fields |
|---|---|---|
| `documents` | source docs + metadata | `_id`, `path`, `title`, `type`, `hash`, `status`, `raw` (BSON binary), `summary`, `keywords`, `chunk_count` |
| `chunks` | text passages + vectors | `_id`, `document_id`, `text`, `embedding` (vector), `page`, `order`, `token_count`, `boost` |
| `conversations` | chat history | `_id`, `user_id`, `messages[]` |
| `memories` | long-term facts + vectors | `_id`, `user_id`, `fact`, `embedding`, `importance` |
| `query_logs` | every query | `_id`, `question`, `chunks_returned`, `chunk_ids[]`, `latency_ms`, `answer_id`, `ts` |
| `eval_results` | LLM-judge scores | `_id`, `answer_id`, `faithfulness`, `relevance`, `judge`, `ts` |
| `feedback` | 👍/👎 ratings | `_id`, `answer_id`, `rating`, `comment`, `ts` |

The **raw document bytes are embedded in the `documents` row as BSON `Binary`**
(`app/core/ingestion.py:create_document`) so the change-stream worker can read
the full content straight off the change event — no separate file store needed.

---

## 3. MongoDB features used (and where)

### 3.1 Indexes — `app/db.py:ensure_indexes`

- **Single-field index** on `documents.status` and `chunks.document_id` (the
  `document_id → chunks` lookup used in citations and re-ingestion).
- **Compound index** on `documents(path, hash)` (dedup detection) and
  `memories(user_id, updated_at)` (per-user recall, newest first).
- **Text index** on `chunks.text` — the lexical fallback, queried with `$text`
  + `$meta: "textScore"` (`app/core/hybrid_search.py:_fallback_hybrid`).
- **HNSW vector index** on `chunks.embedding` (`app/db.py:_vector_index`) with
  `similarity: cosine`, used by `$vectorSearch`.
- **Atlas/Search index** `cogito_text` on `chunks.text`, used by `$search`.

### 3.2 Change streams (event-driven ingestion) — `app/ingest_worker.py`

The write path is **not** a cron job. `db.col("documents").watch(...)` opens a
change stream; every insert/update with `status == "pending"` triggers
chunk → embed → store. The worker:

- persists its **resume token** in Redis (`_save_resume_token`) so a restart
  never drops an event,
- **backfills** any `pending` documents left over from a crash
  (`backfill_pending`).

This is the hardest and most impressive part: ingestion is *reactive*, not
batched.

### 3.3 Hybrid search — `app/core/hybrid_search.py`

Retrieval fuses two signals:

- **Lexical** (`$search` when mongot is present, else `$text`): matches exact
  words and clause numbers.
- **Semantic** (`$vectorSearch` when available, else brute-force cosine): matches
  *meaning* even when the words differ ("late delivery" vs "vendor obligations").

- **Full mode** uses MongoDB 8.0's native **`$rankFusion`**
  (`_full_hybrid`) — a single aggregation stage that runs a `$search` pipeline
  and a `$vectorSearch` pipeline and fuses them with Reciprocal Rank Fusion.
- **Fallback mode** (`_fallback_hybrid`) reproduces the same result contract
  using `$text` + cosine + an in-code RRF (`_rrf_fuse`), so the demo never
  breaks without mongot.

The system **probes** at startup (`app/db.py:mongot_available`) and picks the
right path automatically.

### 3.4 Aggregation pipeline — `app/routers/analytics.py`

The analytics dashboard is a showcase of MongoDB aggregation:

- **`$facet`** (`_query_log_facets`) — computes total queries, unanswered
  queries, and latency stats *in a single pass* over `query_logs`.
- **`$bucketAuto`** (`_latency_histogram`) — latency distribution histogram.
- **`$dateToString` + `$group`** — query volume per day (`by_day`), turning
  epoch-second timestamps into a time series.
- **`$group` + `$sort` + `$limit`** — top questions (`top_queries`).
- **`$cond`, `$avg`, `$max`, `$sum`** — conditional counting and latency stats.

### 3.5 Transactions (multi-document ACID) — `app/core/ingestion.py:_commit_document`

Re-ingesting a document must *delete old chunks and insert new chunks* without a
half-finished state. `process_document` does this inside a **single multi-document
transaction** (`client.start_session()` → `start_transaction()` → delete + insert
+ status flip), with a non-transactional fallback if the deployment cannot open
one. This is a real ACID guarantee, not a demo convenience.

### 3.6 Replica set — `docker/mongodb/init.js`

Change streams and transactions require a replica set. The Docker bootstrap
turns a single node into `rs0` (`replSetInitiate`), so both features work on a
free, single-container deployment.

### 3.7 Atomic updates / operators

- `$inc` / `$set` — feedback bumps chunk `boost` (`app/core/feedback.py`),
  status flips, and conversation history appends.
- `$push` — appending user/assistant messages to `conversations`
  (`app/routers/chat.py`).
- `$in` — bulk operations on the chunks that produced an answer.

---

## 4. AI features used (and where)

### 4.1 Embeddings — `app/core/embeddings.py`

Pluggable embedders behind one interface (`Embedder`): OpenAI, OpenRouter,
Ollama, and a **key-free local hashing embedder** (`LocalHashEmbedder`) that
produces deterministic, normalized 384-d vectors so the whole pipeline demos
offline. `fit()` trims/pads any provider's output to the configured dimension.

### 4.2 Grounded, cited answers (RAG) — `app/core/llm.py`

`generate_cited_answer` sends retrieved chunks to an LLM with a system prompt
that **requires every claim to cite a chunk**, and parses `{answer, citations}`.
The local `LocalTemplateLLM` gives the same shape without any key, so citations
are always present.

### 4.3 Hybrid + reranking — `app/core/hybrid_search.py` + `app/core/reranker.py`

Retrieved candidates are reranked by a **cross-encoder**
(`cross-encoder/ms-marco-MiniLM-L-6-v2`) when available, else a lexical
query-term-overlap rerank. This is a second-pass relevance signal on top of the
fusion score.

### 4.4 Query expansion / multi-query — `app/core/query_expansion.py`

`multi_query_search` expands one question into several query angles (keyword
rephrasings offline, real LLM rephrasings when configured), retrieves for each,
and fuses the lists with RRF. Classic technique for lifting recall on short or
ambiguous questions.

### 4.5 Agentic loop (LangGraph) — `app/core/agent.py`

A `StateGraph` with `retrieve → assess confidence → refine → generate`. If
retrieval confidence is low it **rewrites the query and retries** (bounded by
`agent_max_iterations`), then answers. This is the "the system reasons over what
it knows" tier.

### 4.6 Long-term memory — `app/core/memory.py`

Extracted facts are stored **with embeddings** and recalled by cosine similarity
(MongoDB's "agent memory" pattern). The chat endpoint auto-extracts simple facts
(`"my name is …"`) into memory and injects recalled facts into later queries.

### 4.7 Evaluation pipeline (LLM judge) — `app/core/evaluator.py` + `app/core/service.py`

Every answer is scored for **faithfulness** (is every claim grounded in a
retrieved chunk?) and **relevance** (did it answer?), by an LLM judge when
available, else a deterministic heuristic judge. Scores are stored in
`eval_results` and mirrored to Postgres/Supabase.

### 4.8 Feedback loop — `app/core/feedback.py`

👍/👎 on an answer bump/suppress the `boost` multiplier on the chunks that
produced it, and that multiplier is applied in the next retrieval
(`_apply_feedback_boosts`) — a learning retrieval loop.

### 4.9 Document enrichment — `app/core/enrich.py`

On ingest, Cogito extracts a **summary** and **keywords** per document
(extractive when offline, abstractive with a real LLM) and stores them on the
`document` so the knowledge base is navigable without opening the source.

---

## 5. End-to-end walkthrough (what to say in the demo)

1. `docker compose up -d --build` — Mongo replica set, backend, worker, Redis,
   Postgres.
2. `docker exec cogito-backend python -m app.scripts.seed` — 4 sample documents
   are inserted as `pending`.
3. The **change stream** fires, the worker chunks + embeds + stores them (watch
   `/analytics/freshness` for the drop-to-indexed latency).
4. Ask `"What are our penalty clauses for late delivery?"` at `/ask`:
   - the question is embedded,
   - **hybrid search** fuses keyword + semantic results (native `$rankFusion`
     on MongoDB 8.0, RRF fallback otherwise),
   - the LLM writes a **cited** answer,
   - an **LLM judge** scores it for faithfulness/relevance.
5. Rate it 👍/👎 and re-ask — the feedback changes retrieval ranking.
6. Open the dashboard to see `$facet`/`$bucketAuto`/`$dateToString` analytics.

Useful sample questions:

- `What are our penalty clauses for late delivery?` (semantic match to
  "vendor obligations")
- `How much annual leave do employees get?`
- `What is our net-zero target for 2030?`
- `How long do we retain user data?`
- `What is clause 4.2?` (exact-match stress test)

---

## 6. The two "NoSQL" stories to tell

1. **Event-driven ingestion with change streams + resume tokens + a transaction
   for re-ingestion** — you are not polling a folder; the database itself
   *pushes* the work.
2. **Search + vectors + aggregation all in MongoDB** — `$search`,
   `$vectorSearch`, `$rankFusion`, `$text`, `$facet`, `$bucketAuto`, and a
   multi-document transaction, in one free deployment. No vector DB, no
   separate search index, no sync tax.

And the one "AI" story: **retrieval is the hard part, and the LLM is grounded
and evaluated** — hybrid retrieval, query expansion, reranking, an agentic loop,
memory, an LLM judge, and a feedback loop that keeps improving ranking.
