/**
 * No class references a design token with the syntax that silently does nothing.
 *
 * **45 of them did, across 15 components, and none had ever applied.** Tailwind
 * 4 reads `rounded-(--radius-md)` as `var(--radius-md)` and
 * `rounded-[--radius-md]` as the literal string `--radius-md`, which is not a
 * valid value, so the browser drops the declaration:
 *
 *     .rounded-\(--radius-md\) { border-radius: var(--radius-md) }   ← 12px
 *     .rounded-\[--radius-md\] { border-radius: --radius-md }        ← dropped
 *
 * The bracket form is how Tailwind 3 spelled it. This project has been on `^4`
 * since its first frontend commit, so every one of those classes was written by
 * somebody who could not see that it did nothing — and copied forward for
 * fifteen milestones. Measured on `/login` before the fix: the submit button
 * computed `border-radius: 12px` and the two inputs directly above it computed
 * `0px`, from the same token.
 *
 * **Why a source check when `scripts/assert-css-tokens.mjs` checks the real
 * output.** That one asserts the property that matters — no declaration may have
 * a bare custom-property name as its value — and it catches spellings nobody has
 * thought of. It also needs a full `next build`. This one runs in the unit suite
 * and fails in a second, on the one spelling already known to be wrong. Neither
 * replaces the other, and the fast one is the one somebody will actually see
 * before pushing.
 *
 * Nothing in the type system or the linter can see this: both forms are valid
 * strings in a `className`, so `tsc` and ESLint pass either way, and jsdom runs
 * no Tailwind so no component test can tell either. That combination — invisible
 * to every automated check and visible only to eyes — is why it lasted.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { sourceFilesIn } from "@/test/source";

const SRC = join(import.meta.dirname, "..");

/**
 * `[--token]`, the Tailwind 3 spelling.
 *
 * Deliberately narrow: it requires the bracket contents to *start* with `--`,
 * so genuine arbitrary values are untouched. `h-[36rem]`,
 * `lg:grid-cols-[3fr_2fr]` and `bg-[radial-gradient(...)]` are all correct and
 * all still in use.
 */
const TAILWIND_3_TOKEN = /-\[--[a-z0-9-]+\]/;

function offenders(): string[] {
  return sourceFilesIn(SRC)
    .filter((path) => TAILWIND_3_TOKEN.test(readFileSync(path, "utf8")))
    .map((path) => path.slice(path.indexOf("src")));
}

describe("design tokens in class names", () => {
  it("never use the Tailwind 3 bracket form", () => {
    expect(offenders()).toEqual([]);
  });

  it("is reading real source files rather than finding none", () => {
    // The twin. An empty file list satisfies the test above, and
    // `sourceFilesIn` on a wrong path throws rather than returning `[]` — so
    // the count is what proves the check looked at anything.
    expect(sourceFilesIn(SRC).length).toBeGreaterThan(30);
  });

  it("would catch the form it exists to catch, and leaves arbitrary values alone", () => {
    // The other twin: a pattern that matched nothing would pass both tests
    // above. These are the exact strings from before the fix, and the three
    // arbitrary values still in `Hero`.
    expect(TAILWIND_3_TOKEN.test("rounded-[--radius-md]")).toBe(true);
    expect(TAILWIND_3_TOKEN.test("hover:shadow-[--shadow-md]")).toBe(true);

    expect(TAILWIND_3_TOKEN.test("rounded-(--radius-md)")).toBe(false);
    expect(TAILWIND_3_TOKEN.test("h-[36rem]")).toBe(false);
    expect(TAILWIND_3_TOKEN.test("lg:grid-cols-[3fr_2fr]")).toBe(false);
    expect(TAILWIND_3_TOKEN.test("text-[0.8125rem]")).toBe(false);
  });
});
