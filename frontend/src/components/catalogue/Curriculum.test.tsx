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
    render(<Curriculum sections={SECTIONS} />);

    const headings = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);

    expect(headings[0]).toContain("Getting started");
    expect(headings[1]).toContain("Greetings");
  });

  it("orders lessons by position too", () => {
    render(<Curriculum sections={SECTIONS} />);

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
    render(<Curriculum sections={SECTIONS} />);

    expect(screen.getByText("Free preview")).toBeInTheDocument();
  });

  it("does not mark every lesson free", () => {
    // The negative. A badge on everything is a badge on nothing, and here it
    // would be a claim about what is behind the paywall.
    render(<Curriculum sections={SECTIONS} />);

    expect(screen.getAllByText("Free preview")).toHaveLength(1);
  });

  it("hides the decorative numbering from assistive technology", () => {
    // An ordered list already conveys position. Reading "1. Getting started.
    // List item one of two" is the same fact twice.
    render(<Curriculum sections={SECTIONS} />);

    const heading = screen.getByRole("heading", { name: "Getting started" });

    expect(heading.querySelector('[aria-hidden="true"]')).toHaveTextContent("1.");
  });

  it("says so when there is no outline, rather than rendering nothing", () => {
    // An approved course with no sections is possible, and an empty heading
    // with nothing under it reads as a broken page.
    render(<Curriculum sections={[]} />);

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
      />,
    );

    expect(screen.getByText("Ten")).toBeInTheDocument();
  });

  it("does not link a lesson, because the lesson route is gated", () => {
    // A link here would invite a signed-out visitor into an entitlement
    // refusal, and it would put a gated route inside a statically generated
    // public page.
    render(<Curriculum sections={SECTIONS} />);

    expect(screen.queryAllByRole("link")).toHaveLength(0);
  });
});
