/**
 * The header's one personalised element.
 *
 * Most of this file is about the state nobody designs for: the moment before
 * the answer arrives. It lasts one round trip, it happens on every page load,
 * and getting it wrong tells every subscriber they have been logged out.
 *
 * **Abuse case 8 lives here too.** Invariant 9 puts nothing auth-related in
 * `localStorage` or `sessionStorage`, ever — and a component that fetches the
 * current user is exactly where somebody would cache one "to avoid the
 * flicker". The test for that is the one worth keeping longest.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthMenu } from "@/components/auth/AuthMenu";

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

/** What `/auth/me/` returns to somebody with no session. */
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

/** A promise that never settles, for holding the component in its first state. */
function pending() {
  return new Promise<Response>(() => {});
}

beforeEach(() => {
  // Storage is process-global and `cleanup()` does not touch it, so a test
  // that wrote would leak into the next one's count. Noticed while provoking
  // the abuse-case-8 checks: caching the user broke not only the assertion
  // about it but the twin that keeps the assertion honest.
  localStorage.clear();
  sessionStorage.clear();
  vi.stubGlobal("fetch", vi.fn(async () => notAuthenticated()));
  // jsdom refuses real navigation, and `signOut` performs one deliberately.
  vi.stubGlobal("location", { assign: vi.fn(), href: "http://localhost/" });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("before the answer arrives", () => {
  it("does not claim you are signed out", () => {
    // The whole reason this component has three states rather than two.
    // Rendering "Sign in" as a placeholder shows it to every subscriber on
    // every page load, which reads as having been logged out.
    vi.mocked(globalThis.fetch).mockImplementation(pending);

    render(<AuthMenu />);

    expect(screen.queryByRole("link", { name: "Sign in" })).not.toBeInTheDocument();
  });

  it("does not claim you are signed in either", () => {
    vi.mocked(globalThis.fetch).mockImplementation(pending);

    render(<AuthMenu />);

    expect(screen.queryByRole("button", { name: /sign out/i })).not.toBeInTheDocument();
  });

  it("offers nothing to focus", () => {
    // A keyboard user tabbing through the header should not land on an empty
    // placeholder, and a screen reader should not announce one.
    vi.mocked(globalThis.fetch).mockImplementation(pending);
    const { container } = render(<AuthMenu />);

    expect(container.querySelectorAll("a, button")).toHaveLength(0);
  });
});

describe("signed out", () => {
  it("offers a way in", async () => {
    render(<AuthMenu />);

    expect(await screen.findByRole("link", { name: "Sign in" })).toHaveAttribute(
      "href",
      "/login",
    );
  });

  it("treats the 403 as an answer rather than an error", async () => {
    // `/auth/me/` refuses anonymous requests. If that were handled as a
    // failure, the header would sit in its unknown state forever for every
    // signed-out visitor — which is most of them on a public catalogue.
    render(<AuthMenu />);

    await screen.findByRole("link", { name: "Sign in" });

    expect(screen.queryByText(/error|wrong|failed/i)).not.toBeInTheDocument();
  });

  it("falls back to signed out when the API is unreachable", async () => {
    // A header that cannot tell you who you are should offer the way in, not
    // an error about a request the visitor never made.
    vi.mocked(globalThis.fetch).mockRejectedValue(new TypeError("fetch failed"));

    render(<AuthMenu />);

    expect(await screen.findByRole("link", { name: "Sign in" })).toBeInTheDocument();
  });
});

describe("signed in", () => {
  beforeEach(() => {
    vi.mocked(globalThis.fetch).mockImplementation(async () => json(ME));
  });

  it("links to the learner's own courses", async () => {
    render(<AuthMenu />);

    expect(await screen.findByRole("link", { name: "My courses" })).toHaveAttribute(
      "href",
      "/my-courses",
    );
  });

  it("says who you are", async () => {
    render(<AuthMenu />);

    expect(await screen.findByText("learner@example.test")).toBeInTheDocument();
  });

  it("offers no sign-in link", async () => {
    // The negative. Both states rendering at once is what a component that
    // appends rather than switches produces.
    render(<AuthMenu />);
    await screen.findByRole("button", { name: "Sign out" });

    expect(screen.queryByRole("link", { name: "Sign in" })).not.toBeInTheDocument();
  });
});

describe("signing out", () => {
  beforeEach(() => {
    vi.mocked(globalThis.fetch).mockImplementation(async () => json(ME));
  });

  it("tells the server", async () => {
    render(<AuthMenu />);
    await userEvent.click(await screen.findByRole("button", { name: "Sign out" }));

    await waitFor(() => {
      const paths = vi.mocked(globalThis.fetch).mock.calls.map(([url]) => String(url));
      expect(paths).toContain("/api/v1/auth/logout/");
    });
  });

  it("leaves the page entirely rather than refreshing it", async () => {
    /**
     * A full navigation, and the reason is not routing preference.
     *
     * A soft refresh does not clear client component state. By the time
     * somebody signs out this application may be holding their enrolments,
     * their progress and a lesson body in memory — and leaving all of it there
     * for whoever uses the browser next is precisely what the button exists to
     * prevent.
     */
    render(<AuthMenu />);
    await userEvent.click(await screen.findByRole("button", { name: "Sign out" }));

    await waitFor(() => expect(vi.mocked(globalThis.location.assign)).toHaveBeenCalledWith("/"));
  });

  it("leaves even when the logout request fails", async () => {
    // If the cookie survived server-side the next request re-establishes the
    // truth. Leaving the header signed in after somebody asked to leave is the
    // worse of the two wrongs.
    vi.mocked(globalThis.fetch).mockImplementation(async (url) =>
      String(url).includes("logout") ? Promise.reject(new TypeError("offline")) : json(ME),
    );

    render(<AuthMenu />);
    await userEvent.click(await screen.findByRole("button", { name: "Sign out" }));

    await waitFor(() => expect(vi.mocked(globalThis.location.assign)).toHaveBeenCalledWith("/"));
  });
});

describe("abuse case 8 — nothing auth-related is stored", () => {
  it("writes nothing to localStorage", async () => {
    // Invariant 9. This component is exactly where somebody would cache the
    // current user "to avoid the flicker", and the flicker is a worse problem
    // to solve that way than to leave alone.
    vi.mocked(globalThis.fetch).mockImplementation(async () => json(ME));

    render(<AuthMenu />);
    await screen.findByText("learner@example.test");

    expect(localStorage.length).toBe(0);
  });

  it("writes nothing to sessionStorage either", async () => {
    vi.mocked(globalThis.fetch).mockImplementation(async () => json(ME));

    render(<AuthMenu />);
    await screen.findByText("learner@example.test");

    expect(sessionStorage.length).toBe(0);
  });

  it("and the check would notice a write", () => {
    // The twin. Both assertions above pass against a jsdom where storage does
    // not work at all, which would make them meaningless.
    localStorage.setItem("probe", "1");
    expect(localStorage.length).toBe(1);
    localStorage.clear();
  });
});
