"""Query expansion for multi-query retrieval.

Generates several rephrasings of a user question, each of which is retrieved
independently and then fused (RRF) — a technique that lifts recall on short or
ambiguous questions.

Fully offline: a deterministic keyword-based expansion runs key-free. When a
real LLM is configured it replaces the deterministic variants with actual
rephrasings, so the feature upgrades with the same interface.
"""

from __future__ import annotations

import logging
import re

from app.core import llm

log = logging.getLogger("cogito.query_expansion")

_STOP = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "for",
    "with", "is", "are", "was", "were", "be", "been", "how", "what", "when",
    "where", "why", "which", "who", "whom", "does", "do", "did", "can",
    "could", "would", "should", "will", "shall", "we", "you", "they", "it",
    "our", "your", "their", "at", "by", "as", "from", "about", "if", "not",
    "have", "has", "had", "into", "that", "this", "there", "please", "tell",
}

_REPHRASE_PROMPT = (
    "You are a retrieval-augmentation query rewriter. Given a question, produce "
    "up to {n} distinct, more specific rephrasings that would each retrieve better "
    "evidence from a knowledge base. Return ONLY a JSON object: "
    '{{"queries": ["...", "..."]}}.'
)


def _rare_terms(question: str, limit: int = 6) -> list[str]:
    words = re.findall(r"[a-z0-9]{4,}", question.lower())
    seen: list[str] = []
    for w in words:
        if w not in _STOP and w not in seen:
            seen.append(w)
    return seen[:limit]


def _deterministic(question: str, n: int) -> list[str]:
    terms = _rare_terms(question)
    out = [question]
    if len(terms) >= 2:
        out.append(question + " " + " ".join(terms[:4]))
        out.append(" ".join(terms[:6]))
    elif terms:
        out.append(question + " " + " ".join(terms))
    # de-dup while preserving order
    seen: set[str] = set()
    result = []
    for q in out:
        if q not in seen:
            seen.add(q)
            result.append(q)
    return result[:max(1, n)]


def _llm_expand(judge, question: str, n: int) -> list[str]:
    prompt = _REPHRASE_PROMPT.format(n=n) + f"\n\nQUESTION: {question}"
    raw = judge.complete_json(prompt, [])
    queries = raw.get("queries") or []
    return [q for q in queries if q and q.strip()]


async def expand_queries(question: str, n: int = 3) -> list[str]:
    """Return `n` query variants (including the original) for multi-query search."""
    variants = _deterministic(question, n)
    judge = llm.active_judge()
    if judge is not None:
        try:
            upgraded = _llm_expand(judge, question, n)
            if upgraded:
                variants = [question, *upgraded]
        except Exception as e:  # noqa: BLE001
            log.debug(f"LLM query expansion skipped, using deterministic: {e}")
    return variants[:max(1, n)]
