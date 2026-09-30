/**
 * No positive `tabIndex` anywhere, ever.
 *
 * §9 of the quality addendum puts it plainly: "Do not introduce positive tabindex
 * values to repair layout order." **This repository already complies** — the only
 * two uses are `tabIndex={-1}`, on `<main>` so the skip link can move focus into it
 * and on a nav item the drawer manages. By ADR-023 §1 that makes it a decision
 * nobody has asserted, and this file is the difference.
 *
 * ## Why a positive value is worse than it looks
 *
 * Any element with `tabIndex={1}` or higher is visited **before every element with
 * `tabIndex={0}` or a natural tab stop, anywhere on the page** — not before its
 * siblings, before *everything*. One value in one component reorders the whole
 * document, and the symptom appears somewhere else entirely: a keyboard user tabs
 * into the page and lands in the middle of a form.
 *
 * It is also self-propagating. The usual reason to add one is that the visual order
 * disagrees with the DOM order, and the fix that works is to change the DOM. Adding
 * a `tabIndex` instead means the next element to be inserted needs one too.
 *
 * ## Why a source scan rather than a rendered check
 *
 * A rendered test can only see the components a test renders. The failure mode is
 * somebody adding one to a component nobody wrote a test for, which is precisely the
 * component most likely to have layout-order trouble. `eslint-plugin-jsx-a11y` has
 * `no-noninteractive-tabindex`, which is a different rule and does not forbid a
 * positive value on an interactive element — so this is not duplicated by the linter.
 *
 * `tabIndex={-1}` is deliberately allowed. It is how a programmatically focusable
 * target is made, which is what the skip link needs.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { codeOnly, filesMatching } from "@/test/source";

const SRC = join(import.meta.dirname, "..");

/**
 * A positive `tabIndex`, in the two spellings JSX allows.
 *
 * `tabIndex={1}` and `tabIndex="1"`. Zero and negative values are not matched:
 * `[1-9]` as the first digit excludes `0`, and the literal `-` is absent.
 */
const POSITIVE_TABINDEX = /tabIndex\s*=\s*(?:\{\s*[1-9]|"[1-9])/;

describe("tab order", () => {
  it("is never repaired with a positive tabIndex", () => {
    /**
     * `filesMatching` rather than a hand-rolled sweep, and that is not tidiness.
     *
     * It strips comments first, and `src/test/source.ts` exists because **the same
     * mistake has been made four times in this repository**: a structural guard
     * failing against correct code because the file *documented* the rule it was
     * checked for. The first version of this test read the file raw, which would
     * have fired the day somebody wrote "never use a positive tabIndex" in a
     * component comment — the fifth instance of exactly that trap.
     */
    const offenders = filesMatching(SRC, POSITIVE_TABINDEX).map((file) =>
      file.replace(SRC, "src"),
    );

    expect(offenders).toEqual([]);
  });

  it("still allows -1, which is how the skip link works", () => {
    /**
     * The twin. A rule that banned every `tabIndex` would fail against correct code —
     * `<main tabIndex={-1}>` is what lets the skip link move focus into the content
     * rather than leaving it on the link, and `SiteShell` explains why.
     *
     * Asserted positively so that if the regex is ever widened, this fails rather
     * than the suite going red on a file that is right.
     */
    const shell = codeOnly(
      readFileSync(join(SRC, "components", "site", "SiteShell.tsx"), "utf8"),
    );

    expect(shell).toContain("tabIndex={-1}");
    expect(POSITIVE_TABINDEX.test(shell)).toBe(false);
  });

  it("matches both spellings, and neither zero nor a negative", () => {
    // The regex is the control here, so it is tested directly: a guard that matched
    // nothing would pass the sweep above against any code at all.
    for (const positive of ['tabIndex={1}', 'tabIndex="3"', "tabIndex={ 9 }"]) {
      expect(POSITIVE_TABINDEX.test(positive), positive).toBe(true);
    }

    for (const allowed of ["tabIndex={-1}", 'tabIndex="-1"', "tabIndex={0}", 'tabIndex="0"']) {
      expect(POSITIVE_TABINDEX.test(allowed), allowed).toBe(false);
    }
  });
});
