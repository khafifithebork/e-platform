/**
 * The listing and its filters.
 *
 * The filter is the part of this milestone most likely to be built the wrong
 * way — reading `searchParams` in a server component is the obvious approach
 * and it opts the route into dynamic rendering, which invariant 15 forbids.
 * These tests cover the shape that was chosen instead: data in as props,
 * filtering in the browser over what is already on the page.
 *
 * Queried through the accessibility tree throughout. A filter found by
 * `#language-select` passes while its label is detached and nobody using a
 * screen reader can tell what the control does.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { CourseCatalogue } from "@/components/catalogue/CourseCatalogue";
import type { Language, PublicCourse } from "@/lib/catalogue/courses";

const SPANISH: Language = { code: "es", name: "Spanish", native_name: "Español" };
const FRENCH: Language = { code: "fr", name: "French", native_name: "Français" };

function course(overrides: Partial<PublicCourse> & { slug: string }): PublicCourse {
  return {
    id: `id-${overrides.slug}`,
    title: "A course",
    description: "",
    language: SPANISH,
    level: "A1",
    skill_areas: [],
    instructor_name: "",
    published_at: "2026-01-01T00:00:00Z",
    ...overrides,
  } as PublicCourse;
}

const COURSES: PublicCourse[] = [
  course({ slug: "spanish-a1", title: "Spanish for beginners", language: SPANISH, level: "A1" }),
  course({ slug: "spanish-b1", title: "Spanish conversation", language: SPANISH, level: "B1" }),
  course({ slug: "french-a1", title: "French for beginners", language: FRENCH, level: "A1" }),
];

const LANGUAGES = [SPANISH, FRENCH];

function renderCatalogue(courses = COURSES) {
  return render(<CourseCatalogue courses={courses} languages={LANGUAGES} />);
}

describe("the listing", () => {
  it("shows every course before anything is filtered", () => {
    // Abuse case 7 restated at the component level: the content is present,
    // not fetched on mount. A visitor with no JavaScript sees exactly this.
    renderCatalogue();

    expect(screen.getAllByRole("article")).toHaveLength(3);
  });

  it("links each course to its own page by slug", () => {
    // Slugs, not ids — `PublicCourseViewSet` sets `lookup_field = "slug"`
    // precisely so these are the URLs, and a card linking by UUID would 404.
    renderCatalogue();

    expect(screen.getByRole("link", { name: "Spanish for beginners" })).toHaveAttribute(
      "href",
      "/courses/spanish-a1",
    );
  });

  it("names each card after its title in the accessibility tree", () => {
    // The card is an `article` labelled by its heading. Without that, the
    // landmark list is three unnamed articles.
    renderCatalogue();

    expect(screen.getByRole("article", { name: "Spanish for beginners" })).toBeInTheDocument();
  });

  it("does not wrap the whole card in one link", () => {
    // A link containing the heading, the description and every tag is read out
    // in full as a single link name. There should be one link per card.
    renderCatalogue();

    expect(screen.getAllByRole("link")).toHaveLength(3);
  });
});

describe("filtering", () => {
  it("narrows by language", async () => {
    renderCatalogue();

    await userEvent.selectOptions(screen.getByLabelText("Language"), "fr");

    expect(screen.getAllByRole("article")).toHaveLength(1);
  });

  it("narrows by level", async () => {
    renderCatalogue();

    await userEvent.selectOptions(screen.getByLabelText("Level"), "B1");

    expect(screen.getAllByRole("article")).toHaveLength(1);
  });

  it("combines both filters", async () => {
    renderCatalogue();

    await userEvent.selectOptions(screen.getByLabelText("Language"), "es");
    await userEvent.selectOptions(screen.getByLabelText("Level"), "A1");

    expect(screen.getByRole("article", { name: "Spanish for beginners" })).toBeInTheDocument();
    expect(screen.getAllByRole("article")).toHaveLength(1);
  });

  it("can be widened again", async () => {
    // The negative that makes the rest mean something: a filter that narrows
    // and cannot be undone is a dead end, and "All languages" has to be a real
    // option rather than a placeholder.
    renderCatalogue();
    const language = screen.getByLabelText("Language");

    await userEvent.selectOptions(language, "fr");
    await userEvent.selectOptions(language, "any");

    expect(screen.getAllByRole("article")).toHaveLength(3);
  });

  it("says so when nothing matches, rather than showing an empty page", async () => {
    renderCatalogue();

    await userEvent.selectOptions(screen.getByLabelText("Language"), "fr");
    await userEvent.selectOptions(screen.getByLabelText("Level"), "B1");

    expect(screen.queryAllByRole("article")).toHaveLength(0);
    expect(screen.getByText(/no courses match/i)).toBeInTheDocument();
  });

  it("only offers levels the catalogue actually has", async () => {
    // A C2 filter that always yields nothing is a worse experience than no
    // filter. The options come from the data, not from a hard-coded CEFR list.
    renderCatalogue();

    const levelOptions = screen
      .getAllByRole("option")
      .map((option) => (option as HTMLOptionElement).value);

    expect(levelOptions).not.toContain("C2");
    expect(levelOptions).toContain("B1");
  });

  it("announces the result count politely", async () => {
    // Changing a filter re-renders silently. A sighted user watches it happen;
    // without a live region a screen-reader user gets no signal at all.
    renderCatalogue();

    await userEvent.selectOptions(screen.getByLabelText("Language"), "fr");

    expect(screen.getByText("1 of 3 courses")).toHaveAttribute("aria-live", "polite");
  });

  it("labels its filter region", () => {
    renderCatalogue();

    expect(screen.getByRole("region", { name: "Filter courses" })).toBeInTheDocument();
  });
});

describe("an empty catalogue", () => {
  it("renders without crashing", () => {
    // The first day after launch, and the state a build against an empty
    // database produces. A listing that throws on zero courses fails the
    // build rather than the page.
    renderCatalogue([]);

    expect(screen.getByText("0 courses")).toBeInTheDocument();
  });
});

describe("a course with missing optional fields", () => {
  it("shows the instructor when there is one", () => {
    // The positive half, and it has to come first: the negative below is only
    // meaningful if this element would otherwise be found.
    render(
      <CourseCatalogue
        courses={[course({ slug: "named", title: "Named", instructor_name: "Ada Lovelace" })]}
        languages={LANGUAGES}
      />,
    );

    expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();
  });

  it("omits the instructor line rather than rendering an empty one", () => {
    // The API documents `instructor_name` as "empty when they have not set
    // one". Rendering it unconditionally shows a blank line on exactly the one
    // instructor who never filled in their profile.
    //
    // Asserted by counting the paragraphs inside the card rather than by
    // looking for empty text — an earlier version queried `getByText("")`,
    // which matches nothing whether or not the bug is present and would have
    // passed forever.
    render(
      <CourseCatalogue
        courses={[
          course({ slug: "anon", title: "Anonymous", instructor_name: "", description: "" }),
        ]}
        languages={LANGUAGES}
      />,
    );

    const article = screen.getByRole("article", { name: "Anonymous" });

    expect(article.querySelectorAll("p")).toHaveLength(0);
  });

  it("survives skill_areas being absent entirely", () => {
    // Typed `unknown` in the generated schema, because the backend stores
    // free-form tags. `.map` on undefined is a build-time crash in a static
    // page, which fails the whole build rather than one card.
    render(
      <CourseCatalogue
        courses={[course({ slug: "bare", title: "Bare", skill_areas: undefined })]}
        languages={LANGUAGES}
      />,
    );

    expect(screen.getByRole("article", { name: "Bare" })).toBeInTheDocument();
  });
});
