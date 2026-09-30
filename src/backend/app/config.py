"""Application configuration — every value has a safe default so the stack
runs fully offline, and lights up cloud features when keys are provided."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Core
    cogito_env: str = "production"
    log_level: str = "INFO"

    # Mongo
    mongodb_uri: str = "mongodb://mongodb:27017/cogito?replicaSet=rs0&directConnection=true"
    mongodb_db: str = "cogito"
    atlas_uri: str = ""

    # LLM / embeddings
    llm_provider: str = "local"  # openrouter | openai | ollama | local
    llm_model: str = "deepseek/deepseek-chat"
    openrouter_api_key: str = ""
    openai_api_key: str = ""
    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_llm_model: str = "qwen2.5:7b"

    embedding_provider: str = "local"  # openrouter | openai | ollama | local
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 384
    ollama_embed_model: str = "nomic-embed-text"

    # Telemetry
    posthog_api_key: str = ""
    posthog_host: str = "https://us.i.posthog.com"
    posthog_distinct_id: str = "cogito-demo"
    sentry_dsn: str = ""

    # Redis / Upstash
    redis_url: str = "redis://redis:6379/0"
    upstash_redis_rest_url: str = ""
    upstash_redis_rest_token: str = ""

    # Pinecone
    pinecone_api_key: str = ""
    pinecone_env: str = "us-east4-gcp"
    pinecone_index: str = "cogito"

    # Supabase / Postgres
    supabase_url: str = ""
    supabase_anon_key: str = ""
    postgres_dsn: str = "postgresql+asyncpg://cogito:cogito@postgres:5432/cogito"

    # Agents / search
    agent_max_iterations: int = 3
    retrieval_top_k: int = 5
    search_num_candidates: int = 100
    evaluation_enabled: bool = True

    # Webhooks
    cogito_webhook_url: str = "http://backend:8000/webhooks/ingest"
    n8n_webhook_url: str = "http://n8n:5678/webhook/cogito-ingest"

    # App
    cors_origins: str = "*"
    admin_token: str = "change-me"

    @property
    def is_full_search(self) -> bool:
        """True when mongot (MongoDB Search) is present, which we detect by
        attempting to create a real $search index at startup."""
        return False  # overridden after runtime feature detection

    @property
    def effective_mongo_uri(self) -> str:
        return self.atlas_uri or self.mongodb_uri


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()