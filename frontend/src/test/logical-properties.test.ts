/**
 * Inline-direction spacing is logical, so an RTL interface is a `dir` attribute
 * and not a rewrite.
 *
 * **No locale is approved and none is assumed** (ADR-033 §4). This is not
 * preparation for a launch nobody has planned; it is a cap on a debt that grows
 * with every page. When ADR-033 was written the debt was estimated at "about four"
 * utilities. Counting properly found **nine**, of which six were content flow and
 * two were something else — see below. Six became logical; the estimate was wrong
 * in the direction estimates usually are.
 *
 * `ms-`/`me-`/`ps-`/`pe-`/`border-s`/`border-e`/`text-start`/`text-end` are the
 * same length as what they replace and behave identically in a left-to-right
 * document, so this costs nothing today.
 *
 * **What is deliberately not banned:** `left-` and `right-` insets. Those position
 * an element against the viewport — the skip link, the drawer's edge, the hero's
 * decorative cards — and physical is correct for them. A rule that caught those
 * too would fire on code that is right, and a guard that cries wolf gets deleted.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { codeOnly, sourceFilesIn } from "@/test/source";

const SRC = join(import.meta.dirname, "..");

/**
 * Physical utilities that are *always* wrong when they lay out content.
 *
 * Margin and padding on the inline axis, inline borders, and text alignment.
 * `border-l(?![a-z])` rather than `border-l` because `border-line` is a colour
 * token in this palette and would otherwise match — found by running it.
 */
const PHYSICAL = /\b-?(?:ml|mr|pl|pr)-[a-z0-9.]+|\bborder-l(?![a-z])|\bborder-r(?![a-z])|\btext-(?:left|right)\b/g;

/**
 * The two that stay physical, pinned rather than exempted.
 *
 * `SiteNavTree` anchors the desktop rail and the mobile drawer to the left edge:
 * the rail's `border-r` closes its column, and the drawer's does the same while it
 * sits at `left-0` and slides in from `-100%`. Making those logical is not a
 * utility swap — it flips which side the navigation lives on, which border closes
 * it, and which direction the animation travels. ADR-029 accepted a left rail, so
 * that is a layout decision and not a tidy-up.
 *
 * **Pinned as an exact set, not skipped.** An exemption list silently absorbs the
 * next offender; this fails if anything is added *or* removed, so either direction
 * is a deliberate edit to a test rather than a quiet change to a stylesheet.
 */
const PINNED = ["src/components/site/SiteNavTree.tsx"];

function offenders(): { file: string; match: string }[] {
  return sourceFilesIn(SRC).flatMap((path) => {
    // Comments stripped for the reason `test/source.ts` documents at length:
    // four guards before this one failed against correct code because a file
    // explained the rule it was being checked for. This file is itself an
    // example — it names `ml-` and `text-left` in prose repeatedly.
    const code = codeOnly(readFileSync(path, "utf8"));
    const file = path.slice(path.indexOf("src")).replace(/\\/g, "/");
    return [...code.matchAll(PHYSICAL)].map((m) => ({ file, match: m[0] }));
  });
}

describe("inline-direction utilities", () => {
  it("are logical everywhere except the pinned navigation chrome", () => {
    const unexpected = offenders().filter(({ file }) => !PINNED.includes(file));

    expect(unexpected.map(({ file, match }) => `${file}: ${match}`)).toEqual([]);
  });

  it("are still physical in exactly the two pinned places", () => {
    /**
     * The other half of the pin. If somebody makes the rail logical — which
     * would be a welcome change, made deliberately — this fails and tells them
     * to update `PINNED` and ADR-029. That is the intent: the set is a record of
     * a decision, so it must not drift in either direction unnoticed.
     */
    const pinned = offenders().filter(({ file }) => PINNED.includes(file));

    expect(pinned.map(({ match }) => match)).toEqual(["border-r", "border-r"]);
  });

  it("is looking at real files and a pattern that matches", () => {
    /**
     * The twin. An empty file list or a pattern that matched nothing would
     * satisfy the first test, and `sourceFilesIn` on a wrong path throws rather
     * than returning `[]`.
     */
    expect(sourceFilesIn(SRC).length).toBeGreaterThan(30);

    expect("ps-4 border-s text-start ms-1.5 pe-1".match(PHYSICAL)).toBeNull();
    expect("pl-4 border-l text-left ml-1.5 pr-1".match(PHYSICAL)).toHaveLength(5);
  });

  it("does not mistake a colour token or an inset for a direction", () => {
    // `border-line` is a token in this palette and `left-5` positions the drawer
    // against the viewport. Both are correct and neither may be flagged — the
    // first was a real false positive, caught by running the pattern.
    expect("border-line border-line-strong".match(PHYSICAL)).toBeNull();
    expect("fixed bottom-5 left-5 -right-1 focus:left-4".match(PHYSICAL)).toBeNull();
  });
});
