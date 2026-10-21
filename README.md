# Cogito

Cogito is a MongoDB-backed knowledge assistant. Documents index themselves
through a change stream, questions are answered with hybrid retrieval (keyword
plus vector search, fused into one ranking), and every answer cites the
passages it used. The same assistant is available through a REST API, a small
web dashboard, and an MCP server, so AI clients such as Claude Desktop or
Cursor can query the knowledge base as a tool.

Two documents describe the project in detail:
[`docs/PROJECT_REPORT.txt`](docs/PROJECT_REPORT.txt) is the course report, and
[`docs/DATABASE.txt`](docs/DATABASE.txt) maps every MongoDB and AI feature to
the code that implements it. [`docs/PROPOSAL.md`](docs/PROPOSAL.md) is the
original plan.

## Quick start

1. Start the stack:

```bash
cp .env.example .env      # defaults work; keys are optional
docker compose up -d --build
```

This starts MongoDB (single-node replica set with MongoDB Search, so `$search`,
`$vectorSearch`, and `$rankFusion` run locally), the FastAPI backend on port
8000, the change-stream ingestion worker, Redis, and Postgres. MongoDB is
published on host port 27018 to avoid clashing with any system `mongod`.

2. Add your first document at `http://localhost:3000/documents` (upload a file
   or paste text). The change stream indexes it automatically.

3. Ask a question:

```bash
# cited answer (hybrid retrieval + LLM)
curl -s -XPOST localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"question":"What are our penalty clauses for late delivery?"}'

# agentic loop (retrieve, check confidence, refine, answer)
curl -s -XPOST localhost:8000/ask/agent -H 'Content-Type: application/json' \
  -d '{"question":"How much annual leave do employees get?"}'
```

4. Open the interfaces:

```bash
open http://localhost:8000/docs      # OpenAPI
cd web && npm install && npm run dev # documents at /documents, chat at /chat,
                                     # dashboard at /dashboard
```

`/documents` is the place to upload or paste a document, watch it move from
`pending` to `indexed`, edit its title or text, re-index it, delete it, and run
a hybrid search over the indexed chunks. The same write routes are available
directly on the API:

| Method and path | Purpose |
|---|---|
| `POST /ingest`, `POST /ingest/raw` | create a document from a file or raw text |
| `GET /ingest/documents`, `GET /ingest/documents/{id}` | list or read a document |
| `GET /ingest/documents/{id}/chunks` | read the indexed chunks |
| `PATCH /ingest/documents/{id}` | update title, type, or text (re-indexes) |
| `POST /ingest/documents/{id}/reindex` | queue the document for re-indexing |
| `DELETE /ingest/documents/{id}` | delete the document and all of its chunks |
| `PATCH/DELETE /memories/{id}` | update or delete a long-term memory |

Write routes require the `X-Admin-Token` header. The web app injects it
server-side through its `/api/documents` proxy (`COGITO_ADMIN_TOKEN` in
`web/.env.local`, which must match `ADMIN_TOKEN` in the root `.env`).

Optional: `docker compose --profile automation up -d` adds n8n on port 5678.

## Using Cogito from an AI client (MCP)

Register the MCP server over stdio in Claude Desktop, Cursor, or another MCP
client:

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

The server exposes seven tools: `list_sources`, `search_knowledge`,
`search_multi`, `ask_question`, `add_document`, `remember`, and `recall`.

## Configuration

Everything runs offline by default. A key upgrades the corresponding part:

| Variable | Effect |
|---|---|
| `OPENROUTER_API_KEY` / `OPENAI_API_KEY` / `OLLAMA_BASE_URL` | real LLM and embeddings (set `LLM_PROVIDER` / `EMBEDDING_PROVIDER`) |
| `GEMINI_API_KEY` | Gemini LLM and embeddings (set `LLM_PROVIDER=gemini`, `EMBEDDING_PROVIDER=gemini`, `EMBEDDING_DIM=768`) |
| `POSTHOG_API_KEY` | product analytics |
| `SENTRY_DSN` | error tracking |
| `UPSTASH_REDIS_REST_URL` + `UPSTASH_REDIS_REST_TOKEN` | managed rate limiting and cache |
| `PINECONE_API_KEY` | secondary vector store for cross-store comparison |
| `SUPABASE_URL` + `SUPABASE_ANON_KEY` | Supabase auth and analytics mirror (falls back to the bundled Postgres) |
| `ATLAS_URI` | point MongoDB at Atlas instead of the bundled container |

### Search modes

The compose file uses the `mongodb-atlas-local:8.2` image, which bundles the
database and MongoDB Search in one container, so the native pipeline
(`$search` + `$vectorSearch` + `$rankFusion`) is the default. If `MONGODB_URI`
points at a plain `mongod` or another deployment without MongoDB Search, the
backend detects this at startup and switches to the `$text` + cosine + RRF
fallback, which returns results in the same format. Check which path is active:

```bash
curl -s localhost:8000/capabilities
```

### Switching embedding provider or dimension

Stored vectors and the vector index must match `EMBEDDING_DIM`. When changing
the provider or the dimension (for example to Gemini at 768), drop the vector
index, clear the chunk collection, mark documents as pending, and restart so
the index is recreated and the worker re-embeds:

```bash
docker exec cogito-mongodb mongosh cogito --quiet --eval '
  try { db.chunks.dropSearchIndex("cogito_vector") } catch (e) {}
  db.chunks.deleteMany({});
  db.documents.updateMany({}, { $set: { status: "pending" } })'
docker compose up -d --build backend ingest-worker
```

## Repository layout

```
Cogito/
├── docker-compose.yml           local stack: MongoDB + Search, backend, worker, Redis, Postgres
├── docker/
│   ├── mongodb/init.js          replica-set bootstrap
│   └── postgres/schema.sql      analytics mirror schema
├── src/
│   ├── backend/
│   │   ├── app/                 FastAPI app, ingestion worker, core modules
│   │   │   ├── core/            retrieval, llm, agent, evaluator, memory, feedback
│   │   │   ├── routers/         ingest, search, chat, memory, analytics, health
│   │   │   └── scripts/         ensure_indexes, seed
│   │   └── tests/               unit tests and the MCP smoke test
│   └── mcp_cogito/server.py     MCP tools
├── web/                         Next.js chat page and dashboard
├── infran8n/workflows/          scheduled automation workflows
└── docs/                        proposal, report, and the feature map
```

## Tests and lint

The same commands CI runs:

```bash
cd src/backend
pip install -e ".[dev]"      # or: uv sync
pytest tests/ -q
ruff check app
```
