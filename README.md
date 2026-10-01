# Cogito

**An MCP-Powered RAG Knowledge Assistant.** A MongoDB-native, self-indexing
Retrieval-Augmented Generation (RAG) system that any AI can query.

Drop a document in; a **change stream** chunks + embeds + indexes it
automatically. Ask a question; **hybrid search** (lexical + semantic + fusion)
returns a **grounded, cited answer** — exposed as a REST API, a web dashboard,
and an **MCP server** so Claude Desktop / Cursor / any MCP client can use it.

---

## What it does (end to end)

```mermaid
flowchart TD
    A[Documents: PDF / text / URL] --> B[documents collection]
    B -->|change stream| C[Ingestion worker]
    C --> D[Chunker] --> E[Embeddings] --> F[chunks + vectors]
    Q[User / AI client question] --> G[Hybrid search]
    G --> H["$search + $vectorSearch + $rankFusion (or RRF fallback)"]
    H --> K[Top-k chunks] --> L[LLM answer + citations]
    L --> M[REST / Web / MCP]
    T[Query logs] --> U[Analytics dashboard]
    L -->|[LLM judge]| Eval[faithfulness + relevance tracking]
    Eval --> Feedback --> boosts[retrieval re-ranking]
```

- **Auto-ingestion** — a single-node replica set's change stream indexes every
  new/updated document with zero manual steps. Resume tokens make it crash-safe.
- **Hybrid search** — keyword + semantic + fusion. When MongoDB Search
  (`mongot`) is present it runs the native `$search` + `$vectorSearch` +
  `$rankFusion` aggregation; otherwise it transparently falls back to `$text` +
  brute-force cosine + Reciprocal Rank Fusion with the **same** result contract.
- **Grounded answers** — the LLM must cite every claim to a retrieved chunk.
  Each answer is scored by an LLM-judge for **faithfulness** and **relevance**.
- **Agentic (LangGraph)** — a retrieve → assess-confidence → refine → answer
  loop with long-term **memory** ("agent memory" pattern stored in Mongo).
- **Feedback loop** — 👍/👎 ratings feed back into retrieval ranking.
- **Multi-query retrieval** — query expansion + RRF fusion for higher recall.
- **Document enrichment** — auto summary + keywords on every ingested document.
- **MCP server** — `add_document`, `search_knowledge`, `ask_question`,
  `list_sources`, `remember`, `recall` exposed to any MCP client.
- **Observability & automations** — PostHog (analytics), Sentry (errors),
  Upstash/Redis (rate-limit + cache), Pinecone (secondary vector store),
  Supabase/Postgres (auth + analytics mirror), n8n (scheduled workflows),
  Vercel (web deploy).

## Architecture / services

| Layer | Tech |
|---|---|
| Database | MongoDB 8.x single-node replica set (change streams) |
| Backend | Python **FastAPI** + Motor (async) + LangGraph |
| Search | `$search` / `$vectorSearch` / `$rankFusion` **or** `$text`+cosine+RRF |
| Embeddings / LLM | OpenRouter / OpenAI / Ollama / **built-in local** (key-free) |
| MCP | `mcp` Python SDK (fastmcp) |
| Web | Next.js 15 (App Router) + Recharts → deploys to Vercel |
| Infra | Docker Compose, Redis, Postgres, n8n |

> **Runs fully offline with zero API keys.** The built-in *local* embedding +
> LLM keep the whole pipeline demoable; drop your provider keys into `.env` and
> the real models light up automatically.

> **NoSQL course project?** Two docs explain the project end to end:
> [`docs/PROJECT_REPORT.md`](docs/PROJECT_REPORT.md) — a plain-language report
> on how MongoDB and AI process documents, and
> [`docs/DATABASE.md`](docs/DATABASE.md) — a feature-by-feature map of every
> MongoDB and AI feature to its code location.

## Quick start

1. Start the core stack:

```bash
cp .env.example .env      # defaults work; add keys to upgrade providers
docker compose up -d --build
```

This brings up MongoDB (replica set), the FastAPI backend (`:8000`), the
change-stream ingestion worker, Redis, Postgres, and (opt-in) n8n. Mongo listens
on `27018` to avoid clashing with any system `mongod` on `27017`.

2. Seed the knowledge base with sample documents (change streams index them):

```bash
docker exec cogito-backend python -m app.scripts.seed
```

3. Talk to it.

```bash
# cited answer
curl -s -XPOST localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"question":"What are our penalty clauses for late delivery?"}'

# agentic loop
curl -s -XPOST localhost:8000/ask/agent -H 'Content-Type: application/json' \
  -d '{"question":"How much annual leave do employees get?"}'

# dashboard
open http://localhost:8000/docs          # OpenAPI
cd web && npm install && npm run dev      # chat UI (localhost:3000)
```

4. Enable more services when disk allows:

```bash
docker compose --profile automation up -d   # adds n8n (webhooks :5678)
```

## MCP — use Cogito from any AI client

Register Cogito in `~/.claude/...` / Claude Desktop / Cursor as a stdio MCP
server:

```json
{
  "mcpServers": {
    "cogito": {
      "command": "docker",
      "args": ["exec", "-i", "cogito-backend", "python", "-m", "mcp_cogito.server"]
    }
  }
}
```

Then any MCP client can call `search_knowledge("...")`, `ask_question("...")`,
`add_document("/path/to/file.pdf")`, and more.

## Repository layout

```
Cogito/
├── docker-compose.yml          — isolated self-hosted stack
├── docker/
│   ├── mongodb/init.js         — replica-set bootstrap
│   └── postgres/schema.sql     — Supabase-compatible analytics mirror
├── src/
│   ├── backend/
│   │   ├── app/
│   │   │   ├── main.py         — FastAPI app
│   │   │   ├── config.py        — settings (env-driven)
│   │   │   ├── db.py           — Motor, feature detection, indexes
│   │   │   ├── telemetry.py    — PostHog / Sentry / Upstash / logs
│   │   │   ├── ingest_worker.py — change-stream watcher (+ backfill)
│   │   │   ├── core/
│   │   │   │   ├── embeddings.py  ├── llm.py     ├── chunker.py
│   │   │   │   ├── hybrid_search.py ├── service.py ├── agent.py
│   │   │   │   ├── evaluator.py ├── memory.py   ├── feedback.py
│   │   │   ├── integrations/   — pinecone, supabase, upstash
│   │   │   ├── routers/         — ingest, search, chat, memory, analytics, health
│   │   │   └── scripts/         — ensure_indexes, seed
│   │   └── tests/              — unit tests + MCP client smoke test
│   └── mcp_cogito/server.py     — MCP tools wrapping the assistant
├── web/                        — Next.js chat + analytics dashboard (Vercel-ready)
├── infran8n/workflows/          — scheduled automation workflows
├── docs/PROPOSAL.md             — full project proposal
├── docs/PROJECT_REPORT.md       — how the NoSQL DB + AI process documents (class report)
├── docs/DATABASE.md             — MongoDB + AI feature map, feature → code location
└── .env.example
```

## Environment / feature matrix

Set keys in `.env` to enable the corresponding feature (all are graceful no-ops
otherwise):

| Variable | Feature |
|---|---|
| `OPENROUTER_API_KEY` / `OPENAI_API_KEY` / `OLLAMA_BASE_URL` | real LLM + embeddings |
| `POSTHOG_API_KEY` | product analytics |
| `SENTRY_DSN` | error tracking |
| `UPSTASH_REDIS_REST_URL` + `_TOKEN` | managed rate-limit/cache |
| `PINECONE_API_KEY` | secondary vector store + cross-store comparison |
| `SUPABASE_URL` + `_ANON_KEY` | Supabase auth + analytics mirror (else Postgres) |
| `ATLAS_URI` | point Mongo at Atlas for full `$search`/`$vectorSearch` |

## Notes on MongoDB Search

Cogito probes at startup for `mongot` (MongoDB Search). If present it runs the
full `$search` + `$vectorSearch` + `$rankFusion` pipeline; if not (as in the
default Community `mongod` docker image) it automatically uses the `$text` +
cosine + RRF fallback, so the demo never breaks. Point `MONGODB_URI`/`ATLAS_URI`
at an Atlas M10+ or a local deployment with Search enabled to get the flagship
hybrid pipeline with no code changes.