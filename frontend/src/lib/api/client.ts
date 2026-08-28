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

  /**
   * The entitlement reason, when the API refused for that reason.
   *
   * `EntitlementDenied` carries `reason` and `cta` as RFC 9457 extension
   * members (ADR-004), so a player can say "your subscription lapsed" rather
   * than "403". Read defensively: a 403 from anywhere else has neither.
   */
  get entitlementReason(): string | null {
    const problem: ProblemDetails & { reason?: unknown } = this.problem;
    if (problem.type !== PROBLEM_ENTITLEMENT_DENIED) return null;
    return typeof problem.reason === "string" ? problem.reason : null;
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

/**
 * The header Django reads, generates when absent, and echoes back.
 *
 * architecture.md section 3.7: the id is propagated from Next.js to Django to
 * Celery, and "without this, debugging is archaeology". Django's half has
 * existed since M0; this is the hop that was missing, so until now a browser
 * action and the request it caused could not be joined up in a log query.
 */
const REQUEST_ID_HEADER = "X-Request-ID";

/**
 * One id per request, generated in the browser.
 *
 * `crypto.randomUUID` is available in every browser this app supports and in
 * Workers, but not over plain HTTP on a non-localhost origin — where the whole
 * `crypto` object is absent. The fallback is deliberately not a weaker UUID:
 * it is a clearly-marked value that says where it came from, because a
 * plausible-looking id that is not actually unique is worse for debugging than
 * an obviously improvised one.
 *
 * Django validates whatever arrives against a narrow character class and mints
 * its own if it does not match, so nothing here can inject into a log line.
 * That is the server's job and it already does it; this is not relying on it,
 * it is not duplicating it.
 */
function newRequestId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `web-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

async function request<T>(
  path: string,
  init: RequestInit & { json?: unknown } = {},
): Promise<T> {
  const { json, ...rest } = init;
  const method = rest.method ?? (json ? "POST" : "GET");
  const headers = new Headers(rest.headers);

  // Set rather than appended, and never overwritten if a caller supplied one:
  // a caller that already has an id is continuing a trace, not starting one.
  if (!headers.has(REQUEST_ID_HEADER)) {
    headers.set(REQUEST_ID_HEADER, newRequestId());
  }

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

/**
 * The learning surface, all generated (invariant 16).
 *
 * Hand-written request or response types would be a bug: they drift the first
 * time the API changes, and the drift shows up as a runtime shape mismatch
 * rather than a build failure.
 */
export type GatedLesson = components["schemas"]["GatedLesson"];
export type LessonProgress = components["schemas"]["LessonProgress"];
export type LessonTranscript = components["schemas"]["LessonTranscript"];
export type TranscriptSegment = components["schemas"]["LearnerSegment"];
export type PlaybackToken = components["schemas"]["PlaybackToken"];
export type Enrollment = components["schemas"]["Enrollment"];

/** Problem type the player branches on, to tell "pay" from "went wrong". */
export const PROBLEM_ENTITLEMENT_DENIED = "/problems/entitlement-denied";

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

  lesson: (lessonId: string) => request<GatedLesson>(`/lessons/${lessonId}/`),

  /**
   * The same lesson, addressed the way architecture.md §6.2 says it is.
   *
   * `courses/{slug}/lessons/{lesson_slug}/` was specified at M0 and built at
   * M16 T3; `Lesson` has carried a redundant `course` foreign key and a
   * `lesson_slug_unique_per_course` constraint since M3 to make it resolve to
   * one row (ADR-007 §1).
   *
   * Both slugs are encoded. They come from the API today, so this is not a
   * live injection — it is the assumption that would stop holding the moment a
   * slug came from a URL a person typed, which on this route is exactly where
   * they come from.
   */
  lessonBySlug: (courseSlug: string, lessonSlug: string) =>
    request<GatedLesson>(
      `/courses/${encodeURIComponent(courseSlug)}/lessons/${encodeURIComponent(lessonSlug)}/`,
    ),

  /**
   * Where this learner got to, or `null` if they have never started.
   *
   * The 204 becomes `null` here rather than in each caller: `request` returns
   * `undefined` for an empty body, and a player asking "have I been here
   * before" wants an answer, not a missing value to guard against twice.
   */
  lessonProgress: async (lessonId: string): Promise<LessonProgress | null> =>
    (await request<LessonProgress | undefined>(`/lessons/${lessonId}/progress/`)) ?? null,

  recordProgress: (lessonId: string, positionSeconds: number, watchedDeltaSeconds: number) =>
    request<LessonProgress>(`/lessons/${lessonId}/progress/`, {
      method: "PUT",
      json: {
        position_seconds: Math.max(0, Math.round(positionSeconds)),
        watched_delta_seconds: Math.max(0, Math.round(watchedDeltaSeconds)),
      },
    }),

  markLessonComplete: (lessonId: string) =>
    request<LessonProgress>(`/lessons/${lessonId}/complete/`, { json: {} }),

  playbackToken: (lessonId: string) =>
    request<PlaybackToken>(`/lessons/${lessonId}/playback-token/`, { json: {} }),

  lessonTranscript: (lessonId: string) =>
    request<LessonTranscript>(`/lessons/${lessonId}/transcript/`),

  myCourses: () =>
    request<{ results: Enrollment[] }>("/me/courses/"),
};

/**
 * Report a final heartbeat while the page is going away.
 *
 * An ordinary `fetch` is cancelled when the document unloads, so the stretch
 * between the last beat and closing the tab is exactly what gets lost.
 * `keepalive` asks the browser to deliver the request anyway.
 *
 * Not `navigator.sendBeacon`, which is the usual answer here: it cannot set
 * `X-CSRFToken`, and Django would reject the write. `keepalive` survives
 * unload *and* carries headers.
 *
 * Skipped entirely when no CSRF cookie exists, because the request would be
 * refused and there is no session to report progress for anyway.
 */
export function beaconProgress(
  lessonId: string,
  positionSeconds: number,
  watchedDeltaSeconds: number,
): void {
  const csrf = readCookie("csrftoken");
  if (!csrf) return;

  void fetch(`/api/v1/lessons/${lessonId}/progress/`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
    credentials: "same-origin",
    keepalive: true,
    body: JSON.stringify({
      position_seconds: Math.max(0, Math.round(positionSeconds)),
      watched_delta_seconds: Math.max(0, Math.round(watchedDeltaSeconds)),
    }),
  }).catch(() => {
    // Best effort by definition: the page is going away and there is nobody
    // left to tell. Swallowing this is the difference between losing the last
    // fifteen seconds and an unhandled rejection in the console on every exit.
  });
}
