/**
 * The public course outline.
 *
 * **Abuse case 3 is the reason this file exists**: a public course page must
 * not leak content the entitlement resolver gates. It is satisfied upstream —
 * `PublicLesson` has no `body` field at all, because the serializer's docstring
 * says "a field that is usually hidden is one wrong branch from being
 * visible" — and the test here asserts that rather than trusting it, because
 * the day somebody adds a field to that serializer this is what notices.
 */

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Curriculum } from "@/components/catalogue/Curriculum";
import type { PublicLesson, PublicSection } from "@/lib/catalogue/courses";

function lesson(overrides: Partial<PublicLesson> & { id: string }): PublicLesson {
  return {
    slug: overrides.id,
    title: "A lesson",
    position: 1,
    is_preview: false,
    ...overrides,
  } as PublicLesson;
}

function section(overrides: Partial<PublicSection> & { id: string }): PublicSection {
  return {
    title: "A section",
    position: 1,
    lessons: [],
    ...overrides,
  } as PublicSection;
}

const COURSE = "spanish";

const SECTIONS: PublicSection[] = [
  section({
    id: "s2",
    title: "Greetings",
    position: 2,
    lessons: [
      lesson({ id: "l2", title: "Saying hello", position: 2 }),
      lesson({ id: "l1", title: "The alphabet", position: 1, is_preview: true }),
    ],
  }),
  section({ id: "s1", title: "Getting started", position: 1, lessons: [] }),
];

describe("the outline", () => {
  it("orders sections by position, not by array order", () => {
    // The API maintains `position` for exactly this. Relying on array order
    // means the outline silently reshuffles the day the endpoint changes its
    // default ordering — a change nobody would think to trace this far.
    render(<Curriculum sections={SECTIONS} courseSlug={COURSE} />);

    const headings = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);

    expect(headings[0]).toContain("Getting started");
    expect(headings[1]).toContain("Greetings");
  });

  it("orders lessons by position too", () => {
    render(<Curriculum sections={SECTIONS} courseSlug={COURSE} />);

    const greetings = screen.getByRole("heading", { name: /Greetings/ }).parentElement!;
    const lessons = within(greetings)
      .getAllByRole("listitem")
      .map((item) => item.textContent);

    expect(lessons[0]).toContain("The alphabet");
    expect(lessons[1]).toContain("Saying hello");
  });

  it("marks a preview lesson as free", () => {
    // The single most useful thing this page can tell somebody deciding
    // whether to subscribe.
    render(<Curriculum sections={SECTIONS} courseSlug={COURSE} />);

    expect(screen.getByText("Free preview")).toBeInTheDocument();
  });

  it("does not mark every lesson free", () => {
    // The negative. A badge on everything is a badge on nothing, and here it
    // would be a claim about what is behind the paywall.
    render(<Curriculum sections={SECTIONS} courseSlug={COURSE} />);

    expect(screen.getAllByText("Free preview")).toHaveLength(1);
  });

  it("hides the decorative numbering from assistive technology", () => {
    // An ordered list already conveys position. Reading "1. Getting started.
    // List item one of two" is the same fact twice.
    render(<Curriculum sections={SECTIONS} courseSlug={COURSE} />);

    const heading = screen.getByRole("heading", { name: "Getting started" });

    expect(heading.querySelector('[aria-hidden="true"]')).toHaveTextContent("1.");
  });

  it("says so when there is no outline, rather than rendering nothing", () => {
    // An approved course with no sections is possible, and an empty heading
    // with nothing under it reads as a broken page.
    render(<Curriculum sections={[]} courseSlug={COURSE} />);

    expect(screen.getByText(/not published yet/i)).toBeInTheDocument();
  });
});

describe("abuse case 3 — no gated content reaches a public page", () => {
  it("renders nothing but the lesson title and its preview flag", () => {
    // Given a lesson object carrying a `body` — which the real serializer
    // cannot produce, and which is exactly what a future change to that
    // serializer would introduce — none of it appears.
    const withBody = {
      ...lesson({ id: "l9", title: "Numbers" }),
      body: "SECRET-LESSON-CONTENT",
      transcript: "SECRET-TRANSCRIPT",
    } as unknown as PublicLesson;

    render(
      <Curriculum
        sections={[section({ id: "s9", title: "Numbers", lessons: [withBody] })]}
        courseSlug={COURSE}
      />,
    );

    expect(screen.queryByText(/SECRET-LESSON-CONTENT/)).not.toBeInTheDocument();
    expect(screen.queryByText(/SECRET-TRANSCRIPT/)).not.toBeInTheDocument();
  });

  it("and the check would notice if it did", () => {
    // The twin. The assertion above passes against a component that renders
    // nothing at all, so this shows the same query finding the title it is
    // supposed to find.
    render(
      <Curriculum
        sections={[
          section({ id: "s9", title: "Numbers", lessons: [lesson({ id: "l9", title: "Ten" })] }),
        ]}
        courseSlug={COURSE}
      />,
    );

    expect(screen.getByText("Ten")).toBeInTheDocument();
  });

  it("links each lesson at its course-scoped URL", () => {
    /**
     * **This assertion was the opposite until M16 T3**, and the reversal is
     * the interesting part rather than the link.
     *
     * The original reasoning: "a link here would invite a signed-out visitor
     * into an entitlement refusal." True while a refusal was a bare 403 with
     * nowhere to go. It stopped being true once a preview lesson played for
     * somebody with no account, and once every refusal landed on a page that
     * says what happened and offers a way forward.
     *
     * The URL is the one architecture.md §6.2 specified at M0 and nothing
     * served until T3.
     */
    render(<Curriculum sections={SECTIONS} courseSlug={COURSE} />);

    expect(screen.getByRole("link", { name: "The alphabet" })).toHaveAttribute(
      "href",
      "/courses/spanish/lessons/l1",
    );
  });

  it("scopes every lesson link to the course it was given", () => {
    // The twin. A link built from the lesson slug alone would 404 on the API,
    // which resolves on both slugs and treats a mismatch as not found.
    render(<Curriculum sections={SECTIONS} courseSlug={COURSE} />);

    const hrefs = screen.getAllByRole("link").map((link) => link.getAttribute("href"));

    expect(hrefs.every((href) => href?.startsWith("/courses/spanish/lessons/"))).toBe(true);
  });
});
