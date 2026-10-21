import "server-only";

import { BACKEND_URL } from "@/lib/backend";

export const ADMIN_TOKEN = process.env.COGITO_ADMIN_TOKEN ?? "change-me";

export async function adminFetch(path: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers);
  headers.set("X-Admin-Token", ADMIN_TOKEN);
  return fetch(`${BACKEND_URL}${path}`, { ...init, headers, cache: "no-store" });
}

export async function readJson(res: Response) {
  const text = await res.text();
  try {
    return text ? JSON.parse(text) : null;
  } catch {
    return { detail: text };
  }
}
