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
 * Scoped to the `(marketing)` group deliberately. The same check over the whole
 * app would fail today — the auth pages title themselves `text-3xl` while these
 * use `text-4xl`, so a signed-out visitor moving from `/courses` to `/login`
 * watches the page title change size for no reason. That is a real
 * inconsistency and it belongs to whichever stage redesigns those pages, not
 * to a test that would simply refuse to go green until someone did.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { sourceFilesIn } from "@/test/source";

const GROUP = join(import.meta.dirname);

function headings(level: 1 | 2): string[] {
  return sourceFilesIn(GROUP).flatMap((path) => {
    const source = readFileSync(path, "utf8");
    return [...source.matchAll(new RegExp(`<h${level}[^>]*className="([^"]*)"`, "g"))].map(
      (match) => match[1],
    );
  });
}

describe("the public pages share one type scale", () => {
  it("gives every page title the same treatment", () => {
    const titles = new Set(headings(1));

    expect(titles.size).toBe(1);
    expect([...titles][0]).toContain("text-4xl");
  });

  it("gives every section heading the same treatment", () => {
    // `text-2xl`, and the same one everywhere — a section that sized itself
    // differently would read as a different level to anyone scanning.
    const sections = new Set(headings(2));

    expect(sections.size).toBe(1);
    expect([...sections][0]).toContain("text-2xl");
  });

  it("is reading real headings rather than finding none", () => {
    // The twin. Two empty sets are also "the same", so a regex that matched
    // nothing would satisfy both tests above.
    expect(headings(1).length).toBeGreaterThanOrEqual(3);
    expect(headings(2).length).toBeGreaterThanOrEqual(4);
  });
});
