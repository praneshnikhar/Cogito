"""Embedding provider factory.

Pluggable backends: `openai`, `openrouter`, `ollama`, and `local` (a
deterministic, key-free hashing embedder so the whole stack demos offline).
Every provider returns normalized vectors of `settings.embedding_dim` length.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Protocol

import numpy as np

from app.config import settings

log = logging.getLogger("cogito.embeddings")


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...

    @property
    def dim(self) -> int: ...


# ---------------------------------------------------------------- local hashing
TOKEN_RE = re.compile(r"[a-z0-9]+")


class LocalHashEmbedder:
    """Key-free bag-of-hashed-n-grams embedder. Deterministic + normalized."""

    def __init__(self, dim: int = 384, ng: int = 3) -> None:
        self._dim = dim
        self.ng = ng

    @property
    def dim(self) -> int:
        return self._dim

    def _features(self, text: str) -> list[str]:
        tokens = TOKEN_RE.findall(text.lower())
        feats: list[str] = []
        feats.extend(f"w:{t}" for t in tokens)
        for tok in tokens:
            padded = f"^{tok}$"
            feats.extend(
                padded[i : i + self.ng] for i in range(len(padded) - self.ng + 1)
            )
        return feats

    def _hash(self, feat: str, salt: int) -> int:
        return int(
            hashlib.sha256(f"{salt}:{feat}".encode()).hexdigest()[:8], 16
        ) % self.dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vec = np.zeros(self.dim, dtype=np.float32)
            for feat in self._features(text):
                idx = self._hash(feat, 0)
                vec[idx] += 1.0
                idx2 = self._hash(feat, 1)
                vec[idx2] += 0.5
            norm = float(np.linalg.norm(vec))
            if norm > 0:
                vec /= norm
            out.append(vec.tolist())
        return out


# ---------------------------------------------------------------- openai
class OpenAIEmbedder:
    def __init__(self, model: str) -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = model

    @property
    def dim(self) -> int:
        return settings.embedding_dim

    async def embed_async(self, texts: list[str]) -> list[list[float]]:
        resp = await self._client.embeddings.create(model=self.model, input=texts)
        return [d.embedding for d in resp.data]

    def embed(self, texts: list[str]) -> list[list[float]]:
        import asyncio

        return asyncio.run(self.embed_async(texts))


class OpenRouterEmbedder:
    """OpenRouter serves embedding models through its OpenAI-compatible API."""

    def __init__(self, model: str) -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(
            api_key=settings.openrouter_api_key,
            base_url="https://openrouter.ai/api/v1",
        )
        self.model = model

    @property
    def dim(self) -> int:
        return settings.embedding_dim

    async def embed_async(self, texts: list[str]) -> list[list[float]]:
        resp = await self._client.embeddings.create(model=self.model, input=texts)
        return [d.embedding for d in resp.data]

    def embed(self, texts: list[str]) -> list[list[float]]:
        import asyncio

        return asyncio.run(self.embed_async(texts))


# ---------------------------------------------------------------- ollama
class OllamaEmbedder:
    def __init__(self, model: str) -> None:
        import httpx

        self.model = model
        self.base = settings.ollama_base_url
        self._httpx = httpx

    @property
    def dim(self) -> int:
        return settings.embedding_dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            r = self._httpx.post(
                f"{self.base}/api/embeddings", json={"model": self.model, "prompt": t}
            )
            r.raise_for_status()
            out.append(r.json()["embedding"])
        return out


# ---------------------------------------------------------------- factory
_local = LocalHashEmbedder()

if settings.embedding_provider == "openai":
    _active: Embedder = OpenAIEmbedder(settings.embedding_model)
elif settings.embedding_provider == "openrouter":
    _active = OpenRouterEmbedder(settings.embedding_model)
elif settings.embedding_provider == "ollama":
    _active = OllamaEmbedder(settings.ollama_embed_model)
else:
    _active = _local


def make_embedder(provider: str | None = None) -> Embedder:
    """Instantiate a fresh embedder (used by workers/tests)."""
    p = (provider or settings.embedding_provider).lower()
    if p == "openai":
        return OpenAIEmbedder(settings.embedding_model)
    if p == "openrouter":
        return OpenRouterEmbedder(settings.embedding_model)
    if p == "ollama":
        return OllamaEmbedder(settings.ollama_embed_model)
    return LocalHashEmbedder()


def embed(texts: list[str]) -> list[list[float]]:
    return _active.embed(texts)


def embed_one(text: str) -> list[float]:
    return _active.embed([text])[0]


def embedding_dim() -> int:
    return _active.dim


# If configured dimension differs from the model's, trim/pad local vectors.
def fit(vector: list[float], dim: int | None = None) -> list[float]:
    n = dim or settings.embedding_dim
    v = np.array(vector, dtype=np.float32)
    if len(v) > n:
        v = v[:n]
    elif len(v) < n:
        v = np.pad(v, (0, n - len(v)))
    norm = float(np.linalg.norm(v))
    if norm > 0:
        v = v / norm
    return v.tolist()