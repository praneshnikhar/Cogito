"""LLM provider factory + grounded (cited) answer generation.

Providers: `openrouter`, `openai`, `ollama`, and `local` (a key-free template
generator so the full pipeline demos offline). The local provider produces a
deterministic, source-citing answer from the retrieved chunks.
"""

from __future__ import annotations

import json
import logging
from typing import Protocol

from app.config import settings

log = logging.getLogger("cogito.llm")

SYSTEM_PROMPT = (
    "You are Cogito, a precise knowledge assistant grounded only in the provided "
    "context. Answer using the context. Every factual claim must be supported by a "
    "chunk. Return a JSON object: {\"answer\": str, \"citations\": [{\"document_id\": str, "
    "\"title\": str, \"excerpt\": str, \"score\": float}]}. If the context cannot answer, "
    "say so and cite nothing."
)


class LLM(Protocol):
    def complete_json(self, user_prompt: str, context: list[dict]) -> dict: ...


# ---------------------------------------------------------------- local
class LocalTemplateLLM:
    """Key-free fallback. Builds a cited answer deterministically from chunks."""

    def complete_json(self, user_prompt: str, context: list[dict]) -> dict:
        if not context:
            return {
                "answer": "I could not find supporting evidence for that in the knowledge base.",
                "citations": [],
            }
        body = " ".join(c.get("text", "") for c in context[:3])
        lead = "Based on the retrieved knowledge base excerpts, here is an answer:"
        citations = []
        seen = set()
        for c in context:
            did = c.get("document_id")
            if did in seen:
                continue
            seen.add(did)
            citations.append(
                {
                    "document_id": did,
                    "title": c.get("title", "unknown"),
                    "excerpt": c.get("text", "")[:300],
                    "score": round(float(c.get("score", 0.0)), 3),
                }
            )
        answer = (
            f"{lead}\n\n{body[:1200]}\n\n"
            "This answer is synthesized from the citations below; verify details "
            "against the source excerpts."
        )
        return {"answer": answer, "citations": citations}


# ---------------------------------------------------------------- chat providers
class _OpenAICompatLLM:
    def __init__(self, api_key: str, model: str, base_url: str | None = None) -> None:
        from openai import AsyncOpenAI

        kw = {"api_key": api_key, "model": model}
        if base_url:
            kw["base_url"] = base_url
        self.model = model
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    def complete_json(self, user_prompt: str, context: list[dict]) -> dict:
        import asyncio

        return asyncio.run(self._complete(user_prompt, context))

    async def _complete(self, user_prompt: str, context: list[dict]) -> dict:
        docs = json.dumps(context, default=str)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"CONTEXT:\n{docs}\n\nQUESTION:\n{user_prompt}"},
        ]
        resp = await self._client.chat.completions.create(
            model=self.model, messages=messages, temperature=0.2
        )
        raw = resp.choices[0].message.content
        try:
            return json.loads(raw[raw.index("{") : raw.rindex("}") + 1])
        except Exception:  # noqa: BLE001
            return {"answer": raw, "citations": []}


class OpenRouterLLM(_OpenAICompatLLM):
    def __init__(self, model: str) -> None:
        super().__init__(settings.openrouter_api_key, model, "https://openrouter.ai/api/v1")


class OpenAILLM(_OpenAICompatLLM):
    def __init__(self, model: str) -> None:
        super().__init__(settings.openai_api_key, model)


# ---------------------------------------------------------------- factory
if settings.llm_provider == "openrouter":
    _active_llm: LLM = OpenRouterLLM(settings.llm_model)
elif settings.llm_provider == "openai":
    _active_llm = OpenAILLM(settings.llm_model)
elif settings.llm_provider == "ollama":
    _active_llm = _OpenAICompatLLM(
        "ollama", settings.ollama_llm_model, f"{settings.ollama_base_url}/v1"
    )
else:
    _active_llm = LocalTemplateLLM()
    if settings.cogito_env == "production":
        log.warning(
            "LLM_PROVIDER=local (template answers) in production — set "
            "OPENROUTER_API_KEY/OPENAI_API_KEY or OLLAMA_BASE_URL for real answers"
        )


def make_llm(provider: str | None = None) -> LLM:
    p = (provider or settings.llm_provider).lower()
    if p == "openrouter":
        return OpenRouterLLM(settings.llm_model)
    if p == "openai":
        return OpenAILLM(settings.llm_model)
    if p == "ollama":
        return _OpenAICompatLLM("ollama", settings.ollama_llm_model, f"{settings.ollama_base_url}/v1")
    return LocalTemplateLLM()


def generate_cited_answer(
    question: str, chunks: list[dict], llm: LLM | None = None
) -> dict:
    result = (llm or _active_llm).complete_json(question, chunks)
    result.setdefault("answer", "")
    result.setdefault("citations", [])
    return result


def settings_llm_provider() -> str:
    return settings.llm_provider


def active_judge() -> LLM | None:
    """Return a real LLM for judging, or None (caller falls back to local)."""
    if isinstance(_active_llm, LocalTemplateLLM):
        return None
    return _active_llm