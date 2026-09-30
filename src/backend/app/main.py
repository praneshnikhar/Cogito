"""Cogito FastAPI application entrypoint.

Wires the routers, lifespan (db index provisioning + search feature probe),
CORS, and telemetry."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import db
from app.config import settings
from app.routers import analytics, chat, health, ingest, memory, search

log = logging.getLogger("cogito")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("cogito starting up")
    try:
        await db.ensure_indexes()
    except Exception as e:  # noqa: BLE001
        log.error(f"index provisioning failed: {e}")
    try:
        await db.probe_search()
        log.info(f"search mode: {db.search_mode_sync()}")
    except Exception as e:  # noqa: BLE001
        log.warning(f"search probe failed: {e}")
    try:
        from app import telemetry
        await telemetry.redis_client()  # warm connection
    except Exception:  # noqa: BLE001
        pass
    yield
    log.info("cogito shutting down")


app = FastAPI(title="Cogito", version="0.1.0",
              description="MongoDB-native RAG knowledge assistant (MCP-powered)",
              lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(ingest.router)
app.include_router(search.router)
app.include_router(chat.router)
app.include_router(memory.router)
app.include_router(analytics.router)


@app.get("/")
async def root():
    return {"name": "Cogito", "docs": "/docs", "capabilities": "/capabilities",
            "health": "/health"}