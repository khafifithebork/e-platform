/**
 * The page-title guard, and why it is a source check rather than a render one.
 *
 * `(marketing)/typography.test.ts` used to assert this by grepping that route
 * group for `<h1 className="…">` and comparing the strings. That worked only
 * while every title was hand-written, and it could never leave the group: run
 * over the whole app it would have failed on correct code, because the auth
 * pages and the 404 are deliberately a size down from the catalogue.
 *
 * With `PageTitle` owning both treatments the question changes shape, and the
 * new question is the stronger one — **no `<h1>` anywhere may size itself.** It
 * holds app-wide, and unlike a string comparison it fails on the *first* page
 * that reintroduces a hand-written title rather than on the second.
 *
 * Two files are **pinned** rather than exempted: this component, and
 * `global-error.tsx`, which replaces the document when the root layout fails and
 * so cannot import anything from the design system. A pinned set fails if an entry
 * is removed as well as added, which is what keeps it a record of a decision
 * instead of a hole that widens quietly.
 */

import { render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { PAGE_TITLE, PageTitle } from "@/components/ui/PageTitle";
import { codeOnly, sourceFilesIn } from "@/test/source";

const SRC = join(import.meta.dirname, "..", "..");

/**
 * The only two files permitted a hand-written `<h1>`.
 *
 * `PageTitle.tsx` is the component itself. `global-error.tsx` is the boundary
 * that replaces the document when the root layout fails and therefore cannot
 * depend on the design system at all — see the pinned test below.
 */
const ALLOWED = ["PageTitle.tsx", "global-error.tsx"] as const;

/** Every `<h1 …>` opening tag in the app's own source, comments stripped. */
function rawTitleTags(): { path: string; tag: string }[] {
  return sourceFilesIn(SRC).flatMap((path) => {
    const code = codeOnly(readFileSync(path, "utf8"));
    return [...code.matchAll(/<h1[^>]*>/g)].map((match) => ({ path, tag: match[0] }));
  });
}

describe("nothing writes its own page title", () => {
  it("leaves no <h1> in the app outside this component", () => {
    /**
     * `codeOnly` is not optional here and the reason is written up in
     * `test/source.ts`: four structural guards before this one failed against
     * correct code because the file *documented* the rule it was checked for.
     * This component's own source discusses `<h1>` at length, and two of the
     * pages it replaced explain in a comment why their heading matters.
     */
    const unexpected = rawTitleTags().filter(
      ({ path }) => !ALLOWED.some((name) => path.endsWith(name)),
    );

    expect(unexpected.map(({ path, tag }) => `${path}: ${tag}`)).toEqual([]);
  });

  it("allows a raw <h1> in exactly the two places that cannot use the component", () => {
    /**
     * **Pinned, not exempted**, the same technique as
     * `test/logical-properties.test.ts`: this fails if either file stops having
     * one, so the set is a record of a decision rather than a hole that silently
     * widens.
     *
     * `global-error.tsx` replaces the document when the root layout fails
     * (ADR-031 §2). It cannot import `PageTitle` — or anything else from the
     * design system — because the scenario it exists for is that system being
     * what broke, and `boundaries.test.tsx` asserts it reaches for no custom
     * property at all. So its heading is written out, and that is the point of it.
     */
    const pinned = rawTitleTags().map(({ path }) =>
      ALLOWED.find((name) => path.endsWith(name)),
    );

    expect(pinned.sort()).toEqual([...ALLOWED].sort());
  });

  it("is looking at real source files and finding the pinned <h1>s", () => {
    /**
     * The twin, and it does two jobs. An empty list satisfies the test above,
     * so a broken path or a regex that matched nothing would pass it — and
     * `sourceFilesIn` reading a directory that does not exist throws rather
     * than returning `[]`, so the count is the check that matters.
     */
    expect(sourceFilesIn(SRC).length).toBeGreaterThan(30);
    expect(rawTitleTags()).toHaveLength(ALLOWED.length);
  });

  it("does not count a title that only a comment mentions", () => {
    // Proving `codeOnly` is doing the work rather than being decoration: this
    // file names the tag repeatedly in prose, including right here — <h1> — and
    // must not count itself. Tests are excluded from `sourceFilesIn` as well,
    // so this is belt and braces on purpose.
    const tags = [...codeOnly("// a comment about <h1>\nconst x = 1;").matchAll(/<h1[^>]*>/g)];

    expect(tags).toEqual([]);
  });
});

describe("the treatments", () => {
  it("make page and interstitial differ in exactly one class", () => {
    /**
     * The claim the component is built on: two sizes, one system. If a future
     * edit gives the interstitial its own font, colour or tracking, these have
     * stopped being one scale with two steps and become two designs — which is
     * the drift this replaced, back again with better packaging.
     */
    const page = new Set(PAGE_TITLE.page.split(/\s+/));
    const interstitial = new Set(PAGE_TITLE.interstitial.split(/\s+/));

    const onlyInPage = [...page].filter((cls) => !interstitial.has(cls));
    const onlyInInterstitial = [...interstitial].filter((cls) => !page.has(cls));

    expect(onlyInPage).toEqual(["text-4xl"]);
    expect(onlyInInterstitial).toEqual(["text-3xl"]);
  });

  it("records `section` exactly as it was found, outlier and all", () => {
    /**
     * **Not held to the rule above, on purpose.** `section` is `LessonPlayer`'s
     * existing lesson title, reproduced byte for byte so that adopting the
     * component changed nothing on screen. It sets neither `tracking-tight` nor
     * `leading-tight`, which makes it the one variant that is not simply the
     * others a step smaller.
     *
     * This test pins it so the inconsistency is visible in a test run rather
     * than only in a docstring, and so that normalising it later is a deliberate
     * edit to an assertion rather than a quiet change to a heading nobody is
     * watching. The second expectation is the substance: it is the `<h2>`
     * section-heading treatment the marketing pages use, which is the whole
     * argument for leaving it alone until someone decides otherwise.
     */
    expect(PAGE_TITLE.section).toBe("font-display text-2xl text-ink");

    const sectionHeading = readFileSync(
      join(SRC, "app", "(marketing)", "pricing", "page.tsx"),
      "utf8",
    );
    expect(sectionHeading).toContain(`<h2 id="included" className="${PAGE_TITLE.section}">`);
  });

  it("renders an h1 either way, because the outline does not vary with the size", () => {
    render(<PageTitle>Courses</PageTitle>);
    render(<PageTitle variant="interstitial">That page is not here</PageTitle>);

    const titles = screen.getAllByRole("heading", { level: 1 });
    expect(titles.map((h) => h.textContent)).toEqual(["Courses", "That page is not here"]);
  });

  it("carries an id when one is given, for an aria-labelledby that points at it", () => {
    render(<PageTitle id="course-title">Beginner Spanish</PageTitle>);

    expect(screen.getByRole("heading", { level: 1 })).toHaveAttribute("id", "course-title");
  });
});
