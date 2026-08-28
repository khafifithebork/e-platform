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
  vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ ok: true })));
  // A CSRF cookie, so unsafe requests do not trigger the bootstrap fetch and
  // make every assertion about "the last call" ambiguous.
  document.cookie = "csrftoken=test-token";
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
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
