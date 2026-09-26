/**
 * The public surface uses one type scale, and says so in a test.
 *
 * **This file exists because a redesign is where a scale quietly stops being
 * one.** Stage 1 (ADR-029) set the palette and the shell; stage 2 was meant to
 * be a composition pass over these pages and found almost nothing to do —
 * every section heading already shared a treatment and the page titles differed
 * only in whether they set `leading-tight`. That is worth locking in rather
 * than rediscovering: the cheapest moment to notice a scale has drifted is
 * before four more pages are written against the drifted version.
 *
 * **The page-title half of this file has moved.** It used to grep these pages
 * for `<h1 className="…">` and assert the strings matched, which worked only
 * because every title was hand-written. `PageTitle` now owns the two
 * treatments, so there is no string here to compare — and the guard that
 * replaces it is stronger and app-wide rather than scoped to this group: no
 * `<h1>` anywhere may carry a hand-written size at all. It lives with the
 * component, in `components/ui/PageTitle.test.tsx`.
 *
 * Section headings stay here, because they are still hand-written and the same
 * treatment is only expected *within* this group. `MyCourses` titles its
 * enrollment cards with `<h2 class="text-xl">`, matching `CourseCard` rather
 * than a marketing section heading — that is a card title wearing an `h2` for
 * the heading outline's sake, not a section heading that drifted, so widening
 * this check would fail against correct code.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { sourceFilesIn } from "@/test/source";

const GROUP = join(import.meta.dirname);

function sectionHeadings(): string[] {
  return sourceFilesIn(GROUP).flatMap((path) => {
    const source = readFileSync(path, "utf8");
    return [...source.matchAll(/<h2[^>]*className="([^"]*)"/g)].map((match) => match[1]);
  });
}

describe("the public pages share one type scale", () => {
  it("gives every section heading the same treatment", () => {
    // `text-2xl`, and the same one everywhere — a section that sized itself
    // differently would read as a different level to anyone scanning.
    const sections = new Set(sectionHeadings());

    expect(sections.size).toBe(1);
    expect([...sections][0]).toContain("text-2xl");
  });

  it("is reading real headings rather than finding none", () => {
    // The twin. An empty set is also "the same", so a regex that matched
    // nothing would satisfy the test above.
    expect(sectionHeadings().length).toBeGreaterThanOrEqual(4);
  });
});
