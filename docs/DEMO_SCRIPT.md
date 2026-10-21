# Cogito — Live Demo Script

Target length: **8–10 minutes**. The goal is to show the database doing the work,
not to click through every screen.

## Before the demo

```bash
docker compose ps                 # MongoDB, backend, worker, Redis, Postgres healthy
curl -s localhost:8000/capabilities
# expect: hybrid_search true, llm_provider gemini, embedding_provider gemini
```

Open **http://localhost:3000/documents** in a browser (not an embedded preview;
native file dialogs can be blocked there). Keep **/chat** and **/dashboard** in
separate tabs. Start with an empty knowledge base.

## 1. Show the empty knowledge base (30 s)

- Point at `Documents 0` / `Chunks 0`.
- Say: “No documents are loaded. Everything you see next is created live.”

## 2. Upload a document (60 s)

- Click **Browse files** (or drag a file) and pick a PDF/DOCX/Markdown file.
- Click **Ingest document**.
- Say: “The API writes a `pending` document. A MongoDB change stream wakes the
  worker, which chunks the text, embeds each chunk, and writes the chunks and
  the status flip inside one transaction.”
- Watch the row move `pending → indexed`; open it to show the chunks.

## 3. Search two different things (60 s)

- In **Search the knowledge base**, search for a phrase from the document.
- Then search for a paraphrase that does not appear literally.
- Say: “Both queries run `$search` and `$vectorSearch`, fused by `$rankFusion`.
  The scores and the highlighted chunks come from the database.”
- If `mongot` is unavailable, say: “The fallback path is `$text` + cosine + RRF;
  the result shape is identical.”

## 4. Ask a grounded question (90 s)

- Open **/chat**, ask a question the document answers.
- Show the answer and the citations.
- Ask a question the document does **not** answer.
- Say: “The prompt requires a refusal and no citations when the context is
  irrelevant. This is the hallucination guard.”
- If Gemini returns a 429, wait for the automatic retry; mention the free-tier
  limit and the 429 + `Retry-After` handling.

## 5. Demonstrate update and delete (90 s)

- Open the document row.
- **Rename** it; the chunk titles update so citations stay consistent.
- Edit the content and **Save content**; status returns to `pending` and the
  worker re-chunks/re-embeds it.
- **Delete** it; confirm the chunks disappear too (the delete is transactional).
- Say: “This is full CRUD, not just upload and search.”

## 6. Dashboard and wrap-up (60 s)

- Open **/dashboard**: total queries, latency, unanswered count, top questions,
  eval scores, ingestion freshness.
- Say: “The dashboard is built from aggregation pipelines (`$facet`,
  `$bucketAuto`, `$dateToString`, `$group`), not application-side loops.”
- Close with: “MongoDB is the store, the search engine, the vector store, the
  event bus, and the analytics engine for this application.”

## Reset after the demo

```bash
docker exec cogito-mongodb mongosh cogito --quiet --eval '
  ["documents","chunks","memories","query_logs","eval_results",
   "feedback","conversations"].forEach(c => db.getCollection(c).deleteMany({}));
'
docker exec cogito-redis redis-cli FLUSHDB
```

## If something fails

| Symptom | Check |
|---|---|
| Upload stays `pending` | `docker compose ps` — is `cogito-ingest-worker` up? |
| Upload returns 401 | `ADMIN_TOKEN` in `.env` must match `COGITO_ADMIN_TOKEN` for the web proxy |
| No search results | Is the document `indexed`? Open it and check chunks |
| `hybrid_search: false` | MongoDB Search (mongot) is not available; fallback still works |
| Gemini 429 | Free-tier limit; retry after the shown delay or use a paid key |
