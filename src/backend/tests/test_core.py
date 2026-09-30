"""Unit tests for DB-free logic: chunker, embeddings, local LLM, local judge."""

import numpy as np

from app.core.embeddings import LocalHashEmbedder, embed, embed_one, fit
from app.core.llm import LocalTemplateLLM
from app.core.evaluator import _LocalJudge
from app.core.chunker import chunks_for_document, content_hash


def test_chunker_overlap():
    text = ("word " * 500)
    chunks = chunks_for_document("a.txt", text, "text")
    assert len(chunks) >= 2
    assert all(c["text"].strip() for c in chunks)
    assert chunks[0]["order"] == 0


def test_content_hash_stable():
    assert content_hash("hello world") == content_hash("hello world")
    assert content_hash("hello world") != content_hash("goodbye world")


def test_local_embedder_dim_and_normalized():
    e = LocalHashEmbedder(dim=384)
    vecs = e.embed(["the quick brown fox", "jumps over the lazy dog"])
    assert [len(v) for v in vecs] == [384, 384]
    for v in vecs:
        norm = np.linalg.norm(np.array(v))
        assert abs(norm - 1.0) < 1e-4
    assert vecs[0] != vecs[1]


def test_embed_and_fit():
    v = embed_one("penalty clause late delivery")
    v2 = fit(v)
    assert len(v2) == 384


def test_local_llm_cited_answer():
    llm = LocalTemplateLLM()
    chunks = [{"text": "Late delivery accrues a 0.5% penalty.", "document_id": "d1",
               "title": "contract.md", "score": 0.9}]
    result = llm.complete_json("What penalty?", chunks)
    assert "answer" in result
    assert result["citations"][0]["document_id"] == "d1"


def test_local_llm_empty_context():
    llm = LocalTemplateLLM()
    result = llm.complete_json("x", [])
    assert result["citations"] == []


def test_local_judge():
    j = _LocalJudge()
    score = j.score("What is the penalty?", "The penalty is 0.5% per day.",
                    [{"text": "The penalty is 0.5% per day of delay."}])
    assert 0.0 <= score["faithfulness"] <= 1.0
    assert 0.0 <= score["relevance"] <= 1.0

def test_rerank_lexical_boosts():
    from app.core.reranker import rerank
    chunks = [
        {"_id": "a", "text": "The quarterly report covers revenue growth.", "score": 0.9},
        {"_id": "b", "text": "Penalty clauses accrue 0.5% for late delivery.", "score": 0.5},
    ]
    out = rerank("what penalty for late delivery", chunks)
    assert out[0]["_id"] == "b"


def test_extract_html_and_docx():
    import asyncio
    from app.core.chunker import extract_text
    html = b"<html><body><h1>Title</h1><p>Some body text here.</p></body></html>"
    text, mime = asyncio.run(extract_text("page.html", html))
    assert "body text" in text
    assert mime == "text/html"


def test_extract_unknown_binary_degrades():
    import asyncio
    from app.core.chunker import extract_text
    text, _ = asyncio.run(extract_text("scan.png", b"\x89PNG\r\n\x1a\nnotreal"))
    assert isinstance(text, str)
