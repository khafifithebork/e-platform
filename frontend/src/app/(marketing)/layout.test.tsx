/**
 * The public shell.
 *
 * Two kinds of test here, and the split is deliberate.
 *
 * **Rendered tests** cover the accessibility structure — landmarks, the skip
 * link, focus target. These are the things that are easy to write once and
 * then quietly break, because nothing about the page *looks* wrong when the
 * skip link stops working.
 *
 * **A structural test** covers invariant 15: no file in the `(marketing)` group
 * may fetch at request time. That cannot be asserted by rendering, because a
 * component that fetches renders perfectly well in a test — it is a property of
 * the whole group, including files that do not exist yet, so it is asserted
 * against the directory rather than against any one component.
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import MarketingLayout from "./layout";

const GROUP = join(process.cwd(), "src", "app", "(marketing)");

/**
 * A file's code, with its comments removed.
 *
 * **This is a correction, and the bug was subtle in both directions.** The
 * checks below grep source text, and every one of them was matching prose:
 * `courses/page.tsx` carries a docstring explaining *why* it does not read
 * `searchParams`, and that sentence made the "does not read searchParams"
 * assertion fail against entirely correct code. Documenting a rule made the
 * rule's own test fail.
 *
 * The opposite failure is the one that matters more: a check that people learn
 * to satisfy by rewording a comment is a check that stops meaning anything.
 * Stripping comments first is what keeps these about code.
 */
function codeOnly(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
}

function sourceFilesIn(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) return sourceFilesIn(path);
    return /\.tsx?$/.test(entry) && !entry.endsWith(".test.tsx") ? [path] : [];
  });
}

describe("the marketing shell", () => {
  it("gives the page a main landmark", () => {
    render(
      <MarketingLayout>
        <p>Some content</p>
      </MarketingLayout>,
    );

    expect(screen.getByRole("main")).toBeInTheDocument();
  });

  it("renders whatever page it wraps", () => {
    render(
      <MarketingLayout>
        <p>Some content</p>
      </MarketingLayout>,
    );

    expect(screen.getByText("Some content")).toBeInTheDocument();
  });

  it("offers a skip link before anything else", () => {
    // First in the DOM is the whole point — a skip link that comes after the
    // navigation has already made the user tab through it.
    render(
      <MarketingLayout>
        <p>Some content</p>
      </MarketingLayout>,
    );

    const skip = screen.getByRole("link", { name: /skip to content/i });
    const nav = screen.getByRole("navigation", { name: "Main" });

    expect(skip.compareDocumentPosition(nav) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("points the skip link at the main landmark", () => {
    // A skip link whose target does not exist is worse than none: focus goes
    // nowhere and the user cannot tell whether it worked.
    render(
      <MarketingLayout>
        <p>Some content</p>
      </MarketingLayout>,
    );

    const target = screen.getByRole("link", { name: /skip to content/i }).getAttribute("href");

    expect(screen.getByRole("main").id).toBe(target?.replace("#", ""));
  });

  it("makes the main landmark focusable, so the skip link moves focus", () => {
    // Without tabIndex the browser scrolls to the anchor and leaves focus on
    // the link, so the next Tab goes straight back into the navigation the
    // user just asked to skip. The symptom is subtle and the cause is one
    // attribute.
    render(
      <MarketingLayout>
        <p>Some content</p>
      </MarketingLayout>,
    );

    expect(screen.getByRole("main")).toHaveAttribute("tabindex", "-1");
  });

  it("names its two navigations apart", () => {
    // Two unlabelled `<nav>` elements appear in the landmark list as
    // "navigation" and "navigation", which tells a screen-reader user nothing
    // about which one they are in.
    render(
      <MarketingLayout>
        <p>Some content</p>
      </MarketingLayout>,
    );

    expect(screen.getByRole("navigation", { name: "Main" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Footer" })).toBeInTheDocument();
  });

  it("links to the catalogue, pricing and sign-in", () => {
    render(
      <MarketingLayout>
        <p>Some content</p>
      </MarketingLayout>,
    );

    const hrefs = screen.getAllByRole("link").map((link) => link.getAttribute("href"));

    expect(hrefs).toEqual(expect.arrayContaining(["/courses", "/pricing", "/login"]));
  });
});

describe("invariant 15 — nothing here renders at request time", () => {
  /**
   * Structural, and it has to be.
   *
   * CLAUDE.md invariant 15: "the `(marketing)` route group must not depend on
   * a live API call at request time." A rendered test cannot see this — a
   * component that fetches renders fine under a stubbed `fetch`. What makes it
   * a violation is *when* it runs, and the only place that is visible before
   * deployment is the source of the whole group.
   *
   * It matters beyond page-load time. Under B-lite, Next runs on Cloudflare
   * Workers and Django on Hetzner with no private network between them, so a
   * request-time fetch here would cross the public internet and need its own
   * authentication. These assertions are what keep CLAUDE.md §11 #5 moot
   * rather than something to rediscover at deploy.
   */

  it("no page or layout in the group reads searchParams", () => {
    // **This is the real one.** Reading `searchParams` in a server component
    // opts the route into dynamic rendering — no build-time prerender, a
    // server invocation per request. It is also the obvious way to build the
    // filters T4 added, which is exactly why it is asserted by name.
    const offenders = sourceFilesIn(GROUP).filter((path) =>
      /searchParams/.test(codeOnly(readFileSync(path, "utf8"))),
    );

    expect(offenders).toEqual([]);
  });

  it("no page or layout opts out of static rendering", () => {
    // `export const dynamic = "force-dynamic"` and `revalidate = 0` are the
    // explicit versions of the same thing. Nobody writes these by accident,
    // but they are what somebody reaches for when a page will not build.
    const offenders = sourceFilesIn(GROUP).filter((path) =>
      /export\s+const\s+(dynamic|revalidate|fetchCache)\s*=/.test(
        codeOnly(readFileSync(path, "utf8")),
      ),
    );

    expect(offenders).toEqual([]);
  });

  it("no page or layout calls fetch directly", () => {
    // Blunter than the two above, and it enforces layering rather than timing:
    // a build-time fetch is perfectly legal under invariant 15, so this is not
    // "no fetching" but "not from here". Data access lives in
    // `src/lib/catalogue/`, the way reads live in `selectors.py` on the
    // backend, and a page that fetches inline is the first step toward one
    // that fetches at the wrong time.
    const offenders = sourceFilesIn(GROUP).filter((path) =>
      /[^A-Za-z.]fetch\s*\(/.test(codeOnly(readFileSync(path, "utf8"))),
    );

    expect(offenders).toEqual([]);
  });

  it("no page or layout in the group is a client component", () => {
    // A `"use client"` page still prerenders, so this is not about the HTML
    // being empty. It is that interactivity in this group means hydration
    // before the content is usable, and abuse case 7 says a public page must
    // show its content without JavaScript. Interactive pieces belong in a
    // child component — `CourseCatalogue` is one — not in the page itself.
    const offenders = sourceFilesIn(GROUP).filter((path) =>
      /^["']use client["']/m.test(readFileSync(path, "utf8")),
    );

    expect(offenders).toEqual([]);
  });

  it("and the check can actually see the files it is checking", () => {
    // The twin. Every assertion above passes trivially against an empty list,
    // so a wrong path or a bad glob would look like compliance forever. This
    // is the only thing standing between "no violations" and "no files".
    expect(sourceFilesIn(GROUP).length).toBeGreaterThan(0);
  });
});
