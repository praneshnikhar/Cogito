import { NextResponse } from "next/server";

import { BACKEND_URL } from "@/lib/backend";
import { readJson } from "@/lib/server";

type Ctx = { params: Promise<{ id: string }> };

export async function GET(_req: Request, ctx: Ctx) {
  const { id } = await ctx.params;
  try {
    const res = await fetch(
      `${BACKEND_URL}/ingest/documents/${encodeURIComponent(id)}/chunks`,
      { cache: "no-store" }
    );
    return NextResponse.json(await readJson(res), { status: res.status });
  } catch {
    return NextResponse.json({ detail: "backend unreachable" }, { status: 502 });
  }
}
