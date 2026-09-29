/**
 * "My courses".
 *
 * **Abuse case 6 is structural rather than testable from here.** The endpoint
 * is scoped to the requesting user server-side — `courses_in_progress` filters
 * on `user=user` and `test_and_nobody_else_s` proves it. What this file can
 * assert is that the component never takes an id from anywhere else: it renders
 * exactly what `/me/courses/` returned, and asks for nothing by id.
 *
 * The interesting cases are the three states nobody designs for — signed out,
 * enrolled in nothing, and finished — because each is indistinguishable from a
 * bug if it is rendered as an empty list.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MyCourses } from "@/components/learn/MyCourses";
import type { Enrollment } from "@/lib/api/client";

function enrollment(overrides: Partial<Enrollment> = {}): Enrollment {
  return {
    id: "e1",
    course_slug: "spanish",
    course_title: "Spanish for beginners",
    last_lesson: "l1",
    last_lesson_slug: "intro",
    next_lesson: "l2",
    next_lesson_slug: "greetings",
    completed_lesson_count: 3,
    lesson_count: 8,
    last_activity: "2026-08-01T00:00:00Z",
    started_at: "2026-07-01T00:00:00Z",
    completed_at: null,
    ...overrides,
  } as Enrollment;
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

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
  vi.stubGlobal("fetch", vi.fn(async () => json({ results: [enrollment()] })));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the list", () => {
  it("names each course", async () => {
    render(<MyCourses />);

    expect(await screen.findByText("Spanish for beginners")).toBeInTheDocument();
  });

  it("reports progress as a number, not only a bar", async () => {
    // A bar alone leaves the value to be inferred from a width. The visible
    // text is what somebody reads, and what a screen reader gets for free.
    render(<MyCourses />);

    expect(await screen.findByText("3 of 8 lessons")).toBeInTheDocument();
  });

  it("uses a real progress element", async () => {
    // `<progress>` carries the role and the values without any ARIA. A styled
    // div would need three attributes to say the same thing, and would say
    // nothing if one were forgotten.
    render(<MyCourses />);

    const bar = await screen.findByRole("progressbar", { name: /progress through/i });

    expect(bar).toHaveAttribute("value", "3");
    expect(bar).toHaveAttribute("max", "8");
  });

  it("links the title to the course", async () => {
    render(<MyCourses />);

    expect(await screen.findByRole("link", { name: "Spanish for beginners" })).toHaveAttribute(
      "href",
      "/courses/spanish",
    );
  });
});

describe("resuming", () => {
  it("points at the next lesson, not the bookmark", async () => {
    /**
     * They differ for anybody who skipped ahead, and the selector says which
     * is which: the bookmark is where the learner *was*, `next_lesson` walks
     * back to the earliest unfinished lesson.
     *
     * Sending somebody to their bookmark would quietly write off everything
     * they skipped — the exact behaviour `_next_lesson_id` was written to
     * avoid.
     */
    render(<MyCourses />);

    expect(await screen.findByRole("link", { name: "Continue" })).toHaveAttribute(
      "href",
      "/courses/spanish/lessons/greetings",
    );
  });

  it("builds the URL from slugs, never from ids", async () => {
    // The lesson route is `/courses/{slug}/lessons/{lessonSlug}` since T3.
    // Before this task the payload carried only UUIDs and this link could not
    // have been built at all.
    render(<MyCourses />);
    const href = (await screen.findByRole("link", { name: "Continue" })).getAttribute("href");

    expect(href).not.toContain("l2");
    expect(href).toContain("greetings");
  });

  it("says Start when nothing has been watched yet", async () => {
    // An enrolment with no bookmark was created and abandoned before the first
    // lesson. "Continue" would be describing something that did not happen.
    vi.mocked(globalThis.fetch).mockResolvedValue(
      json({ results: [enrollment({ last_lesson: null, last_lesson_slug: null })] }),
    );

    render(<MyCourses />);

    expect(await screen.findByRole("link", { name: "Start" })).toBeInTheDocument();
  });

  it("offers nothing to resume on a finished course", async () => {
    // `next_lesson` is null when there is nothing left. A resume link here
    // would send somebody back into a course they completed.
    vi.mocked(globalThis.fetch).mockResolvedValue(
      json({
        results: [
          enrollment({
            next_lesson: null,
            next_lesson_slug: null,
            completed_lesson_count: 8,
          }),
        ],
      }),
    );

    render(<MyCourses />);
    await screen.findByText("Finished");

    expect(screen.queryByRole("link", { name: /continue|start/i })).not.toBeInTheDocument();
  });
});

describe("the states nobody designs for", () => {
  it("tells a signed-out visitor to sign in", async () => {
    // A 403 here is somebody without an account reaching a page that needs
    // one — not an outage. "Something went wrong" would send them looking for
    // a fault that is not there.
    vi.mocked(globalThis.fetch).mockResolvedValue(notAuthenticated());

    render(<MyCourses />);

    expect(await screen.findByRole("link", { name: "Sign in" })).toHaveAttribute(
      "href",
      "/login",
    );
  });

  it("does not call a signed-out visitor an error", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(notAuthenticated());

    render(<MyCourses />);
    await screen.findByRole("link", { name: "Sign in" });

    expect(screen.queryByText(/could not be loaded/i)).not.toBeInTheDocument();
  });

  it("explains an empty list rather than showing nothing", async () => {
    // There is no enrol button — starting a lesson is what enrols somebody —
    // so an empty page with no explanation reads as a bug.
    vi.mocked(globalThis.fetch).mockResolvedValue(json({ results: [] }));

    render(<MyCourses />);

    expect(await screen.findByText(/not started a course yet/i)).toBeInTheDocument();
  });

  it("sends an unenrolled learner to the catalogue", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(json({ results: [] }));

    render(<MyCourses />);

    expect(await screen.findByRole("link", { name: /browse the catalogue/i })).toHaveAttribute(
      "href",
      "/courses",
    );
  });

  it("offers a retry that re-requests, rather than advice", async () => {
    /**
     * **This used to say "Try again in a moment" and give nobody anything to
     * press.** The common cause is a transient connection failure, which is exactly
     * the case one click fixes.
     *
     * The retry re-runs the load rather than reloading the page: a reload would
     * throw away everything else on screen to recover one request.
     */
    vi.mocked(globalThis.fetch).mockRejectedValueOnce(new TypeError("fetch failed"));

    render(<MyCourses />);
    await screen.findByText(/could not be loaded/i);
    const before = vi.mocked(globalThis.fetch).mock.calls.length;

    vi.mocked(globalThis.fetch).mockResolvedValue(json({ results: [enrollment()] }));
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByText("Spanish for beginners")).toBeInTheDocument();
    expect(vi.mocked(globalThis.fetch).mock.calls.length).toBeGreaterThan(before);
  });

  it("offers the retry again when the retry also fails", async () => {
    // The second failure is the one where somebody is most likely to give up, and a
    // component that dropped the control after one attempt would strand them.
    vi.mocked(globalThis.fetch).mockRejectedValue(new TypeError("fetch failed"));

    render(<MyCourses />);
    await screen.findByText(/could not be loaded/i);

    await userEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("reports a real failure as a failure", async () => {
    // The negative that keeps the signed-out branch honest. If every error
    // became "sign in", an outage would look like a session problem and
    // somebody would sign in repeatedly to fix a server.
    vi.mocked(globalThis.fetch).mockRejectedValue(new TypeError("fetch failed"));

    render(<MyCourses />);

    expect(await screen.findByText(/could not be loaded/i)).toBeInTheDocument();
  });

  it("says something while loading", async () => {
    vi.mocked(globalThis.fetch).mockImplementation(() => new Promise<Response>(() => {}));

    render(<MyCourses />);

    expect(screen.getByText(/loading your courses/i)).toHaveAttribute("aria-live", "polite");
  });
});

describe("abuse case 6 — only your own enrolments", () => {
  it("asks for the scoped endpoint and nothing else", async () => {
    // The endpoint is scoped server-side; what this asserts is that the
    // component never reaches for an enrolment by id, which is the only way a
    // frontend could widen it.
    render(<MyCourses />);
    await screen.findByText("Spanish for beginners");

    const urls = vi.mocked(globalThis.fetch).mock.calls.map(([url]) => String(url));

    expect(urls).toEqual(["/api/v1/me/courses/"]);
  });

  it("renders exactly what it was given", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      json({ results: [enrollment(), enrollment({ id: "e2", course_title: "French" })] }),
    );

    render(<MyCourses />);
    await screen.findByText("French");

    expect(screen.getAllByRole("article")).toHaveLength(2);
  });
});

/**
 * Pagination, which was silently dropped until 2026-09-27.
 *
 * `/me/courses/` is cursor-paginated and the client's response type was
 * hand-written as `{ results: Enrollment[] }` — a shape invariant 16 forbids
 * writing by hand. Because it omitted `next`, the second page was not so much
 * ignored as **invisible**: a learner past the first page saw part of their list
 * and nothing suggested more existed.
 *
 * The `next` values below deliberately carry an **internal** host. That is what
 * Django really returns: it builds the URL from the request's Host header, and
 * the Next.js rewrite forwards its own destination as Host, so `next` names `api`
 * rather than the origin the browser is on. A component following that URL would
 * request the wrong host from the browser. `cursorFrom` takes the cursor and
 * discards the rest, and these fixtures are what prove it.
 */
describe("more courses than fit on one page", () => {
  it("offers no control when the API says there is no next page", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      json({ next: null, previous: null, results: [enrollment()] }),
    );

    render(<MyCourses />);
    await screen.findByText("Spanish for beginners");

    expect(screen.queryByRole("button", { name: /show more/i })).toBeNull();
  });

  it("appends the next page, keeping what was already shown", async () => {
    const user = userEvent.setup();
    vi.mocked(globalThis.fetch)
      .mockResolvedValueOnce(
        json({
          next: "http://api/api/v1/me/courses/?cursor=cD0yMDI2",
          previous: null,
          results: [enrollment()],
        }),
      )
      .mockResolvedValueOnce(
        json({
          next: null,
          previous: null,
          results: [enrollment({ id: "e2", course_slug: "french", course_title: "French, slowly" })],
        }),
      );

    render(<MyCourses />);
    await user.click(await screen.findByRole("button", { name: /show more/i }));

    /**
      * Presence, not visibility. Cards sit inside `StaggerList`, which renders
      * `opacity: 0` until an `IntersectionObserver` raises them — and
      * `vitest.setup.ts` stubs that observer as a no-op, so it never fires here.
      * `motion.test.tsx` records the same behaviour deliberately ("is present but
      * NOT yet visible until the observer fires"). Asserting visibility would be
      * asserting a motion library's runtime, not this component's logic.
      *
      * Both, and in order: an implementation that replaced rather than appended
      * would pass a test that only looked for the second one.
      */
    expect(await screen.findByText("French, slowly")).toBeInTheDocument();
    expect(screen.getByText("Spanish for beginners")).toBeInTheDocument();
    expect(screen.getAllByRole("article")).toHaveLength(2);

    // And the control is gone, because that page said there is no next.
    expect(screen.queryByRole("button", { name: /show more/i })).toBeNull();
  });

  it("sends the cursor, not the URL Django handed back", async () => {
    /**
     * **The assertion that matters most here.** The `next` fixture points at
     * `http://api/...`, an internal name the browser cannot and must not resolve.
     * The second request must go to our own origin with the cursor as a query
     * parameter.
     */
    const user = userEvent.setup();
    vi.mocked(globalThis.fetch)
      .mockResolvedValueOnce(
        json({
          next: "http://api/api/v1/me/courses/?cursor=cD0yMDI2",
          previous: null,
          results: [enrollment()],
        }),
      )
      .mockResolvedValueOnce(json({ next: null, previous: null, results: [] }));

    render(<MyCourses />);
    await user.click(await screen.findByRole("button", { name: /show more/i }));

    await waitFor(() => expect(vi.mocked(globalThis.fetch).mock.calls.length).toBeGreaterThan(1));
    const urls = vi.mocked(globalThis.fetch).mock.calls.map(([input]) => String(input));

    expect(urls).toContain("/api/v1/me/courses/?cursor=cD0yMDI2");
    expect(urls.some((url) => url.includes("http://api"))).toBe(false);
  });

  it("keeps the first page on screen when loading more fails", async () => {
    /**
     * A failed second request must not cost the learner what they could already
     * see. Moving to the `failed` state would replace a usable list with an
     * error, which is worse than the error alone.
     */
    const user = userEvent.setup();
    vi.mocked(globalThis.fetch)
      .mockResolvedValueOnce(
        json({
          next: "http://api/api/v1/me/courses/?cursor=cD0yMDI2",
          previous: null,
          results: [enrollment()],
        }),
      )
      .mockResolvedValueOnce(json({ detail: "Server error" }, 500));

    render(<MyCourses />);
    await user.click(await screen.findByRole("button", { name: /show more/i }));

    // The notice is outside the stagger list, so it is genuinely visible.
    expect(await screen.findByRole("alert")).toBeVisible();
    expect(screen.getByText("Spanish for beginners")).toBeInTheDocument();
    // The cursor is kept, so a retry is one click away.
    expect(screen.getByRole("button", { name: /show more/i })).toBeVisible();
  });

  it("ignores a malformed next link rather than breaking the page", async () => {
    // A `next` with no cursor ends the list. The alternative — throwing — would
    // take down a page that had already rendered correctly.
    vi.mocked(globalThis.fetch).mockResolvedValue(
      json({ next: "http://api/api/v1/me/courses/", previous: null, results: [enrollment()] }),
    );

    render(<MyCourses />);
    await screen.findByText("Spanish for beginners");

    expect(screen.queryByRole("button", { name: /show more/i })).toBeNull();
  });
});
