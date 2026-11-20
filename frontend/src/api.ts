// Thin fetch wrapper. Auth is Django's session cookie; the browser sends it
// automatically because /api is same-origin (via the Vite proxy).
//
// The client never sends an org. The server takes it from the logged-in user.

import type { AskResult, ExceptionItem, LocationOption, Me, ReasonOption } from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

function getCookie(name: string): string | undefined {
  return document.cookie
    .split("; ")
    .find((c) => c.startsWith(name + "="))
    ?.split("=")[1];
}

async function request<T>(method: "GET" | "POST", path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (method === "POST") {
    headers["Content-Type"] = "application/json";
    // Read fresh each time: Django rotates the CSRF token on login.
    const token = getCookie("csrftoken");
    if (token) headers["X-CSRFToken"] = token;
  }

  const resp = await fetch(path, {
    method,
    headers,
    credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (resp.status === 204) return undefined as T;
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new ApiError(resp.status, typeof data.detail === "string" ? data.detail : `Request failed (${resp.status})`);
  }
  return data as T;
}

export const api = {
  /** Returns null when not logged in. Also sets the csrftoken cookie. */
  async me(): Promise<Me | null> {
    try {
      return await request<Me>("GET", "/api/me");
    } catch (e) {
      if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return null;
      throw e;
    }
  },
  login: (username: string, password: string) => request<Me>("POST", "/api/login", { username, password }),
  logout: () => request<void>("POST", "/api/logout"),
  /** Body is the question only. A refusal is a normal 200 response. */
  ask: (question: string) => request<AskResult>("POST", "/api/ask", { question }),
  reasons: () => request<ReasonOption[]>("GET", "/api/reasons"),
  locations: () => request<LocationOption[]>("GET", "/api/locations"),
  exceptions(filters: { reason: string; location: string }) {
    // Filtering happens on the server; empty values mean "all".
    const qs = new URLSearchParams();
    if (filters.reason) qs.set("reason", filters.reason);
    if (filters.location) qs.set("location", filters.location);
    const suffix = qs.toString() ? `?${qs}` : "";
    return request<ExceptionItem[]>("GET", `/api/exceptions${suffix}`);
  },
};
