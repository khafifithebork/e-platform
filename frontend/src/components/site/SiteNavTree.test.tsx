/**
 * The site map in the margin, and the one branch that depends on who you are.
 *
 * 233 lines shipped with the redesign and no tests. Most of it is markup, and
 * markup that is wrong is visible. **One part is not**: the account branch
 * renders "My courses" or the sign-in pair depending on `useCurrentUser`, and
 * the failure mode of getting that wrong is quiet in both directions — a
 * signed-out visitor offered a page they cannot open, or a subscriber told to
 * sign in on every page load while the answer is still in flight.
 *
 * That third state is what most of this file is about. `AuthMenu` has the same
 * shape and the same reasoning documented at length; this is the second
 * consumer of it, and until now the untested one.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SiteNavTree } from "@/components/site/SiteNavTree";

vi.mock("next/navigation", () => ({
  usePathname: () => "/courses",
}));

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

function notAuthenticated() {
  return json({ type: "/problems/not-authenticated", status: 403, errors: null }, 403);
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("the account branch", () => {
  it("offers nothing at all while the answer is in flight", () => {
    vi.mocked(fetch).mockReturnValue(new Promise(() => {}));

    render(<SiteNavTree />);

    // Neither choice, because either would be a guess. `AuthMenu` documents
    // the reasoning: showing "Sign in" to a subscriber for one round trip on
    // every page load reads as having been logged out.
    expect(screen.queryByRole("link", { name: /my courses/i })).toBeNull();
    expect(screen.queryByRole("link", { name: /sign in/i })).toBeNull();
  });

  it("shows the sign-in pair once the visitor is known to be anonymous", async () => {
    vi.mocked(fetch).mockResolvedValue(notAuthenticated());

    render(<SiteNavTree />);

    await waitFor(() => expect(screen.getByRole("link", { name: /sign in/i })).toBeVisible());
    expect(screen.queryByRole("link", { name: /my courses/i })).toBeNull();
  });

  it("does not offer a learner page to somebody who is not signed in", async () => {
    /**
     * The one that matters. `/my-courses` refuses an anonymous caller — the
     * entitlement resolver is not bypassed by a link — so this is a dead end
     * rather than a hole. A navigation aid that offers pages the visitor
     * cannot open is still a bug, and the quiet kind.
     */
    vi.mocked(fetch).mockResolvedValue(notAuthenticated());

    render(<SiteNavTree />);
    await waitFor(() => expect(screen.getByRole("link", { name: /sign in/i })).toBeVisible());

    const links = screen.getAllByRole("link").map((a) => a.getAttribute("href"));
    expect(links).not.toContain("/my-courses");
  });

  it("shows My courses to a signed-in learner, and not the sign-in pair", async () => {
    vi.mocked(fetch).mockResolvedValue(json(ME));

    render(<SiteNavTree />);

    await waitFor(() => expect(screen.getByRole("link", { name: /my courses/i })).toBeVisible());
    expect(screen.queryByRole("link", { name: /^sign in$/i })).toBeNull();
  });
});

describe("what it always shows", () => {
  it("renders the public pages regardless of who is asking", async () => {
    // The twin for the account tests: a tree that rendered nothing would
    // satisfy every "is absent" assertion above.
    vi.mocked(fetch).mockResolvedValue(notAuthenticated());

    render(<SiteNavTree />);
    await waitFor(() => expect(screen.getByRole("link", { name: /sign in/i })).toBeVisible());

    const links = screen.getAllByRole("link").map((a) => a.getAttribute("href"));
    expect(links).toContain("/courses");
    expect(links).toContain("/pricing");
  });

  it("marks the current page for anyone who cares which one it is", async () => {
    vi.mocked(fetch).mockResolvedValue(notAuthenticated());

    render(<SiteNavTree />);

    await waitFor(() => expect(screen.getByRole("link", { name: /sign in/i })).toBeVisible());
    const current = screen
      .getAllByRole("link")
      .filter((a) => a.getAttribute("aria-current") === "page");

    expect(current.map((a) => a.getAttribute("href"))).toContain("/courses");
  });
});
