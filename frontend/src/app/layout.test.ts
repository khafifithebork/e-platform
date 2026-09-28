/**
 * The root element's two responsibilities, and why one of them is asserted at
 * all.
 *
 * `scroll-pb-20 xl:scroll-pb-0` on `<html>` is WCAG 2.2 AA, 2.4.11 Focus Not
 * Obscured (Minimum). Below `xl`, `SiteNavTree` renders a fixed "Site map" button
 * at the bottom left; tabbing to an element just below the fold makes the browser
 * scroll it in *minimally* — `block: "nearest"` — parking it flush against the
 * bottom edge, exactly where that button sits, so the focus ring lands behind it.
 *
 * **Reported by the owner, then reproduced and measured before being fixed**
 * (ADR-006). At 420×480 on `/courses`, three focusable elements overlapped the
 * button: the course card's link and both footer links. After the fix, the same
 * probe at the same size reports none, and `scroll-padding-bottom` computes to
 * `80px` where it was `auto`.
 *
 * **The first attempt at this fix disappeared without an error**, which is why
 * there is a test rather than a class and a comment. It was written as a
 * hand-rolled `@media (width < 80rem) { :root { scroll-padding-bottom: 5rem } }`
 * in `globals.css`, and the whole block was dropped from the compiled stylesheet
 * while the rules either side of it survived. Nothing failed; the page simply
 * behaved as before. That is the second time CSS has silently vanished in this
 * codebase — the first was the `[--token]` syntax, 45 classes that never applied
 * in any release — and both times the only reason it was caught was that somebody
 * measured the result instead of trusting the diff.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { codeOnly } from "@/test/source";

const LAYOUT = codeOnly(readFileSync(join(import.meta.dirname, "layout.tsx"), "utf8"));

/** The `class` attribute on the root `<html>` element. */
function htmlClasses(): string[] {
  const match = LAYOUT.match(/<html[^>]*className="([^"]*)"/);
  return match ? match[1].split(/\s+/).filter(Boolean) : [];
}

describe("the root element", () => {
  it("reserves scroll padding for the fixed navigation toggle", () => {
    // 20 on Tailwind's scale is 5rem, and the button occupies the bottom 62px —
    // `bottom-5` at 1.25rem plus roughly 42px of height. 80px clears it with a
    // visible gap rather than a hairline.
    expect(htmlClasses()).toContain("scroll-pb-20");
  });

  it("drops that padding above xl, where no fixed button exists", () => {
    /**
     * Not cosmetic tidiness. Above `xl` the navigation is a static rail and
     * nothing is fixed over the content, so leaving 5rem of scroll padding there
     * would stop every keyboard scroll short of the viewport edge for no reason —
     * a small, permanent oddity on the widest screens, caused by a fix for a
     * problem those screens do not have.
     */
    expect(htmlClasses()).toContain("xl:scroll-pb-0");
  });

  it("is reading the real attribute and would notice it missing", () => {
    // The twin. A regex that matched nothing returns `[]`, and `toContain` on an
    // empty array fails — but only if the array is genuinely being read, so the
    // known-present class is checked too.
    expect(htmlClasses().length).toBeGreaterThanOrEqual(3);
    expect(htmlClasses()).toContain("h-full");
  });

  it("keeps the language declared", () => {
    // 3.1.1 Language of Page. English, and hardcoded — ADR-033 defers
    // localisation, so there is no locale to vary this by yet.
    expect(LAYOUT).toMatch(/<html[^>]*lang="en"/);
  });
});
