/**
 * Runtime dependencies are pinned to exact versions.
 *
 * **This has already gone wrong once.** During M13 T7 `npm install` rewrote
 * exact pins back into `^` ranges and the change was committed without anyone
 * re-reading the file; it took a follow-up commit to undo. The five packages
 * the redesign added arrived as ranges for the same reason — npm writes a
 * caret unless told otherwise, and nothing here objected.
 *
 * **Why exact, for runtime dependencies specifically.** A caret means the
 * version that ships is whichever minor release existed when somebody last ran
 * `npm install`, which is not the version any test ran against. The lockfile
 * makes that reproducible for anyone who runs `npm ci` — but the lockfile is
 * also what npm rewrites, and a range is the thing that lets it. For the
 * packages that end up in the browser bundle, "what did we actually ship" should
 * be answerable from `package.json` alone.
 *
 * **`devDependencies` are deliberately not covered.** `@types/node`, `eslint`
 * and `tailwindcss` carry ranges here on purpose: they shape the build and the
 * checks rather than the artifact, a minor bump is usually wanted, and CI runs
 * `npm ci` against the lockfile either way. Widening this guard to them would
 * be a change to an existing convention rather than a guard on it.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const PACKAGE_JSON = join(import.meta.dirname, "..", "..", "package.json");

function runtimeDependencies(): Record<string, string> {
  return JSON.parse(readFileSync(PACKAGE_JSON, "utf8")).dependencies;
}

/** `1.2.3` and nothing else — no `^`, `~`, `*`, ranges, tags or URLs. */
const EXACT = /^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/;

describe("runtime dependencies", () => {
  it("are all pinned to an exact version", () => {
    const floating = Object.entries(runtimeDependencies())
      .filter(([, range]) => !EXACT.test(range))
      .map(([name, range]) => `${name}@${range}`);

    expect(floating).toEqual([]);
  });

  it("checks a real, non-empty list", () => {
    // The twin. A misread path or a renamed field would make the test above
    // pass by finding nothing to object to.
    const deps = runtimeDependencies();

    expect(Object.keys(deps).length).toBeGreaterThan(5);
    expect(deps).toHaveProperty("next");
  });

  it("would reject a caret", () => {
    // The other twin: a regex that matched everything would also pass.
    expect(EXACT.test("^1.2.3")).toBe(false);
    expect(EXACT.test("~1.2.3")).toBe(false);
    expect(EXACT.test(">=1.2.3 <2")).toBe(false);
    expect(EXACT.test("latest")).toBe(false);
    expect(EXACT.test("1.2.3")).toBe(true);
  });
});
