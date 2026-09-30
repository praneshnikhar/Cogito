-- ============================================================================
-- Cogito — Postgres schema. Acts as a Supabase-compatible mirror for
-- analytics + auth. When a real SUPABASE_URL is configured the backend uses
-- Supabase's REST/PostgREST instead; otherwise this local Postgres is used.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Lightweight users table mirroring Supabase auth.users (id = supabase uuid)
CREATE TABLE IF NOT EXISTS users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email       TEXT UNIQUE,
    display_name TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Rolled-up analytics over Mongo query_logs, hydrated by the sync job / n8n.
CREATE TABLE IF NOT EXISTS query_analytics_daily (
    day          DATE PRIMARY KEY,
    total_queries BIGINT NOT NULL DEFAULT 0,
    unanswered   BIGINT NOT NULL DEFAULT 0,
    avg_latency_ms DOUBLE PRECISION NOT NULL DEFAULT 0,
    top_questions JSONB NOT NULL DEFAULT '[]'::jsonb,
    by_source    JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Mirrors of Mongo eval_results + feedback for charting from a single SQL store.
CREATE TABLE IF NOT EXISTS feedback_events (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    answer_id  TEXT,
    rating     INT,
    comment    TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS eval_scores (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    answer_id    TEXT,
    faithfulness DOUBLE PRECISION,
    relevance    DOUBLE PRECISION,
    judge        TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);