import Link from "next/link";

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
      <nav className="nav">
        <span className="brand">∎ Cogito</span>
        <Link href="/chat">Chat</Link>
        <Link href="/dashboard">Dashboard</Link>
        <a href="http://localhost:8000/docs" target="_blank" rel="noreferrer">
          API Docs
        </a>
      </nav>

      <h1 style={{ fontSize: 40, marginBottom: 4 }}>
        A knowledge base that <em>reasons</em>.
      </h1>
      <p style={{ color: "var(--muted)", maxWidth: 680 }}>
        Cogito is a MongoDB-native, MCP-powered RAG assistant. Drop documents in,
        a change stream chunks + embeds + indexes them automatically, and ask
        questions — answered with grounded, cited evidence fused from keyword
        and semantic search.
      </p>

      <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", margin: "24px 0" }}>
        <div className="card">
          <h2>Talk to your knowledge</h2>
          <p className="hint">
            Ask about the indexed contracts, policies, and notices.
          </p>
          <Link className="btn" href="/chat">Open chat</Link>
        </div>
        <div className="card">
          <h2>Live analytics</h2>
          <p className="hint">
            Query volume, unanswered questions, eval scores, freshness.
          </p>
          <Link className="btn secondary" href="/dashboard">Dashboard</Link>
        </div>
      </div>

      <span className="klabel">Runtime capabilities</span>
      <div className="row" style={{ flexWrap: "wrap", gap: 8, marginTop: 8 }}>
        {features.length
          ? features.map(([name, on]) => (
              <span key={name} className={`badge ${on ? "on" : ""}`}>
                {on ? "● " : "○ "} {name}
              </span>
            ))
          : <span className="badge">backend offline — run docker compose up</span>}
      </div>
    </main>
  );
}