# Cogito

**An MCP-Powered RAG Knowledge Assistant** — a self-indexing knowledge base that any AI can query.

Cogito is a MongoDB-native Retrieval-Augmented Generation (RAG) system:

- **Auto-ingestion** — drop a document in, a change stream chunks + embeds + indexes it automatically.
- **Hybrid search** — `$search` (keyword) + `$vectorSearch` (semantic) + `$rankFusion` (fusion) in one pipeline.
- **MCP exposure** — the assistant is an MCP server, so Claude Desktop / Cursor / any MCP client can use it as a tool.
- **Agentic + memory + evaluation** — LangGraph loop, long-term memory, and an LLM-judge eval pipeline.

## Layout

```
Cogito/
├── README.md          ← this file
├── PROPOSAL.pdf       ← full project proposal (detailed)
├── docs/
│   └── PROPOSAL.md    ← the proposal source (markdown)
├── src/               ← backend, ingestion, MCP server (to be built)
└── notebooks/         ← exploration notebooks
```

## Stack

- **Database:** MongoDB Community Edition 8.2+ (free; ships `$vectorSearch`, `$search`, `$rankFusion`)
- **Backend:** Python + FastAPI
- **Agent:** LangGraph
- **MCP:** MCP Python/TS SDK (outbound) + `mongodb-mcp-server` (inbound)
- **Embeddings/LLM:** OpenAI, Gemini, or Ollama (pluggable)

## Getting started

1. Run MongoDB 8.2+ (Community Edition) with `mongod` + `mongot` (see Docker option).
2. Set `MONGODB_URI` and an embedding/LLM provider key.
3. Build the ingestion pipeline (`src/ingest`), then hybrid search (`src/retrieval`), then the MCP server (`src/mcp`).

See `PROPOSAL.pdf` for the full architecture, data model, pipeline deep-dive, and build roadmap.


