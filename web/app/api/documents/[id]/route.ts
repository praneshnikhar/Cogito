import { NextResponse } from "next/server";

import { BACKEND_URL } from "@/lib/backend";
import { adminFetch, readJson } from "@/lib/server";

type Ctx = { params: Promise<{ id: string }> };

export async function GET(req: Request, ctx: Ctx) {
  const { id } = await ctx.params;
  const include = new URL(req.url).searchParams.get("include_text") ?? "false";
  try {
    const res = await fetch(
      `${BACKEND_URL}/ingest/documents/${encodeURIComponent(id)}?include_text=${include}`,
      { cache: "no-store" }
    );
    return NextResponse.json(await readJson(res), { status: res.status });
  } catch {
    return NextResponse.json({ detail: "backend unreachable" }, { status: 502 });
  }
}

export async function PATCH(req: Request, ctx: Ctx) {
  const { id } = await ctx.params;
  try {
    const body = await req.text();
    const res = await adminFetch(`/ingest/documents/${encodeURIComponent(id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body,
    });
    return NextResponse.json(await readJson(res), { status: res.status });
  } catch {
    return NextResponse.json({ detail: "backend unreachable" }, { status: 502 });
  }
}

export async function DELETE(_req: Request, ctx: Ctx) {
  const { id } = await ctx.params;
  try {
    const res = await adminFetch(`/ingest/documents/${encodeURIComponent(id)}`, {
      method: "DELETE",
    });
    return NextResponse.json(await readJson(res), { status: res.status });
  } catch {
    return NextResponse.json({ detail: "backend unreachable" }, { status: 502 });
  }
}
