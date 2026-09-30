"""Agentic RAG loop built with LangGraph.

Pipeline: retrieve → assess confidence → (refine the query + re-retrieve if
weak) → generate a grounded, cited answer. Demonstrates the reasoning loop
Tier-3 feature (M5) on top of the hybrid retriever."""

from __future__ import annotations

import logging
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.config import settings
from app.core.hybrid_search import hybrid_search
from app.core.llm import generate_cited_answer

log = logging.getLogger("cogito.agent")

CONFIDENCE_FLOOR = 0.05
RETRIEVE_BUDGET = 40  # fetch more, keep top-k after confidence check


class AgentState(TypedDict, total=False):
    question: str
    user_id: str | None
    chunks: list[dict]
    refined: str
    confidence: float
    iterations: int
    answer: str
    citations: list[dict]


# ------------------------------------------------------------------ nodes
async def retrieve(state: AgentState) -> AgentState:
    q = state.get("refined") or state["question"]
    chunks = await hybrid_search(q, k=RETRIEVE_BUDGET)
    # confidence = mean top-3 score (boost-aware)
    scores = [float(c.get("score", 0)) for c in chunks[:3]]
    confidence = sum(scores) / max(1, len(scores))
    return {
        **state,
        "chunks": chunks,
        "confidence": confidence,
        "iterations": state.get("iterations", 0) + 1,
    }


async def refine(state: AgentState) -> AgentState:
    """Rewrite a weak query into a more precise one and re-retrieve."""
    top = " ".join(c.get("text", "") for c in (state.get("chunks") or []))[:600]
    # Deterministic refinement: rephrase using the top chunk's domain terms.
    import re

    terms = set(re.findall(r"\w{4,}", top.lower()))
    question = state["question"]
    q_terms = set(re.findall(r"\w{4,}", question.lower()))
    extra = sorted(terms - q_terms)[:4]
    refined = question + (" " + " ".join(extra) if extra else "")
    log.info(f"refined query: {question!r} -> {refined!r}")
    return {**state, "refined": refined}


async def generate(state: AgentState) -> AgentState:
    q = state["question"]
    chunks = state.get("chunks") or []
    answer = generate_cited_answer(q, chunks)
    return {**state, "answer": answer.get("answer", ""), "citations": answer.get("citations", [])}


def should_refine(state: AgentState) -> str:
    if (
        state.get("iterations", 0) < settings.agent_max_iterations
        and state.get("confidence", 0) < CONFIDENCE_FLOOR
        and len(state.get("chunks") or []) < settings.retrieval_top_k
    ):
        return "refine"
    return "generate"


# ------------------------------------------------------------------ graph
def build_graph():
    g = StateGraph(AgentState)
    g.add_node("retrieve", retrieve)
    g.add_node("refine", refine)
    g.add_node("generate", generate)
    g.add_edge(START, "retrieve")
    g.add_conditional_edges("retrieve", should_refine, {"refine": "refine", "generate": "generate"})
    g.add_edge("refine", "retrieve")
    g.add_edge("generate", END)
    return g.compile()


_compiled = build_graph()


async def run_agent(question: str, user_id: str | None = None) -> dict:
    result = await _compiled.ainvoke(
        {"question": question, "user_id": user_id, "iterations": 0}
    )
    return {
        "answer": result.get("answer", ""),
        "citations": result.get("citations", []),
        "chunks": result.get("chunks", []),
        "confidence": result.get("confidence", 0),
        "iterations": result.get("iterations", 0),
        "refined_query": result.get("refined"),
    }