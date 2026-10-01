# Cogito — Project Report

## How a NoSQL Database and AI Work Together to Process Documents

This document explains, in plain language, **how Cogito uses MongoDB (a NoSQL
document database)** and **how AI is used for document processing** in the
project. It is written as a report you can hand in or speak from for a NoSQL
database course.

---

## 1. What the project is

Cogito is a **Retrieval-Augmented Generation (RAG) knowledge assistant**. You
drop documents into it (PDFs, text files, contracts, policies, web content), and
it automatically reads them, breaks them into pieces, understands their meaning,
and lets you ask questions that it answers **with citations to the exact source**.

The two ideas the project demonstrates are:

1. **A NoSQL database (MongoDB) can do far more than store data** — it can
   trigger work automatically, search text and *meaning* natively, and compute
   analytics, all in one place.
2. **AI turns a pile of documents into something you can talk to** — the AI
   reads the documents, embeds their meaning, and answers questions grounded in
   the actual text rather than making things up.

---

## 2. How the NoSQL database is used

### 2.1 Why a document database fits

The natural unit of work in a RAG system is a **chunk** — a small piece of a
document (a paragraph or two) together with its metadata and its numeric
meaning-vector (embedding). That is exactly one JSON document, not a row split
across three relational tables. So every collection in Cogito is a set of
self-describing documents.

### 2.2 The collections

| Collection | What it holds |
|---|---|
| `documents` | The source documents (title, type, status, the raw bytes, and later an AI-generated summary + keywords) |
| `chunks` | The text pieces, each with its embedding vector, page number, and a feedback "boost" score |
| `conversations` | Chat history between a user and the assistant |
| `memories` | Long-term facts the assistant remembers about a user, stored with embeddings |
| `query_logs` | Every question ever asked, with latency and which chunks were used |
| `eval_results` | AI-judge scores for every answer (faithfulness + relevance) |
| `feedback` | User 👍/👎 ratings |

### 2.3 Event-driven ingestion with change streams

This is the headline NoSQL feature. When a document is inserted, it is marked
`pending`. A **change stream** (`db.collection.watch()`) listens to the
`documents` collection. The instant a `pending` document appears, the stream
fires and a worker:

1. extracts the text,
2. chunks it,
3. generates embeddings,
4. stores the chunks,
5. flips the document to `indexed`.

No cron job, no "re-run the import script." The database itself *pushes* the
work. The worker also saves a **resume token**, so if it crashes it resumes from
where it left off instead of losing events.

### 2.4 Search and vector search — both native

MongoDB lets Cogito search two ways, and combine them:

- **Full-text search** (`$text`, and `$search` when the search engine is
  present) finds chunks containing the literal words ("penalty", "clause 4.2").
- **Vector search** (`$vectorSearch`) finds chunks by *meaning* — a question
  about "late delivery fees" also matches a chunk titled "vendor obligations."

These are fused into one ranked result with **`$rankFusion`** (MongoDB 8.0's
native reciprocal-rank-fusion stage). When that feature isn't available, Cogito
transparently falls back to `$text` + cosine similarity + an in-code RRF that
returns the same shape of result.

### 2.5 Aggregation for analytics

The dashboard queries are built on MongoDB's **aggregation pipeline**:

- **`$facet`** computes total queries, unanswered queries, and latency in a
  single pass.
- **`$bucketAuto`** builds a latency histogram.
- **`$dateToString` + `$group`** turns raw timestamps into "queries per day."
- **`$group` / `$sort` / `$limit`** produce the "top questions" list.

### 2.6 Transactions

Re-ingesting a document must replace its old chunks without leaving a
half-updated state. Cogito deletes old chunks + inserts new chunks + updates the
status **inside a single multi-document transaction**, so the operation is
atomic (all-or-nothing).

### 2.7 Indexes

- Text index on `chunks.text` (lexical search).
- HNSW vector index on `chunks.embedding` (semantic search).
- Compound indexes for common lookups (chunks-by-document, memories-by-user).

### 2.8 Replica set

Change streams and transactions require a replica set. The Docker setup boots a
single-node replica set (`rs0`), so both features work for free on one container.

---

## 3. How AI is used for document processing

AI appears at every stage of the pipeline. Each stage is pluggable — it runs
fully offline with built-in local models, and upgrades automatically when you
add a real LLM or embedding API key.

### 3.1 Embeddings (understanding meaning)

The first AI step converts text into **numbers** — an embedding vector where
similar sentences land close together in space. Cogito supports OpenAI,
OpenRouter, and Ollama embeddings, plus a **built-in local embedder** that
generates deterministic vectors with no API key, so the pipeline demos offline.

### 3.2 Chunking

Before embedding, each document is split into overlapping passages (recursive
text splitting). PDF pages are tracked so citations can point to an exact page.

### 3.3 Document enrichment (summary + keywords)

On ingestion, AI reads each document and produces a **summary** and a list of
**keywords**, stored on the document. Offline it uses an extractive summarizer
(picking the most representative sentences); with a real LLM it writes an
abstractive summary. This makes the knowledge base navigable without opening
the source.

### 3.4 Retrieval (finding the right pieces)

When a question arrives, it is embedded and searched against the chunks using
**hybrid retrieval** (keyword + semantic, fused). Two AI techniques improve
recall:

- **Reranking** — a cross-encoder model re-scores the candidate chunks for the
  specific question.
- **Query expansion (multi-query)** — the question is rewritten into several
  angles, each is searched, and the results are fused, helping on short or
  ambiguous questions.

### 3.5 Grounded, cited answers

The retrieved chunks are sent to an LLM with an instruction: **every factual
claim must cite a source chunk.** The model returns an answer plus a list of
citations (document, page, excerpt). This is what makes it *retrieval-augmented*
— the model is grounded in your documents, not its general training.

### 3.6 Evaluation (an AI that grades the AI)

Every answer is scored by an **LLM judge** on two axes:

- **Faithfulness** — is every claim supported by a retrieved chunk? (hallucination
  guard)
- **Relevance** — did the answer actually address the question?

Scores are stored and charted over time, so you can see whether changes improve
quality.

### 3.7 Feedback loop

When a user rates an answer 👍 or 👎, the chunks that produced it get a higher
or lower ranking boost. The next retrieval uses that boost, so the system
improves from feedback.

### 3.8 Agentic loop and memory

- **Agentic loop (LangGraph)** — the assistant reasons in steps: retrieve,
  assess confidence, and, if confidence is low, rewrite the query and try again
  before answering.
- **Memory** — facts the assistant learns (e.g., "I work at Acme") are stored
  with embeddings and recalled later by vector similarity, so the assistant
  personalizes answers.

---

## 4. One end-to-end example

1. A user uploads `acme_vendor_contract_2026.pdf`.
2. A change stream fires; the worker chunks it, embeds each chunk, and enriches
   the document with a summary and keywords.
3. The user asks: *"What are our penalty clauses for late delivery?"*
4. The question is embedded, and hybrid search fuses keyword + semantic matches.
5. The top chunks are reranked and passed to the LLM.
6. The LLM returns a cited answer pointing at the exact clause and page.
7. An LLM judge scores the answer for faithfulness and relevance.
8. The user rates it 👍, boosting those chunks for future questions.

---

## 5. What this demonstrates

- **NoSQL beyond CRUD**: change streams (event-driven), `$search` +
  `$vectorSearch` + `$rankFusion` (hybrid search), `$facet`/`$bucketAuto`/
  `$dateToString` (analytics), and multi-document transactions.
- **AI as a document-processing layer**: embeddings, chunking, enrichment,
  retrieval, grounded generation, evaluation, and a feedback loop — all wired
  together so the "database" and the "AI" reinforce each other.
- **A real architecture**: the same design maps to production RAG systems, but
  it runs completely free and offline for a demo.

For a feature-by-feature map of *where* each MongoDB and AI feature lives in the
code, see [`DATABASE.md`](./DATABASE.md).
