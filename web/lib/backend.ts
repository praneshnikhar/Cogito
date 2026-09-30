export const BACKEND_URL =
  process.env.NEXT_PUBLIC_COGITO_API ?? "http://localhost:8000";

export async function backend(path: string, init?: RequestInit) {
  const res = await fetch(`${BACKEND_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json();
}