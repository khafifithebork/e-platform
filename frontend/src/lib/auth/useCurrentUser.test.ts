/**
 * Who is signed in, resolved in the browser.
 *
 * Extracted from `AuthMenu` during the redesign and shipped with no tests of
 * its own, while `AuthMenu` — which resolves the same three states by its own
 * copy of this logic — has a file largely devoted to them. This closes that.
 *
 * **The state nobody designs for is `unknown`.** It lasts one round trip, it
 * happens on every page load, and resolving it to `anonymous` by default is
 * how every subscriber gets told they have been signed out for a moment on
 * every navigation.
 *
 * **Invariant 9 is the other half.** Nothing auth-related may touch
 * `localStorage` or `sessionStorage`, ever — and a hook that fetches the
 * current user is exactly where somebody caches one "to stop the flicker".
 */

import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useCurrentUser } from "@/lib/auth/useCurrentUser";

const ME = {
  id: "u1",
  email: "learner@example.test",
  role: "STUDENT",
  is_email_verified: true,
  profile: {},
  access: { allowed: true, reason: "SUBSCRIPTION_ACTIVE", cta: null },
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** What `/auth/me/` returns to somebody with no session: an answer, not a fault. */
function notAuthenticated() {
  return json(
    {
      type: "/problems/not-authenticated",
      title: "Authentication required",
      status: 403,
      detail: "Authentication credentials were not provided.",
      errors: null,
    },
    403,
  );
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("the three states", () => {
  it("starts unknown rather than guessing anonymous", () => {
    // Never resolves, so the hook is observed mid-flight.
    vi.mocked(fetch).mockReturnValue(new Promise(() => {}));

    const { result } = renderHook(() => useCurrentUser());

    expect(result.current.status).toBe("unknown");
  });

  it("resolves to signed-in and carries the user", async () => {
    vi.mocked(fetch).mockResolvedValue(json(ME));

    const { result } = renderHook(() => useCurrentUser());

    await waitFor(() => expect(result.current.status).toBe("signed-in"));
    expect(result.current).toMatchObject({ me: { email: "learner@example.test" } });
  });

  it("treats a 403 as the answer 'nobody', not a failure", async () => {
    vi.mocked(fetch).mockResolvedValue(notAuthenticated());

    const { result } = renderHook(() => useCurrentUser());

    await waitFor(() => expect(result.current.status).toBe("anonymous"));
  });

  it("falls back to anonymous when the request fails outright", async () => {
    // A network error is not an authorisation answer, but the safe reading of
    // "we could not tell" is the one that shows less, not more.
    vi.mocked(fetch).mockRejectedValue(new TypeError("Failed to fetch"));

    const { result } = renderHook(() => useCurrentUser());

    await waitFor(() => expect(result.current.status).toBe("anonymous"));
  });
});

describe("invariant 9", () => {
  it("writes nothing to localStorage or sessionStorage", async () => {
    const local = vi.spyOn(Storage.prototype, "setItem");
    vi.mocked(fetch).mockResolvedValue(json(ME));

    const { result } = renderHook(() => useCurrentUser());
    await waitFor(() => expect(result.current.status).toBe("signed-in"));

    expect(local).not.toHaveBeenCalled();
  });

  it("reads nothing from them either", async () => {
    // The twin. A cache that is written elsewhere and only *read* here would
    // pass the test above while still putting the session in storage.
    const read = vi.spyOn(Storage.prototype, "getItem");
    vi.mocked(fetch).mockResolvedValue(json(ME));

    const { result } = renderHook(() => useCurrentUser());
    await waitFor(() => expect(result.current.status).toBe("signed-in"));

    expect(read).not.toHaveBeenCalled();
  });
});

describe("it asks the server once, with credentials", () => {
  it("makes exactly one request per mount", async () => {
    vi.mocked(fetch).mockResolvedValue(json(ME));

    const { result } = renderHook(() => useCurrentUser());
    await waitFor(() => expect(result.current.status).toBe("signed-in"));

    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(1);
  });

  it("guards against setting state after unmount, which no test here can prove", async () => {
    /**
     * **Provoked, and it could not fail.** The first version of this test
     * removed the hook's `current` flag and asserted `console.error` was
     * called — the React 17 warning about updating an unmounted component.
     * React 18 removed that warning deliberately, on the grounds that the
     * update is a harmless no-op rather than a leak, so all eight tests passed
     * against a hook with the guard deleted.
     *
     * Rather than keep a test that guards nothing, this asserts the guard is
     * *present* and says plainly what it is worth: defence in depth against a
     * React version or a future effect where the update stops being harmless.
     * The same conclusion M16 reached about `LessonPlayer`'s `readyRef`.
     */
    const source = await import("node:fs").then((fs) =>
      fs.readFileSync("src/lib/auth/useCurrentUser.ts", "utf8"),
    );

    expect(source).toContain("let current = true");
    expect(source).toContain("current = false");
    expect(source).toMatch(/if \(current\)/);
  });
});
