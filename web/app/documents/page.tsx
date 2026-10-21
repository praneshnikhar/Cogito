"use client";

import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";

import { Nav } from "@/components/nav";

type Doc = {
  _id: string;
  title: string;
  path: string;
  type: string;
  status: string;
  chunk_count?: number;
  created_at?: number;
  indexed_at?: number;
  summary?: string;
  keywords?: string[];
  mime?: string;
  error?: string;
  editable?: boolean;
  text?: string;
};

type Chunk = {
  _id: string;
  text: string;
  order: number;
  page?: number;
  token_count?: number;
  boost?: number;
};

type Hit = {
  _id: string;
  document_id: string;
  title: string;
  text: string;
  page?: number;
  score: number;
};

type Notice = { text: string; kind: "ok" | "error" };

const DOC_TYPES = ["text", "contract", "markdown", "html", "csv", "json"];

function detailOf(data: any, fallback: string): string {
  const detail = data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d: any) => d?.msg ?? JSON.stringify(d))
      .join("; ");
  }
  return fallback;
}

function when(ts?: number) {
  if (!ts) return "—";
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return new Date(ts * 1000).toLocaleDateString();
}

export default function Documents() {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);

  const [tab, setTab] = useState<"file" | "paste">("file");
  const [file, setFile] = useState<File | null>(null);
  const fileInput = useRef<HTMLInputElement | null>(null);
  const [text, setText] = useState("");
  const [filename, setFilename] = useState("notes.txt");
  const [docType, setDocType] = useState("text");
  const [uploading, setUploading] = useState(false);

  const [openId, setOpenId] = useState<string | null>(null);
  const [detail, setDetail] = useState<Doc | null>(null);
  const [chunks, setChunks] = useState<Chunk[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);
  const [draftText, setDraftText] = useState("");
  const [saving, setSaving] = useState(false);
  const [editingTitle, setEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState("");

  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Hit[]>([]);
  const [searching, setSearching] = useState(false);
  const [searched, setSearched] = useState(false);
  const offline = useRef(false);

  const flash = useCallback((textMsg: string, kind: "ok" | "error" = "ok") => {
    setNotice({ text: textMsg, kind });
    window.setTimeout(() => setNotice(null), 5000);
  }, []);

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/documents", { cache: "no-store" });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(detailOf(data, `could not load documents (${res.status})`));
      }
      setDocs(Array.isArray(data) ? data : []);
      setLoadError(null);
      offline.current = false;
    } catch (e) {
      const msg = e instanceof Error ? e.message : "backend unreachable";
      setLoadError(msg);
      if (!offline.current) {
        flash(msg, "error");
        offline.current = true;
      }
    } finally {
      setLoading(false);
    }
  }, [flash]);

  useEffect(() => {
    load();
    const timer = window.setInterval(load, 4000);
    return () => window.clearInterval(timer);
  }, [load]);

  const stats = useMemo(() => {
    const indexed = docs.filter((d) => d.status === "indexed").length;
    const pending = docs.filter((d) => d.status === "pending").length;
    const failed = docs.filter((d) => d.status === "failed").length;
    const chunkCount = docs.reduce((sum, d) => sum + (d.chunk_count ?? 0), 0);
    return { indexed, pending, failed, chunkCount };
  }, [docs]);

  const viewDoc = useCallback(
    async (doc: Doc) => {
      if (openId === doc._id) {
        setOpenId(null);
        setDetail(null);
        return;
      }
      setOpenId(doc._id);
      setDetail(null);
      setChunks([]);
      setDetailLoading(true);
      setEditingTitle(false);
      try {
        const [dRes, cRes] = await Promise.all([
          fetch(`/api/documents/${doc._id}?include_text=true`, { cache: "no-store" }),
          fetch(`/api/documents/${doc._id}/chunks`, { cache: "no-store" }),
        ]);
        const d = await dRes.json();
        const c = await cRes.json();
        if (!dRes.ok) throw new Error(d?.detail ?? "could not load document");
        setDetail(d);
        setDraftText(d.text ?? "");
        setTitleDraft(d.title ?? "");
        setChunks(Array.isArray(c) ? c : []);
      } catch (e) {
        flash(e instanceof Error ? e.message : "could not load document", "error");
      } finally {
        setDetailLoading(false);
      }
    },
    [flash, openId]
  );

  async function upload() {
    setUploading(true);
    try {
      const form = new FormData();
      if (tab === "file") {
        if (!file) throw new Error("choose a file first");
        if (file.size > 10 * 1024 * 1024) {
          throw new Error("file is larger than 10 MB");
        }
        form.append("file", file);
      } else {
        if (!text.trim()) throw new Error("paste some text first");
        const name = filename.trim() || "notes.txt";
        form.append("file", new File([text], name, { type: "text/plain" }));
      }
      form.append("doc_type", docType);
      form.append("source", tab);

      const res = await fetch("/api/documents", { method: "POST", body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(detailOf(data, `upload failed (${res.status})`));
      flash(`Queued ${data.document_id.slice(0, 8)}… — the change stream will index it.`);
      setFile(null);
      setText("");
      setFilename("notes.txt");
      await load();
    } catch (e) {
      flash(e instanceof Error ? e.message : "upload failed", "error");
    } finally {
      setUploading(false);
    }
  }

  async function remove(doc: Doc) {
    if (!window.confirm(`Delete "${doc.title}" and all of its chunks?`)) return;
    try {
      const res = await fetch(`/api/documents/${doc._id}`, { method: "DELETE" });
      const data = await res.json();
      if (!res.ok) throw new Error(detailOf(data, `delete failed (${res.status})`));
      if (openId === doc._id) {
        setOpenId(null);
        setDetail(null);
      }
      flash(`Deleted document and ${data.chunks_deleted} chunk(s).`);
      await load();
    } catch (e) {
      flash(e instanceof Error ? e.message : "delete failed", "error");
    }
  }

  async function reindex(doc: Doc) {
    try {
      const res = await fetch(`/api/documents/${doc._id}/reindex`, { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(detailOf(data, `reindex failed (${res.status})`));
      flash("Re-index queued.");
      await load();
    } catch (e) {
      flash(e instanceof Error ? e.message : "reindex failed", "error");
    }
  }

  async function saveTitle(doc: Doc) {
    const title = titleDraft.trim();
    if (!title) {
      flash("Title cannot be empty.", "error");
      return;
    }
    try {
      const res = await fetch(`/api/documents/${doc._id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(detailOf(data, `rename failed (${res.status})`));
      setDetail(data);
      setEditingTitle(false);
      flash("Title updated.");
      await load();
    } catch (e) {
      flash(e instanceof Error ? e.message : "rename failed", "error");
    }
  }

  async function saveText(doc: Doc) {
    if (!draftText.trim()) {
      flash("Text cannot be empty — use Delete if you want to remove the document.", "error");
      return;
    }
    setSaving(true);
    try {
      const res = await fetch(`/api/documents/${doc._id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: draftText }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(detailOf(data, `update failed (${res.status})`));
      setDetail(data);
      flash("Content updated — re-indexing through the change stream.");
      await load();
    } catch (e) {
      flash(e instanceof Error ? e.message : "update failed", "error");
    } finally {
      setSaving(false);
    }
  }

  async function search(e?: React.FormEvent) {
    e?.preventDefault();
    if (!query.trim() || searching) return;
    setSearching(true);
    setSearched(true);
    try {
      const res = await fetch("/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, k: 5 }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(detailOf(data, `search failed (${res.status})`));
      setResults(Array.isArray(data.chunks) ? data.chunks : []);
    } catch (e) {
      flash(e instanceof Error ? e.message : "search failed", "error");
      setResults([]);
    } finally {
      setSearching(false);
    }
  }

  const maxScore = Math.max(0.0001, ...results.map((r) => r.score || 0));

  return (
    <main className="wrap">
      <Nav />
      <div className="bread">Home / Documents</div>

      <header className="page-head">
        <div>
          <span className="eyebrow">MongoDB knowledge base</span>
          <h1>Your documents, indexed automatically.</h1>
          <p className="hint" style={{ maxWidth: 620 }}>
            Upload a file or paste text. A MongoDB change stream chunks and embeds
            it in the background — usually in under a second — then hybrid search
            can retrieve it.
          </p>
        </div>
        <Link className="btn secondary" href="/chat">
          Ask a question →
        </Link>
      </header>

      {loadError && (
        <div className="banner error">
          <b>Backend request failed:</b> {loadError}
          <div className="hint" style={{ marginTop: 4 }}>
            Check that FastAPI is running on port 8000, and that{" "}
            <code>COGITO_ADMIN_TOKEN</code> in <code>web/.env.local</code> matches{" "}
            <code>ADMIN_TOKEN</code> in the root <code>.env</code>.
          </div>
        </div>
      )}

      <div className="stats grid">
        <div className="card">
          <span className="klabel">Documents</span>
          <div className="stat">{docs.length}</div>
        </div>
        <div className="card">
          <span className="klabel">Indexed</span>
          <div className="stat good">{stats.indexed}</div>
        </div>
        <div className="card">
          <span className="klabel">Chunks</span>
          <div className="stat">{stats.chunkCount}</div>
        </div>
        <div className="card">
          <span className="klabel">Pending</span>
          <div className={`stat ${stats.pending ? "warn" : ""}`}>{stats.pending}</div>
        </div>
      </div>

      {stats.failed > 0 && (
        <div className="banner error">
          {stats.failed} document(s) failed to index. Open the document to see the error.
        </div>
      )}

      <div className="grid two-col" style={{ marginTop: 18 }}>
        <section className="card">
          <h2>Add a document</h2>
          <p className="hint">PDF, DOCX, HTML, CSV, JSON, Markdown, images, or plain text.</p>

          <div className="tabs">
            <button
              className={`tab ${tab === "file" ? "active" : ""}`}
              onClick={() => setTab("file")}
            >
              Upload file
            </button>
            <button
              className={`tab ${tab === "paste" ? "active" : ""}`}
              onClick={() => setTab("paste")}
            >
              Paste text
            </button>
          </div>

          {tab === "file" ? (
            <div
              className={`dropzone ${file ? "filled" : ""}`}
              role="button"
              tabIndex={0}
              onClick={() => fileInput.current?.click()}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  fileInput.current?.click();
                }
              }}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                const dropped = e.dataTransfer.files?.[0];
                if (dropped) setFile(dropped);
              }}
            >
              <input
                ref={fileInput}
                className="file-input"
                type="file"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                accept=".pdf,.docx,.txt,.md,.csv,.json,.html,.htm,.png,.jpg,.jpeg"
              />
              <span className="dropzone-icon">⇪</span>
              <b>{file ? file.name : "Choose a file"}</b>
              <span className="hint">
                {file
                  ? `${(file.size / 1024).toFixed(1)} KB — ready to ingest`
                  : "Click to browse or drop a file here · max 10 MB"}
              </span>
              <span className="btn secondary small" style={{ marginTop: 8 }}>
                Browse files
              </span>
            </div>
          ) : (
            <div className="grid" style={{ gap: 8 }}>
              <input
                type="text"
                value={filename}
                onChange={(e) => setFilename(e.target.value)}
                placeholder="filename.md"
              />
              <textarea
                rows={8}
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Paste the document text here…"
              />
            </div>
          )}

          <div className="row" style={{ marginTop: 12 }}>
            <select value={docType} onChange={(e) => setDocType(e.target.value)}>
              {DOC_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <button className="btn" onClick={upload} disabled={uploading}>
              {uploading ? "Queuing…" : "Ingest document"}
            </button>
          </div>
          <p className="hint" style={{ marginBottom: 0 }}>
            A change stream watches the <code>documents</code> collection; the
            worker writes chunks + embeddings, then flips the status to{" "}
            <code>indexed</code>.
          </p>
        </section>

        <section className="card">
          <h2>Search the knowledge base</h2>
          <p className="hint">
            Hybrid retrieval: keyword (<code>$search</code> / <code>$text</code>) plus
            vector search, fused with RRF.
          </p>
          <form className="row" onSubmit={search}>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search your documents…"
            />
            <button className="btn" type="submit" disabled={searching}>
              {searching ? "…" : "Search"}
            </button>
          </form>

          <div className="results">
            {searched && !searching && results.length === 0 && (
              <p className="hint">
                No matches. Ingest a document first, or try different words.
              </p>
            )}
            {results.map((r) => (
              <div className="result" key={r._id}>
                <div className="result-head">
                  <b>{r.title}</b>
                  <span className="score">{Number(r.score ?? 0).toFixed(3)}</span>
                </div>
                <p>{r.text}</p>
                <div className="scorebar">
                  <div style={{ width: `${Math.max(4, ((r.score || 0) / maxScore) * 100)}%` }} />
                </div>
                <div className="hint">
                  {r.page ? `page ${r.page} · ` : ""}document {r.document_id.slice(0, 8)}…
                </div>
              </div>
            ))}
          </div>
          {results.length > 0 && (
            <Link className="hint" href="/chat">
              Want a cited answer? Continue in chat →
            </Link>
          )}
        </section>
      </div>

      <section className="card" style={{ marginTop: 18 }}>
        <div className="row between">
          <div>
            <h2 style={{ marginBottom: 2 }}>Documents</h2>
            <span className="hint">
              {loading ? "Loading…" : `${docs.length} document(s) in MongoDB`}
            </span>
          </div>
          <button className="btn secondary small" onClick={load}>
            Refresh
          </button>
        </div>

        {docs.length === 0 && !loading ? (
          <div className="empty">
            <p>No documents yet.</p>
            <p className="hint">Upload a file or paste text above to start searching.</p>
          </div>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Document</th>
                  <th>Status</th>
                  <th>Type</th>
                  <th>Chunks</th>
                  <th>Added</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {docs.map((d) => (
                  <Fragment key={d._id}>
                    <tr className={openId === d._id ? "active" : ""}>
                      <td>
                        <button className="linklike" onClick={() => viewDoc(d)}>
                          {d.title}
                        </button>
                        <div className="hint mono">{d.path}</div>
                      </td>
                      <td>
                        <span className={`status ${d.status}`}>{d.status}</span>
                      </td>
                      <td className="hint">{d.type}</td>
                      <td>{d.chunk_count ?? 0}</td>
                      <td className="hint">{when(d.created_at)}</td>
                      <td className="actions">
                        <button className="btn secondary small" onClick={() => viewDoc(d)}>
                          {openId === d._id ? "Close" : "Open"}
                        </button>
                        <button className="btn secondary small" onClick={() => reindex(d)}>
                          Reindex
                        </button>
                        <button className="btn danger small" onClick={() => remove(d)}>
                          Delete
                        </button>
                      </td>
                    </tr>

                    {openId === d._id && (
                      <tr className="detail-row">
                        <td colSpan={6}>
                          {detailLoading ? (
                            <p className="hint">Loading document…</p>
                          ) : detail ? (
                            <div className="detail">
                              <div className="row between">
                                <div>
                                  {editingTitle ? (
                                    <div className="row">
                                      <input
                                        type="text"
                                        value={titleDraft}
                                        onChange={(e) => setTitleDraft(e.target.value)}
                                      />
                                      <button
                                        className="btn small"
                                        onClick={() => saveTitle(d)}
                                      >
                                        Save
                                      </button>
                                      <button
                                        className="btn secondary small"
                                        onClick={() => setEditingTitle(false)}
                                      >
                                        Cancel
                                      </button>
                                    </div>
                                  ) : (
                                    <h3 style={{ margin: 0 }}>{detail.title}</h3>
                                  )}
                                  <div className="hint">
                                    {detail.mime ?? detail.type}
                                    {detail.indexed_at
                                      ? ` · indexed ${when(detail.indexed_at)}`
                                      : ""}
                                  </div>
                                </div>
                                <button
                                  className="btn secondary small"
                                  onClick={() => {
                                    setEditingTitle(true);
                                    setTitleDraft(detail.title);
                                  }}
                                >
                                  Rename
                                </button>
                              </div>

                              {detail.summary && (
                                <p>
                                  <b>Summary.</b> {detail.summary}
                                </p>
                              )}
                              {detail.keywords?.length ? (
                                <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
                                  {detail.keywords.map((k) => (
                                    <span className="badge" key={k}>
                                      {k}
                                    </span>
                                  ))}
                                </div>
                              ) : null}

                              {detail.error && (
                                <p className="error">Index error: {detail.error}</p>
                              )}

                              <div>
                                <span className="klabel">Content</span>
                                {detail.editable ? (
                                  <>
                                    <textarea
                                      rows={8}
                                      value={draftText}
                                      onChange={(e) => setDraftText(e.target.value)}
                                    />
                                    <div className="row" style={{ marginTop: 8 }}>
                                      <button
                                        className="btn small"
                                        onClick={() => saveText(d)}
                                        disabled={saving || draftText === (detail.text ?? "")}
                                      >
                                        {saving ? "Saving…" : "Save content"}
                                      </button>
                                      <span className="hint">
                                        Saving marks the document pending; the worker
                                        re-chunks and re-embeds it.
                                      </span>
                                    </div>
                                  </>
                                ) : (
                                  <p className="hint">
                                    Binary document — content is not editable, but you
                                    can rename or reindex it.
                                  </p>
                                )}
                              </div>

                              <div>
                                <span className="klabel">
                                  Chunks ({chunks.length}) — stored in the{" "}
                                  <code>chunks</code> collection
                                </span>
                                <div className="chunk-list">
                                  {chunks.length === 0 && (
                                    <p className="hint">
                                      No chunks yet — the change stream may still be
                                      processing.
                                    </p>
                                  )}
                                  {chunks.map((c) => (
                                    <div className="chunk" key={c._id}>
                                      <div className="chunk-meta">
                                        #{c.order + 1}
                                        {c.page ? ` · page ${c.page}` : ""}
                                        {c.token_count ? ` · ${c.token_count} tokens` : ""}
                                        {c.boost ? ` · boost ${c.boost}` : ""}
                                      </div>
                                      <p>{c.text}</p>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            </div>
                          ) : (
                            <p className="hint">Could not load this document.</p>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {notice && <div className={`toast ${notice.kind}`}>{notice.text}</div>}
    </main>
  );
}
