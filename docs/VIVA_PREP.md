# Viva preparation

Study aid for the project defence. This file is not part of the submission.

It has three parts: the passages you must rewrite in your own words, a short
routine for the rewrite, and a question sheet with answers you should be able
to give without notes.

---

## Part A. Passages to rewrite in your own words

The report master is `docs/PROJECT_REPORT.md` (the `.docx` and `.txt` versions
are generated from it). The header block (group members and roll numbers) and
the conclusion are already drafted. Three markers remain, each looking like
`[FILL IN - ...]`. Each marker lists the facts to include, so you do not need
to invent content, only wording. Divide them among the group members, and
prefer that each member writes the passage they can explain best in the viva.

After filling them in, regenerate the docx with:

```bash
bash docs/build-docx.sh
```

1. **Section 1, introduction.** Why you chose this topic and what you hoped to
   learn. Three sentences are enough. Do not repeat the sentences above the
   marker.
2. **Section 11, problems.** Pick two of the bugs and write what you saw,
   what you suspected, and how you confirmed the fix. Two to three sentences
   each. Use the ones you actually remember struggling with; the refresher is in
   Part C, questions 11 and 12.
3. **Section 12, limitations (optional).** One improvement you would do first
   and why.
4. **Section 13, conclusion.** A draft is in place. Rework it in your own words
   anyway: the introduction and the conclusion are the parts a reader treats as
   the author's voice.

## Part B. Routine for the rewrite

- Close this repo, open a blank document, and write from memory using the facts
  listed at each marker. Reading the current sentence and "changing it a bit"
  produces awkward text and keeps the original voice.
- Read each finished paragraph aloud. If a sentence does not sound like
  something you would say in a lab report, simplify it until it does.
- Mix sentence lengths. Do not start consecutive sentences the same way.
- Keep the measured numbers exactly as they are (0.26 s, 6 ms, 17 tests,
  4 citations). They are checkable and they are yours.
- Then do one read-aloud pass over the rest of the report and change any
  sentence that feels foreign. Small edits are fine; you only need to be able
  to defend every paragraph.

---

## Part C. Question sheet

Answers are short on purpose. Each one names the file that backs it up.

**Q1. Why MongoDB instead of Postgres with pgvector?**
The retrieval unit is a chunk: text, vector, and metadata together. That is one
JSON document, not rows spread over tables. The database also provides the
search engine, change streams, and the aggregation analytics, so there is no
sync layer between a database and a vector store. Optional fields (page,
boost, summary) simply appear when relevant.
Code: `app/core/ingestion.py`, `app/db.py`.

**Q2. What is a change stream and why use it?**
A cursor that emits events when documents change. The ingestion worker watches
the `documents` collection and reacts to inserts with status `pending`. Nothing
polls and nothing is scheduled, so the index cannot drift out of date.
Code: `app/ingest_worker.py` (`watch`).

**Q3. What happens if the worker is down when a document is inserted?**
The document stays `pending`. On startup the worker runs `backfill_pending()`
and processes everything that was not handled. During normal operation it also
saves the change-stream resume token in Redis after every event, so a restart
resumes from the last processed event instead of skipping the gap.
Code: `app/ingest_worker.py` (`backfill_pending`, `_save_resume_token`).

**Q4. What is hybrid search, in one paragraph?**
Two retrievals run for the same question. Lexical search matches exact words
and clause numbers (`$search`, or `$text` as fallback). Semantic search matches
meaning through vectors (`$vectorSearch`, or cosine in Python). The two ranked
lists are fused into one ranking. Keyword-only search misses paraphrases;
vector-only search is weak on exact identifiers. Fusion keeps both strengths.
Code: `app/core/hybrid_search.py` (`_full_hybrid`, `_fallback_hybrid`).

**Q5. What is Reciprocal Rank Fusion?**
A method that merges ranked lists by score, not by raw similarity. Each list
contributes `1/(60 + rank)` per document, optionally weighted, and the terms are
summed. The constant 60 comes from the original paper (Cormack et al., SIGIR
2009). MongoDB's `$rankFusion` implements it; the fallback path implements the
same formula in `_rrf_fuse`.
Code: `app/core/hybrid_search.py`.

**Q6. When does `$rankFusion` work, and what happens when it doesn't?**
It needs MongoDB 8.0 or newer and its two input stages (`$search`,
`$vectorSearch`), which come from MongoDB Search. The compose stack uses the
`mongodb-atlas-local` image, so it is always available locally. When pointed at
a plain `mongod`, the startup probe detects this and the fallback path runs
instead, returning the same fields.
Code: `app/db.py` (`mongot_available`, `search_mode`), `app/core/hybrid_search.py`.

**Q7. What is an embedding, and what does the local embedder do?**
A vector of numbers that places text with similar meaning nearby. The local
embedder hashes word unigrams and trigrams into 384 dimensions, then
normalizes, so the pipeline runs with no API key. `fit()` trims or pads any
provider's output to `EMBEDDING_DIM` and re-normalizes, which is how a 3072-dim
Gemini vector becomes a valid 768-dim stored vector.
Code: `app/core/embeddings.py`.

**Q8. How is the vector index configured?**
An HNSW index on `chunks.embedding` with cosine similarity, dimension taken
from `EMBEDDING_DIM`, scalar quantization. A separate text index powers the
lexical side. Changing the embedding model or dimension requires dropping the
index and re-embedding, which the README explains.
Code: `app/db.py` (`_vector_index`, `ensure_indexes`).

**Q9. Why 100 vector candidates for 5 results?**
Approximate search trades recall for speed. The MongoDB documentation
recommends over-requesting (at least 20x the result limit) so the fused ranking
has enough material. `numCandidates` is the only knob for that tradeoff.
Code: `app/core/hybrid_search.py`, config `search_num_candidates`.

**Q10. What is the reranker doing?**
A cross-encoder (`ms-marco-MiniLM-L-6-v2`) reads the question and a candidate
together and gives a relevance score, which is more accurate than comparing
vectors separately. It is lazy-loaded and optional, because
`sentence-transformers` is not a required dependency. Without it, a lexical
overlap boost runs instead, and the function never raises.
Code: `app/core/reranker.py`.

**Q11. What was the transaction bug, concretely?**
Motor returns a future from `client.start_session()`. The first version used it
directly in an `async with`, so the transaction never started; the code fell
through to the three-write fallback without an error. The fix is
`async with await client.start_session() as session, session.start_transaction():`
which makes re-indexing atomic.
Code: `app/core/ingestion.py` (`_commit_document`).

**Q12. What was the analytics bug?**
`$facet` returns each sub-pipeline's output as an array. The endpoint treated
those arrays as objects and returned 500 as soon as `query_logs` had rows. The
fix unwraps the first element (`_first()`) for totals, unanswered counts, and
latency. Found by running the endpoint with real data, not by reading it.
Code: `app/routers/analytics.py`.

**Q13. How are citations enforced?**
The system prompt requires a JSON object with the answer and a citations list,
and instructs the model to state when the context does not answer. The reply is
parsed and stored with the answer. The offline template generator returns the
same shape, so citations exist even without a model key.
Code: `app/core/llm.py` (`SYSTEM_PROMPT`, `generate_cited_answer`).

**Q14. How do you know an answer is good?**
Every answer is scored by a judge on faithfulness (claims supported by
retrieved chunks) and relevance (does it answer the question). With a key the
judge is the model; offline it is a deterministic heuristic. Scores are stored
in `eval_results` and charted on the dashboard.
Code: `app/core/evaluator.py`, `app/core/service.py` (`evaluate`).

**Q15. How does the feedback loop change future results?**
A rating adjusts the `boost` multiplier on the chunks that produced the answer:
+0.5 for helpful, -0.25 for poor, clamped between 0.25 and 4.0. Retrieval
multiplies the fusion score by that boost before reranking.
Code: `app/core/feedback.py`, `app/core/hybrid_search.py` (`_apply_feedback_boosts`).

**Q16. What does the agent loop actually decide?**
It retrieves, then computes confidence as the mean score of the top three
chunks. If confidence is low and fewer results came back than top-k, it
enriches the query with distinctive terms from the best chunk and retrieves
again, up to `agent_max_iterations` (3). Otherwise it answers. The graph is a
LangGraph `StateGraph`.
Code: `app/core/agent.py` (`should_refine`, `build_graph`).

**Q17. Why do change streams and transactions need a replica set?**
Both depend on the operation log, which only exists with replication. The
Docker bootstrap promotes the single node into a one-member replica set (rs0),
so both features work with one container and no extra machine.
Code: `docker/mongodb/init.js`, `app/db.py` (`is_replica_set`).

**Q18. Which aggregation stages does the dashboard use?**
`$facet` for counts and latency stats in one pass, `$bucketAuto` for the latency
histogram, `$dateToString` with `$group` for questions per day, and
`$group`/`$sort`/`$limit` for top questions.
Code: `app/routers/analytics.py`.

**Q19. How does the MCP integration work?**
Cogito runs an MCP server over stdio using the MCP Python SDK (FastMCP). A
client registers it with a small JSON block and gets seven tools. The smoke
test exercises it end to end; it also caught one environment-variable
whitelisting issue in the client library.
Code: `src/mcp_cogito/server.py`, `src/backend/tests/test_mcp_client.py`.

**Q20. What is the memory feature?**
Facts are stored in `memories` with an embedding. Recall embeds the query and
computes cosine similarity against that user's memories, returning the closest
few, which are injected into later prompts.
Code: `app/core/memory.py`.

**Q21. What is not finished, and what would you fix first?**
No real authentication (a shared admin token guards write routes); offline
answers are templates, so answer quality needs a provider key; the deployment
is a single container; the offline judge is heuristic. The first fix would
probably be real accounts, since `user_id` fields already exist everywhere.
Code: `app/config.py` (`admin_token`), `app/core/service.py`.

**Q22. How would you add another model provider?**
Add a cluster in `config.py` for the key and model names, then a client class
in `app/core/llm.py` and `app/core/embeddings.py` following the existing
OpenAI-compatible pattern, and register it in the factories and `make_llm` /
`make_embedder`. That is exactly how the Gemini provider was added.
Code: `app/core/llm.py`, `app/core/embeddings.py`.
