"""Document enrichment — extract a summary and keywords from a document's text
so the knowledge base is navigable without opening the source.

Fully offline: an extractive summarizer (sentence scoring) and a frequency
keyword extractor run key-free. When a real LLM is configured, `summarize`
swaps in an abstractive summary with the same return shape.
"""

from __future__ import annotations

import logging
import re
from collections import Counter

from app.core import llm

log = logging.getLogger("cogito.enrich")

_SENT_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_WORD_RE = re.compile(r"[a-z0-9]{3,}")

_STOP = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "for",
    "with", "is", "are", "was", "were", "be", "been", "has", "have", "had",
    "it", "this", "that", "these", "those", "they", "we", "you", "your",
    "our", "their", "will", "shall", "may", "can", "should", "would", "could",
    "not", "no", "yes", "as", "at", "by", "from", "into", "about", "over",
    "under", "between", "during", "each", "any", "all", "some", "such", "than",
    "then", "there", "here", "when", "where", "why", "how", "what", "which",
    "who", "whom", "whose", "also", "only", "very", "more", "most", "must",
}

_SUMMARY_PROMPT = (
    "Summarize the following document in at most 3 concise sentences. Return ONLY "
    "a JSON object: {\"summary\": str, \"keywords\": [\"...\", ...]}.\n\nDOCUMENT:\n{text}"
)


def _sentences(text: str) -> list[str]:
    parts = [s.strip() for s in _SENT_RE.split(text) if s and s.strip()]
    return parts


def _word_freq(text: str) -> Counter:
    words = [w for w in _WORD_RE.findall(text.lower()) if w not in _STOP]
    return Counter(words)


def extractive_summary(text: str, sentences: int = 2) -> str:
    """Frequency-based extractive summary: score sentences by the summed
    frequency of their non-stop words and return the top `sentences`."""
    sents = _sentences(text)
    if not sents:
        return ""
    if len(sents) <= sentences:
        return " ".join(sents)
    freq = _word_freq(text)
    if not freq:
        return sents[0]
    scored = []
    for s in sents:
        words = [w for w in _WORD_RE.findall(s.lower()) if w in freq]
        score = sum(freq[w] for w in words) / max(1, len(words) or 1)
        scored.append((score, s))
    scored.sort(key=lambda x: -x[0])
    top = [s for _, s in scored[:sentences]]
    # preserve original order
    top.sort(key=lambda s: sents.index(s))
    return " ".join(top)


def extract_keywords(text: str, limit: int = 8) -> list[str]:
    freq = _word_freq(text)
    return [w for w, _ in freq.most_common(limit)]


def enrich(text: str) -> dict:
    """Offline enrichment: summary + keywords."""
    return {"summary": extractive_summary(text), "keywords": extract_keywords(text)}


def enrich_llm(text: str) -> dict | None:
    """Abstractive enrichment when a real LLM is configured; else None."""
    judge = llm.active_judge()
    if judge is None:
        return None
    try:
        raw = judge.complete_json(_SUMMARY_PROMPT.format(text=text[:6000]), [])
        return {
            "summary": raw.get("summary", "") or extractive_summary(text),
            "keywords": raw.get("keywords") or extract_keywords(text),
        }
    except Exception as e:  # noqa: BLE001
        log.debug(f"LLM enrichment failed, using extractive: {e}")
        return None


async def enrich_document(text: str) -> dict:
    """Best-available enrichment (LLM abstractive, else extractive)."""
    return enrich_llm(text) or enrich(text)
