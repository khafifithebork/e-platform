/**
 * Personal progress on an impersonal page.
 *
 * The course page is statically generated — one HTML file built before any of
 * these learners existed — so this is the only place on it that knows who is
 * reading. Everything here is about **not** intruding: three of its four states
 * render nothing at all, and the fourth is a strip.
 *
 * The state worth the most attention is the anonymous one. A public catalogue
 * page is read mostly by people with no account, `/me/courses/` refuses them,
 * and a component that treated that refusal as an error would put a broken
 * strip on the busiest page in the product.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CourseProgress } from "@/components/catalogue/CourseProgress";
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

describe("an enrolled learner", () => {
  it("sees how far through they are", async () => {
    render(<CourseProgress courseSlug="spanish" />);

    expect(await screen.findByText("3 of 8 lessons")).toBeInTheDocument();
  });

  it("gets a real progress element, not a styled div", async () => {
    render(<CourseProgress courseSlug="spanish" />);

    const bar = await screen.findByRole("progressbar", { name: "Lessons completed" });

    expect(bar).toHaveAttribute("value", "3");
    expect(bar).toHaveAttribute("max", "8");
  });

  it("can continue from where they left off", async () => {
    render(<CourseProgress courseSlug="spanish" />);

    expect(
      await screen.findByRole("link", { name: /continue where you left off/i }),
    ).toHaveAttribute("href", "/courses/spanish/lessons/greetings");
  });

  it("is offered a start, not a continue, before watching anything", async () => {
    // The same distinction "my courses" makes. An enrolment with no bookmark
    // was created and abandoned before the first lesson.
    vi.mocked(globalThis.fetch).mockResolvedValue(
      json({ results: [enrollment({ last_lesson: null, last_lesson_slug: null })] }),
    );

    render(<CourseProgress courseSlug="spanish" />);

    expect(await screen.findByRole("link", { name: /start the first lesson/i })).toBeInTheDocument();
  });

  it("is told when there is nothing left", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      json({
        results: [
          enrollment({ next_lesson: null, next_lesson_slug: null, completed_lesson_count: 8 }),
        ],
      }),
    );

    render(<CourseProgress courseSlug="spanish" />);
    await screen.findByText("Finished");

    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("names its region, so it is findable and skippable", async () => {
    render(<CourseProgress courseSlug="spanish" />);

    expect(await screen.findByRole("complementary", { name: "Your progress" })).toBeInTheDocument();
  });
});

describe("everybody else sees nothing", () => {
  it("renders nothing for a visitor with no account", async () => {
    // The common case on a public catalogue page. A 403 here is not a fault,
    // and an error strip on the busiest page in the product would be.
    vi.mocked(globalThis.fetch).mockResolvedValue(notAuthenticated());
    const { container } = render(<CourseProgress courseSlug="spanish" />);

    await waitFor(() => expect(vi.mocked(globalThis.fetch)).toHaveBeenCalled());

    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing for a learner who has not started this course", async () => {
    // They are enrolled in something, just not this. Showing "0 of 8" would be
    // a fact they cannot act on attached to a page they are still deciding
    // about.
    vi.mocked(globalThis.fetch).mockResolvedValue(
      json({ results: [enrollment({ course_slug: "french" })] }),
    );
    const { container } = render(<CourseProgress courseSlug="spanish" />);

    await waitFor(() => expect(vi.mocked(globalThis.fetch)).toHaveBeenCalled());

    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing while it is still resolving", () => {
    // No skeleton, no placeholder. This is supplementary detail on a page that
    // is complete without it, and a shimmer would draw the eye to something
    // most readers will never see.
    vi.mocked(globalThis.fetch).mockImplementation(() => new Promise<Response>(() => {}));
    const { container } = render(<CourseProgress courseSlug="spanish" />);

    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when the API is unreachable", async () => {
    // The course page must not look broken because a supplementary strip
    // failed. Everything above it came from the build and is still correct.
    vi.mocked(globalThis.fetch).mockRejectedValue(new TypeError("fetch failed"));
    const { container } = render(<CourseProgress courseSlug="spanish" />);

    await waitFor(() => expect(vi.mocked(globalThis.fetch)).toHaveBeenCalled());

    expect(container).toBeEmptyDOMElement();
  });

  it("and the check would notice if it rendered", async () => {
    // The twin. Four assertions of emptiness all pass against a component that
    // renders nothing under any circumstances.
    render(<CourseProgress courseSlug="spanish" />);

    expect(await screen.findByText("3 of 8 lessons")).toBeInTheDocument();
  });
});

describe("invariant 15 — the page it sits on stays static", () => {
  it("matches the enrolment by slug, not by position", async () => {
    // The list is the learner's own handful and its order is not a contract.
    // Taking `results[0]` would show one course's progress on another's page.
    vi.mocked(globalThis.fetch).mockResolvedValue(
      json({
        results: [
          enrollment({ id: "e0", course_slug: "french", completed_lesson_count: 7 }),
          enrollment(),
        ],
      }),
    );

    render(<CourseProgress courseSlug="spanish" />);

    expect(await screen.findByText("3 of 8 lessons")).toBeInTheDocument();
  });

  it("asks only for the learner's own list", async () => {
    // No course-specific endpoint exists, and inventing one to save a filter
    // is not this milestone's business.
    render(<CourseProgress courseSlug="spanish" />);
    await screen.findByText("3 of 8 lessons");

    const urls = vi.mocked(globalThis.fetch).mock.calls.map(([url]) => String(url));

    expect(urls).toEqual(["/api/v1/me/courses/"]);
  });
});
