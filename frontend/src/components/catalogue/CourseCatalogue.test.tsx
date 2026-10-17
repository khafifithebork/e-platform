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

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CourseCatalogue } from "@/components/catalogue/CourseCatalogue";
import type { Language, PublicCourse } from "@/lib/catalogue/courses";

afterEach(() => vi.unstubAllGlobals());

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

describe("calm discovery and recovery", () => {
  it("clears outdated cards immediately when a different search query is entered", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      results: [COURSES[0]], count: 1, limit: 50, truncated: false,
    }), { headers: { "Content-Type": "application/json" } })));
    renderCatalogue();
    const input = screen.getByRole("searchbox");
    fireEvent.change(input, { target: { value: "spanish" } });
    await waitFor(() => expect(screen.getAllByRole("article")).toHaveLength(1));
    fireEvent.change(input, { target: { value: "french" } });
    expect(screen.queryByRole("article")).not.toBeInTheDocument();
    expect(screen.queryByText("1 result")).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Filter courses" })).not.toBeInTheDocument();
    expect(input).toHaveValue("french");
  });
  it("keeps a long course title complete in its link name", () => {
    const title = "A long course title for learners practising everyday conversations across different situations";
    renderCatalogue([course({ slug: "long-title", title })]);
    expect(screen.getByRole("link", { name: title })).toHaveTextContent(title);
    expect(screen.getByRole("article", { name: title })).toBeInTheDocument();
  });

  it("renders readable course results before hydration without entrance motion", () => {
    const html = renderToString(<CourseCatalogue courses={COURSES} languages={LANGUAGES} />);
    expect(html).toContain("Spanish for beginners");
    expect(html).not.toMatch(/opacity:0|transform:translate/);
  });

  it("restores browsing after a refused search and keeps the query available to edit", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 503 })));
    renderCatalogue();
    await userEvent.setup({ delay: null }).type(screen.getByRole("searchbox"), "spanish");
    await waitFor(() => expect(screen.getByText(/search is unavailable/i)).toBeVisible());
    expect(screen.getAllByRole("article")).toHaveLength(3);
    expect(screen.getByRole("searchbox")).toHaveValue("spanish");
  });

  it("offers a clear search action after no matches and returns to browsing", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      results: [], count: 0, limit: 50, truncated: false,
    }), { headers: { "Content-Type": "application/json" } })));
    renderCatalogue();
    const user = userEvent.setup({ delay: null });
    await user.type(screen.getByRole("searchbox"), "zzmissing");
    await waitFor(() => expect(screen.getByText(/nothing matched/i)).toBeVisible());
    await user.click(screen.getByRole("button", { name: "Clear search" }));
    expect(screen.getByRole("searchbox")).toHaveValue("");
    expect(screen.getAllByRole("article")).toHaveLength(3);
  });

  it("clears a filter combination with no matches", async () => {
    renderCatalogue();
    await userEvent.selectOptions(screen.getByLabelText("Language"), "fr");
    await userEvent.selectOptions(screen.getByLabelText("Level"), "B1");
    await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(screen.getAllByRole("article")).toHaveLength(3);
    expect(screen.getByLabelText("Language")).toHaveValue("any");
    expect(screen.getByLabelText("Level")).toHaveValue("any");
  });
});

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

  it("says nothing is published rather than blaming filters nobody set", () => {
    /**
     * **A real defect, and this test is why it lasted.** One branch served both
     * emptinesses, so a catalogue with nothing published told its first visitors
     * "No courses match those filters yet. Try widening one of them" — pointing
     * them at controls that were not the problem and implying they had done
     * something.
     *
     * The test above asserted only that the component "renders without crashing",
     * which was true of the wrong message as well as the right one.
     */
    renderCatalogue([]);

    expect(screen.getByText(/no courses have been published yet/i)).toBeInTheDocument();
    expect(screen.queryByText(/widening/i)).toBeNull();
  });

  it("still blames the filters when the filters really are the reason", async () => {
    // The twin. A component that always said "nothing published" would satisfy the
    // test above and mislead in the opposite direction — telling somebody who
    // filtered to French that the catalogue is empty.
    renderCatalogue();

    await userEvent.selectOptions(screen.getByLabelText("Language"), "fr");
    await userEvent.selectOptions(screen.getByLabelText("Level"), "B1");

    expect(screen.getByText(/widening/i)).toBeInTheDocument();
    expect(screen.queryByText(/no courses have been published/i)).toBeNull();
  });

  it("offers no skill filter when nothing is tagged", () => {
    // An empty "Skill" select promises a way to narrow and delivers one option.
    renderCatalogue([]);

    expect(screen.queryByLabelText("Skill")).toBeNull();
  });
});

describe("filtering by skill area", () => {
  const TAGGED = [
    course({ slug: "speak", title: "Conversation", skill_areas: ["speaking", "listening"] }),
    course({ slug: "read", title: "Reading practice", skill_areas: ["reading"] }),
    course({ slug: "none", title: "General Spanish", skill_areas: [] }),
  ];

  /** The option labels of a select, in order. */
  function optionsOf(label: string): (string | null)[] {
    return [...screen.getByLabelText(label).querySelectorAll("option")].map(
      (option) => option.textContent,
    );
  }

  it("offers only the skills this catalogue has", () => {
    /**
     * The same rule levels follow: "a catalogue with no C2 courses should not offer
     * a C2 filter that always yields nothing". A hard-coded list of the four
     * language skills would offer "writing" here and match nothing.
     */
    render(<CourseCatalogue courses={TAGGED} languages={LANGUAGES} />);

    expect(optionsOf("Skill")).toEqual(["All skills", "listening", "reading", "speaking"]);
  });

  it("narrows to the courses carrying that tag", async () => {
    render(<CourseCatalogue courses={TAGGED} languages={LANGUAGES} />);

    await userEvent.selectOptions(screen.getByLabelText("Skill"), "speaking");

    expect(screen.getAllByRole("article")).toHaveLength(1);
    expect(screen.getByRole("heading", { name: "Conversation" })).toBeInTheDocument();
  });

  it("matches a course on any of its tags, not only the first", async () => {
    // "Conversation" is tagged speaking *and* listening. A filter reading
    // `skill_areas[0]` would pass the test above and fail this one.
    render(<CourseCatalogue courses={TAGGED} languages={LANGUAGES} />);

    await userEvent.selectOptions(screen.getByLabelText("Skill"), "listening");

    expect(screen.getByRole("heading", { name: "Conversation" })).toBeInTheDocument();
  });

  it("treats tags that differ only in case as one skill", async () => {
    /**
     * `skill_areas` is a free-form `JSONField`, so "Listening" and "listening" are
     * both real values two instructors can enter. Offering them as separate
     * options, each matching half the courses, is the failure this guards against.
     *
     * The label is the first spelling seen rather than a normalised one, so the
     * data as entered stays visible — a controlled vocabulary is the real fix and
     * it is a backend decision, not something a filter should impose quietly.
     */
    const mixed = [
      course({ slug: "a", title: "One", skill_areas: ["Listening"] }),
      course({ slug: "b", title: "Two", skill_areas: ["listening"] }),
    ];

    render(<CourseCatalogue courses={mixed} languages={LANGUAGES} />);

    expect(optionsOf("Skill")).toHaveLength(2);

    await userEvent.selectOptions(screen.getByLabelText("Skill"), "listening");
    expect(screen.getAllByRole("article")).toHaveLength(2);
  });

  it("survives a tag list that is not a list of strings", () => {
    // `skill_areas` is a `JSONField`: the generated type is `unknown` and the
    // stored value is whatever was written. A catalogue page that threw on one
    // malformed row would fail the build for every course.
    const odd = [
      course({ slug: "weird", title: "Odd", skill_areas: { not: "a list" } as unknown as [] }),
      course({ slug: "mixed", title: "Mixed", skill_areas: ["speaking", 7] as unknown as [] }),
    ];

    render(<CourseCatalogue courses={odd} languages={LANGUAGES} />);

    expect(optionsOf("Skill")).toEqual(["All skills", "speaking"]);
  });
});

describe("clearing the filters", () => {
  it("is offered only once something is set", async () => {
    // A permanently visible "Clear" on an unfiltered listing is a button that does
    // nothing, which is worse than no button.
    renderCatalogue();
    expect(screen.queryByRole("button", { name: /clear filters/i })).toBeNull();

    await userEvent.selectOptions(screen.getByLabelText("Language"), "fr");

    expect(screen.getByRole("button", { name: /clear filters/i })).toBeInTheDocument();
  });

  it("resets every filter at once, not only the last one touched", async () => {
    renderCatalogue();

    await userEvent.selectOptions(screen.getByLabelText("Language"), "es");
    await userEvent.selectOptions(screen.getByLabelText("Level"), "B1");
    expect(screen.getAllByRole("article")).toHaveLength(1);

    await userEvent.click(screen.getByRole("button", { name: /clear filters/i }));

    expect(screen.getAllByRole("article")).toHaveLength(3);
    expect(screen.getByLabelText("Language")).toHaveValue("any");
    expect(screen.getByLabelText("Level")).toHaveValue("any");
  });

  it("goes away again once nothing is filtered", async () => {
    renderCatalogue();
    await userEvent.selectOptions(screen.getByLabelText("Language"), "fr");

    await userEvent.click(screen.getByRole("button", { name: /clear filters/i }));

    expect(screen.queryByRole("button", { name: /clear filters/i })).toBeNull();
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
