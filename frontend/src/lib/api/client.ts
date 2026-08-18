/**
 * The API client.
 *
 * Requests go to `/api/v1/...` on this origin and the Next rewrite carries
 * them to Django (ADR-005 §2.1 — no BFF layer). Same-origin is what keeps the
 * session cookie simple: the browser sends it without any CORS negotiation,
 * and nothing auth-related is ever readable by JavaScript (invariant 9).
 */

import type { components } from "@/types/api";

/**
 * RFC 9457 Problem Details — the one error shape the API returns
 * (architecture.md §6.1). One type here means one error component in the UI.
 */
export interface ProblemDetails {
  type: string;
  title: string;
  status: number;
  detail: string;
  errors: Record<string, string[]> | null;
}

/** Problem type URIs the UI branches on (ADR-004). */
export const PROBLEM_NOT_AUTHENTICATED = "/problems/not-authenticated";

export class ApiError extends Error {
  constructor(readonly problem: ProblemDetails) {
    super(problem.detail);
    this.name = "ApiError";
  }

  /**
   * Django answers 403 for both "not signed in" and "not allowed", because
   * SessionAuthentication offers no WWW-Authenticate header. The status alone
   * cannot tell them apart — the problem type can (ADR-004).
   */
  get isNotAuthenticated(): boolean {
    return this.problem.type === PROBLEM_NOT_AUTHENTICATED;
  }

  /** Field errors for a form, or an empty object. */
  get fieldErrors(): Record<string, string[]> {
    return this.problem.errors ?? {};
  }
}

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(^| )${name}=([^;]+)`));
  return match ? decodeURIComponent(match[2]) : null;
}

/**
 * Ensure a CSRF token exists before the first unsafe request.
 *
 * Django only sets the cookie when a view asks for it, so a fresh visitor has
 * none. Login is deliberately not CSRF-exempt — forcing someone's browser to
 * sign in as an attacker is a real attack — so this has to happen first.
 */
async function ensureCsrfToken(): Promise<string> {
  const existing = readCookie("csrftoken");
  if (existing) return existing;

  await fetch("/api/v1/auth/csrf/", { credentials: "same-origin" });
  return readCookie("csrftoken") ?? "";
}

async function toProblem(response: Response): Promise<ProblemDetails> {
  try {
    return (await response.json()) as ProblemDetails;
  } catch {
    // A gateway timeout or a proxy error is never JSON. The UI still needs
    // something with the right shape rather than a thrown parse error.
    return {
      type: "about:blank",
      title: response.statusText || "Request failed",
      status: response.status,
      detail: "Something went wrong. Please try again.",
      errors: null,
    };
  }
}

async function request<T>(
  path: string,
  init: RequestInit & { json?: unknown } = {},
): Promise<T> {
  const { json, ...rest } = init;
  const method = rest.method ?? (json ? "POST" : "GET");
  const headers = new Headers(rest.headers);

  if (json !== undefined) headers.set("Content-Type", "application/json");
  if (method !== "GET" && method !== "HEAD") {
    headers.set("X-CSRFToken", await ensureCsrfToken());
  }

  const response = await fetch(`/api/v1${path}`, {
    ...rest,
    method,
    headers,
    // The whole point of same-origin: the session cookie rides along and
    // never touches JavaScript.
    credentials: "same-origin",
    body: json === undefined ? rest.body : JSON.stringify(json),
  });

  if (!response.ok) throw new ApiError(await toProblem(response));
  if (response.status === 204) return undefined as T;

  return (await response.json()) as T;
}

/** The signed-in user, generated from the OpenAPI schema (invariant 16). */
export type Me = components["schemas"]["Me"];

export const api = {
  me: () => request<Me>("/auth/me/"),

  login: (email: string, password: string) =>
    request<{ detail: string }>("/auth/login/", { json: { email, password } }),

  logout: () => request<{ detail: string }>("/auth/logout/", { json: {} }),

  register: (email: string, password: string) =>
    request<{ detail: string }>("/auth/register/", { json: { email, password } }),

  requestPasswordReset: (email: string) =>
    request<{ detail: string }>("/auth/password/reset/", { json: { email } }),

  confirmPasswordReset: (token: string, newPassword: string) =>
    request<{ detail: string }>("/auth/password/reset/confirm/", {
      json: { token, new_password: newPassword },
    }),

  verifyEmail: (token: string) =>
    request<{ detail: string }>("/auth/verify-email/", { json: { token } }),
};
