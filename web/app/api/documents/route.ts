import { NextResponse } from "next/server";

import { BACKEND_URL } from "@/lib/backend";
import { adminFetch, readJson } from "@/lib/server";

export async function GET() {
  try {
    const res = await fetch(`${BACKEND_URL}/ingest/documents`, { cache: "no-store" });
    return NextResponse.json(await readJson(res), { status: res.status });
  } catch {
    return NextResponse.json({ detail: "backend unreachable" }, { status: 502 });
  }
}

export async function POST(req: Request) {
  try {
    const form = await req.formData();
    const res = await adminFetch("/ingest", { method: "POST", body: form });
    return NextResponse.json(await readJson(res), { status: res.status });
  } catch {
    return NextResponse.json({ detail: "backend unreachable" }, { status: 502 });
  }
}
