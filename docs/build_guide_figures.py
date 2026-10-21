#!/usr/bin/env python3
"""Generate diagrams for docs/Cogito_Project_Guide.docx."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "guide_assets"
OUT.mkdir(parents=True, exist_ok=True)

NAVY = "#142033"
MUTED = "#5B6B82"
BLUE = "#2563EB"
PURPLE = "#6D4AFF"
GREEN = "#0F9D6E"
AMBER = "#B45309"
BG = "#F7F9FC"
WHITE = "#FFFFFF"


def canvas(w=14, h=7.5):
    fig, ax = plt.subplots(figsize=(w, h), dpi=200)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.axis("off")
    return fig, ax


def box(ax, x, y, w, h, title, lines, fc=WHITE, ec=BLUE, tc=NAVY, title_size=12, body_size=9.5):
    patch = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.04,rounding_size=0.12",
        linewidth=1.2, edgecolor=ec, facecolor=fc, zorder=2,
    )
    ax.add_patch(patch)
    ax.text(x + w / 2, y + h - 0.24, title, ha="center", va="top",
            fontsize=title_size, fontweight="bold", color=tc, zorder=3)
    for i, line in enumerate(lines):
        ax.text(x + w / 2, y + h - 0.58 - i * 0.24, line, ha="center", va="top",
                fontsize=body_size, color=MUTED, zorder=3)


def arrow(ax, p1, p2, label=None, color=PURPLE, rad=0.0, lx=0, ly=0, dashed=False):
    ax.add_patch(FancyArrowPatch(
        p1, p2, arrowstyle="-|>", mutation_scale=14, linewidth=1.4,
        color=color, connectionstyle=f"arc3,rad={rad}", zorder=1,
        linestyle=(0, (4, 3)) if dashed else "solid",
    ))
    if label:
        mx = (p1[0] + p2[0]) / 2 + lx
        my = (p1[1] + p2[1]) / 2 + ly
        ax.text(mx, my, label, ha="center", va="center", fontsize=8.5,
                color=MUTED, bbox=dict(boxstyle="round,pad=0.18", fc=BG, ec="none"), zorder=4)


def title(ax, text, sub=None):
    w = ax.get_xlim()[1]
    h = ax.get_ylim()[1]
    ax.text(w / 2, h - 0.32, text, ha="center", va="top", fontsize=17,
            fontweight="bold", color=NAVY)
    if sub:
        ax.text(w / 2, h - 0.72, sub, ha="center", va="top", fontsize=10, color=MUTED)


# ---------------------------------------------------------------- architecture
fig, ax = canvas(14, 7.8)
title(ax, "Cogito architecture", "Next.js UI, FastAPI backend, MongoDB + mongot, worker, Redis, Postgres, and a pluggable LLM/embedding provider")

# Docker boundary
ax.add_patch(FancyBboxPatch((0.25, 0.42), 13.5, 6.3, boxstyle="round,pad=0.02,rounding_size=0.15",
                            fill=False, edgecolor="#94A3B8", linestyle=(0, (5, 4)), linewidth=1.0, zorder=0))
ax.text(0.42, 0.56, "Docker Compose · web UI can also run with npm on the host",
        fontsize=8.2, color="#64748B")

box(ax, 0.55, 4.72, 3.3, 1.7, "Browser / Next.js UI", ["/documents  /chat  /dashboard", "React components + route handlers"], "#E8F0FF", BLUE)
box(ax, 4.35, 4.72, 3.3, 1.7, "FastAPI backend", ["REST endpoints", "Pydantic validation", "async Motor driver"], "#EEF2FF", PURPLE)
box(ax, 8.35, 4.52, 5.0, 2.05, "MongoDB 8.2 + mongot", [
    "documents · chunks · memories",
    "$search · $vectorSearch · $rankFusion",
    "change streams · transactions",
    "aggregation pipelines",
], "#E7F7F0", GREEN, title_size=12.5)
box(ax, 8.35, 1.65, 3.0, 1.45, "Ingest worker", ["watches the change stream", "extract → chunk → embed"], "#FFF6E5", AMBER)
box(ax, 4.35, 1.65, 3.3, 1.45, "LLM + embeddings", ["configurable provider", "chat · embeddings · judge", "local fallback"], "#F3EDFF", PURPLE)
box(ax, 0.55, 1.65, 1.55, 1.2, "Redis", ["cache", "rate limit"], "#EEF2FF", BLUE, title_size=10.5, body_size=8.6)
box(ax, 2.3, 1.65, 1.55, 1.2, "Postgres", ["analytics", "mirror"], "#EEF2FF", BLUE, title_size=10.5, body_size=8.6)

arrow(ax, (3.85, 5.55), (4.35, 5.55), "REST / JSON", BLUE, ly=-0.27)
arrow(ax, (7.65, 5.55), (8.35, 5.55), "queries", PURPLE, ly=-0.27)
arrow(ax, (9.15, 4.52), (9.15, 3.10), "", GREEN)
arrow(ax, (10.25, 3.10), (10.25, 4.52), "", GREEN)
ax.text(8.98, 3.80, "change stream", ha="right", va="center", fontsize=8.5, color=MUTED)
ax.text(10.42, 3.80, "chunks + status", ha="left", va="center", fontsize=8.5, color=MUTED)
arrow(ax, (5.45, 4.72), (5.45, 3.10), "ask / answer", PURPLE, lx=0.75, ly=0.0)
arrow(ax, (8.35, 2.35), (7.65, 2.35), "embed", PURPLE, ly=0.25)

fig.savefig(OUT / "architecture.png", bbox_inches="tight", facecolor=BG)
plt.close(fig)

# ---------------------------------------------------------------- upload flow
fig, ax = canvas(14, 4.6)
title(ax, "Upload → indexed, step by step", "The API only writes a pending document; MongoDB and the worker do the rest")
steps = [
    ("1. Upload", ["UI sends file", "POST /api/documents"]),
    ("2. Pending", ["FastAPI inserts", "status = pending"]),
    ("3. Change stream", ["MongoDB emits", "the insert event"]),
    ("4. Process", ["worker extracts", "text and chunks"]),
    ("5. Embed", ["each chunk gets", "a 768-d vector"]),
    ("6. Commit", ["transaction writes", "chunks + indexed"]),
]
w, gap = 1.95, 0.22
start = (14 - (6 * w + 5 * gap)) / 2
for i, (t, lines) in enumerate(steps):
    x = start + i * (w + gap)
    color = GREEN if i in (2, 5) else (AMBER if i == 3 else BLUE)
    box(ax, x, 1.50, w, 1.9, t, lines, WHITE, color, title_size=10.5, body_size=8.2)
    if i < 5:
        arrow(ax, (x + w, 2.45), (x + w + gap, 2.45), color=color)
ax.text(14 / 2, 0.68, "The UI polls GET /ingest/documents until status becomes indexed.",
        ha="center", va="top", fontsize=9.5, color=MUTED)
fig.savefig(OUT / "upload_flow.png", bbox_inches="tight", facecolor=BG)
plt.close(fig)

# ---------------------------------------------------------------- search flow
fig, ax = canvas(14, 6.6)
title(ax, "One question, two search signals, one ranking", "Keyword and vector results are fused, then reranked")
box(ax, 0.55, 3.0, 2.5, 1.35, "Question", ["plain English"], "#E8F0FF", BLUE, title_size=11)
box(ax, 3.55, 3.0, 2.5, 1.35, "Embed query", ["same 768-d space", "as the chunks"], "#EEF2FF", PURPLE, title_size=11)
box(ax, 7.0, 4.25, 2.8, 1.35, "Lexical branch", ["$search / $text", "exact words + clause IDs"], "#E7F7F0", GREEN, title_size=11)
box(ax, 7.0, 2.15, 2.8, 1.35, "Semantic branch", ["$vectorSearch", "meaning + paraphrase"], "#E7F7F0", GREEN, title_size=11)
box(ax, 10.35, 3.0, 3.05, 1.6, "Fuse + rerank", ["$rankFusion (RRF)", "cross-encoder or lexical boost"], "#FFF6E5", AMBER, title_size=11)
box(ax, 10.35, 0.75, 3.05, 1.15, "Answer + citations", ["top-k chunks", "grounded JSON"], "#F3EDFF", PURPLE, title_size=11)
arrow(ax, (3.05, 3.68), (3.55, 3.68), "embed", BLUE)
arrow(ax, (6.05, 3.68), (7.0, 4.9), "keywords", GREEN, rad=-0.05)
arrow(ax, (6.05, 3.68), (7.0, 2.8), "meaning", GREEN, rad=0.05)
arrow(ax, (9.8, 4.9), (10.35, 4.0), "", GREEN)
arrow(ax, (9.8, 2.8), (10.35, 3.55), "", GREEN)
arrow(ax, (11.85, 3.0), (11.85, 1.9), "", PURPLE)
ax.text(14 / 2, 0.28, "Fallback on plain mongod: $text + cosine similarity + Python RRF. Same result shape.",
        ha="center", va="bottom", fontsize=8.8, color=MUTED)
fig.savefig(OUT / "search_flow.png", bbox_inches="tight", facecolor=BG)
plt.close(fig)

# ---------------------------------------------------------------- data model
fig, ax = canvas(14, 6.4)
title(ax, "Data model at a glance", "One document per retrieval unit; chunks are the bridge between files and search")
box(ax, 0.6, 3.65, 3.3, 1.6, "documents", ["source file + metadata", "status, raw, summary"], "#E8F0FF", BLUE, title_size=11)
box(ax, 5.0, 3.65, 3.3, 1.6, "chunks", ["text + embedding", "page, order, token_count"], "#E7F7F0", GREEN, title_size=11)
box(ax, 9.4, 3.65, 3.9, 1.6, "query_logs / eval_results", ["one row per question", "latency, chunk_ids, judge"], "#EEF2FF", PURPLE, title_size=11)
box(ax, 0.6, 1.25, 3.3, 1.3, "conversations", ["messages[] embedded"], "#FFF6E5", AMBER, title_size=11)
box(ax, 5.0, 1.25, 3.3, 1.3, "memories", ["facts + embeddings"], "#FFF6E5", AMBER, title_size=11)
box(ax, 9.4, 1.25, 3.9, 1.3, "feedback", ["ratings (API only)"], "#F3EDFF", PURPLE, title_size=11)
arrow(ax, (3.9, 4.45), (5.0, 4.45), "1 → N", BLUE)
arrow(ax, (8.3, 4.45), (9.4, 4.45), "chunk ids", PURPLE)
arrow(ax, (3.9, 1.9), (5.0, 1.9), "user facts", AMBER)
ax.text(14 / 2, 0.35, "Embedded arrays avoid joins on the read path; indexes follow the access patterns.",
        ha="center", va="bottom", fontsize=9, color=MUTED)
fig.savefig(OUT / "data_model.png", bbox_inches="tight", facecolor=BG)
plt.close(fig)

print("figures written to", OUT)
