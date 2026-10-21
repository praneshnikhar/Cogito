"use client";

import { useState } from "react";
import Link from "next/link";

import { Nav } from "@/components/nav";
import { backend } from "@/lib/backend";

type Msg = { role: "user" | "assistant"; content: string; citations?: any[] };

export default function Chat() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<"basic" | "agent" | "multi">("basic");

  const ask = async () => {
    const question = input.trim();
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

  return (
    <main className="wrap">
      <Nav />
      <div className="bread">
        Home / Chat ·{" "}
        <select value={mode} onChange={(e) => setMode(e.target.value as any)}>
          <option value="basic">single-pass (Tier 1)</option>
          <option value="agent">agent loop (LangGraph)</option>
          <option value="multi">multi-query (expanded)</option>
        </select>
      </div>

      <div className="grid" style={{ gap: 10, minHeight: "52vh" }}>
        {messages.length === 0 && (
          <div className="card" style={{ margin: "8px 0" }}>
            <h2 style={{ marginTop: 0 }}>Ask your documents</h2>
            <p className="hint">
              The knowledge base is empty. Add documents in{" "}
              <Link href="/documents">Documents</Link>, then ask a question here.
              Answers will cite the passages they use.
            </p>
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