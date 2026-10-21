import { NextResponse } from "next/server";

import { BACKEND_URL } from "@/lib/backend";
import { readJson } from "@/lib/server";

export async function POST(req: Request) {
  try {
    const body = await req.json().catch(() => ({}));
    const query = String(body.query ?? "").trim();
    const k = Math.max(1, Math.min(Number(body.k) || 5, 20));
    if (!query) {
      return NextResponse.json({ detail: "query is required" }, { status: 400 });
    }
    const params = new URLSearchParams({ query, k: String(k) });
    const res = await fetch(`${BACKEND_URL}/search?${params}`, {
      method: "POST",
      cache: "no-store",
    });
    return NextResponse.json(await readJson(res), { status: res.status });
  } catch {
    return NextResponse.json({ detail: "backend unreachable" }, { status: 502 });
  }
}
