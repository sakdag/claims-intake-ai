import { authConfigured, type Session } from "./auth";

export const API_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://127.0.0.1:8000";

export async function apiFetch(
  path: string,
  session: Session | null,
  init?: RequestInit,
): Promise<Response> {
  const headers = new Headers(init?.headers);
  if (!headers.has("Content-Type") && init?.body) {
    headers.set("Content-Type", "application/json");
  }
  if (session?.idToken && authConfigured()) {
    headers.set("Authorization", `Bearer ${session.idToken}`);
  }
  return fetch(`${API_BASE}${path}`, { ...init, headers });
}
