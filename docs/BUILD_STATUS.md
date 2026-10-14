# Cogito — Build Status

_Session log for standing the project up from `docs/PROPOSAL.md`.
Last updated: 2026-10-14._

---

## TL;DR

The repo was already substantially implemented; this session **stood it up end to
end, fixed 5 real bugs found by exercising it, and upgraded the stack to the
plan's flagship configuration** (mongod 8.2 + mongot, so `$search` +
`$vectorSearch` + `$rankFusion` run natively — no fallback).

Verified working: auto-ingestion change streams, hybrid search, cited answers,
agentic loop, memory recall, evaluation, analytics, feedback, MCP server
(stdio), web UI.

---

## What was done

### 1. Stack brought up

- `docker compose up -d --build` — MongoDB, backend (FastAPI), ingest worker,
  Redis, Postgres all healthy.
- Seeded via `docker exec cogito-backend python -m app.scripts.seed`.
- Backend `:8000`, web `:3000` (running via `npm start`, log at
  `/tmp/cogito-web.log`). Mongo published on `:27018`.

### 2. Flagship pipeline enabled (mongot)

- **`docker-compose.yml`**: MongoDB image switched from `mongo:8.0` to
  **`mongodb/mongodb-atlas-local:8.2`** (bundles mongod 8.2.11 + mongot in one
  container, no Atlas account needed). Added `hostname: rs0` because the image
  names its replica set after the container hostname (must match
  `replicaSet=rs0` in the URI). Removed the custom `mongod` command — the image
  manages startup.
- Result at startup:
  `search mode: {'replica_set': True, 'mongot': True, 'full_hybrid': True}`
  and both search indexes `cogito_text` / `cogito_vector` report
  `READY, queryable: true`.
- **Note:** the old `mongo_data` volume (initialized by mongo:8.0) must not be
  reused — the atlas-local runner refuses to start on a foreign data dir. It
  was removed; state is reproducible via the seed script. (Future image swaps:
  `docker volume rm cogito_mongo_data` if the container won't start.)

### 3. Bugs found and fixed

| # | Bug | Where | Fix |
|---|-----|-------|-----|
| 1 | `/analytics/overview` 500'd as soon as `query_logs` had data — `$facet` sub-pipelines return **arrays**, code treated them as objects | `app/routers/analytics.py` | Added `_first()` helper unwrapping `[0]` for `totals`/`unanswered`/`latency` |
| 2 | Transactions never ran: `client.start_session()` used as async CM without `await` (Motor returns a future) — silent `RuntimeWarning`, non-atomic fallback always used | `app/core/ingestion.py:132` | `async with await client.start_session() as session, session.start_transaction():` |
| 3 | `$rankFusion` docs carried no score — projection referenced `$scoreDetails.value` (wrong shape on 8.2) | `app/core/hybrid_search.py` | Project with `{"$meta": "score"}` |
| 4 | `/eval` 500 — raw docs returned with Mongo `ObjectId` `_id`, not JSON-serializable | `app/routers/memory.py` | Stringify `_id` in the response |
| 5 | MCP smoke test failed — the MCP SDK stdio client only inherits whitelisted env vars, so `MONGODB_URI` never reached the spawned server | `tests/test_mcp_client.py` | Pass `env={**os.environ, "MONGODB_URI": ...}` to `StdioServerParameters` |

Also: dashboard empty-eval edge case (`web/app/dashboard/page.tsx` —
`data?.eval?.samples` instead of truthiness), and 19 ruff findings in `app/`
made CI-passing (8 auto-fixed, rest → `noqa: S110`/`BLE001`/`B008` on the
intentional no-op guards).

### 4. Verification evidence

- `pytest tests/ -q` → **13 passed**
- `ruff check app` → **All checks passed**
- `POST /ingest/raw` → doc `pending` → change stream → `indexed` with summary +
  keywords in **~260 ms first run / 6 ms warm**
- `POST /ask` → grounded answer + 4 citations, RRF scores present (full hybrid
  path confirmed via `$rankFusion`)
- `POST /ask/agent` → 1 iteration, cited answer
- `/analytics/overview|histogram|eval|freshness|queries` → all 200 with live
  data (freshness ≈ 0.02 s)
- `/memories` + `/memories/recall` → vector search ranking (0.408 vs 0.052)
- `/chat` → answer + conversation persisted + memory recall hook
- MCP stdio smoke test → 7 tools (`list_sources`, `search_knowledge`,
  `search_multi`, `ask_question`, `add_document`, `remember`, `recall`),
  `ask_question` returns a cited answer
- `npm run build` clean; pages `/`, `/chat`, `/dashboard` → 200;
  `/api/analytics` proxy → live data, `capabilities.hybrid_search: true`

---

## Current state / open items

- **Uncommitted changes**: 15 files (see `git diff --stat`). Nothing committed.
- **Pending verification**: the final `docker compose up -d --build backend
  ingest-worker` (with the lint + transaction-combine fixes) was interrupted
  after the build; the containers may already be recreated. Confirm with:

  ```bash
  docker compose ps
  curl -s localhost:8000/health
  curl -s localhost:8000/capabilities   # expect hybrid_search: true
  curl -s localhost:8000/eval | head -c 200
  docker logs cogito-ingest-worker --tail 20 | grep -v mongot
  ```

  Re-run the rebuild if in doubt:
  `docker compose up -d --build backend ingest-worker`
- **Cleanup not yet done** (throwaway containers/volumes from the mongot test):
  `docker rm -f atlas-local-test atlas-name-test` and
  `docker volume prune` (fish out the anonymous `atlas-*` volumes), plus
  `rm /tmp/atlas_test.js`.
- **README not yet updated** to say the default compose stack now includes
  mongot (full hybrid is the default; the `$text`+cosine+RRF fallback applies
  only when pointing `MONGODB_URI` at a plain mongod / old Atlas tier).
- Both `docs/PROPOSAL.md` (plan) and `docs/PROJECT_REPORT.txt` /
  `docs/DATABASE.txt` still describe the old “Community image = fallback”
  behavior in places — README is the main one to true up.
- LLM answers are running with the **built-in local provider** (template
  answers). Drop `OPENROUTER_API_KEY` / `OPENAI_API_KEY` / an Ollama URL into
  `.env` and restart for real model answers.

## How to resume

```bash
# 1) stack
docker compose up -d --build
docker exec cogito-backend python -m app.scripts.seed   # only if DB is empty

# 2) web UI (already running; restart if needed)
cd web && npm run build && npm start

# 3) checks
curl -s localhost:8000/capabilities        # expect full hybrid + mongot true
curl -XPOST localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"question":"What are the penalty clauses for late delivery?"}'
cd src/backend && .venv/bin/python -m pytest tests/ -q
uv tool run ruff check app
```

## Key file references

- Plan: `docs/PROPOSAL.md` · report: `docs/PROJECT_REPORT.txt` · feature map:
  `docs/DATABASE.txt`
- Compose: `docker-compose.yml` (mongodb-atlas-local:8.2, `hostname: rs0`)
- Hybrid search: `src/backend/app/core/hybrid_search.py`
  (`_full_hybrid` = `$search` + `$vectorSearch` + `$rankFusion`)
- Ingestion: `src/backend/app/core/ingestion.py` (`_commit_document`
  transaction), worker: `src/backend/app/ingest_worker.py`
- Analytics: `src/backend/app/routers/analytics.py` (`$facet`, `$bucketAuto`,
  `$dateToString`)
- MCP: `src/mcp_cogito/server.py` · smoke test:
  `src/backend/tests/test_mcp_client.py`
- Web: `web/app/chat/page.tsx`, `web/app/dashboard/page.tsx`,
  `web/app/api/analytics/route.ts`
