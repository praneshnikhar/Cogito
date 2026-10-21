import Link from "next/link";

import { Nav } from "@/components/nav";

async function capabilities() {
  try {
    const { BACKEND_URL } = await import("@/lib/backend");
    const res = await fetch(`${BACKEND_URL}/capabilities`, { cache: "no-store" });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export default async function Home() {
  const caps = await capabilities();
  const features = caps
    ? [
        ["Hybrid Search", caps.hybrid_search],
        ["PostHog", caps.posthog],
        ["Sentry", caps.sentry],
        ["Upstash", caps.upstash],
        ["Pinecone", caps.pinecone],
        ["Supabase/Postgres", caps.supabase],
        ["n8n automation", caps.n8n],
        ["LLM judge eval", caps.evaluation],
        [`LLM (${caps.llm_provider})`, true],
        [`Embeddings (${caps.embedding_provider})`, true],
      ]
    : [];

  return (
    <main className="wrap">
      <Nav />

      <header className="page-head" style={{ marginTop: 26 }}>
        <div>
          <span className="eyebrow">MongoDB · FastAPI · Next.js · MCP</span>
          <h1 style={{ fontSize: 44, marginBottom: 8 }}>
            A knowledge base that <em>reasons</em>.
          </h1>
          <p style={{ color: "var(--muted)", maxWidth: 680 }}>
            Cogito is a MongoDB-native, MCP-powered RAG assistant. Add documents,
            a change stream chunks + embeds + indexes them automatically, and ask
            questions — answered with grounded, cited evidence fused from keyword
            and semantic search.
          </p>
        </div>
      </header>

      <div className="grid three" style={{ margin: "24px 0" }}>
        <div className="card">
          <span className="eyebrow">Start here</span>
          <h2>Add your documents</h2>
          <p className="hint">
            Upload a PDF or paste text. Watch it move from <code>pending</code> to{" "}
            <code>indexed</code>, then search it.
          </p>
          <Link className="btn" href="/documents">
            Open documents
          </Link>
        </div>
        <div className="card">
          <h2>Talk to your knowledge</h2>
          <p className="hint">
            Ask questions about the documents you add. Answers cite
            the passages they used.
          </p>
          <Link className="btn secondary" href="/chat">
            Open chat
          </Link>
        </div>
        <div className="card">
          <h2>Live analytics</h2>
          <p className="hint">
            Query volume, unanswered questions, eval scores, and ingestion
            freshness — all aggregation pipelines.
          </p>
          <Link className="btn secondary" href="/dashboard">
            Dashboard
          </Link>
        </div>
      </div>

      <span className="klabel">Runtime capabilities</span>
      <div className="row" style={{ flexWrap: "wrap", gap: 8, marginTop: 8 }}>
        {features.length ? (
          features.map(([name, on]) => (
            <span key={name} className={`badge ${on ? "on" : ""}`}>
              {on ? "● " : "○ "} {name}
            </span>
          ))
        ) : (
          <span className="badge">backend offline — run docker compose up</span>
        )}
      </div>
    </main>
  );
}
