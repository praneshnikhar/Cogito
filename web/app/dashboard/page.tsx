"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
  CartesianGrid,
} from "recharts";

type Data = {
  overview?: any;
  queries?: any[];
  eval?: any;
  freshness?: any[];
  unanswered?: any[];
  capabilities?: any;
};

export default function Dashboard() {
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/analytics")
      .then((r) => r.json())
      .then(setData)
      .catch(() => setError("Could not reach the analytics proxy."));
  }, []);

  const o = data?.overview;
  const stats = o
    ? [
        ["Total queries", o.total_queries],
        ["Today", o.queries_today],
        ["Unanswered", o.unanswered],
        ["Avg latency (ms)", o.avg_latency_ms],
        ["Documents", o.documents],
        ["Chunks", o.chunks],
        ["Memories", o.memories],
        ["Ratings", o.rated_answers],
      ]
    : [];

  const qData = (data?.queries ?? []).map((q, i) => ({
    name: (q.question || "?").slice(0, 22) + (q.question?.length > 22 ? "…" : ""),
    count: q.count,
    full: q.question,
    fill: i % 2 ? "#7c5cff" : "#4f8cff",
  }));

  const dayData = ((o?.queries_by_day) ?? []).map((d: any) => ({
    name: d._id ?? "?",
    count: d.count,
  }));

  return (
    <main className="wrap">
      <nav className="nav">
        <span className="brand">∎ Cogito</span>
        <Link href="/">Home</Link>
        <Link href="/chat">Chat</Link>
      </nav>
      <div className="bread">Home / Analytics</div>

      {error && <div className="card hint">{error}</div>}

      <h2>Knowledge engine overview</h2>
      <div className="grid" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
        {stats.map(([k, v]) => (
          <div key={k as string} className="card">
            <span className="klabel">{k}</span>
            <div className="stat">{v ?? "…"}</div>
          </div>
        ))}
      </div>

      <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", marginTop: 18 }}>
        <div className="card">
          <h3>Top questions</h3>
          {qData.length ? (
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={qData} layout="horizontal" margin={{ left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2a3554" />
                <XAxis dataKey="name" stroke="#93a0bf" tick={{ fontSize: 11 }} />
                <YAxis stroke="#93a0bf" allowDecimals={false} />
                <Tooltip
                  cursor={{ fill: "rgba(255,255,255,0.05)" }}
                  contentStyle={{ background: "#131a2e", border: "1px solid #2a3554", borderRadius: 8 }}
                  formatter={(v, n, item: any) => [v, item.payload.full || n]}
                />
                <Bar dataKey="count" radius={[6, 6, 0, 0]}>
                  {qData.map((e, i) => (
                    <Cell key={i} fill={e.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="hint">No queries yet.</p>
          )}
        </div>

        <div className="grid" style={{ gap: 12 }}>
          <div className="card">
            <h3>Answer quality (LLM judge)</h3>
            {data?.eval ? (
              <p>
                Faithfulness <b>{data.eval.avg_faithfulness}</b> · Relevance{" "}
                <b>{data.eval.avg_relevance}</b> · {data.eval.samples} answers scored
              </p>
            ) : (
              <p className="hint">No evaluations yet.</p>
            )}
          </div>
          <div className="card">
            <h3>Ingestion freshness (latency s)</h3>
            {(data?.freshness ?? []).map((f, i) => (
              <div key={i} className="hint">
                {f.title}: <b>{f.delta_s}s</b>
              </div>
            ))}
            {!data?.freshness?.length && <p className="hint">No documents yet.</p>}
          </div>
        </div>
      </div>

      <div className="card" style={{ marginTop: 18 }}>
        <h3>Query volume over time ($dateToString + $group)</h3>
        {dayData.length ? (
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={dayData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a3554" />
              <XAxis dataKey="name" stroke="#93a0bf" tick={{ fontSize: 11 }} />
              <YAxis stroke="#93a0bf" allowDecimals={false} />
              <Tooltip
                cursor={{ fill: "rgba(255,255,255,0.05)" }}
                contentStyle={{ background: "#131a2e", border: "1px solid #2a3554", borderRadius: 8 }}
              />
              <Bar dataKey="count" fill="#4f8cff" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <p className="hint">No query activity yet.</p>
        )}
      </div>
    </main>
  );
}