"""LLM-judge evaluation pipeline — scores every answer for faithfulness
(is every claim grounded in a retrieved chunk?) and relevance (did it answer?).
Works fully offline with the local judge and upgrades when a real LLM is set."""

from __future__ import annotations

import logging
import re

from app.core import llm

log = logging.getLogger("cogito.eval")

_JUDGE_PROMPT = """You are an evaluation judge. Score the assistant's answer on two
0-1 scales given the retrieved context chunks.

Context:
{context}

Question: {question}

Answer:
{answer}

Return ONLY a JSON object:
{{"faithfulness": 0.0-1.0, "relevance": 0.0-1.0, "explanation": "one line"}}
"""


class _LocalJudge:
    """Deterministic heuristic judge for the offline/no-key case."""

    def score(self, question: str, answer: str, context: list[dict]) -> dict:
        if not context:
            return {"faithfulness": 0.0, "relevance": 0.0, "judge": "local"}

        ctx_text = " ".join(c.get("text", "") for c in context)
        # relevance: does the answer share terms with the question?
        q_terms = set(re.findall(r"\w{3,}", question.lower()))
        a_terms = set(re.findall(r"\w{3,}", answer.lower()))
        overlap = len(q_terms & a_terms) / max(1, len(q_terms))
        relevance = min(1.0, overlap + 0.2 if answer else 0.0)

        # faithfulness: fraction of answer notable terms found in context
        notable = [t for t in a_terms if len(t) > 4 and t not in {"based", "answer", "context"}]
        matched = [t for t in notable if t in ctx_text.lower()]
        faithfulness = min(1.0, (len(matched) / max(1, len(notable))) * 0.8 + 0.2)

        return {"faithfulness": round(float(faithfulness), 3),
                "relevance": round(float(relevance), 3), "judge": "local"}


def evaluate_answer(question: str, answer: str, context: list[dict]) -> dict:
    judge = llm.active_judge()
    if judge is None:
        return _LocalJudge().score(question, answer, context)
    try:
        docs = "\n\n".join(f"[{i}] {c.get('text', '')}" for i, c in enumerate(context))
        prompt = _JUDGE_PROMPT.format(question=question, answer=answer, context=docs)
        raw = judge.complete_json(prompt, context)
        return {"faithfulness": float(raw.get("faithfulness", 0)),
                "relevance": float(raw.get("relevance", 0)),
                "judge": judge.__class__.__name__}
    except Exception as e:  # noqa: BLE001
        log.warning(f"LLM judge failed, using local: {e}")
        return _LocalJudge().score(question, answer, context)