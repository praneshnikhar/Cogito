"""LLM provider factory + grounded (cited) answer generation.

Providers: `openrouter`, `openai`, `gemini`, `ollama`, and `local` (a key-free
template generator so the full pipeline demos offline). The local provider
produces a deterministic, source-citing answer from the retrieved chunks.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Protocol

from app.config import settings
from app.core.async_runner import runner

log = logging.getLogger("cogito.llm")

GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

SYSTEM_PROMPT = (
    "You are Cogito, a precise knowledge assistant grounded only in the provided "
    "context. Follow these rules exactly:\n"
    "1. Answer ONLY the user's question, directly and concisely, in at most 4 sentences. "
    "Never dump, repeat, or summarize whole documents.\n"
    "2. Every factual claim must be supported by a provided chunk. Never use outside "
    "knowledge.\n"
    "3. Cite only the chunks you actually used. Each excerpt must be a short quote of "
    "at most 25 words.\n"
    "4. If the context does not contain the answer, set answer to exactly 'I could not "
    "find this in the knowledge base.' and return an empty citations array.\n"
    "Return one JSON object: {\"answer\": str, \"citations\": [{\"document_id\": str, "
    "\"title\": str, \"excerpt\": str, \"score\": float}]}."
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
def _retry_delay(error: Exception, attempt: int) -> float:
    """Honor a provider's retry hint, capped so a demo does not hang."""
    text = str(error)
    match = re.search(r"retry in ([\d.]+)s", text)
    if not match:
        match = re.search(r"retryDelay'?:\s*'?(\d+)s", text)
    if match:
        return min(30.0, max(2.0, float(match.group(1))))
    return 4.0 * (attempt + 1)


class _OpenAICompatLLM:
    def __init__(self, api_key: str, model: str, base_url: str | None = None) -> None:
        from openai import AsyncOpenAI

        self.model = model
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    def complete_json(self, user_prompt: str, context: list[dict]) -> dict:
        return runner.run(self._complete(user_prompt, context))

    async def _complete(self, user_prompt: str, context: list[dict]) -> dict:
        from openai import InternalServerError, RateLimitError

        docs = json.dumps(context, default=str)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"CONTEXT:\n{docs}\n\nQUESTION:\n{user_prompt}"},
        ]
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                resp = await self._client.chat.completions.create(
                    model=self.model, messages=messages, temperature=0.2
                )
                break
            except (RateLimitError, InternalServerError) as e:
                last_error = e
                if attempt == 2:
                    raise
                await asyncio.sleep(_retry_delay(e, attempt))
        else:  # pragma: no cover - defensive
            raise last_error or RuntimeError("LLM request failed")
        raw = resp.choices[0].message.content or ""
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


class GeminiLLM(_OpenAICompatLLM):
    """Google Gemini through its OpenAI-compatible endpoint."""

    def __init__(self, model: str) -> None:
        super().__init__(settings.gemini_api_key, model, GEMINI_OPENAI_BASE_URL)


# ---------------------------------------------------------------- factory
if settings.llm_provider == "openrouter":
    _active_llm: LLM = OpenRouterLLM(settings.llm_model)
elif settings.llm_provider == "openai":
    _active_llm = OpenAILLM(settings.llm_model)
elif settings.llm_provider == "gemini":
    _active_llm = GeminiLLM(settings.gemini_llm_model)
elif settings.llm_provider == "ollama":
    _active_llm = _OpenAICompatLLM(
        "ollama", settings.ollama_llm_model, f"{settings.ollama_base_url}/v1"
    )
else:
    _active_llm = LocalTemplateLLM()
    if settings.cogito_env == "production":
        log.warning(
            "LLM_PROVIDER=local (template answers) in production — set "
            "OPENROUTER_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY or "
            "OLLAMA_BASE_URL for real answers"
        )


def make_llm(provider: str | None = None) -> LLM:
    p = (provider or settings.llm_provider).lower()
    if p == "openrouter":
        return OpenRouterLLM(settings.llm_model)
    if p == "openai":
        return OpenAILLM(settings.llm_model)
    if p == "gemini":
        return GeminiLLM(settings.gemini_llm_model)
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