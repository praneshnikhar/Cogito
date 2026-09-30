import { NextResponse } from "next/server";
import { BACKEND_URL } from "@/lib/backend";

const PROXY = [
  "overview",
  "queries",
  "eval",
  "freshness",
  "unanswered",
] as const;

export async function GET() {
  const out: Record<string, unknown> = {};
  await Promise.all(
    PROXY.map(async (key) => {
      try {
        const res = await fetch(`${BACKEND_URL}/analytics/${key}`, { cache: "no-store" });
        out[key] = res.ok ? await res.json() : [];
      } catch {
        out[key] = [];
      }
    })
  );
  try {
    const cap = await fetch(`${BACKEND_URL}/capabilities`, { cache: "no-store" });
    out["capabilities"] = cap.ok ? await cap.json() : null;
  } catch {
    out["capabilities"] = null;
  }
  return NextResponse.json(out);
}