/**
 * The learner pages wear the same chrome as the public ones.
 *
 * **They had none until M16 T9.** `(learner)` was created at T3 for the lesson
 * route and gained "my courses" at T5, and neither task noticed the group had
 * no `layout.tsx` — so a learner who followed "My courses" out of the header
 * arrived at a page with no header, no footer, no navigation and no skip link.
 * Browser-back was the only way out.
 *
 * It was invisible from the source, because nothing was *wrong* in any file:
 * the page rendered exactly what it said it would. It showed up in the built
 * HTML, where the whole document read *"My courses · Lingua / My courses /
 * Loading your courses…"*.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { filesMatching, sourceFilesIn } from "@/test/source";

import LearnerLayout from "./layout";

const GROUP = join(process.cwd(), "src", "app", "(learner)");

// The shell greets people by name, which means a request. Stubbed so these
// tests are about structure rather than about the session.
vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => {})));

function renderLayout() {
  return render(
    <LearnerLayout>
      <p>Some content</p>
    </LearnerLayout>,
  );
}

describe("the learner shell", () => {
  it("gives the page a main landmark", () => {
    renderLayout();

    expect(screen.getByRole("main")).toBeInTheDocument();
  });

  it("renders whatever page it wraps", () => {
    renderLayout();

    expect(screen.getByText("Some content")).toBeInTheDocument();
  });

  it("offers a way back to the catalogue", () => {
    // The specific thing whose absence stranded people: reaching "my courses"
    // and finding nothing to click.
    renderLayout();

    const hrefs = screen.getAllByRole("link").map((link) => link.getAttribute("href"));

    expect(hrefs).toEqual(expect.arrayContaining(["/", "/courses", "/pricing"]));
  });

  it("offers a skip link", () => {
    renderLayout();

    expect(screen.getByRole("link", { name: /skip to content/i })).toBeInTheDocument();
  });

  it("names its two navigations apart", () => {
    renderLayout();

    expect(screen.getByRole("navigation", { name: "Main" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Footer" })).toBeInTheDocument();
  });

  it("is the same shell the public pages wear", async () => {
    /**
     * Not "looks similar" — literally the same component.
     *
     * Two layouts rendering alike would drift, and the half that drifts is the
     * one nobody has open when they change the other. A learner crossing
     * between the catalogue and their own courses should not feel they have
     * left the site.
     */
    const learner = readFileSync(join(GROUP, "layout.tsx"), "utf8");
    const marketing = readFileSync(
      join(process.cwd(), "src", "app", "(marketing)", "layout.tsx"),
      "utf8",
    );

    expect(learner).toContain("SiteShell");
    expect(marketing).toContain("SiteShell");
  });
});

describe("the shell owns the main landmark", () => {
  it("no page in the group renders its own", () => {
    /**
     * **The regression this check exists for happened while writing T9.**
     *
     * Adding the layout gave every learner page a second `<main>`, because
     * `my-courses/page.tsx` and `LessonGate` each had one from when there was
     * no shell to provide it. The document-structure checker caught it on the
     * built HTML — *"my-courses.html: 2 `<main>` landmarks"* — but only for the
     * statically generated pages. The lesson route is dynamic and has no built
     * HTML at all, so nothing would have caught it there.
     *
     * This covers the group by source instead, which reaches the pages the
     * build output cannot.
     */
    // Comments stripped — `my-courses/page.tsx` explains that the shell owns
    // this landmark, and grepping the raw file fails against correct code.
    // Fourth time that has happened in this project; `@/test/source` is where
    // it stops.
    expect(filesMatching(GROUP, /<main[\s>]/)).toEqual([]);
  });

  it("and the check can see the files it is checking", () => {
    // Both assertions above pass trivially against an empty list.
    expect(sourceFilesIn(GROUP).length).toBeGreaterThan(0);
  });
});
