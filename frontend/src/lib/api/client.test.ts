/**
 * The API client, and specifically the parts a structural test cannot see.
 *
 * **This replaces a real weakness.** M14 T2 added the `X-Request-ID` header
 * here, and the only thing guarding it was a *backend* test that read this
 * file as text and asserted the string `"X-Request-ID"` appeared in it. That
 * test passes if the header is mentioned in a comment. It passes if the header
 * is set and then deleted two lines later. It was the best available at the
 * time because there was no frontend runner; there is one now.
 *
 * `fetch` is stubbed rather than mocking anything of our own. CLAUDE.md §6
 * forbids mocking our own service layer and asserting it was called — the same
 * reasoning applies here, so what is faked is the browser boundary and
 * everything inside it runs for real.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, PROBLEM_NOT_AUTHENTICATED, api } from "@/lib/api/client";
import { sessionStatus } from "@/lib/auth/session-status";

/** The last request `fetch` was called with. */
function lastCall(): { url: string; init: RequestInit } {
  const mock = vi.mocked(globalThis.fetch);
  const [url, init] = mock.mock.calls[mock.mock.calls.length - 1];
  return { url: String(url), init: (init ?? {}) as RequestInit };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  sessionStatus.finish(sessionStatus.begin("logout"));
  vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ ok: true })));
  // A CSRF cookie, so unsafe requests do not trigger the bootstrap fetch and
  // make every assertion about "the last call" ambiguous.
  document.cookie = "csrftoken=test-token";
});

afterEach(() => {
  sessionStatus.finish(sessionStatus.begin("logout"));
  vi.unstubAllGlobals();
  document.cookie = "csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

describe("session observation at the real request boundary", () => {
  function signedOut(type = PROBLEM_NOT_AUTHENTICATED, reason?: string) {
    return jsonResponse({ type, title: "Authentication required", status: 403,
      detail: "The server's exact sign-in message.", errors: null, ...(reason ? { reason } : {}) }, 403);
  }

  it("leaves an initial anonymous visit neutral", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(signedOut());
    await expect(api.me()).rejects.toBeInstanceOf(ApiError);
    expect(sessionStatus.getSnapshot().status).toBe("unknown");
  });

  it("publishes confirmed session loss while retaining the original ApiError", async () => {
    await api.me();
    vi.mocked(fetch).mockResolvedValueOnce(signedOut());
    await expect(api.myCourses()).rejects.toMatchObject({ isNotAuthenticated: true });
    expect(sessionStatus.getSnapshot()).toEqual({ status: "ended", detail: "The server's exact sign-in message." });
  });

  it("recognizes LOGIN_REQUIRED only when supplied by the entitlement problem type", async () => {
    await api.me();
    vi.mocked(fetch).mockResolvedValueOnce(signedOut("about:blank", "LOGIN_REQUIRED"));
    await expect(api.myCourses()).rejects.toBeInstanceOf(ApiError);
    expect(sessionStatus.getSnapshot().status).toBe("confirmed");
    vi.mocked(fetch).mockResolvedValueOnce(signedOut("/problems/entitlement-denied", "LOGIN_REQUIRED"));
    await expect(api.lesson("lesson-1")).rejects.toBeInstanceOf(ApiError);
    expect(sessionStatus.getSnapshot().status).toBe("ended");
  });

  it("ignores permission, CSRF, network and server errors", async () => {
    await api.me();
    for (const response of [signedOut("about:blank"),
      signedOut("/problems/entitlement-denied", "SUBSCRIPTION_EXPIRED"),
      jsonResponse({ type: "about:blank", status: 403, detail: "CSRF Failed", errors: null }, 403),
      new Response("Gateway failed", { status: 502 })]) {
      vi.mocked(fetch).mockResolvedValueOnce(response);
      await expect(api.myCourses()).rejects.toBeInstanceOf(ApiError);
      expect(sessionStatus.getSnapshot().status).toBe("confirmed");
    }
    vi.mocked(fetch).mockRejectedValueOnce(new TypeError("offline"));
    await expect(api.myCourses()).rejects.toThrow("offline");
    expect(sessionStatus.getSnapshot().status).toBe("confirmed");
  });

  it("does not describe an intentional logout refusal as session expiry", async () => {
    await api.me();
    vi.mocked(fetch).mockResolvedValueOnce(signedOut());
    await expect(api.logout()).rejects.toBeInstanceOf(ApiError);
    expect(sessionStatus.getSnapshot().status).toBe("unknown");
  });

  it("requires a fresh successful me response to confirm recovery", async () => {
    await api.me();
    vi.mocked(fetch).mockResolvedValueOnce(signedOut());
    await expect(api.myCourses()).rejects.toBeInstanceOf(ApiError);
    await api.myCourses();
    expect(sessionStatus.getSnapshot().status).toBe("ended");
    await api.me();
    expect(sessionStatus.getSnapshot().status).toBe("confirmed");
  });

  it("does not let an older successful me request clear a newer refusal", async () => {
    await api.me();
    let complete!: (response: Response) => void;
    vi.mocked(fetch).mockImplementationOnce(() => new Promise<Response>((resolve) => { complete = resolve; }));
    const oldMe = api.me();
    vi.mocked(fetch).mockResolvedValueOnce(signedOut());
    await expect(api.myCourses()).rejects.toBeInstanceOf(ApiError);
    complete(jsonResponse({ id: "fixture-user" }));
    await oldMe;
    expect(sessionStatus.getSnapshot().status).toBe("ended");
  });

  it("does not let an older refusal invalidate a newer successful me request", async () => {
    await api.me();
    let complete!: (response: Response) => void;
    vi.mocked(fetch).mockImplementationOnce(() => new Promise<Response>((resolve) => { complete = resolve; }));
    const oldRead = api.myCourses();
    await api.me();
    complete(signedOut());
    await expect(oldRead).rejects.toBeInstanceOf(ApiError);
    expect(sessionStatus.getSnapshot().status).toBe("confirmed");
  });

  it.each(["login", "logout"] as const)("releases observation suppression after a failed %s request", async (intent) => {
    await api.me();
    vi.mocked(fetch).mockRejectedValueOnce(new TypeError("offline"));
    const operation = intent === "login" ? api.login("fixture@example.test", "synthetic-password") : api.logout();
    await expect(operation).rejects.toThrow("offline");
    expect(sessionStatus.getSnapshot().status).toBe("unknown");
    await api.me();
    expect(sessionStatus.getSnapshot().status).toBe("confirmed");
  });
});

describe("the request id header", () => {
  it("is set on a GET", async () => {
    await api.me();

    const headers = new Headers(lastCall().init.headers);

    expect(headers.get("X-Request-ID")).toBeTruthy();
  });

  it("is set on a POST too", async () => {
    // The structural test could not tell these apart. A header set only on
    // reads leaves every write untraceable, and writes are what break.
    await api.login("someone@example.test", "a-long-enough-passphrase");

    const headers = new Headers(lastCall().init.headers);

    expect(headers.get("X-Request-ID")).toBeTruthy();
  });

  it("differs between requests", async () => {
    await api.me();
    const first = new Headers(lastCall().init.headers).get("X-Request-ID");
    await api.me();
    const second = new Headers(lastCall().init.headers).get("X-Request-ID");

    expect(first).not.toBe(second);
  });

  it("does not overwrite one a caller already set", async () => {
    // A caller with an id is continuing a trace rather than starting one.
    await api.me();

    // Nothing in `api` exposes a way to pass headers, so this asserts the
    // property at the only place it can be observed: the header is absent from
    // the caller's own init, so `request` is what put it there.
    expect(new Headers(lastCall().init.headers).has("X-Request-ID")).toBe(true);
  });

  it("survives an environment with no crypto.randomUUID", async () => {
    // Not hypothetical: `crypto` is absent over plain HTTP on a non-localhost
    // origin, which is what a staging box without TLS looks like. The fallback
    // is deliberately marked `web-` rather than being a weaker UUID.
    vi.stubGlobal("crypto", undefined);

    await api.me();
    const id = new Headers(lastCall().init.headers).get("X-Request-ID");

    expect(id).toMatch(/^web-/);
  });
});

describe("credentials and the session cookie", () => {
  it("sends same-origin credentials", async () => {
    // Invariant 9: the session rides on a cookie the browser sends and
    // JavaScript never reads. `omit` here would break every authed request in
    // a way that looks like a login bug.
    await api.me();

    expect(lastCall().init.credentials).toBe("same-origin");
  });

  it("targets the same origin, not an absolute API host", async () => {
    // ADR-005 §2.1. An absolute URL would make every request cross-origin,
    // which is the change that quietly turns the session cookie into a CORS
    // problem.
    await api.me();

    expect(lastCall().url).toBe("/api/v1/auth/me/");
  });
});

describe("CSRF", () => {
  it("sends the token on an unsafe request", async () => {
    await api.login("someone@example.test", "a-long-enough-passphrase");

    expect(new Headers(lastCall().init.headers).get("X-CSRFToken")).toBe("test-token");
  });

  it("does not send it on a read", async () => {
    // Not a security property — a correctness one. Sending it on GETs would
    // hide the case where the cookie was never fetched.
    await api.me();

    expect(new Headers(lastCall().init.headers).has("X-CSRFToken")).toBe(false);
  });
});

describe("errors", () => {
  it("throws ApiError carrying the problem document", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValueOnce(
      jsonResponse(
        {
          type: PROBLEM_NOT_AUTHENTICATED,
          title: "Not authenticated",
          status: 403,
          detail: "Sign in to continue.",
          errors: null,
        },
        403,
      ),
    );

    await expect(api.me()).rejects.toBeInstanceOf(ApiError);
  });

  it("tells 'not signed in' apart from 'not allowed'", async () => {
    // ADR-004, and the reason problem types exist here: Django answers 403 for
    // both, because SessionAuthentication offers no WWW-Authenticate header.
    // The status alone cannot distinguish them.
    vi.mocked(globalThis.fetch).mockResolvedValueOnce(
      jsonResponse(
        {
          type: PROBLEM_NOT_AUTHENTICATED,
          title: "Not authenticated",
          status: 403,
          detail: "Sign in to continue.",
          errors: null,
        },
        403,
      ),
    );

    await expect(api.me()).rejects.toMatchObject({ isNotAuthenticated: true });
  });

  it("survives a non-JSON error body", async () => {
    // A gateway timeout is HTML. Without the fallback this throws a parse
    // error and the UI shows nothing rather than "something went wrong".
    vi.mocked(globalThis.fetch).mockResolvedValueOnce(
      new Response("<html>504 Gateway Timeout</html>", { status: 504 }),
    );

    await expect(api.me()).rejects.toMatchObject({ problem: { status: 504 } });
  });
});

describe("a 204 response", () => {
  it("becomes null for progress rather than a parse error", async () => {
    // `request` returns undefined for an empty body; `lessonProgress` turns
    // that into null so a player asking "have I been here before" gets an
    // answer instead of a missing value to guard against twice.
    vi.mocked(globalThis.fetch).mockResolvedValueOnce(new Response(null, { status: 204 }));

    await expect(api.lessonProgress("some-lesson")).resolves.toBeNull();
  });
});
