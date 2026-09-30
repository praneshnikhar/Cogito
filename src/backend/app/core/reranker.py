"""Result reranking — cross-encoder when available, else a lightweight
query-aware lexical rerank that boosts chunks sharing distinctive terms."""

from __future__ import annotations

import logging
import re

log = logging.getLogger("cogito.reranker")

_rerank_model = None
_model_loaded = False

_STOP = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "for",
    "with", "is", "are", "was", "were", "be", "been", "how", "what", "when",
    "where", "why", "which", "who", "whom", "does", "do", "did", "can",
    "could", "would", "should", "will", "shall", "we", "you", "they", "it",
    "our", "your", "their", "at", "by", "as", "from", "about", "if", "not",
}


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]{3,}", text.lower()) if t not in _STOP}


def _load_model():
    """Lazily load a cross-encoder reranker; returns None if unavailable."""
    global _rerank_model, _model_loaded
    if _model_loaded:
        return _rerank_model
    _model_loaded = True
    try:
        from sentence_transformers import CrossEncoder

        _rerank_model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
        log.info("cross-encoder reranker loaded")
    except Exception as e:  # noqa: BLE001
        log.info(f"cross-encoder unavailable, using lexical rerank: {e}")
        _rerank_model = None
    return _rerank_model


def _lexical_rerank(question: str, chunks: list[dict]) -> list[dict]:
    q_terms = _tokens(question)
    if not q_terms:
        return chunks
    for c in chunks:
        overlap = len(q_terms & _tokens(c.get("text", "")))
        if overlap:
            # boost distinctive overlap, damped by hybrid score dominance
            c["score"] = float(c.get("score", 0)) * (1.0 + 0.35 * overlap)
    chunks.sort(key=lambda c: -float(c.get("score", 0)))
    return chunks


def rerank(question: str, chunks: list[dict]) -> list[dict]:
    """Rerank chunks against the question. Never raises; degrades gracefully."""
    if not chunks:
        return chunks
    model = _load_model()
    if model is None:
        return _lexical_rerank(question, chunks)
    try:
        pairs = [(question, c.get("text", "")) for c in chunks]
        scores = model.predict(pairs)
        for c, s in zip(chunks, scores):
            c["score"] = float(s) + float(c.get("score", 0))
        chunks.sort(key=lambda c: -float(c.get("score", 0)))
        return chunks
    except Exception as e:  # noqa: BLE001
        log.warning(f"cross-encoder rerank failed, falling back: {e}")
        return _lexical_rerank(question, chunks)