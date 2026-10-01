"use client";

import { useState } from "react";
import Link from "next/link";
import { backend } from "@/lib/backend";

type Msg = { role: "user" | "assistant"; content: string; citations?: any[]; answer_id?: string };

const SUGGESTIONS = [
  "What are our penalty clauses for late delivery?",
  "How much annual leave do employees get?",
  "What is our net-zero emissions target for 2030?",
  "How long do we retain user data?",
];

export default function Chat() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<"basic" | "agent" | "multi">("basic");

  const ask = async (q?: string) => {
    const question = (q ?? input).trim();
    if (!question || loading) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: question }]);
    setLoading(true);
    try {
      const path = mode === "agent" ? "/ask/agent" : mode === "multi" ? "/ask/multi" : "/ask";
      const body = mode === "agent" ? { question } : { question, k: 6 };
      const data = await backend(path, { method: "POST", body: JSON.stringify(body) });
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: data.answer,
          citations: data.citations ?? [],
          answer_id: data.answer_id,
        },
      ]);
    } catch (e: any) {
      setMessages((m) => [
        ...m,
        { role: "assistant", content: `Error: ${e.message} (is the backend up?)` },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const rate = async (ansId: string | undefined, rating: number) => {
    if (!ansId) return;
    try {
      await backend("/feedback", {
        method: "POST",
        body: JSON.stringify({ answer_id: ansId, rating }),
      });
    } catch {}
  };

  return (
    <main className="wrap">
      <nav className="nav">
        <span className="brand">∎ Cogito</span>
        <Link href="/">Home</Link>
        <Link href="/dashboard">Dashboard</Link>
      </nav>
      <div className="bread">Home / Chat ·{" "}
        <select value={mode} onChange={(e) => setMode(e.target.value as any)}>
          <option value="basic">single-pass (Tier 1)</option>
          <option value="agent">agent loop (LangGraph)</option>
          <option value="multi">multi-query (expanded)</option>
        </select>
      </div>

      <div className="grid" style={{ gap: 10, minHeight: "52vh" }}>
        {messages.length === 0 && (
          <div style={{ margin: "8px 0" }}>
            <span className="klabel">Try one of these</span>
            <div className="row" style={{ flexWrap: "wrap" }}>
              {SUGGESTIONS.map((s) => (
                <button key={s} className="btn secondary" onClick={() => ask(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className="card" style={{ alignSelf: m.role === "user" ? "flex-end" : "stretch", maxWidth: m.role === "user" ? "80%" : "100%", background: m.role === "user" ? "var(--panel-2)" : "var(--panel)" }}>
            <span className="klabel">{m.role}</span>
            <p style={{ margin: "6px 0" }}>{m.content}</p>
            {m.citations?.map((c, ci) => (
              <div key={ci} className="cite">
                <b>{c.title}</b> · score {c.score}
                <div>{c.excerpt}</div>
              </div>
            ))}
            {m.answer_id && (
              <div className="row" style={{ marginTop: 8 }}>
                <button className="btn secondary" onClick={() => rate(m.answer_id, 1)}>👍</button>
                <button className="btn secondary" onClick={() => rate(m.answer_id, -1)}>👎</button>
              </div>
            )}
          </div>
        ))}
        {loading && <div className="hint">thinking…</div>}
      </div>

      <div className="row">
        <input
          type="text"
          placeholder="Ask about your knowledge base…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && ask()}
        />
        <button className="btn" onClick={() => ask()} disabled={loading}>
          Send
        </button>
      </div>
    </main>
  );
}