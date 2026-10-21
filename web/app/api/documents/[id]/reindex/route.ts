import { NextResponse } from "next/server";

import { adminFetch, readJson } from "@/lib/server";

type Ctx = { params: Promise<{ id: string }> };

export async function POST(_req: Request, ctx: Ctx) {
  const { id } = await ctx.params;
  try {
    const res = await adminFetch(`/ingest/documents/${encodeURIComponent(id)}/reindex`, {
      method: "POST",
    });
    return NextResponse.json(await readJson(res), { status: res.status });
  } catch {
    return NextResponse.json({ detail: "backend unreachable" }, { status: 502 });
  }
}
