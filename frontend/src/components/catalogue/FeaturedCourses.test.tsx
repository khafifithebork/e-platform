/**
 * The featured band on the landing page.
 *
 * Small component, and the tests are mostly about the two states nobody builds
 * for: a catalogue with nothing in it, and a catalogue with more courses than
 * fit. Both are certain to happen — the first on launch day, the second within
 * a month — and both look like a broken page rather than an error.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { FEATURED_LIMIT, FeaturedCourses } from "@/components/catalogue/FeaturedCourses";
import type { Language, PublicCourse } from "@/lib/catalogue/courses";

const SPANISH: Language = { code: "es", name: "Spanish", native_name: "Español" };

function course(slug: string, published_at: string | null): PublicCourse {
  return {
    id: `id-${slug}`,
    slug,
    title: slug,
    description: "",
    language: SPANISH,
    level: "A1",
    skill_areas: [],
    instructor_name: "",
    published_at,
  } as PublicCourse;
}

describe("an empty catalogue", () => {
  it("renders nothing at all", () => {
    // Launch day. A heading over blank space looks broken in a way a shorter
    // page does not, so the whole section disappears rather than emptying.
    const { container } = render(<FeaturedCourses courses={[]} />);

    expect(container).toBeEmptyDOMElement();
  });

  it("and the check would notice a heading", () => {
    // The twin. `toBeEmptyDOMElement` passes against a component that renders
    // nothing under any circumstances, so this shows it rendering.
    render(<FeaturedCourses courses={[course("a", "2026-01-01T00:00:00Z")]} />);

    expect(screen.getByRole("heading", { name: "Recently published" })).toBeInTheDocument();
  });
});

describe("ordering", () => {
  it("shows the most recently published first", () => {
    render(
      <FeaturedCourses
        courses={[
          course("older", "2026-01-01T00:00:00Z"),
          course("newest", "2026-06-01T00:00:00Z"),
          course("middle", "2026-03-01T00:00:00Z"),
        ]}
      />,
    );

    const titles = screen.getAllByRole("article").map((article) => article.textContent);

    expect(titles[0]).toContain("newest");
    expect(titles[2]).toContain("older");
  });

  it("does not depend on the order the API returned", () => {
    // The endpoint paginates by publication date, but "the order it happened
    // to return" is not a contract. A landing page that silently reorders when
    // the backend changes its default ordering is a change nobody traces back.
    const ascending = [
      course("older", "2026-01-01T00:00:00Z"),
      course("newest", "2026-06-01T00:00:00Z"),
    ];

    render(<FeaturedCourses courses={ascending} />);

    expect(screen.getAllByRole("article")[0]?.textContent).toContain("newest");
  });

  it("breaks ties on slug, so two builds agree", () => {
    // Two courses approved in the same second would otherwise swap places
    // between builds, which shows up as a diff nobody can explain.
    const sameSecond = [
      course("bravo", "2026-06-01T00:00:00Z"),
      course("alpha", "2026-06-01T00:00:00Z"),
    ];

    render(<FeaturedCourses courses={sameSecond} />);

    expect(screen.getAllByRole("article")[0]?.textContent).toContain("alpha");
  });

  it("survives courses that have never been published", () => {
    // `published_at` is nullable — "null means it has never been live". Sorting
    // on it without a guard reaches `null.localeCompare` and throws, which in a
    // statically generated page is a failed build rather than a broken card.
    //
    // Several undated entries, not one, and that is a correction: with a
    // two-element array the comparator may only ever see the null in its first
    // argument, where `localeCompare` coerces rather than throws — so the test
    // passed against an unguarded sort. Found by removing the guard and
    // watching it not fail.
    render(
      <FeaturedCourses
        courses={[
          course("undated-a", null),
          course("dated", "2026-01-01T00:00:00Z"),
          course("undated-b", null),
          course("undated-c", null),
        ]}
      />,
    );

    expect(screen.getAllByRole("article")).toHaveLength(FEATURED_LIMIT);
  });

  it("does not mutate the array it was given", () => {
    // The page passes the same array to this component and could later pass it
    // elsewhere. An in-place `.sort()` would reorder the caller's data as a
    // side effect of rendering.
    const courses = [
      course("older", "2026-01-01T00:00:00Z"),
      course("newest", "2026-06-01T00:00:00Z"),
    ];

    render(<FeaturedCourses courses={courses} />);

    expect(courses[0].slug).toBe("older");
  });
});

describe("a catalogue larger than the band", () => {
  it("shows only as many as fit", () => {
    const many = Array.from({ length: FEATURED_LIMIT + 4 }, (_, index) =>
      course(`course-${index}`, `2026-01-0${(index % 9) + 1}T00:00:00Z`),
    );

    render(<FeaturedCourses courses={many} />);

    expect(screen.getAllByRole("article")).toHaveLength(FEATURED_LIMIT);
  });

  it("offers a way to see the rest", () => {
    render(<FeaturedCourses courses={[course("a", "2026-01-01T00:00:00Z")]} />);

    expect(screen.getByRole("link", { name: "All courses" })).toHaveAttribute(
      "href",
      "/courses",
    );
  });

  it("does not claim a course count", () => {
    // A number here is accurate only until the next publication, and "12
    // courses" over a catalogue of 13 is wrong in the way nobody checks.
    render(<FeaturedCourses courses={[course("a", "2026-01-01T00:00:00Z")]} />);

    expect(screen.queryByText(/\d+\s+courses?/i)).not.toBeInTheDocument();
  });
});
